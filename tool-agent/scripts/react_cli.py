import os
import requests
import json
import litellm
litellm.drop_params = True

TOOL_AGENT_URL = "http://localhost:8141/api/v1/tools/query"

def ask_tool_agent(query: str) -> str:
    print(f"\n[ToolAgent] Executing query: {query}")
    try:
        res = requests.post(TOOL_AGENT_URL, json={"query": query})
        data = res.json()
        if res.status_code == 200:
            result_data = data.get("data")
            return json.dumps(result_data)[:2000] # truncate to avoid blowing up context
        else:
            return f"Error: {json.dumps(data)}"
    except Exception as e:
        return f"Error connecting to ToolAgent: {e}"

def run_react_agent(question: str, max_iterations=5):
    system_prompt = """You are an intelligent ReAct agent. You have access to one tool:

Tool Name: ToolAgent
Description: A powerful natural language tool that can query multiple cluster backends: Postgres, MongoDB, Kafka, Redis, and Qdrant. You give it a natural language query, and it translates it into the appropriate backend command and returns the JSON result.
Input: A natural language query string.

To answer the user's question, you must use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: ToolAgent
Action Input: the query to send to the tool (e.g., "list all postgres tables")
Observation: [The system will provide the observation]
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Only output the Thought, Action, and Action Input. Stop generating once you output the Action Input. The system will provide the Observation.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Question: {question}"}
    ]

    print(f"\n=== ReAct Agent Started ===")
    print(f"Goal: {question}\n")

    for i in range(max_iterations):
        response = litellm.completion(
            model="together_ai/Prism-ML/Ternary-Bonsai-27B",
            messages=messages,
            stop=["Observation:"]
        )
        
        content = response.choices[0].message.content
        if not content:
            print("\n=== Agent Finished (No output) ===")
            return
        output = content.strip()
        print(output)
        
        messages.append({"role": "assistant", "content": output})

        if "Final Answer:" in output:
            print("\n=== Agent Finished ===")
            return

        if "Action:" in output and "Action Input:" in output:
            try:
                # Parse action and input
                lines = output.split('\n')
                action = [line for line in lines if line.startswith('Action:')][0].replace('Action:', '').strip()
                action_input = [line for line in lines if line.startswith('Action Input:')][0].replace('Action Input:', '').strip()
                
                if action == "ToolAgent":
                    observation = ask_tool_agent(action_input)
                else:
                    observation = f"Unknown tool: {action}"
                    
                print(f"\nObservation: {observation}\n")
                messages.append({"role": "user", "content": f"Observation: {observation}"})
            except Exception as e:
                error_obs = f"Failed to parse action. Make sure to use the exact format. Error: {e}"
                print(f"\nObservation: {error_obs}\n")
                messages.append({"role": "user", "content": f"Observation: {error_obs}"})
        else:
            obs = "You must provide an Action and Action Input, or a Final Answer."
            print(f"\nObservation: {obs}\n")
            messages.append({"role": "user", "content": f"Observation: {obs}"})
            
    print("\n=== Max iterations reached without a Final Answer ===")

if __name__ == "__main__":
    # Test a compound question that requires multiple tool agent queries
    test_q = "First, list all mongo databases. Then, list all kafka topics. Finally, tell me how many mongo databases and kafka topics there are in total."
    run_react_agent(test_q)
