from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .action_executor import execute_actions
from .cascade_engine import CascadeEngine, Effect
from .decision_engine import decide_all
from .engines import conflict, economic, energy, social
from .event_bus import event_bus
from .event_engine import normalize
from .forecasting_engine import forecast
from .integration_state import load_world_state, persist_tick, sync_world_state_to_db
from .models import ActorPerceptionModel, EffectModel, ForecastModel, SimulationRunModel
from .perception_engine import PerceptionEngine
from .reaction_engine import plan_reactions
from .realtime_pipeline import save_world_version
from .simulation_tick import SimulationTickEngine, TickContext


_ACTION_EFFECT_FIELDS = {
    "information_quality_delta": "information_quality",
    "economic_capacity_delta": "economic_capacity",
    "stability_delta": "stability",
    "security_capacity_delta": "security_capacity",
    "domestic_pressure_delta": "domestic_pressure",
    "diplomatic_capacity_delta": "diplomatic_capacity",
}


def _action_effects_to_initial_effects(actions: list[dict]) -> list[Effect]:
    initial: list[Effect] = []
    for action in actions:
        actor_id = action.get("actor_id")
        if not actor_id or action.get("status") != "executed":
            continue
        action_effects = action.get("effects", {})
        for key, field in _ACTION_EFFECT_FIELDS.items():
            delta = action_effects.get(key)
            if isinstance(delta, (int, float)) and delta:
                initial.append(Effect(source=str(actor_id), target=str(actor_id), field=field, delta=float(delta), mechanism="action"))
        diplomatic_delta = action_effects.get("diplomatic_delta")
        target_actor_id = action_effects.get("target_actor_id")
        if isinstance(diplomatic_delta, (int, float)) and diplomatic_delta and target_actor_id:
            initial.append(Effect(source=str(actor_id), target=str(target_actor_id), field="diplomatic", delta=float(diplomatic_delta), mechanism="diplomatic_action"))
    return initial


