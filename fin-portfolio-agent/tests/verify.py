import asyncio
import os
import sys
import json
from unittest.mock import MagicMock, AsyncMock

# Ensure path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from am_fin_portfolio_analysis.chatbot.bot import ChatAgent
from shared.llm.client import llm_client

async def run_verification():
    print("Starting Verification...")
    
    # Mock the LLM client to avoid needing a real key for logic testing
    original_chat = llm_client.chat
    llm_client.chat = AsyncMock()
    
    # Initialize the LangGraph-based agent
    agent = ChatAgent()

    test_cases = [
        {
            "query": "What is my total portfolio value?",
            # Intent detection mock return
            "mock_intent": '{"intent": "PORTFOLIO_SUMMARY", "entities": {}}',
            # Response generation mock return
            "mock_response": "This is a mocked response about portfolio value.",
            "expected_context_part": "Portfolio Performance"
        },
        {
            "query": "How is HDFC Bank doing?",
            "mock_intent": '{"intent": "HOLDING_DETAILS", "entities": {"stock_name": "HDFC Bank"}}',
            "mock_response": "This is a mocked response about HDFC Bank.",
            "expected_context_part": "Holding Details for HDFC Bank"
        }
    ]
    
    for i, test in enumerate(test_cases):
        print(f"\nTest Case {i+1}: {test['query']}")
        
        # Setup Mock for the TWO LLM calls in the graph:
        # 1. detect_intent node calls LLM
        # 2. generate_response node calls LLM
        llm_client.chat.side_effect = [
            test["mock_intent"], 
            test["mock_response"]
        ]
        
        response = ""
        async for event in agent.process_query(test['query']):
            if event["type"] == "response":
                response = event["content"]
        
        print(f"Agent Response: {response}")
        
        # Verification Logic
        # We need to verify that 'generate_response' node received the correct context data.
        # This data comes from 'retrieve_data' node, which isn't mocked but uses real engine.
        # So we check the 2nd LLM call arguments.
        
        calls = llm_client.chat.call_args_list
        # We expect 2 calls per test case. Since we loop, the list grows.
        # The last call should be the generate_response call.
        last_call_args = calls[-1] 
        messages = last_call_args[1].get('messages') or last_call_args[0][0]
        final_user_msg = messages[-1]["content"]
        
        if test["expected_context_part"] in final_user_msg:
            print(f"✅ Context Verification Passed: Found '{test['expected_context_part']}'")
        else:
            print(f"❌ Context Verification Failed: Did not find '{test['expected_context_part']}'")
            print(f"Actual Context Content snippet: {final_user_msg[:200]}...")

    print("\nVerification Complete.")
    
    # Restore
    llm_client.chat = original_chat

if __name__ == "__main__":
    asyncio.run(run_verification())
