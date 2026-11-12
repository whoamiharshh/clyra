"""In-memory key-value cache with eviction handling."""

import time
from collections import OrderedDict
from typing import Any, Optional


class MemoryCache:
    """Simple LRU cache supporting time-to-live expiration."""

    def __init__(self, capacity: int = 128, default_ttl_seconds: int = 300) -> None:
        self.capacity = capacity
        self.default_ttl = default_ttl_seconds
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve an unexpired value, bumping its access order."""
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with an expiration timestamp."""
        ttl_val = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + ttl_val
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, expires_at)
        if len(self._store) > self.capacity:
            self._store.popitem(last=False)
