import json
from typing import List, Dict, Any

class SwaggerParser:
    """Parses OpenAPI/Swagger JSON into a flattened registry for the agent."""
    
    @staticmethod
    def parse_file(file_path: str) -> List[Dict[str, Any]]:
        with open(file_path, 'r') as f:
            spec = json.load(f)
        return SwaggerParser.parse_spec(spec)

    @staticmethod
    def parse_spec(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        registry = []
        paths = spec.get("paths", {})
        components = spec.get("components", {}).get("schemas", {})
        
        def resolve_ref(schema):
            if not isinstance(schema, dict):
                return schema
            if "$ref" in schema:
                ref_path = schema["$ref"].split("/")
                if ref_path[1] == "components" and ref_path[2] == "schemas":
                    return components.get(ref_path[3], schema)
            return schema

        for path, methods in paths.items():
            for method, details in methods.items():
                request_body = details.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
                response_200 = details.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
                response_201 = details.get("responses", {}).get("201", {}).get("content", {}).get("application/json", {}).get("schema", {})
                
                entry = {
                    "operationId": details.get("operationId", f"{method}_{path.replace('/', '_')}"),
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "parameters": details.get("parameters", []),
                    "request_schema": resolve_ref(request_body),
                    "response_schema": resolve_ref(response_200 or response_201)
                }
                registry.append(entry)
        
        return registry
