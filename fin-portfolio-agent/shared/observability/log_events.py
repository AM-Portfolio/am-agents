"""Canonical fin-agent log event names — grep these in kubectl / Loki."""


class AgentLogEvent:
    # HTTP
    REQUEST_START = "request_start"
    REQUEST_END = "request_end"
    REQUEST_ERROR = "request_error"

    # Chat lifecycle
    CHAT_START = "chat_start"
    CHAT_COMPLETE = "chat_complete"
    CHAT_ERROR = "chat_error"
    CHAT_STREAM_ERROR = "chat_stream_error"

    # LLM
    LLM_REQUEST = "llm_request"
    LLM_SUCCESS = "llm_success"
    LLM_FAILURE = "llm_failure"
    LLM_TEXT_RESPONSE = "llm_text_response"
    LLM_TOOL_CALLS = "llm_tool_calls"
    LLM_TEXT_TOOL_COERCED = "llm_text_tool_coerced"
    LLM_ALL_TIERS_FAILED = "llm_all_tiers_failed"

    # Tools / MCP
    TOOL_EXECUTE_START = "tool_execute_start"
    TOOL_EXECUTE_END = "tool_execute_end"
    TOOL_EXECUTE_ERROR = "tool_execute_error"
    TOOL_UNKNOWN = "tool_unknown"
    MCP_CALL_START = "mcp_call_start"
    MCP_CALL_END = "mcp_call_end"
    MCP_CALL_ERROR = "mcp_call_error"
    MCP_HEALTH_FAIL = "mcp_health_fail"

    # Startup / config
    STARTUP = "fin_agent_startup"
    MODULE_LOAD = "module_load"
    MODULE_LOAD_ERROR = "module_load_error"
