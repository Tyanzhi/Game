from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class TickResult:
    simulation_id: str
    tick: int


class TickScheduler:
    """Controls simulation cadence independently from the HTTP layer."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._stops: dict[str, asyncio.Event] = {}

    async def run(self, simulation_id: str, tick_fn, interval_seconds: float = 1.0) -> None:
        if simulation_id in self._tasks:
            return
        stop = asyncio.Event()
        self._stops[simulation_id] = stop

        async def loop() -> None:
            tick = 0
            try:
                while not stop.is_set():
                    tick += 1
                    await tick_fn(simulation_id, tick)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
                    except asyncio.TimeoutError:
                        pass
            finally:
                self._stops.pop(simulation_id, None)
                self._tasks.pop(simulation_id, None)

        task = asyncio.create_task(loop())
        self._tasks[simulation_id] = task
        await asyncio.sleep(0)

    async def stop(self, simulation_id: str) -> None:
        stop = self._stops.get(simulation_id)
        if stop:
            stop.set()
        task = self._tasks.get(simulation_id)
        if task:
            await task

    def active(self) -> list[str]:
        return list(self._tasks)
