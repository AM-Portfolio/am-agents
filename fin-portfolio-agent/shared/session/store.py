import os
import logging
from collections import defaultdict, deque, OrderedDict
from typing import List, Dict

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

session_store = SessionStore()
