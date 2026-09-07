import os
import logging
from collections import defaultdict, deque, OrderedDict
from typing import Any, List, Dict

from shared.clients.user_platform_client import (
    AGENT_TYPE,
    CHANNEL,
    PRODUCT_ID,
    user_platform_client,
)
from shared.core.config import settings

logger = logging.getLogger(__name__)

# In-memory session store.
AI_SESSION_MAX_TURNS = int(os.getenv('AI_SESSION_MAX_TURNS', '20'))

_store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=AI_SESSION_MAX_TURNS))

# Idempotency store (max 1000 entries, LRU)
_idempotency_store: OrderedDict = OrderedDict()
_MAX_IDEMPOTENCY = 1000

class SessionStore:
    def get_history(self, user_id: str, session_id: str) -> List[Dict]:
        """Return all stored messages for a session."""
        key = f"{user_id}:{session_id}"
        if key not in _store:
            return []
        return list(_store[key])

    def append_turn(self, user_id: str, session_id: str, role: str, content: str) -> None:
        """Append a message to the session history."""
        key = f"{user_id}:{session_id}"
        _store[key].append({"role": role, "content": content})
        logger.info(f"Appended turn for session_id={session_id}, total_turns={len(_store[key])}")

    def clear_session(self, user_id: str, session_id: str) -> None:
        """Clear a session's history."""
        key = f"{user_id}:{session_id}"
        if key in _store:
            del _store[key]

    def idempotency_seen(self, key: str) -> bool:
        return key in _idempotency_store

    def mark_idempotency(self, key: str) -> None:
        if key in _idempotency_store:
            _idempotency_store.move_to_end(key)
        else:
            _idempotency_store[key] = True
            if len(_idempotency_store) > _MAX_IDEMPOTENCY:
                _idempotency_store.popitem(last=False)

    async def load_history(self, user_id: str, session_id: str) -> List[Dict]:
        """RAM history, hydrated from user-platform when USER_PLATFORM_URL is set."""
        if user_platform_client.enabled:
            remote = await user_platform_client.get_context(
                session_id,
                user_id,
                limit=settings.AI_HISTORY_MAX_TURNS,
            )
            if remote is not None:
                key = f"{user_id}:{session_id}"
                _store[key].clear()
                for msg in remote:
                    _store[key].append(
                        {"role": msg["role"], "content": msg["content"]}
                    )
                return list(_store[key])
        return self.get_history(user_id, session_id)

    async def persist_turn(
        self,
        user_id: str,
        session_id: str,
        messages: List[Dict[str, Any]],
        *,
        product_id: str = PRODUCT_ID,
        agent_type: str = AGENT_TYPE,
        channel: str = CHANNEL,
    ) -> None:
        """Best-effort durable append. RAM is already updated via append_turn."""
        if not user_platform_client.enabled or not messages:
            return
        await user_platform_client.append_messages(
            session_id,
            user_id,
            messages,
            product_id=product_id,
            agent_type=agent_type,
            channel=channel,
        )

session_store = SessionStore()