async def run_simulation(session, ticks=5, seed=0, simulation_id=None, raw_events=None, broadcast=None):
    ticks = max(1, min(120, int(ticks)))
    simulation_id = simulation_id or f"sim-{uuid4().hex}"
    run = SimulationRunModel(id=simulation_id, mode="simulation", status="running", query="local")
    session.add(run)
    await session.flush()
    state = await load_world_state(session, simulation_id, 0, seed)
    normalized = normalize(raw_events or [])
    event_ids = [event.event_id for event in normalized]
    from .event_store import persist_events
    await persist_events(session, normalized)
    history = []
    parent_hash = None
    for tick in range(1, ticks + 1):
        state.tick = tick
        changes: dict = {}
        phase_data: dict = {}
        context = TickContext(simulation_id, tick, seed + tick)
        async def publish(phase: str, result):
            await event_bus.publish(f"simulation.{phase}", {"simulation_id": simulation_id, "tick": tick, "phase": phase, "result": result})
        async def ingest(ctx):
            result = {"events": len(normalized), "event_ids": event_ids}
            await publish("ingest", result)
            return result
        async def state_update(ctx):
            result = {"tick": state.tick, "actors": len(state.actors)}
            await publish("state_update", result)
            return result
        async def perception(ctx):
            pe = PerceptionEngine()
            count = 0
            for actor_id, actor in state.actors.items():
                facts = [{"fact_id": event.event_id, "value": event.description, "confidence": event.confidence, "source_ids": [source.get("source_id", "unknown") for source in (event.metadata or {}).get("sources", [])]} for event in normalized]
                perception_result = pe.build(actor_id, facts, actor.values.get("information_quality", 0.7))
                session.add(ActorPerceptionModel(simulation_id=simulation_id, tick=tick, actor_id=actor_id, facts_json={key: value.__dict__ for key, value in perception_result.facts.items()}))
                count += 1
            result = {"actors": count}
            await publish("perception", result)
            return result
        async def decision(ctx):
            decisions = await decide_all(session, simulation_id)
            result = {"count": len(decisions), "decisions": decisions}
            await publish("decision", result)
            return result
        async def interaction(ctx):
            result = {"status": "no_interaction_handler"}
            await publish("interaction", result)
            return result
        async def action(ctx):
            decisions = ctx.phase_results["decision"].get("decisions", [])
            actions = await execute_actions(session, [item["action_id"] for item in decisions])
            result = {"actions": actions, "count": len(actions)}
            await publish("action", result)
            return result
        async def cascade(ctx):
            adjacency = {}
            for key in state.metadata.get("relationships", {}):
                source, target = key.split(":", 1)
                adjacency.setdefault(source, []).append(target)
            action_results = ctx.phase_results.get("action", {}).get("actions", [])
            reactions, shocks = await plan_reactions(session, action_results, simulation_id, seed + tick)
            if reactions:
                reaction_actions = await execute_actions(session, [item["action_id"] for item in reactions])
                action_results = action_results + reaction_actions
                ctx.phase_results["action"]["actions"] = action_results
                ctx.phase_results["action"]["count"] = len(action_results)
            initial_effects = _action_effects_to_initial_effects(action_results)
            initial_effects.extend(Effect(**shock) for shock in shocks)
            cascaded, truncated = CascadeEngine().run(initial_effects, adjacency)
            for effect in cascaded:
                if effect.field == "diplomatic":
                    state.apply_relationship_delta(effect.source, effect.target, effect.field, effect.delta)
                else:
                    state.apply_delta(effect.target, effect.field, effect.delta)
                    changes.setdefault(effect.target, {})[effect.field] = changes.setdefault(effect.target, {}).get(effect.field, 0) + effect.delta
                session.add(EffectModel(simulation_id=simulation_id, tick=tick, source=effect.source, target=effect.target, field=effect.field, delta=effect.delta, confidence=effect.confidence, depth=effect.depth, mechanism=effect.mechanism))
            result = {"count": len(cascaded), "initial_count": len(initial_effects), "reactions": len(reactions), "unexpected_shocks": len(shocks), "truncated": truncated}
            await publish("cascade", result)
            return result
        async def forecast_phase(ctx):
            for actor_id, actor in state.actors.items():
                prediction = forecast(f"{actor_id}:stability", actor.values, {"economic": changes.get(actor_id, {}).get("economic_capacity", 0), "social": changes.get(actor_id, {}).get("domestic_pressure", 0) * -0.5}, 5, seed + tick)
                probabilities = prediction["probabilities"]
                expected = probabilities["low"] * 0.25 + probabilities["medium"] * 0.50 + probabilities["high"] * 0.75
                uncertainty = prediction["uncertainty"]
                session.add(ForecastModel(simulation_id=simulation_id, tick=tick, target=prediction["target"], horizon=prediction["horizon"], expected=expected, lower=max(0.0, expected - uncertainty), upper=min(1.0, expected + uncertainty), confidence=max(0.0, 1.0 - uncertainty), drivers={"drivers": prediction["drivers"], "probabilities": probabilities}))
            result = {"actors": len(state.actors)}
            await publish("forecast", result)
            return result
        async def snapshot(ctx):
            await sync_world_state_to_db(session, state)
            await persist_tick(session, simulation_id, state, changes, event_ids, ctx.phase_results)
            snapshot_data = state.snapshot()
            previous_hash = parent_hash
            snapshot_hash = await save_world_version(session, simulation_id, tick, snapshot_data, parent_hash=previous_hash, dataset_version="live")
            ctx.payload["snapshot_hash"] = snapshot_hash
            result = {"state_hash": snapshot_hash, "parent_hash": previous_hash}
            await publish("snapshot", result)
            return result
        engine = SimulationTickEngine({"ingest": ingest, "state_update": state_update, "perception": perception, "decision": decision, "interaction": interaction, "action": action, "cascade": cascade, "forecast": forecast_phase, "snapshot": snapshot})
        completed = await engine.run(context)
        phase_data = completed.phase_results
        parent_hash = phase_data["snapshot"]["state_hash"]
        snapshot_data = state.snapshot()
        history.append(snapshot_data)
        if broadcast:
            await broadcast({"type": "tick_completed", "simulation_id": simulation_id, "tick": tick, "state": snapshot_data, "phase": phase_data, "changes": changes})
        await event_bus.publish("simulation.tick_completed", {"simulation_id": simulation_id, "tick": tick, "state": snapshot_data, "phases": phase_data})
    run.status = "completed"
    run.ticks = ticks
    run.events_ingested = len(raw_events or [])
    run.events_new = len(normalized)
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return {"simulation_id": simulation_id, "ticks": ticks, "history": history}
