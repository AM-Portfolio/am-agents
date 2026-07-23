from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    """Hot list columns — keep slim for low-latency list/MCP."""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_config_started", "config_id", "started_at"),
        Index("ix_runs_svc_env_started", "service", "environment", "started_at"),
        Index("ix_runs_status_started", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[str | None] = mapped_column(String(64), index=True)
    finished_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), index=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    runner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    config_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    config_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    service: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    openapi_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caller_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    caller_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_pass_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_fail_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iterations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fail_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rps: Mapped[float | None] = mapped_column(Float, nullable=True)
    auth_username: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_short: Mapped[str | None] = mapped_column(String(512), nullable=True)
    grafana_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    detail: Mapped[RunDetailRow | None] = relationship(
        back_populates="run", uselist=False, cascade="all, delete-orphan"
    )
    live: Mapped[RunLiveRow | None] = relationship(
        back_populates="run", uselist=False, cascade="all, delete-orphan"
    )


class RunDetailRow(Base):
    """Cold / fat fields — loaded only on get_run."""

    __tablename__ = "runs_detail"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    payloads_used: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    api_summary: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    steps: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    api_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    run: Mapped[RunRow] = relationship(back_populates="detail")


class RunLiveRow(Base):
    """Progress-only updates — avoid rewriting fat JSON."""

    __tablename__ = "runs_live"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    live: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped[RunRow] = relationship(back_populates="live")


class ProfileRow(Base):
    """Run settings profiles (formerly configs.json)."""

    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_profiles_svc_audience", "service", "audience"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    service: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(32), nullable=True)
    openapi_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_set_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_api_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    payloads: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scripts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(24), index=True)
    role: Mapped[str] = mapped_column(String(32))  # developer|agent|ci|shared
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("key", name="uq_idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
