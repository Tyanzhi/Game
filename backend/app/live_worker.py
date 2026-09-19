from __future__ import annotations

import asyncio
import signal

from sqlalchemy import text

from .db import SessionLocal
from .live_intelligence import live_intelligence_loop
from .runtime_bus import runtime_bus


async def wait_for_dependencies(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            if await runtime_bus.ping():
                return
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3)
        except asyncio.TimeoutError:
            continue


async def run_worker() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop() -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop)
        except NotImplementedError:
            pass

    await wait_for_dependencies(stop_event)
    if not stop_event.is_set():
        await live_intelligence_loop(
            broadcast=runtime_bus.publish,
            stop_event=stop_event,
        )
    await runtime_bus.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
