import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from .swagger_parser import SwaggerParser
from .api_registry import APIRegistry
from shared.llm.client import llm_client

logger = logging.getLogger(__name__)

class MetaEngine:
    """
    Engine that coordinates API discovery, dependency resolution, 
    and execution for the Meta-Tool system.
    Now enhanced with LLM-powered reasoning for payload generation and error recovery.
    """
    
    def __init__(self, swagger_path: str = None):
        self.apis = []
        self.registry: Optional[APIRegistry] = None
        self.base_url_map = {} # operationId -> base_url
        self.llm = llm_client
        if swagger_path:
            self.load_registry(swagger_path)

    def remove_apis_for_base_url(self, base_url: str):
        """Remove all APIs associated with a specific base URL."""
        if not base_url:
            return
        base_url = base_url.rstrip("/")
        self.apis = [api for api in self.apis if api.get("base_url", "").rstrip("/") != base_url]
        # Clean up base_url_map
        keys_to_remove = [k for k, v in self.base_url_map.items() if v.rstrip("/") == base_url]
        for k in keys_to_remove:
            del self.base_url_map[k]
        logger.info(f"Cleared existing APIs for {base_url}")

    def load_registry(self, swagger_path: str, base_url: str = None):
        """Load a new registry (replaces current or specific service)."""
        try:
            if base_url:
                self.remove_apis_for_base_url(base_url)
            
            new_apis = SwaggerParser.parse_file(swagger_path)
            if base_url:
                for api in new_apis:
                    api["base_url"] = base_url
                    self.base_url_map[api["operationId"]] = base_url
            
            if not base_url:
                self.apis = new_apis
            else:
                self.apis.extend(new_apis)
                
            self.registry = APIRegistry(self.apis)
            logger.info(f"Loaded {len(new_apis)} APIs into MetaEngine from {swagger_path}")
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            raise

    def add_registry(self, swagger_path: str, base_url: str = None):
        """Add APIs from a new spec to the existing registry, replacing old ones for the same base_url."""
        try:
            if base_url:
                self.remove_apis_for_base_url(base_url)
                
            new_apis = SwaggerParser.parse_file(swagger_path)
            if base_url:
                for api in new_apis:
                    api["base_url"] = base_url
                    self.base_url_map[api["operationId"]] = base_url
            self.apis.extend(new_apis)
            # Re-initialize APIRegistry to rebuild the dependency graph with new nodes
            self.registry = APIRegistry(self.apis)
            logger.info(f"Added {len(new_apis)} new APIs. Total APIs: {len(self.apis)}")
        except Exception as e:
            logger.error(f"Failed to add registry: {e}")
            raise

    def add_registry_json(self, spec_json: Dict[str, Any], base_url: str = None):
        """Add APIs from a JSON spec directly, replacing old ones for the same base_url."""
        try:
            if base_url:
                self.remove_apis_for_base_url(base_url)
                
            from .swagger_parser import SwaggerParser
            new_apis = SwaggerParser.parse_spec(spec_json)
            if base_url:
                for api in new_apis:
                    api["base_url"] = base_url
                    self.base_url_map[api["operationId"]] = base_url
            self.apis.extend(new_apis)
            self.registry = APIRegistry(self.apis)
            logger.info(f"Added {len(new_apis)} manual APIs. Total APIs: {len(self.apis)}")
        except Exception as e:
            logger.error(f"Failed to add manual registry: {e}")
            raise

    def search_apis(self, query: str) -> List[Dict[str, Any]]:
        if not self.registry:
            return []
        
        query = query.lower()
        matches = []
        for api in self.registry.apis:
            if (query in api["operationId"].lower() or 
                query in api["summary"].lower() or 
                query in api.get("description", "").lower() or
                query in api["path"].lower()):
                matches.append({
                    "operationId": api["operationId"],
                    "summary": api["summary"],
                    "path": api["path"],
                    "method": api["method"]
                })
        return matches

    def get_api_details(self, operation_id: str) -> Optional[Dict[str, Any]]:
        if not self.registry:
            return None
        return self.registry.registry.get(operation_id)

    def get_workflow(self, operation_id: str) -> List[str]:
        if not self.registry:
            return []
        return self.registry.get_workflow_for(operation_id)

    async def generate_payload_template(self, operation_id: str) -> Dict[str, Any]:
        """
        Generates a payload template using LLM reasoning (ReAct).
        """
        api = self.get_api_details(operation_id)
        if not api:
            return {"error": f"API {operation_id} not found"}
        
        schema = api.get("request_schema", {})
        
        # LLM ReAct: Understand schema -> Generate data
        logger.info(f"Agent Reasoning: Generating realistic payload for {operation_id}")
        llm_payload = await self._llm_generate_data(api, schema)
        if llm_payload and isinstance(llm_payload, dict):
            return llm_payload
            
        logger.error(f"LLM failed to generate payload for {operation_id}. No hardcoded fallback used.")
        return {"error": "LLM failed to generate schema-valid data."}

    async def refine_payload(self, operation_id: str, current_payload: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
        """
        Refines a payload based on an error message using LLM reasoning (ReAct).
        No hardcoded heuristics allowed.
        """
        api = self.get_api_details(operation_id)
        if not api:
            return current_payload

        # ReAct pattern: Observe error -> Reason -> Act (new payload)
        prompt = f"""
        [REASONING]
        You are an API Testing Agent with ReAct capabilities.
        Current Goal: Resolve a '400 Bad Request' for endpoint '{api['path']}'.
        
        [OBSERVATION]
        Operation ID: {operation_id}
        Method: {api['method']}
        Failed Payload: {json.dumps(current_payload)}
        Server Error Message: "{error_msg}"
        Schema Definition: {json.dumps(api.get('request_schema', {}))}
        
        [THINK]
        Identify the violated constraint (e.g., email exists, phone exists). 
        Determine ALL fields that need to change to ensure a UNIQUE identity.
        
        [ACT]
        Respond ONLY with a corrected JSON payload that resolves the conflict. 
        IMPORTANT: Pick high-entropy random values if previous attempts failed.
        Only JSON.
        """
        
        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1)
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"LLM self-healing failed: {e}")
            
        return current_payload

    async def _llm_generate_data(self, api: Dict[str, Any], schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Reasoning loop for initial data generation optimized for gpt-oss."""
        prompt = f"""
        [GOAL]
        Generate a VALD JSON request body for endpoint: {api.get('path')}
        Summary: {api.get('summary')}
        
        [STRICT SCHEMA]
        {json.dumps(schema)}
        
        [TASK]
        1. Identify REQUIRED fields from the schema (e.g., 'symbol', 'indicators').
        2. Generate realistic financial values (e.g., symbol 'RELIANCE', 'SBIN').
        3. For 'indicators', provide a list of common technical indicator configs (e.g., kind='sma', length=14).
        
        [CONSTRAINT]
        Respond ONLY with the RAW JSON. Do not include markdown code blocks or explanations.
        Valid JSON ONLY.
        """
        
        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}], temperature=0.7)
            # Find first { and last } to handle any extra chatter from OSS models
            import re
            json_match = re.search(r'(\{.*\})', response, re.DOTALL)
            if json_match:
                content = json_match.group(1)
                return json.loads(content)
            else:
                # Try simple load if regex fails to find braces
                return json.loads(response.strip())
        except Exception as e:
            logger.error(f"LLM generation failed for {api.get('operationId')}: {e}")
            return None

    # HEURISTIC FALLBACKS REMOVED PER USER REQUIREMENT

    def load_services(self):
        import os
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    self.services = json.load(f)
                return self.services
            except Exception as e:
                logger.error(f"Failed to load services.json: {e}")
        
        self.services = self._get_default_services()
        return self.services

    def save_services(self, services: List[Dict[str, str]]):
        import os
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services.json")
        with open(config_path, "w") as f:
            json.dump(services, f, indent=2)
        self.services = services

    def _get_default_services(self):
        return [
            {"name": "Auth Tokens", "url": "http://localhost:8001", "spec_url": "http://localhost:8001/v3/api-docs"},
            {"name": "User Management", "url": "http://localhost:8002", "spec_url": "http://localhost:8002/v3/api-docs"},
            {"name": "Market Data", "url": "http://localhost:8092", "spec_url": "http://localhost:8092/v3/api-docs"},
            {"name": "Trade Service", "url": "http://localhost:8040", "spec_url": "http://localhost:8040/v3/api-docs"},
            {"name": "Analysis Service", "url": "http://localhost:8010", "spec_url": "http://localhost:8010/v3/api-docs"},
            {"name": "Market Data Parser", "url": "http://localhost:8022", "spec_url": "http://localhost:8022/v3/api-docs"},
            {"name": "Document Processor", "url": "http://localhost:8081", "spec_url": "http://localhost:8081/v3/api-docs"},
            {"name": "Email Extractor", "url": "http://localhost:8088", "spec_url": "http://localhost:8088/v3/api-docs"}
        ]

    async def check_service_health(self, service: Dict[str, str]):
        import httpx
        name = service["name"]
        url = service["url"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=2.0)
                status = "healthy" if resp.status_code < 500 else "unhealthy"
                return status
        except Exception as e:
            return "unhealthy"

    async def refresh_all_specs(self, dashboard_logger):
        await dashboard_logger.log("default", "info", "Starting Global Service Discovery...")
        for service in self.load_services():
            name = service["name"]
            spec_url = service.get("spec_url") or f"{service['url']}/v3/api-docs"
            await dashboard_logger.log("default", "info", f"Discovery: Fetching spec for {name} from {spec_url}")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(spec_url, timeout=5.0)
                    if resp.status_code == 200:
                        spec = resp.json()
                        self.add_registry_json(spec, service["url"])
                        await dashboard_logger.log("default", "success", f"Discovery: Successfully indexed {name} ({len(spec.get('paths', {}))} endpoints)")
                    else:
                        await dashboard_logger.log("default", "error", f"Discovery: Failed for {name}. Status {resp.status_code} at {spec_url}")
            except Exception as e:
                await dashboard_logger.log("default", "error", f"Discovery: Connection failed for {name} at {spec_url}")

# Global instance
meta_engine = MetaEngine()
