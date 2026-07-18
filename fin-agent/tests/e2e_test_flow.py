import requests
import json
import uuid

def test_e2e_meta_flow():
    url = "http://localhost:8100/api/v1/ai/chat"
    
    payload = {
        "message": "I want to test the connect service API. Show me the workflow and a sample payload.",
        "userId": "user_test_e2e",
        "sessionId": str(uuid.uuid4())
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"--- Sending E2E Request to {url} ---")
    print(f"Message: {payload['message']}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        print("\n--- E2E Response Received ---")
        print(f"Agent Message: {data.get('message')}")
        print(f"Widget ID: {data.get('widgetId')}")
        print(f"Tools Used: {data.get('toolsUsed')}")
        
        # Check if the data is present in widgetParams
        params = data.get("widgetParams", {})
        if "data" in params:
            print("\n--- Data returned in Widget Params ---")
            print(json.dumps(params["data"], indent=2))
        else:
            print("\n❌ No data found in widgetParams")
            
        if data.get("widgetId") == "API_TEST_WIDGET":
            print("\n✅ End-to-End Flow Success: Correct Widget ID triggered.")
        else:
            print(f"\n❌ End-to-End Flow Error: Unexpected Widget ID {data.get('widgetId')}")
            
    except Exception as e:
        print(f"\n❌ E2E Test Failed: {e}")

if __name__ == "__main__":
    test_e2e_meta_flow()
