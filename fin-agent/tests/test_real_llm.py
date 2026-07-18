import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env BEFORE importing client which initializes at module level
from dotenv import load_dotenv
# Explicitly set for testing if .env load is being blocked
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
os.environ["LLM_MODEL"] = "gpt-oss:20b-cloud"

print(f"DEBUG: LLM_PROVIDER final: {os.getenv('LLM_PROVIDER')}")
print(f"DEBUG: OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL')}")

from shared.llm.client import llm_client

async def test_connection():
    print("Testing Real LLM Connection...")
    print(f"API Key present: {bool(os.getenv('TOGETHER_API_KEY'))}")
    
    try:
        response = await llm_client.chat(
            messages=[{"role": "user", "content": "Say 'Connection Successful' if you can read this."}],
            temperature=0.7
        )
        print(f"Response: {response}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
