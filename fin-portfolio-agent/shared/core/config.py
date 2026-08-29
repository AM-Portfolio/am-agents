import os
from dotenv import load_dotenv

# Find and load .env file by searching upwards, then load Vault sidecar secrets
def _load_env():
    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        env_path = os.path.join(curr, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            break
        curr = os.path.dirname(curr)

    # Automatically parse Vault secrets injected by the Vault Agent sidecar
    vault_dir = "/vault/secrets"
    if os.path.exists(vault_dir):
        for fname in os.listdir(vault_dir):
            fpath = os.path.join(vault_dir, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("export "):
                                line = line[7:]
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip("\"' ")
                                if k:
                                    os.environ[k] = v
                except Exception:
                    pass

_load_env()

# ---------------------------------------------------------------------------
# Env-tier helpers
# ---------------------------------------------------------------------------
_AM_AGENT_ENV = os.getenv("AM_AGENT_ENV", "dev").lower()   # local | dev | preprod | prod


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
    LLM_PLANNER_MODEL = os.getenv("LLM_MODEL", os.getenv("LLM_PLANNER_MODEL", "together-llama-turbo"))
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))

    # Langfuse Observability Configurations
    LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org")
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_TRACE_MAX_OUTPUT_CHARS = int(os.getenv("LANGFUSE_TRACE_MAX_OUTPUT_CHARS", "8000"))
    LANGFUSE_PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME", "fin-agent/finance-system")
    LANGFUSE_PROMPT_LABEL = os.getenv(
        "LANGFUSE_PROMPT_LABEL",
        os.getenv("APP_ENV", _AM_AGENT_ENV),
    )
    LANGFUSE_PROMPT_VERSION = os.getenv("LANGFUSE_PROMPT_VERSION", "").strip()

    # ---------------------------------------------------------------------------
    # Phase 0b — 3-Tier Fallback Chain
    # ---------------------------------------------------------------------------
    # Each tier is (base_url, model_id, api_key_env_var)
    # LiteLLM proxy (LITELLM_BASE_URL) acts as Plan A when configured;
    # otherwise direct provider URLs are used as fallbacks.

    # Plan A — primary: cheap, fast (Together AI / LiteLLM proxy)
    LLM_PLAN_A_MODEL: str = os.getenv(
        "LLM_PLAN_A_MODEL",
        "together-llama-turbo",
    )
    LLM_PLAN_A_BASE_URL: str = os.getenv(
        "LLM_PLAN_A_BASE_URL",
        os.getenv("LITELLM_BASE_URL", "").strip()
        or "https://api.together.ai/v1",
    )
    LLM_PLAN_A_API_KEY: str = os.getenv(
        "LLM_PLAN_A_API_KEY",
        os.getenv("LITELLM_MASTER_KEY") or os.getenv("TOGETHER_API_KEY") or "",
    )

    # Plan B — fallback 1: Gemini 2.0 Flash via LiteLLM alias
    LLM_PLAN_B_MODEL: str = os.getenv("LLM_PLAN_B_MODEL", "gemini-2.0-flash")
    LLM_PLAN_B_BASE_URL: str = os.getenv(
        "LLM_PLAN_B_BASE_URL",
        os.getenv("LITELLM_BASE_URL", "").strip()
        or "https://generativelanguage.googleapis.com/v1beta/openai",
    )
    LLM_PLAN_B_API_KEY: str = os.getenv(
        "LLM_PLAN_B_API_KEY",
        os.getenv("LITELLM_MASTER_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "",
    )

    # Plan C — fallback 2: DeepSeek Chat via LiteLLM alias
    LLM_PLAN_C_MODEL: str = os.getenv("LLM_PLAN_C_MODEL", "deepseek-chat")
    LLM_PLAN_C_BASE_URL: str = os.getenv(
        "LLM_PLAN_C_BASE_URL",
        os.getenv("LITELLM_BASE_URL", "").strip()
        or "https://api.openai.com/v1",
    )
    LLM_PLAN_C_API_KEY: str = os.getenv(
        "LLM_PLAN_C_API_KEY",
        os.getenv("LITELLM_MASTER_KEY") or os.getenv("OPENAI_API_KEY") or "",
    )

    # ---------------------------------------------------------------------------
    # Phase 0b — Retry / timeout policy
    # ---------------------------------------------------------------------------
    # NOTE: LiteLLM proxy adds latency on top of providers — 30s minimum per attempt
    LLM_ATTEMPT_TIMEOUT_SECONDS: float = float(os.getenv("LLM_ATTEMPT_TIMEOUT_SECONDS", "30.0"))
    LLM_MAX_RETRIES_PER_TIER: int = int(os.getenv("LLM_MAX_RETRIES_PER_TIER", "2"))
    LLM_RETRY_BACKOFF_SECONDS: float = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1.0"))

    # ---------------------------------------------------------------------------
    # Phase 0b — Cost / budget alerts (0 = disabled)
    # ---------------------------------------------------------------------------
    LLM_DAILY_BUDGET_USD: float = float(os.getenv("LLM_DAILY_BUDGET_USD", "0"))
    LLM_MONTHLY_BUDGET_USD: float = float(os.getenv("LLM_MONTHLY_BUDGET_USD", "0"))

    # ---------------------------------------------------------------------------
    # Env tier (useful for model routing decisions at runtime)
    # ---------------------------------------------------------------------------
    AM_AGENT_ENV: str = _AM_AGENT_ENV

    # ---------------------------------------------------------------------------
    # Phase 1 — MCP client wiring
    # ---------------------------------------------------------------------------
    MCP_BASE_URL: str = os.getenv(
        "MCP_BASE_URL",
        os.getenv("MCP_SERVER_URL",
            os.getenv("AM_MCP_SERVER_URL", "https://am.asrax.in/mcp")
        ),
    ).replace("/sse", "").rstrip("/")
    AI_MCP_REQUIRED: bool = os.getenv("AI_MCP_REQUIRED", "false").lower() in {"1", "true", "yes"}
    AI_WRITE_TOOLS_ENABLED: bool = os.getenv("AI_WRITE_TOOLS_ENABLED", "false").lower() in {"1", "true", "yes"}

    # ---------------------------------------------------------------------------
    # Phase 1 — Session / conversation history caps
    # ---------------------------------------------------------------------------
    AI_HISTORY_MAX_TURNS: int = int(os.getenv("AI_HISTORY_MAX_TURNS", "10"))
    AI_SESSION_MAX_TURNS: int = int(os.getenv("AI_SESSION_MAX_TURNS", "20"))

    # Phase 1 — Tool execution
    # ---------------------------------------------------------------------------
    TOOL_TIMEOUT_SECONDS: float = float(os.getenv("TOOL_TIMEOUT_SECONDS", "30.0"))

    # ---------------------------------------------------------------------------
    # Phase 1 — Tool result compression
    # ---------------------------------------------------------------------------
    AI_TOOL_RESULT_MAX_CHARS: int = int(os.getenv("AI_TOOL_RESULT_MAX_CHARS", "4000"))
    AI_TOOL_RESULT_MAX_ROWS: int = int(os.getenv("AI_TOOL_RESULT_MAX_ROWS", "20"))
    AI_OBSERVATION_FORMAT: str = os.getenv("AI_OBSERVATION_FORMAT", "toon").lower()

settings = Config()
