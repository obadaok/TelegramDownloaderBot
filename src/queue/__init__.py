"""Redis queue module for task management."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from src.config.settings import settings

logger = logging.getLogger(__name__)


class RedisQueue:
    """Async Redis queue for download tasks."""

    def __init__(self):
        self._redis: Optional[Redis] = None
        self._url = settings.redis_url
        self._queue_key = "download_queue"

    async def init(self) -> None:
        """Initialize Redis connection."""
        self._redis = redis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        await self._redis.ping()
        logger.info("Redis connected at %s", self._url)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def enqueue(self, task: Dict[str, Any]) -> bool:
        """Add task to queue."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        await self._redis.lpush(self._queue_key, json.dumps(task))
        return True

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get next task from queue (blocking)."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        item = await self._redis.brpop(self._queue_key, timeout=5)
        if item:
            _, data = item
            return json.loads(data)
        return None

    async def size(self) -> int:
        """Get queue size."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        return await self._redis.llen(self._queue_key)

    async def clear(self) -> None:
        """Clear queue."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        await self._redis.delete(self._queue_key)

    async def dedupe_check(self, url: str, ttl: int = 900) -> bool:
        """Check if URL was recently processed (for deduplication)."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        key = f"dedupe:{url}"
        result = await self._redis.set(key, "1", nx=True, ex=ttl)
        return bool(result)

    async def is_processing(self, job_id: int) -> bool:
        """Check if a job is currently being processed."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        key = f"processing:{job_id}"
        return await self._redis.exists(key)

    async def mark_processing(self, job_id: int, ttl: int = 3600) -> None:
        """Mark job as being processed."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        key = f"processing:{job_id}"
        await self._redis.set(key, "1", ex=ttl)

    async def unmark_processing(self, job_id: int) -> None:
        """Unmark job as processed."""
        if not self._redis:
            raise RuntimeError("Queue not initialized")
        key = f"processing:{job_id}"
        await self._redis.delete(key)


_queue: Optional[RedisQueue] = None


async def get_queue() -> RedisQueue:
    """Get singleton queue instance."""
    global _queue
    if _queue is None:
        _queue = RedisQueue()
        await _queue.init()
    return _queue