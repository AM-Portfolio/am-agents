import toml
from typing import Dict, Any, List

def tools_to_toml(tools: List[Dict[str, Any]]) -> str:
    """
    Convert tool definitions from JSON to TOML format.
    TOML is more compact and reduces token usage.
    
    Args:
        tools: List of tool definitions in JSON format
    
    Returns:
        TOML string representation
    """
    toml_tools = {}
    
    for i, tool in enumerate(tools):
        if tool["type"] == "function":
            func = tool["function"]
            tool_name = func["name"]
            
            toml_tools[tool_name] = {
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {})
            }
    
    return toml.dumps(toml_tools)

def toml_to_tools(toml_str: str) -> List[Dict[str, Any]]:
    """
    Convert TOML tool definitions back to JSON format.
    
    Args:
        toml_str: TOML string
    
    Returns:
        List of tool definitions in JSON format
    """
    toml_tools = toml.loads(toml_str)
    tools = []
    
    for name, config in toml_tools.items():
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": config.get("description", ""),
                "parameters": config.get("parameters", {})
            }
        })
    
    return tools

def format_tool_response_toml(tool_name: str, result: Any) -> str:
    """
    Format tool response in TOML instead of JSON.
    More compact for LLM context.
    
    Args:
        tool_name: Name of the tool
        result: Tool execution result
    
    Returns:
        TOML formatted string
    """
    response = {
        "tool": tool_name,
        "result": str(result)  # Convert to string for TOML compatibility
    }
    return toml.dumps(response)
