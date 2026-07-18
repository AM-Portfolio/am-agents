#!/usr/bin/env python3
import sys
import os
import time
import json
import random
import requests
import asyncio
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Add parent dir (root) to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Force API Testing Mode
os.environ["ENABLE_PORTFOLIO_ANALYSIS"] = "false"
os.environ["ENABLE_API_TESTING"] = "true"

# Robust environment loading
env_path = os.path.join(root_dir, ".env")
load_dotenv(env_path, override=True)

from am_fin_api_testing.core.meta_engine import MetaEngine

class MetaAgentCLI:
    def __init__(self):
        # Use mock swagger from the module directory
        mock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_swagger.json")
        self.engine = MetaEngine(swagger_path=mock_path)
        self.services = {
            "User Management": {"url": "http://localhost:8002", "spec": "http://localhost:8002/openapi.json"},
            "Auth Tokens": {"url": "http://localhost:8001", "spec": "http://localhost:8001/auth/v1/openapi.json"},
            "Market Data": {"url": "http://localhost:8092", "spec": "http://localhost:8092/v3/api-docs"},
            "Analysis Service": {"url": "http://localhost:8010", "spec": "http://localhost:8010/openapi.json"},
        }

    async def ainput(self, prompt: str) -> str:
        return await asyncio.get_event_loop().run_in_executor(None, input, prompt)

    def print_header(self, text):
        print("\n" + "="*60)
        print(f" 🤖 {text}")
        print("="*60)

    async def agent_think(self, text, delay=0.5):
        print(f"🧠 [Thinking] {text}...", end="\r")
        await asyncio.sleep(delay)
        print(f"✅ [Thought]  {text}   ")

    async def register_all(self):
        self.print_header("Initializing LLM-Powered API Testing Agent")
        for name, info in self.services.items():
            try:
                await self.agent_think(f"Fetching spec for {name}")
                spec_file = f"/tmp/{name.lower().replace(' ', '_')}_spec.json"
                
                # Fetch spec in thread to avoid blocking loop
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, requests.get, info["spec"])
                
                if resp.status_code == 200:
                    with open(spec_file, 'w') as f:
                        json.dump(resp.json(), f)
                    self.engine.add_registry(spec_file, info["url"])
                else:
                    print(f"❌ Failed to reach {name}")
            except Exception as e:
                print(f"⚠️  Skipping {name}: {str(e)}")
        print("\nReady! Agent is powered by Local LLM and knows about your services.")

    async def run_discovery(self):
        self.print_header("Autonomous Service Discovery")
        query = await self.ainput("🔍 What do you want to test? (e.g. 'user', 'price', 'auth'): ")
        await self.agent_think(f"Analyzing my memory for '{query}'")
        results = self.engine.search_apis(query)
        
        if not results:
            print("❌ No matching APIs found.")
            return

        print(f"\nDiscovered {len(results)} matching operations:")
        for idx, res in enumerate(results):
            print(f"  {idx+1}. [{res['operationId']}] {res['method'].upper()} {res['path']}")
        
        choice = await self.ainput("\nEnter number to test (or 'q' to go back): ")
        if choice.lower() == 'q': return
        
        try:
            op = results[int(choice)-1]
            await self.test_operation(op['operationId'])
        except Exception as e:
            print(f"Error: {e}")

    async def test_operation(self, op_id):
        self.print_header(f"Testing Operation: {op_id}")
        
        await self.agent_think("Checking for dependencies in the graph")
        
        await self.agent_think("LLM Reasoner: Analyzing schema and generating realistic data")
        payload = await self.engine.generate_payload_template(op_id)
        
        print(f"\n✍️ Initial Payload (AI Generated): {json.dumps(payload, indent=2)}")
        
        confirm = await self.ainput("\n🚀 Ready to execute? (y/n): ")
        if confirm.lower() != 'y': return

        max_retries = 3
        for attempt in range(max_retries):
            await self.agent_think(f"Executing HTTP request (Attempt {attempt+1})")
            api = self.engine.get_api_details(op_id)
            base_url = self.engine.base_url_map.get(op_id, "http://localhost:8000")
            
            path = api['path']
            # Basic path param resolution
            if "{symbol}" in path: path = path.replace("{symbol}", "AAPL")
            if "{exchange}" in path: path = path.replace("{exchange}", "NSE")
            if "{user_id}" in path: path = path.replace("{user_id}", "86e1eaeb-bd01-4602-8337-b791a3fdf99f")
            
            url = f"{base_url}{path}"
            method = api['method'].upper()
            
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: requests.request(method, url, json=payload, timeout=10))
                
                print(f"\n📡 Request: {method} {url}")
                print(f"📥 Status: {resp.status_code}")
                
                if resp.status_code in [200, 201]:
                    print(f"✅ Success!\n{json.dumps(resp.json(), indent=2)[:800]}...")
                    break
                elif resp.status_code in [400, 409] and attempt < max_retries - 1:
                    try:
                        error_data = resp.json()
                        error_msg = str(error_data.get("detail", str(error_data)))
                    except:
                        error_msg = resp.text
                    
                    print(f"⚠️  Received {resp.status_code}: {error_msg}")
                    
                    self.print_header("Agent Self-Healing Loop (ReAct)")
                    await self.agent_think(f"LLM Reasoning: Why did it fail? '{error_msg}'")
                    
                    await self.agent_think("LLM Acting: Refining payload to resolve constraints")
                    payload = await self.engine.refine_payload(op_id, payload, error_msg)
                    
                    print(f"✍️ Refined Payload (AI Reasoning Applied):")
                    print(json.dumps(payload, indent=2))
                    await asyncio.sleep(1)
                    print("\n🔄 Retrying with corrected data...")
                else:
                    try:
                        print(f"📄 Response:\n{json.dumps(resp.json(), indent=2)[:800]}...")
                    except:
                        print(f"📄 Raw Response: {resp.text[:500]}")
                    break
            except Exception as e:
                print(f"❌ Execution failed: {str(e)}")
                break

    async def main_menu(self):
        await self.register_all()
        while True:
            print("\n" + "-"*30)
            print("    LLM AGENT CONTROL CENTER")
            print("-"*30)
            print("1. Discovery & Test (Manual Selection)")
            print("2. Run M-Auth Workflow (Autonomous Loop)")
            print("3. Re-scan Services")
            print("4. Run Batch Test (Whole Service)")
            print("q. Exit")
            
            choice = await self.ainput("\nSelect an option: ")
            if choice == '1': await self.run_discovery()
            elif choice == '2': await self.run_mauth_workflow()
            elif choice == '3': await self.register_all()
            elif choice == '4': await self.run_service_batch()
            elif choice == 'q': break

    async def run_mauth_workflow(self):
        self.print_header("Autonomous M-Auth Workflow (multi-service)")
        await self.agent_think("Orchestrating multi-step authentication sequence")
        
        # Step 1: Register (with Self-Healing)
        reg_op = "register_users_account_v1_auth_register_post"
        await self.agent_think("Step 1: AI Payload Generation for Registration")
        reg_payload = await self.engine.generate_payload_template(reg_op)
        
        user_id = None
        max_retries = 5
        for attempt in range(max_retries):
            print(f"✍️ Attempt {attempt+1}: Registering with: {reg_payload.get('email')}")
            reg_url = "http://localhost:8002/users/account/v1/auth/register"
            loop = asyncio.get_event_loop()
            reg_resp = await loop.run_in_executor(None, lambda: requests.post(reg_url, json=reg_payload))
            
            if reg_resp.status_code in [200, 201]:
                user_id = reg_resp.json()["user_id"]
                print(f"✅ User Created: {user_id}")
                break
            elif reg_resp.status_code in [400, 409] and attempt < max_retries - 1:
                error_data = reg_resp.json()
                error_msg = str(error_data.get("detail", str(error_data)))
                print(f"⚠️  Step 1 Failed ({reg_resp.status_code}): {error_msg}")
                
                self.print_header("Step 1: Agent Self-Healing")
                await self.agent_think(f"Analyzing conflict: '{error_msg}'")
                await self.agent_think("Generating unique identity via LLM Reasoner")
                reg_payload = await self.engine.refine_payload(reg_op, reg_payload, error_msg)
                await asyncio.sleep(1)
            else:
                print(f"❌ Step 1 Critical Failure: {reg_resp.text}")
                return

        if not user_id: return
        
        # Step 2: Login
        await self.agent_think("Step 2: AI Payload Generation for Login")
        login_payload = {"email": reg_payload["email"], "password": reg_payload["password"]}
        login_url = "http://localhost:8002/users/account/v1/auth/login"
        loop = asyncio.get_event_loop()
        login_resp = await loop.run_in_executor(None, lambda: requests.post(login_url, json=login_payload))
        
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.text}")
            return
            
        print("✅ Login Successful. Token received.")
        
        # Step 3: Auth Token
        await self.agent_think("Step 3: Generating cross-service session in Auth Token Service")
        token_url = "http://localhost:8001/auth/token/v1/tokens/by-user-id"
        token_resp = await loop.run_in_executor(None, lambda: requests.post(token_url, json={"user_id": user_id}))
        
        if token_resp.status_code == 200:
            print("✨ WORKFLOW COMPLETE: Total Access Granted.")
            print(f"JWT: {token_resp.json()['access_token'][:40]}...")
        else:
            print(f"❌ Token generation failed: {token_resp.text}")

    async def batch_test_operation(self, op_id) -> Dict[str, Any]:
        """Non-interactive version of test_operation for batch runs."""
        print(f"\n🚀 Batch Testing Operation: {op_id}")
        
        await self.agent_think("LLM Reasoner: Generating realistic data")
        payload = await self.engine.generate_payload_template(op_id)
        
        last_status = None
        last_error = None
        
        max_retries = 3
        for attempt in range(max_retries):
            api = self.engine.get_api_details(op_id)
            base_url = self.engine.base_url_map.get(op_id, "http://localhost:8000")
            
            path = api['path']
            # Basic path param resolution
            if "{symbol}" in path: path = path.replace("{symbol}", "AAPL")
            if "{exchange}" in path: path = path.replace("{exchange}", "NSE")
            if "{user_id}" in path: path = path.replace("{user_id}", str(random.randint(100,999)))
            
            url = f"{base_url}{path}"
            method = api['method'].upper()
            
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: requests.request(method, url, json=payload, timeout=5))
                last_status = resp.status_code
                
                if resp.status_code in [200, 201]:
                    print(f"✅ Success (Status {resp.status_code})")
                    return {"success": True, "status": resp.status_code, "error": None}
                elif resp.status_code in [400, 409] and attempt < max_retries - 1:
                    try:
                        error_msg = str(resp.json().get("detail", resp.text))
                    except:
                        error_msg = resp.text
                    
                    last_error = error_msg
                    print(f"⚠️  Received {resp.status_code}: {error_msg}. Retrying with ReAct healing...")
                    payload = await self.engine.refine_payload(op_id, payload, error_msg)
                else:
                    try:
                        last_error = str(resp.json().get("detail", resp.text))
                    except:
                        last_error = resp.text
                    print(f"❌ Failed (Status {resp.status_code})")
                    return {"success": False, "status": resp.status_code, "error": last_error}
            except Exception as e:
                print(f"❌ Execution error: {str(e)}")
                return {"success": False, "status": "ERR", "error": str(e)}
        return {"success": False, "status": last_status, "error": last_error}

    async def run_service_batch(self):
        self.print_header("Batch API Testing Loop")
        print("\nSelect service to batch test:")
        service_list = list(self.services.keys())
        for idx, name in enumerate(service_list):
            print(f"  {idx+1}. {name}")
            
        choice = await self.ainput("\nChoice: ")
        try:
            service_name = service_list[int(choice)-1]
            service_url = self.services[service_name]["url"]
            print(f"\n🔍 Scanning all ops for {service_name} at {service_url}")
            
            # Simple discovery of all ops for this base_url
            ops = [op for op, burl in self.engine.base_url_map.items() if burl == service_url]
            
            if not ops:
                print("❌ No operations found for this service. Ensure it was scanned during init.")
                return

            print(f"Found {len(ops)} operations. Starting autonomous batch run...\n")
            
            results = {"pass": 0, "fail": 0, "details": []}
            
            for op_id in ops:
                res = await self.batch_test_operation(op_id)
                if res["success"]:
                    results["pass"] += 1
                else:
                    results["fail"] += 1
                results["details"].append((op_id, res))
                
            self.print_header("Detailed Batch Test Report")
            print(f"{'STATUS':<10} | {'CODE':<5} | {'OPERATION ID':<40} | {'ERROR QUICKVIEW'}")
            print("-" * 100)
            for op_id, res in results["details"]:
                status = "✅ PASS" if res["success"] else "❌ FAIL"
                code = str(res["status"])
                error = (res["error"][:30] + "...") if res["error"] else "-"
                print(f"{status:<10} | {code:<5} | {op_id:<40} | {error}")
            
            print("-" * 100)
            print(f"TOTAL: {len(ops)} | PASSED: {results['pass']} | FAILED: {results['fail']}")
            
        except Exception as e:
            print(f"Error during batch selection: {e}")

if __name__ == "__main__":
    try:
        cli = MetaAgentCLI()
        asyncio.run(cli.main_menu())
    except KeyboardInterrupt:
        print("\nExiting...")
