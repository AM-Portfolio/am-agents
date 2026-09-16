"""In-cluster D1 persist check. Run inside the fin-agent pod. Prints counts only."""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx

from shared.clients.user_platform_client import user_platform_client
from shared.core.config import settings


USER_ID = "d1-persist-verify"
SESSION_ID = str(uuid.uuid4())


async def main() -> None:
    print("url_set", bool(settings.USER_PLATFORM_URL))
    print("secret_set", bool(settings.AM_FIN_AGENT_CLIENT_SECRET))
    print("client_enabled", user_platform_client.enabled)
    print("session", SESSION_ID)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "http://127.0.0.1:8101/api/v1/ai/chat",
            json={
                "message": "Say only: ok",
                "userId": USER_ID,
                "sessionId": SESSION_ID,
            },
        )
    print("chat_status", resp.status_code)
    if resp.status_code != 200:
        print("chat_fail_len", len(resp.text or ""))
        return
    body = resp.json()
    print("chat_msg_len", len(body.get("message") or ""))

    rows = await user_platform_client.get_context(SESSION_ID, USER_ID, limit=20)
    if rows is None:
        print("context", "failed")
        return
    print("context_count", len(rows))
    print("roles", ",".join(r.get("role", "") for r in rows))


if __name__ == "__main__":
    asyncio.run(main())
