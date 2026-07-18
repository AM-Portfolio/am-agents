from typing import List, Dict, Any, Set

class APIRegistry:
    """Manages the API list and calculates execution dependencies (Workflow Graph)."""

    def __init__(self, apis: List[Dict[str, Any]]):
        self.apis = apis
        self.registry = {api["operationId"]: api for api in apis}
        self.dependency_graph = self._build_dependency_graph()

    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        """
        Builds a graph where Edge A -> B means B depends on a field returned by A.
        """
        graph = {api["operationId"]: [] for api in self.apis}
        
        for source_id, source_api in self.registry.items():
            output_fields = self._get_schema_fields(source_api.get("response_schema", {}))
            
            for target_id, target_api in self.registry.items():
                if source_id == target_id: continue
                
                input_fields = self._get_schema_fields(target_api.get("request_schema", {}))
                for p in target_api.get("parameters", []):
                    input_fields.add(p.get("name", ""))

                common_fields = output_fields.intersection(input_fields)
                if common_fields:
                    semantic_fields = {f for f in common_fields if f.lower() not in ["status", "message", "ok"]}
                    if semantic_fields:
                        graph[source_id].append(target_id)
        
        return graph

    def _get_schema_fields(self, schema: Dict[str, Any]) -> Set[str]:
        fields = set()
        if not schema or not isinstance(schema, dict): return fields
        
        props = schema.get("properties", {})
        if not isinstance(props, dict): return fields
        
        for name, details in props.items():
            fields.add(name)
            if isinstance(details, dict) and details.get("type") == "object":
                fields.update(self._get_schema_fields(details))
        
        return fields

    def get_workflow_for(self, target_operation_id: str) -> List[str]:
        needed = []
        visited = set()

        def find_predecessor(op_id):
            if op_id in visited: return
            visited.add(op_id)
            for potential_parent, children in self.dependency_graph.items():
                if op_id in children:
                    find_predecessor(potential_parent)
                    if potential_parent not in needed:
                        needed.append(potential_parent)

        find_predecessor(target_operation_id)
        return needed
