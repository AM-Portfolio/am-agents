import time
from typing import Any, Dict, Optional
import hashlib
import json

class SimpleCache:
    """Simple in-memory cache with TTL (time-to-live)."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str, ttl_seconds: int = 3600) -> Optional[Any]:
        """
        Get cached value if it exists and hasn't expired.
        
        Args:
            key: Cache key
            ttl_seconds: Time to live in seconds (default 1 hour)
        
        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        age = time.time() - entry["timestamp"]
        
        if age > ttl_seconds:
            # Expired, remove it
            del self._cache[key]
            return None
        
        return entry["value"]
    
    def set(self, key: str, value: Any):
        """Store value in cache with current timestamp."""
        self._cache[key] = {
            "value": value,
            "timestamp": time.time()
        }
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
    
    @staticmethod
    def make_key(*args) -> str:
        """Generate cache key from arguments."""
        # Create a stable hash from arguments
        key_str = json.dumps(args, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

# Global cache instance
cache = SimpleCache()
