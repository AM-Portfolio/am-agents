from collections import defaultdict, deque
from typing import List, Dict

# In-memory session store.
# To upgrade to Redis: replace _store with redis.hgetall / hset calls.
_MAX_HISTORY = 20
_store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_HISTORY))


class SessionStore:
    def get(self, session_id: str) -> List[Dict]:
        """Return all stored messages for a session."""
        return list(_store[session_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append a message to the session history."""
        _store[session_id].append({"role": role, "content": content})

    def clear(self, session_id: str) -> None:
        """Clear a session's history."""
        if session_id in _store:
            del _store[session_id]


session_store = SessionStore()
