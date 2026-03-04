"""
Simple in-memory TTL cache for public read endpoints.

Reduces DB round-trips for frequently-read, slowly-changing data
(blog posts, job listings) which is important on the free tier
where every ms matters.

Usage:
    from app.services.cache_service import cache

    @router.get("/")
    async def list_posts():
        cached = cache.get("blog:published")
        if cached:
            return cached
        result = await db_query(...)
        cache.set("blog:published", result, ttl=300)
        return result
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            logger.debug("Cache MISS (expired): %s", key)
            return None
        logger.debug("Cache HIT: %s", key)
        return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._store[key] = (value, time.monotonic() + ttl)
        logger.debug("Cache SET: %s (ttl=%ds)", key, ttl)

    def invalidate(self, prefix: str) -> None:
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        logger.debug("Cache INVALIDATED prefix=%s (%d keys)", prefix, len(keys_to_delete))

    def clear(self) -> None:
        self._store.clear()
        logger.debug("Cache CLEARED")


# Module-level singleton — shared across all requests in the process
cache = TTLCache()