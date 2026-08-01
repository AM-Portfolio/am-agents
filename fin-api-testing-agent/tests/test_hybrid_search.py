import sys
import os
import asyncio
import logging

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.curdir))

from shared.tools.tool_index import index_all_tools, retrieve_tools
from shared.tools.registry import register_openapi_tools

# Mock some tools
mock_apis = [
    {
        "type": "function",
        "function": {
            "name": "login_user",
            "description": "Authenticate a user with credentials",
            "parameters": {"type": "object", "properties": {"username": {"type": "string"}, "password": {"type": "string"}}}
        },
        "_meta": {"method": "POST", "path": "/auth/login", "base_url": "http://localhost:8001"}
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "Retrieve the user's investment portfolio",
            "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}}
        },
        "_meta": {"method": "GET", "path": "/api/v1/portfolio", "base_url": "http://localhost:8040"}
    }
]

async def test():
    logging.basicConfig(level=logging.INFO)
    
    print("Indexing tools...")
    register_openapi_tools(mock_apis)
    index_all_tools()
    
    print("\nTest 1: Direct endpoint query '/auth/login'")
    results = retrieve_tools("/auth/login", top_k=1)
    if results and results[0]["function"]["name"] == "login_user":
        print("✅ Success: Found login_user for /auth/login")
    else:
        print(f"❌ Failure: Found {results[0]['function']['name'] if results else 'nothing'}")

    print("\nTest 2: Semantic query 'show me my stocks'")
    results = retrieve_tools("show me my stocks", top_k=1)
    if results and results[0]["function"]["name"] == "get_portfolio":
        print("✅ Success: Found get_portfolio for 'show me my stocks'")
    else:
        print(f"❌ Failure: Found {results[0]['function']['name'] if results else 'nothing'}")

    print("\nTest 3: Keyword query 'auth login'")
    results = retrieve_tools("auth login", top_k=1)
    if results and results[0]["function"]["name"] == "login_user":
        print("✅ Success: Found login_user for 'auth login'")
    else:
        print(f"❌ Failure: Found {results[0]['function']['name'] if results else 'nothing'}")

if __name__ == "__main__":
    asyncio.run(test())
