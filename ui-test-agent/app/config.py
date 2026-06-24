import os
import tempfile
from pathlib import Path
from typing import Literal, Optional, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE_PATH", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_PORT: int = Field(default=8130)
    APP_ENV: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="text")
    TZ: str = Field(default="Asia/Kolkata")

    # gateway (production default) | direct (local dev fast path — skips gateway hop)
    LLM_ROUTING: Literal["gateway", "direct"] = Field(default="gateway")

    MCP_GATEWAY_BASE_URL: str = Field(default="http://localhost:8120")
    MCP_GATEWAY_AUTH_DISABLED: bool = Field(default=False)

    LITELLM_BASE_URL: str = Field(default="http://localhost:4000")
    LITELLM_MASTER_KEY: Optional[str] = Field(default=None)

    LLM_PLANNER_MODEL: str = Field(default="deepseek-chat")
    LLM_VISION_MODEL: str = Field(default="Qwen/Qwen2.5-VL-7B-Instruct")
    LLM_TEMPERATURE: float = Field(default=0.2)
    LLM_MAX_TOKENS: int = Field(default=2048)
    LLM_TIMEOUT_SECONDS: float = Field(default=120.0)

    KEYCLOAK_TOKEN_URL: str = Field(
        default="http://auth.munish.org/auth/realms/am-preprod-realm/protocol/openid-connect/token"
    )
    AM_MCP_CLIENT_ID: str = Field(default="am-mcp-service")
    AM_MCP_CLIENT_SECRET: Optional[str] = Field(default=None)

    HEADLESS: bool = Field(default=True)
    BROWSER_VIEWPORT_WIDTH: int = Field(default=1280)
    BROWSER_VIEWPORT_HEIGHT: int = Field(default=800)
    REPORT_DIR: str = Field(
        default_factory=lambda: str(Path(tempfile.gettempdir()) / "am-ui-test-reports")
    )

    # am-modern-ui auth: demo = click Demo Login in login section; credentials = fill email/password
    AUTH_LOGIN_MODE: Literal["demo", "credentials"] = Field(default="demo")
    TEST_USER_EMAIL: str = Field(default="ssd2658@gmail.com")
    TEST_USER_PASSWORD: str = Field(default="@M1unish")
    UI_APP_MODE: Literal["portfolio", "main"] = Field(
        default="portfolio",
        description="Default UI shell when port cannot be inferred from target URL",
    )
    MODERN_UI_PORTFOLIO_URL: str = Field(default="http://localhost:9005")
    MODERN_UI_MAIN_URL: str = Field(default="http://localhost:9000")

    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_HTTPS: bool = Field(default=False)
    QDRANT_API_KEY: Optional[str] = Field(default=None)

    DESIGN_REVIEW_ENABLED: bool = Field(default=True)
    DESIGN_SIMILARITY_PASS: float = Field(default=0.92)
    DESIGN_SIMILARITY_REVIEW: float = Field(default=0.78)
    DESIGN_GATE_STRICT: bool = Field(default=False)
    DESIGN_BUG_MEMORY_THRESHOLD: float = Field(default=0.95)
    BASELINE_MODE: Literal["compare", "seed", "promote"] = Field(default="compare")
    REPORT_LLM_ENABLED: bool = Field(default=True)
    REPORT_LLM_VISION: bool = Field(
        default=True,
        description="Vision LLM summary of final authenticated screenshot in report",
    )
    LLM_VISION_ENABLED: bool = Field(
        default=True,
        description="Call vision LLM for design-review drift; disable if provider needs dedicated endpoint",
    )
    CLIP_EMBEDDING_MODEL: Optional[str] = Field(
        default=None,
        description="Optional LiteLLM embedding model; local hash embedder if unset",
    )

    MONGO_URI: str = Field(default="mongodb://localhost:27017")
    MONGO_DATABASE: str = Field(default="am_ui_testing")

    @property
    def llm_routing(self) -> str:
        return self.LLM_ROUTING.strip().lower()

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        report = Path(self.REPORT_DIR)
        if not report.is_absolute():
            agent_root = Path(__file__).resolve().parents[1]
            self.REPORT_DIR = str((agent_root / report).resolve())
        if self.llm_routing not in ("gateway", "direct"):
            raise ValueError("LLM_ROUTING must be 'gateway' or 'direct'")
        if self.llm_routing == "direct" and self.APP_ENV.lower() == "production":
            raise ValueError("LLM_ROUTING=direct is not allowed when APP_ENV=production")
        if self.llm_routing == "direct" and not self.LITELLM_MASTER_KEY:
            raise ValueError("LITELLM_MASTER_KEY is required when LLM_ROUTING=direct")
        return self


settings = Settings()
