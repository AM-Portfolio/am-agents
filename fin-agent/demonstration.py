import asyncio
import json
import logging
import sys
import os

# Ensure paths are correct
sys.path.append(os.getcwd())

from agents.finance_agent import finance_agent
from tools.registry import TOOL_REGISTRY

# Configure logging to see the inner thoughts of the agent
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo")

async def run_demonstration():
    # 1. Setup a clean MOCK registry for the demo (Zero Latency)
    import tools.registry as registry
    from tools.tool_index import index_all_tools
    
    # Define a few mock tools manually
    registry.OPENAPI_EXECUTOR_MAP.clear()
    registry.TOOL_REGISTRY.clear()
    
    # Mock Tool 1: User Search
    def search_users(query: str):
        return [{"id": "u-123", "name": "John Doe", "role": "admin"}]
    registry.register_tool(search_users, "Search for users in the database.")
    
    # Mock Tool 2: Account Balance (requires id)
    def get_balance(user_id: str):
        if not user_id: return "Error: user_id required"
        return {"user_id": user_id, "balance": "5000 USD"}
    registry.register_tool(get_balance, "Get account balance for a specific user ID.")
    
    # Index them for semantic search
    index_all_tools()

    print("\n" + "="*60)
    print("🚀 LIVE REASONING DEMONSTRATION (MOCK MODE)")
    print("="*60)

    # --- TEST CASE: Semantic Multi-Step Search ---
    user_query = "What is the balance for John Doe? If you don't know his ID, please look him up first."
    print(f"\n👤 USER: {user_query}")
    print("\n🤖 AGENT IS THINKING (Reasoning across multiple tools)...")
    
    response = await finance_agent.run(
        message=user_query,
        history=[],
        user_id="demo-user",
        session_id="demo-session",
        trace_id="demo-trace-final"
    )
    
    print(f"\n🤖 AGENT RESPONSE: {response.message}")
    print("\n" + "="*60)
    print("✅ DEMONSTRATION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    # We need a dummy .env for together if not set
    if not os.getenv("TOGETHER_API_KEY") and not os.getenv("OLLAMA_BASE_URL"):
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
        
    asyncio.run(run_demonstration())
