import asyncio

import pytest

import app.live_worker as live_worker
from app.runtime_bus import RuntimeBus


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiry = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        self.expiry[key] = ex
        return True

    async def eval(self, script, _numkeys, key, token, *args):
        if self.values.get(key) != token:
            return 0
        if "expire" in script:
            self.expiry[key] = int(args[0])
            return 1
        if "del" in script:
            self.values.pop(key, None)
            self.expiry.pop(key, None)
            return 1
        return 0

    async def ping(self):
        return True

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_runtime_bus_lock_requires_owner_token():
    bus = RuntimeBus(url="")
    bus._redis = FakeRedis()

    assert await bus.acquire_lock("leader", "worker-a", 90) is True
    assert await bus.acquire_lock("leader", "worker-b", 90) is False
    assert await bus.renew_lock("leader", "worker-b", 120) is False
    assert await bus.renew_lock("leader", "worker-a", 120) is True
    assert await bus.release_lock("leader", "worker-b") is False
    assert await bus.release_lock("leader", "worker-a") is True
    assert await bus.acquire_lock("leader", "worker-b", 90) is True


class FakeLeaderBus:
    enabled = True

    def __init__(self):
        self.acquired = 0
        self.renewed = 0
        self.released = 0

    async def acquire_lock(self, key, token, ttl):
        self.acquired += 1
        return True

    async def renew_lock(self, key, token, ttl):
        self.renewed += 1
        return True

    async def release_lock(self, key, token):
        self.released += 1
        return True

    async def publish(self, payload):
        return None


@pytest.mark.asyncio
async def test_live_worker_runs_cycle_only_as_leader(monkeypatch):
    fake_bus = FakeLeaderBus()
    stop_event = asyncio.Event()
    cycles = []

    async def fake_cycle(**kwargs):
        cycles.append(kwargs)
        stop_event.set()
        return {"ok": True}

    monkeypatch.setattr(live_worker, "runtime_bus", fake_bus)
    monkeypatch.setattr(live_worker, "run_live_intelligence_cycle", fake_cycle)

    await live_worker.run_leader_worker(
        stop_event,
        interval_seconds=60,
        lease_seconds=180,
        standby_poll_seconds=5,
    )

    assert len(cycles) == 1
    assert fake_bus.acquired == 1
    assert fake_bus.renewed >= 1
    assert fake_bus.released == 1
