"""HTTP client for am-user-platform internal AI APIs."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

import httpx

from shared.core.config import settings

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

PRODUCT_ID = "am_app"
AGENT_TYPE = "fin_portfolio"
CHANNEL = "user_app"


def session_uuid(session_id: str) -> UUID | None:
    try:
        return UUID(str(session_id))
    except (ValueError, TypeError, AttributeError):
        return None


class UserPlatformClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def enabled(self) -> bool:
        return bool((settings.USER_PLATFORM_URL or "").strip())

    def _base_url(self) -> str:
        return (settings.USER_PLATFORM_URL or "").rstrip("/")

    def _timeout(self) -> httpx.Timeout:
        seconds = float(settings.USER_PLATFORM_TIMEOUT_SECONDS)
        return httpx.Timeout(seconds)

    async def _bearer_token(self) -> str:
        static = (settings.USER_PLATFORM_SERVICE_TOKEN or "").strip()
        if static and static.count(".") == 2:
            return static
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        token_url = (settings.KEYCLOAK_TOKEN_URL or "").strip()
        client_id = settings.AM_FIN_AGENT_CLIENT_ID
        client_secret = settings.AM_FIN_AGENT_CLIENT_SECRET or ""
        if not token_url or not client_secret:
            raise RuntimeError(
                "user-platform auth needs USER_PLATFORM_SERVICE_TOKEN or "
                "KEYCLOAK_TOKEN_URL + AM_FIN_AGENT_CLIENT_SECRET"
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": _UA,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body.get("expires_in", 300))
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._bearer_token()
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": _UA,
            "Content-Type": "application/json",
        }

    async def get_context(
        self,
        session_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]] | None:
        """Return last-N messages as {role, content, ...}, or None on failure."""
        if not self.enabled:
            return None
        sid = session_uuid(session_id)
        if sid is None:
            logger.warning("user-platform skip get_context: session_id is not a UUID")
            return None
        url = f"{self._base_url()}/internal/ai/sessions/{sid}/context"
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                resp = await client.get(
                    url,
                    params={"user_id": user_id, "limit": limit},
                    headers=await self._headers(),
                )
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("data") or {}
            rows = data.get("messages") or []
            out: list[dict[str, Any]] = []
            for row in rows:
                role = row.get("role")
                content = row.get("content") or ""
                if role in {"user", "assistant"}:
                    out.append({"role": role, "content": content})
            return out
        except Exception as exc:
            logger.warning("user-platform get_context failed: %s", exc)
            return None

    async def append_messages(
        self,
        session_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
        *,
        product_id: str = PRODUCT_ID,
        agent_type: str = AGENT_TYPE,
        channel: str = CHANNEL,
    ) -> bool:
        if not self.enabled or not messages:
            return False
        sid = session_uuid(session_id)
        if sid is None:
            logger.warning("user-platform skip append: session_id is not a UUID")
            return False
        url = f"{self._base_url()}/internal/ai/sessions/{sid}/messages"
        body = {
            "user_id": user_id,
            "product_id": product_id,
            "agent_type": agent_type,
            "channel": channel,
            "messages": messages,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers=await self._headers(),
                )
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("user-platform append_messages failed: %s", exc)
            return False


user_platform_client = UserPlatformClient()
