import asyncio
import os
import json
import sys

# Ensure the Finance App directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load env vars
from dotenv import load_dotenv
load_dotenv(".env", override=True)

from am_fin_api_testing.core.meta_engine import MetaEngine

async def test_meta_engine():
    print("=== Testing MetaEngine with Mock Swagger ===")
    engine = MetaEngine()
    
    # 1. Load the mock swagger
    swagger_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "am_fin_api_testing", "mock_swagger.json")
    engine.load_registry(swagger_path, base_url="http://mock-api.local")
    
    # 2. Search for APIs
    results = engine.search_apis("order")
    print(f"Discovered APIs for 'order': {results}")
    
    if not results:
        print("❌ No APIs discovered. Check swagger parsing.")
        return
    
    op_id = results[0]["operationId"]
    print(f"Testing operation: {op_id}")
    
    # 3. Get Details
    details = engine.get_api_details(op_id)
    print(f"API Details: {json.dumps(details, indent=2)}")
    
    # 4. Generate Payload (Requires LLM)
    print("\nGenerating Payload via LLM Reasoning...")
    try:
        payload = await engine.generate_payload_template(op_id)
        print(f"Generated Payload: {json.dumps(payload, indent=2)}")
        
        if "error" in payload:
            print(f"❌ LLM Reasoning Failed: {payload['error']}")
        else:
            print("✅ LLM Reasoning Successful!")
            
    except Exception as e:
        print(f"❌ Exception during generation: {e}")

if __name__ == "__main__":
    asyncio.run(test_meta_engine())
