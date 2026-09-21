from __future__ import annotations

import asyncio
import os
import signal
import socket
from uuid import uuid4

from sqlalchemy import text

from .db import SessionLocal
from .live_intelligence import run_live_intelligence_cycle
from .runtime_bus import runtime_bus


_LEADER_KEY = "world-engine:live-worker-leader"


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


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0.1, seconds))
    except asyncio.TimeoutError:
        pass


async def run_leader_worker(
    stop_event: asyncio.Event,
    *,
    interval_seconds: int | None = None,
    lease_seconds: int | None = None,
    standby_poll_seconds: int | None = None,
) -> None:
    interval = max(
        60,
        int(
            interval_seconds
            or os.getenv("LIVE_INTELLIGENCE_INTERVAL_SECONDS", "300")
        ),
    )
    lease = max(
        interval + 120,
        int(
            lease_seconds
            or os.getenv("LIVE_WORKER_LEASE_SECONDS", str(interval * 3))
        ),
    )
    standby_poll = max(
        5,
        min(
            interval,
            int(
                standby_poll_seconds
                or os.getenv("LIVE_WORKER_STANDBY_POLL_SECONDS", "30")
            ),
        ),
    )
    token = f"{socket.gethostname()}:{uuid4().hex}"
    leader = False

    try:
        while not stop_event.is_set():
            if runtime_bus.enabled:
                if leader:
                    leader = await runtime_bus.renew_lock(
                        _LEADER_KEY,
                        token,
                        lease,
                    )
                if not leader:
                    leader = await runtime_bus.acquire_lock(
                        _LEADER_KEY,
                        token,
                        lease,
                    )
            else:
                leader = True

            if not leader:
                await _sleep_or_stop(stop_event, standby_poll)
                continue

            try:
                await run_live_intelligence_cycle(
                    broadcast=runtime_bus.publish,
                )
            except Exception:
                # The cycle records its error in shared live-state. A transient
                # source failure should not cause the leader to abandon its lease.
                pass

            if runtime_bus.enabled:
                leader = await runtime_bus.renew_lock(
                    _LEADER_KEY,
                    token,
                    lease,
                )

            if leader:
                await _sleep_or_stop(stop_event, interval)
            else:
                await _sleep_or_stop(stop_event, standby_poll)
    finally:
        if runtime_bus.enabled and leader:
            try:
                await runtime_bus.release_lock(_LEADER_KEY, token)
            except Exception:
                pass


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
        await run_leader_worker(stop_event)
    await runtime_bus.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
