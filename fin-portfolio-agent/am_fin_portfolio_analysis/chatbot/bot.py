import json
import logging
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, ToolMessage, AIMessage
import operator
import asyncio
import os

from shared.core.config import settings
from shared.llm.client import llm_client

# ─── Dynamic Module Loading ──────────────────────────────────────────────────

if settings.ENABLE_PORTFOLIO_ANALYSIS:
    try:
        import am_fin_portfolio_analysis.tools.portfolio_tools  # noqa
        import am_fin_portfolio_analysis.tools.analysis_tools   # noqa
        import am_fin_portfolio_analysis.tools.trade_tools      # noqa
    except ImportError:
        pass

# Note: This legacy bot used its own TOOL_DEFINITIONS and execute_tool.
# We'll point them to the new registry for consistency.
from shared.tools.registry import TOOL_REGISTRY as TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

# --- State Definition ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    intent: Optional[str] 
    final_response: Optional[str]

# --- Nodes ---

async def agent_node(state: AgentState) -> Dict[str, Any]:
    """Decide what to do: calls LLM with tools."""
    messages = state["messages"]
    
    print(f"\n[LOG] 🧠 Agent Node: Thinking with {len(messages)} messages...")
    
    # System Prompt: Principles of Agentic Intelligence
    system_msg = SystemMessage(content="""You are an advanced Financial Intelligence Agent. Your goal is to provide highly personalized, data-driven financial advice.

    PRINCIPLES OF OPERATION:
    1. **Context is King**: Generic advice is useless. To answer any investment question, you MUST first understand the user's *current* financial context. 
       - *Reasoning*: "I cannot advise on adding pharma stocks until I know if the user already owns them."
       - *Action*: Spontaneously check the portfolio summary and specifically look for existing exposure (stocks or ETFs) before advising.

    2. **Multi-Step Reasoning**: Complex questions require multiple angles.
       - If asked "Should I invest in X?", a human advisor would:
         a) Check what you own.
         b) Check the market outlook for X.
         c) Compare a & b.
       - You must mirror this behavior by chaining tools logically.

    3. **Precision**: Use specific tools for specific tasks.
       - Use `count_etfs` and `analyze_etf_overlap` to find hidden exposures.
       - Use `web_search` for external market sentiment.

    4. **Holistic Synthesis**: Your final answer should weave together:
       - The user's specific data ("You already hold 15% in pharma...")
       - External market data ("...but the sector outlook is bearish...")
       - A synthesized recommendation ("...so holding might be better than buying more.")

    CRITICAL EXECUTION RULES:
    - **DO NOT STOP** to tell the user what you play to do. JUST DO IT.
    - If you need to analyze multiple ETFs, call the tool multiple times in the SAME turn.
    - Do not return a text response until you have gathered ALL necessary data.
    - If you find 18 ETFs, pick the top 3-5 to analyze overlap for, don't ask the user which ones.

    Refuse to give generic, GPT-like text answers. Always ground your responses in the tools available.
    """)
    
    full_messages = [system_msg] + messages
    
    msg_payload = []
    for m in full_messages:
        if isinstance(m, SystemMessage):
            msg_payload.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            msg_payload.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            msg_dict = {"role": "assistant", "content": m.content or ""}
            if m.additional_kwargs.get("tool_calls"):
                msg_dict["tool_calls"] = m.additional_kwargs["tool_calls"]
            msg_payload.append(msg_dict)
        elif isinstance(m, ToolMessage):
            msg_payload.append({
                "role": "tool",
                "content": m.content,
                "tool_call_id": m.tool_call_id,
                "name": m.name
            })

    response = await llm_client.chat(
        messages=msg_payload,
        temperature=0.0,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto"
    )
    
    if isinstance(response, dict) and response.get("tool_calls"):
        ai_msg = AIMessage(content=response.get("content") or "", additional_kwargs={"tool_calls": response["tool_calls"]})
        return {"messages": [ai_msg]}
    
    return {"messages": [AIMessage(content=str(response))], "final_response": str(response)}

async def tools_node(state: AgentState) -> Dict[str, Any]:
    """Execute the tools requested by the Agent in parallel."""
    messages = state["messages"]
    last_message = messages[-1]
    tool_calls = last_message.additional_kwargs.get("tool_calls", [])
    
    async def run_one_tool(call):
        func = call["function"]
        f_name = func["name"]
        args_raw = func.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                f_args = json.loads(args_raw)
            except:
                f_args = {}
        else:
            f_args = args_raw
        
        result_str = execute_tool(f_name, f_args)
        return ToolMessage(tool_call_id=call["id"], content=str(result_str), name=f_name)

    results = await asyncio.gather(*[run_one_tool(c) for c in tool_calls])
    return {"messages": list(results)}

# --- Edges & Graph ---

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.additional_kwargs.get("tool_calls"):
        return "tools"
    return END

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    return workflow.compile()

class ChatAgent:
    def __init__(self):
        self.app = create_graph()
        
    async def process_query(self, query: str, history: List[Dict[str, str]] = []):
        lc_messages = []
        for msg in history[-10:]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=query))

        initial_state = {"messages": lc_messages, "intent": None, "final_response": None}
        yield {"type": "status", "content": "🧠 Thinking..."}
        
        async for chunk in self.app.astream(initial_state, config={"recursion_limit": 50}):
            if "agent" in chunk:
                state_update = chunk["agent"]
                new_msgs = state_update.get("messages", [])
                if new_msgs:
                    last = new_msgs[-1]
                    if isinstance(last, AIMessage):
                        calls = last.additional_kwargs.get("tool_calls")
                        if calls:
                            tool_details = []
                            for c in calls:
                                func_name = c["function"]["name"]
                                args = c["function"].get("arguments", "{}")
                                tool_details.append(f"{func_name}({args})")
                            
                            tool_summary = ", ".join([c["function"]["name"] for c in calls])
                            yield {"type": "status", "content": f"🛠️ Calling: {tool_summary}"}
                            
                            # Detailed view
                            for detail in tool_details:
                                yield {"type": "status", "content": f"   → {detail}"}
                        else:
                            yield {"type": "response", "content": last.content}
            elif "tools" in chunk:
                yield {"type": "status", "content": "⚡ Tools Executed. Analysing results..."}
