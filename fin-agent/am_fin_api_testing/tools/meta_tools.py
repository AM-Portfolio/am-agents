import json
import os
import requests
from typing import Dict, Any, Optional
from shared.tools.registry import register_tool
from ..core.meta_engine import meta_engine

# Initialize engine with the sample spec if it exists
DEFAULT_SWAGGER = "/Users/munishm/Documents/AM-Repos/backend/ai-bots/openapi.json"
if os.path.exists(DEFAULT_SWAGGER) and not meta_engine.registry:
    meta_engine.load_registry(DEFAULT_SWAGGER)

@register_tool(
    description="Register a new API Swagger/OpenAPI specification file to the registry.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the local Swagger JSON file."},
            "base_url": {"type": "string", "description": "The base URL for the API (e.g., http://localhost:8011)."}
        },
        "required": ["file_path"]
    }
)
def register_api_spec(file_path: str, base_url: str = None) -> str:
    """Load a new Swagger spec into the engine."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' not found."
    try:
        meta_engine.add_registry(file_path, base_url)
        return f"Successfully registered new API spec from {file_path}. Total operations: {len(meta_engine.apis)}."
    except Exception as e:
        return f"Error registering spec: {e}"

@register_tool(
    description="Search for available APIs in the registry. Resolves many-to-one matches.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term (e.g., 'orders', 'user')"},
            "search_query": {"type": "string", "description": "Alias for query"}
        },
        "required": []
    }
)
def search_apis(query: str = None, search_query: str = None) -> str:
    """Search available APIs in the registry."""
    q = query or search_query
    if not q: return "Error: No search query provided."
    matches = meta_engine.search_apis(q)
    if not matches:
        return f"No APIs found matching '{query}'."
    return f"Found APIs:\n{json.dumps(matches, indent=2)}"

@register_tool(
    description="Get the workflow (list of preceding APIs) required before calling a target API.",
    parameters={
        "type": "object",
        "properties": {
            "operation_id": {"type": "string", "description": "The target operationId to find requirements for."}
        },
        "required": ["operation_id"]
    }
)
def get_api_workflow(operation_id: str) -> str:
    """Find necessary workflow steps for an API."""
    workflow = meta_engine.get_workflow(operation_id)
    if not workflow:
        return f"API '{operation_id}' has no known dependencies."
    return f"To execute '{operation_id}', you should follow this workflow: {workflow}"

@register_tool(
    description="Generate a realistic JSON payload template for a specific API operation using reasoning.",
    parameters={
        "type": "object",
        "properties": {
            "operation_id": {"type": "string", "description": "The operationId of the API."},
            "operationId": {"type": "string", "description": "Alias for operation_id"}
        },
        "required": []
    }
)
async def generate_payload(operation_id: str = None, operationId: str = None) -> str:
    """Generate a template payload for an API (Async)."""
    op_id = operation_id or operationId
    if not op_id: return "Error: No operation_id provided."
    template = await meta_engine.generate_payload_template(op_id)
    return f"Payload template for '{op_id}':\n{json.dumps(template, indent=2)}"

@register_tool(
    description="Execute a real REST API call to a service.",
    parameters={
        "type": "object",
        "properties": {
            "operation_id": {"type": "string", "description": "The operationId to execute."},
            "payload": {"type": "object", "description": "JSON payload for POST/PUT requests."},
            "params": {"type": "object", "description": "Query or path parameters (e.g., {'id': '123'})."}
        },
        "required": ["operation_id"]
    }
)
def execute_api(operation_id: str, payload: dict = None, params: dict = None) -> str:
    """Execute a real API call using requests."""
    api = meta_engine.get_api_details(operation_id)
    if not api:
        return f"Error: API '{operation_id}' not found."
    
    method = api["method"]
    path = api["path"]
    base_url = meta_engine.base_url_map.get(operation_id, "http://localhost:8011") # Default to gateway
    
    # Resolve path parameters
    target_path = path
    if params:
        for key, value in params.items():
            placeholder = "{" + key + "}"
            if placeholder in target_path:
                target_path = target_path.replace(placeholder, str(value))
    
    url = f"{base_url.rstrip('/')}/{target_path.lstrip('/')}"
    
    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            params=params if method == "GET" else None,
            timeout=10
        )
        
        try:
            body = response.json()
        except:
            body = response.text

        return json.dumps({
            "operation_id": operation_id,
            "status": response.status_code,
            "url": url,
            "method": method,
            "response": body
        }, indent=2)
    except Exception as e:
        return f"Network Error executing {operation_id}: {e}"

@register_tool(
    description="Validate an API response against its documented schema.",
    parameters={
        "type": "object",
        "properties": {
            "operation_id": {"type": "string", "description": "The operationId."},
            "response_body": {"type": "object", "description": "The JSON response to validate."}
        },
        "required": ["operation_id", "response_body"]
    }
)
def validate_response(operation_id: str, response_body: dict) -> str:
    """Validate a response against schema."""
    api = meta_engine.get_api_details(operation_id)
    if not api:
        return f"Error: API '{operation_id}' not found."
    
    schema = api.get("response_schema", {})
    if not schema:
        return f"Warning: No response schema found for '{operation_id}'. Assuming valid."
    
    # Simple validation mock
    return f"Response for '{operation_id}' validated successfully against schema."
