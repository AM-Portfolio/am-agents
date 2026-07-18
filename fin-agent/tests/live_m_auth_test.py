import json
import random
import string
from am_fin_api_testing.tools.meta_tools import register_api_spec, search_apis, get_api_workflow, execute_api, generate_payload

def random_id(length=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def run_test():
    test_user_email = f"agent_test_{random_id()}@example.com"
    test_password = "Password123!"
    
    print(f"🚀 Starting Live 'M-Auth' Test for user: {test_user_email}\n")
    
    # 1. Register Specs with Direct Service URLs
    # User Management is on 8002, Auth Tokens is on 8001
    register_api_spec('/tmp/auth_tokens_spec.json', base_url="http://localhost:8001")
    register_api_spec('/tmp/user_mgmt_spec.json', base_url="http://localhost:8002")
    
    # 2. Step 1: User Registration (User Management - 8002)
    # Endpoint: /users/account/v1/auth/register (POST)
    print("--- Step 1: Registering User ---")
    reg_payload = {
        "email": test_user_email,
        "password": test_password,
        "phone_number": f"+1{random.randint(1000000000, 9999999999)}"
    }
    reg_response = json.loads(execute_api("register_users_account_v1_auth_register_post", payload=reg_payload))
    print(f"Status: {reg_response['status']}")
    
    if reg_response['status'] not in [200, 201]:
        print(f"❌ Registration Failed: {reg_response['response']}")
        return

    user_id = reg_response['response'].get('user_id')
    print(f"✅ User Registered. ID: {user_id}")
    
    # 3. Step 2: User Login (to get access_token for auth-tokens service)
    # Endpoint: /users/account/v1/auth/login (POST)
    print("\n--- Step 2: Logging In ---")
    login_payload = {
        "email": test_user_email,
        "password": test_password
    }
    login_response = json.loads(execute_api("login_users_account_v1_auth_login_post", payload=login_payload))
    print(f"Status: {login_response['status']}")
    
    token = login_response['response'].get('access_token')
    if not token:
        print(f"❌ Login Failed: {login_response['response']}")
        return
    print("✅ Login Successful. Token acquired.")

    # 4. Step 3: Create Token By User ID
    # Endpoint: /auth/token/v1/tokens/by-user-id (POST)
    # This requires user_id in the payload
    print("\n--- Step 3: Creating Auth Token via User ID ---")
    token_payload = {
        "user_id": user_id
    }
    token_response = json.loads(execute_api("create_token_by_user_id_auth_token_v1_tokens_by_user_id_post", payload=token_payload))
    print(f"Status: {token_response['status']}")
    
    if token_response['status'] == 200:
        print("✅ Auth Token Created Successfully!")
        print(f"Result: {json.dumps(token_response['response'], indent=2)}")
    else:
        print(f"❌ Token Creation Failed: {token_response['response']}")

if __name__ == "__main__":
    run_test()
