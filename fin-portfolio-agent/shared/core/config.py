import os
from dotenv import load_dotenv

# Find and load .env file by searching upwards
def _load_env():
    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        env_path = os.path.join(curr, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            return
        curr = os.path.dirname(curr)

_load_env()

class Config:
    ENABLE_PORTFOLIO_ANALYSIS = os.getenv("ENABLE_PORTFOLIO_ANALYSIS", "true").lower() == "true"
    ENABLE_API_TESTING = os.getenv("ENABLE_API_TESTING", "true").lower() == "true"
    
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
    MONGODB_URI = os.getenv("MONGODB_URI")
    DB_NAME = os.getenv("DB_NAME", "portfolio")

    # Unified LLM Configuration (matching tool-agent)
    LLM_ROUTING = os.getenv("LLM_ROUTING", "direct")
    LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "").strip() or os.getenv("LLM_BASE_URL", "").strip()
    LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY")
    MCP_GATEWAY_BASE_URL = os.getenv("MCP_GATEWAY_BASE_URL", "http://localhost:8120")
    MCP_GATEWAY_AUTH_DISABLED = os.getenv("MCP_GATEWAY_AUTH_DISABLED", "true").lower() == "true"
    AM_MCP_CLIENT_ID = os.getenv("AM_MCP_CLIENT_ID", "am-mcp-service")
    AM_MCP_CLIENT_SECRET = os.getenv("AM_MCP_CLIENT_SECRET")
    KEYCLOAK_TOKEN_URL = os.getenv("KEYCLOAK_TOKEN_URL")
    # Java am-mcp-server (data plane)
    AM_MCP_SERVER_URL = os.getenv(
        "AM_MCP_SERVER_URL",
        "http://am-mcp-server.am-apps-dev.svc.cluster.local:8080",
    ).rstrip("/")
    MCP_TOOL_CACHE_TTL_SECONDS = int(os.getenv("MCP_TOOL_CACHE_TTL_SECONDS", "120"))
    MCP_TOOL_BLOCKLIST = os.getenv("MCP_TOOL_BLOCKLIST", "ask_finance_agent")
    MCP_CLIENT_TIMEOUT_SECONDS = float(os.getenv("MCP_CLIENT_TIMEOUT_SECONDS", "30"))
    MCP_SSE_READ_TIMEOUT_SECONDS = float(os.getenv("MCP_SSE_READ_TIMEOUT_SECONDS", "60"))
    # Keep REST code out of the default path; MCP failure must surface as error.
    DATA_FALLBACK_REST = os.getenv("DATA_FALLBACK_REST", "false").lower() in {
        "1", "true", "yes", "on",
    }
    LLM_PLANNER_MODEL = os.getenv("LLM_MODEL", os.getenv("LLM_PLANNER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))
    MCP_TOOL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_TIMEOUT_SECONDS", "45"))

    # Langfuse Observability Configurations
    LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org")
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_TRACE_MAX_OUTPUT_CHARS = int(os.getenv("LANGFUSE_TRACE_MAX_OUTPUT_CHARS", "8000"))
    LANGFUSE_ENV = os.getenv("LANGFUSE_ENV", os.getenv("APP_ENV", "dev")).strip() or "dev"
    # full = include tool payloads (dev); summary = redact raw tool bodies (preprod/prod)
    LANGFUSE_TOOL_PAYLOAD_MODE = os.getenv("LANGFUSE_TOOL_PAYLOAD_MODE", "full").strip().lower()

    # Prompt management — file locally; langfuse in cluster
    PROMPT_SOURCE = os.getenv("PROMPT_SOURCE", "file").strip().lower()  # langfuse | file
    PROMPT_LABEL = os.getenv("PROMPT_LABEL", "production").strip() or "production"
    PROMPT_CACHE_TTL_SECONDS = int(os.getenv("PROMPT_CACHE_TTL_SECONDS", "60"))

settings = Config()
