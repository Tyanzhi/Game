from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

Subscriber = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process event bus; can later be replaced by Redis/NATS without changing callers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, topic: str, subscriber: Subscriber) -> None:
        if subscriber not in self._subscribers[topic]:
            self._subscribers[topic].append(subscriber)

    def unsubscribe(self, topic: str, subscriber: Subscriber) -> None:
        if subscriber in self._subscribers[topic]:
            self._subscribers[topic].remove(subscriber)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        subscribers = tuple(self._subscribers.get(topic, ()))
        if subscribers:
            await asyncio.gather(*(subscriber(payload) for subscriber in subscribers))


event_bus = EventBus()
