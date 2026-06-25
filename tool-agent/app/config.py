from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = AGENT_ROOT / "config"
TOOLS_DIR = AGENT_ROOT / "tools"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE_PATH", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_PORT: int = Field(default=8141)
    APP_ENV: str = Field(default="local")
    LOG_LEVEL: str = Field(default="INFO")

    LLM_ROUTING: Literal["gateway", "direct"] = Field(default="direct")
    LITELLM_BASE_URL: str = Field(default="http://localhost:4000")
    LITELLM_MASTER_KEY: str | None = Field(default=None)
    MCP_GATEWAY_BASE_URL: str = Field(default="http://localhost:8120")
    MCP_GATEWAY_AUTH_DISABLED: bool = Field(default=True)
    AM_MCP_CLIENT_ID: str = Field(default="am-mcp-service")
    AM_MCP_CLIENT_SECRET: str | None = Field(default=None)
    KEYCLOAK_TOKEN_URL: str | None = Field(default=None)
    LLM_PLANNER_MODEL: str = Field(
        default="together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite"
    )
    LLM_TEMPERATURE: float = Field(default=0.1)
    LLM_MAX_TOKENS: int = Field(default=1024)
    LLM_TIMEOUT_SECONDS: float = Field(default=60.0)
    LLM_INTENT_ENABLED: bool = Field(default=True)
    LLM_SUMMARY_ENABLED: bool = Field(default=True)

    TOOL_AGENT_READ_ONLY_DEFAULT: bool = Field(default=True)
    TOOL_AGENT_ALLOW_WRITES: bool = Field(default=False)
    TOOL_AGENT_MAX_ROWS: int = Field(default=100)
    TOOL_AGENT_TIMEOUT_SECONDS: int = Field(default=30)
    TOOL_AGENT_INTENT_MIN_CONFIDENCE: float = Field(default=0.75, ge=0.0, le=1.0)
    TOOL_AGENT_REQUIRE_BACKEND_FOR_AGENTS: bool = Field(default=True)

    MCP_DEPLOYMENT_MODE: Literal["self_hosted", "managed", "hybrid"] = Field(
        default="self_hosted"
    )
    MCP_UNIVERSAL_GATEWAY: Literal["toolbox", "none"] = Field(default="toolbox")
    MCP_ENABLED: bool = Field(default=False)
    TOOLBOX_TOOLS_FILE: str = Field(default="config/toolbox.yaml")
    TOOLBOX_URL: str | None = Field(default=None)

    POSTGRES_URL: str | None = Field(default=None)
    MONGODB_URI: str | None = Field(default=None)
    REDIS_URL: str | None = Field(default=None)
    QDRANT_URL: str | None = Field(default=None)
    QDRANT_API_KEY: str | None = Field(default=None)
    KAFKA_BOOTSTRAP_SERVERS: str | None = Field(default=None)
    KAFKA_USERNAME: str | None = Field(default=None)
    KAFKA_PASSWORD: str | None = Field(default=None)
    KAFKA_SECURITY_PROTOCOL: str = Field(default="SASL_PLAINTEXT")
    KAFKA_SASL_MECHANISM: str = Field(default="SCRAM-SHA-256")
    KAFKA_UI_URL: str | None = Field(default=None)
    KAFKA_UI_CLUSTER: str = Field(default="am-preprod")
    KAFKA_PEEK_MODE: Literal["auto", "native", "kafka_ui"] = Field(default="auto")

    GRAFANA_MCP_URL: str | None = Field(
        default="http://kagent-grafana-mcp.kagent.svc.cluster.local:8000/mcp"
    )
    GRAFANA_MCP_TIMEOUT_SECONDS: float = Field(default=30.0)

    VAULT_MCP_URL: str | None = Field(
        default="http://kagent-vault-mcp.kagent.svc.cluster.local:8080/mcp"
    )
    VAULT_MCP_TIMEOUT_SECONDS: float = Field(default=30.0)
    VAULT_MCP_MOUNT: str = Field(default="apps")
    VAULT_MCP_WRITES_ENABLED: bool = Field(default=False)

    PROMPT_SOURCE: Literal["langfuse", "file"] = Field(default="file")
    TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS: int = Field(default=60)

    LANGFUSE_ENABLED: bool = Field(default=False)
    LANGFUSE_HOST: str = Field(default="https://langfuse.munish.org")
    LANGFUSE_PUBLIC_KEY: str | None = Field(default=None)
    LANGFUSE_SECRET_KEY: str | None = Field(default=None)
    LANGFUSE_TRACE_MAX_OUTPUT_CHARS: int = Field(default=8000)

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        toolbox = Path(self.TOOLBOX_TOOLS_FILE)
        if not toolbox.is_absolute():
            self.TOOLBOX_TOOLS_FILE = str((AGENT_ROOT / toolbox).resolve())
        return self

    def langfuse_prompt_label(self) -> str:
        if self.APP_ENV in ("prod", "production"):
            return "production"
        if self.APP_ENV in ("dev", "local"):
            return "latest"
        return self.APP_ENV

    def backends_file(self) -> Path:
        path = CONFIG_DIR / f"backends.{self.APP_ENV}.yaml"
        if path.exists():
            return path
        return CONFIG_DIR / "backends.local.yaml"

    def load_backends_config(self) -> dict:
        path = self.backends_file()
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


settings = Settings()
