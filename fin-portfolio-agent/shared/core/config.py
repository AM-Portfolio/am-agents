import os
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

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
    LLM_PLANNER_MODEL = os.getenv("LLM_MODEL", os.getenv("LLM_PLANNER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))

    # Langfuse Observability Configurations
    LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org")
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_TRACE_MAX_OUTPUT_CHARS = int(os.getenv("LANGFUSE_TRACE_MAX_OUTPUT_CHARS", "8000"))

settings = Config()
