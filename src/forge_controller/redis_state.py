from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


class RedisStateStore:
    """Ephemeral coordination only; durable truth remains PostgreSQL/Hermes/Git."""

    def __init__(self, client: Redis) -> None:
        self.client = client

    async def set_task_wake(self, task_id: str, retry_at: datetime) -> None:
        await self.client.zadd("forge:wakes", {task_id: retry_at.timestamp()})

    async def clear_task_wake(self, task_id: str) -> None:
        await self.client.zrem("forge:wakes", task_id)

    async def due_tasks(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC)
        values = await self.client.zrangebyscore("forge:wakes", min="-inf", max=now.timestamp())
        return [value.decode() if isinstance(value, bytes) else str(value) for value in values]

    async def next_wake(self) -> datetime | None:
        values = await self.client.zrange("forge:wakes", 0, 0, withscores=True)
        if not values:
            return None
        _, score = values[0]
        return datetime.fromtimestamp(float(score), tz=UTC)

    async def acquire_lease(self, resource: str, owner: str, ttl_seconds: int = 60) -> bool:
        return bool(await self.client.set(f"forge:lease:{resource}", owner, ex=ttl_seconds, nx=True))

    async def release_lease(self, resource: str, owner: str) -> bool:
        result = await self.client.eval(_RELEASE_IF_OWNER, 1, f"forge:lease:{resource}", owner)
        return bool(result)
