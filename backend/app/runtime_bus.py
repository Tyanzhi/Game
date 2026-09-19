from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis


class RuntimeBus:
    def __init__(self, url: str | None = None, channel: str = "world-engine:runtime") -> None:
        self.url = url or os.getenv("REDIS_URL", "")
        self.channel = channel
        self._redis: Redis | None = Redis.from_url(self.url, decode_responses=True) if self.url else None

    @property
    def enabled(self) -> bool:
        return self._redis is not None

    async def ping(self) -> bool:
        if self._redis is None:
            return True
        return bool(await self._redis.ping())

    async def publish(self, payload: dict) -> None:
        if self._redis is None:
            return
        await self._redis.publish(self.channel, json.dumps(payload, separators=(",", ":")))

    async def set_json(self, key: str, payload: dict, ttl_seconds: int | None = None) -> None:
        if self._redis is None:
            return
        value = json.dumps(payload, separators=(",", ":"))
        if ttl_seconds:
            await self._redis.set(key, value, ex=ttl_seconds)
        else:
            await self._redis.set(key, value)

    async def get_json(self, key: str) -> dict | None:
        if self._redis is None:
            return None
        value = await self._redis.get(key)
        if not value:
            return None
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    async def subscribe(
        self,
        handler: Callable[[dict], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        if self._redis is None:
            await stop_event.wait()
            return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.channel)
        try:
            while not stop_event.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message.get("type") == "message":
                    try:
                        payload = json.loads(message["data"])
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict):
                        await handler(payload)
                await asyncio.sleep(0.02)
        finally:
            await pubsub.unsubscribe(self.channel)
            await pubsub.aclose()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


runtime_bus = RuntimeBus()
