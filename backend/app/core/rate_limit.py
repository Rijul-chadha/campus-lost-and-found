"""Sliding-window rate limiter on Redis (sorted set per key; atomic via Lua).

Works across any number of API replicas, unlike in-process limiters.
"""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

from app.domain.errors import RateLimited

_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, math.ceil((tonumber(oldest[2]) + window - now))}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, 0}
"""


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_SCRIPT)

    async def hit(self, bucket: str, subject: str, *, limit: int, window_seconds: int) -> None:
        now_ms = int(time.time() * 1000)
        allowed, retry_ms = await self._script(
            keys=[f"rl:{bucket}:{subject}"],
            args=[now_ms, window_seconds * 1000, limit, f"{now_ms}-{uuid.uuid4().hex[:8]}"],
        )
        if not int(allowed):
            raise RateLimited(
                "Too many requests, please slow down.",
                details={"retry_after_seconds": max(1, int(retry_ms) // 1000)},
            )
