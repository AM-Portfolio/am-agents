import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_ollama():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("LLM_MODEL", "gpt-oss:20b-cloud")
    
    print(f"Testing Ollama at {base_url} with model {model}...")
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello, are you working?"}],
        "temperature": 0.7
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{base_url}/chat/completions", json=payload)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"Response: {resp.json()['choices'][0]['message']['content']}")
            else:
                print(f"Error: {resp.text}")
        except Exception as e:
            print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama())
