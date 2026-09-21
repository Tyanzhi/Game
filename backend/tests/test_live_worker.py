import asyncio

import pytest

import app.live_worker as live_worker


@pytest.mark.asyncio
async def test_one_shot_worker_runs_exactly_one_cycle_without_runtime_bus(monkeypatch):
    calls = []

    async def fake_cycle(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(live_worker, "run_live_intelligence_cycle", fake_cycle)
    monkeypatch.setattr(live_worker.runtime_bus, "_redis", None)

    await live_worker.run_one_shot_worker(asyncio.Event())

    assert len(calls) == 1
    assert calls[0]["broadcast"] == live_worker.runtime_bus.publish


@pytest.mark.asyncio
async def test_one_shot_worker_honors_stop_event(monkeypatch):
    calls = []

    async def fake_cycle(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(live_worker, "run_live_intelligence_cycle", fake_cycle)
    monkeypatch.setattr(live_worker.runtime_bus, "_redis", None)

    stop = asyncio.Event()
    stop.set()
    await live_worker.run_one_shot_worker(stop)

    assert calls == []
