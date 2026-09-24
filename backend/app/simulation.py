from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import asdict
from .explainability import build_explanation

from sqlalchemy import select

from .action_executor import execute_actions
from .cascade_engine import CascadeEngine, Effect
from .crisis_graph import CrisisGraph
from .decision_engine import decide_all
from .engines import conflict, economic, energy, social
from .event_bus import event_bus
from .event_engine import normalize
from .event_propagation import EventPropagation
from .forecasting_engine import forecast
from .integration_state import load_world_state, persist_tick, sync_world_state_to_db
from .models import ActorPerceptionModel, EffectModel, ForecastModel, SimulationRunModel, SimulationTickModel, WorldStateVersionModel
from .perception_engine import PerceptionEngine
from .reaction_engine import plan_reactions
from .realtime_pipeline import save_world_version
from .simulation_tick import SimulationTickEngine, TickContext
from .state_compaction import compact_world_metadata
from .strategic_memory import decay_memory, update_memory_from_action
from .strategic_dynamics import (
    build_coalitions,
    build_multilateral_coalitions,
    nash_bargain,
    pop_due_effects,
    schedule_delayed_effects,
    signal_profile,
    update_belief_from_action,
    update_forecast_calibration,
)
from .strategic_planning import update_strategy_learning
from .strategic_foresight import assess_multilateral_reliability, brinkmanship_state


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
                initial.append(Effect(source=str(actor_id), target=str(actor_id), field=field, delta=float(delta), mechanism="action", action_id=action.get("action_id")))
        diplomatic_delta = action_effects.get("diplomatic_delta")
        target_actor_id = action_effects.get("target_actor_id")
        if isinstance(diplomatic_delta, (int, float)) and diplomatic_delta and target_actor_id:
            initial.append(Effect(source=str(actor_id), target=str(target_actor_id), field="diplomatic", delta=float(diplomatic_delta), mechanism="diplomatic_action", action_id=action.get("action_id")))
    return initial


async def run_simulation(
    session,
    ticks=5,
    seed=0,
    simulation_id=None,
    raw_events=None,
    broadcast=None,
    controlled_actor_id: str | None = None,
    mode: str = "simulation",
    initial_state=None,
    player_actions=None,
    parent_simulation_id=None,
    disable_ai=False,
):
    ticks = max(1, min(120, int(ticks)))
    simulation_id = simulation_id or f"sim-{uuid4().hex}"

    run = await session.get(SimulationRunModel, simulation_id)
    if run is None:
        run = SimulationRunModel(
            id=simulation_id,
            mode=mode,
            status="running",
            query="local",
        )
        session.add(run)
        await session.flush()
    else:
        run.status = "running"
        run.mode = mode
        run.finished_at = None

    state = initial_state if initial_state is not None else await load_world_state(session, simulation_id, 0, seed)
    start_tick = int(state.tick)

    latest_version = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    normalized = normalize(raw_events or [])
    event_ids = [event.event_id for event in normalized]
    from .event_store import persist_events
    new_events, duplicate_events = await persist_events(session, normalized)
    history = []
    parent_hash = latest_version.state_hash if latest_version is not None else None
    previous_tick = (await session.execute(select(SimulationTickModel)
        .where(SimulationTickModel.simulation_id == (parent_simulation_id or simulation_id))
        .order_by(SimulationTickModel.tick.desc()).limit(1))).scalar_one_or_none()
    previous_report = (previous_tick.phase_log or {}).get("explanation") if previous_tick else None
    if initial_state is not None and parent_simulation_id:
        from .realtime_pipeline import state_hash
        parent_hash = state_hash(state.snapshot())

    for step in range(1, ticks + 1):
        state_before_tick = state.snapshot()
        explanation_effects = []
        explanation_forecasts = []
        explanation_events = list(normalized)
        explanation_decisions = []
        tick = start_tick + step
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
            decay_memory(state.metadata)
            due_effects = pop_due_effects(state.metadata, tick)
            for effect in due_effects:
                target = str(effect["target"])
                field = str(effect["field"])
                delta = float(effect["delta"])
                state.apply_delta(target, field, delta)
                changes.setdefault(target, {})[field] = changes.setdefault(target, {}).get(field, 0.0) + delta
                explanation_effects.append(asdict(Effect(source=str(effect.get("source", target)),
                    target=target, field=field, delta=delta, mechanism="delayed_effect",
                    action_id=effect.get("source_action_id"))))

            result = {
                "tick": state.tick,
                "actors": len(state.actors),
                "strategic_memory_edges": len(state.metadata.get("strategic_memory", {})),
                "belief_edges": len(state.metadata.get("beliefs", {})),
                "delayed_effects_applied": len(due_effects),
                "delayed_effects_pending": len(state.metadata.get("delayed_effects", [])),
            }
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
            decisions = [] if disable_ai else await decide_all(
                session,
                simulation_id,
                state.metadata,
                tick,
                excluded_actor_ids={controlled_actor_id} if controlled_actor_id else None,
            )
            result = {"count": len(decisions), "decisions": decisions}
            await publish("decision", result)
            return result
        async def interaction(ctx):
            decisions = ctx.phase_results.get("decision", {}).get("decisions", [])
            actor_values = {actor_id: actor.values for actor_id, actor in state.actors.items()}
            coalitions = build_coalitions(
                actor_values,
                state.metadata.get("relationships", {}),
                state.metadata.get("crisis_graph", {}),
            )
            multilateral_coalitions = build_multilateral_coalitions(
                actor_values,
                state.metadata.get("relationships", {}),
                state.metadata.get("crisis_graph", {}),
            )

            bargains = []
            diplomatic = [
                item for item in decisions
                if item.get("action") == "diplomatic_outreach"
                and item.get("target_actor_id")
            ]
            by_actor = {item["actor_id"]: item for item in diplomatic}
            seen_pairs = set()
            for item in diplomatic:
                actor_a = item["actor_id"]
                actor_b = item["target_actor_id"]
                pair = tuple(sorted((actor_a, actor_b)))
                if pair in seen_pairs or actor_b not in by_actor:
                    continue
                seen_pairs.add(pair)
                other = by_actor[actor_b]
                bargain = nash_bargain(
                    actor_a,
                    actor_b,
                    float(item.get("expected_utility", 0.0)),
                    float(other.get("expected_utility", 0.0)),
                    float(item.get("risk", 0.0)),
                    float(other.get("risk", 0.0)),
                )
                bargains.append(bargain.__dict__)
                if bargain.accepted:
                    state.apply_relationship_delta(actor_a, actor_b, "diplomatic", 0.01)
                    state.apply_relationship_delta(actor_b, actor_a, "diplomatic", 0.01)
                    for source, target, decision_row in ((actor_a, actor_b, item), (actor_b, actor_a, other)):
                        explanation_effects.append(asdict(Effect(source=source, target=target,
                            field="diplomatic", delta=0.01, mechanism="accepted_bargain",
                            action_id=decision_row["action_id"])))

            reliable_multilateral = [
                assess_multilateral_reliability(
                    coalition,
                    state.metadata.get("relationships", {}),
                    state.metadata.get("strategic_memory", {}),
                    state.metadata.get("crisis_graph", {}),
                )
                for coalition in multilateral_coalitions
            ]

            brinkmanship = []
            seen_brinkmanship_pairs = set()
            for item in decisions:
                actor_a = str(item.get("actor_id") or "")
                actor_b = str(item.get("target_actor_id") or "")
                if not actor_a or not actor_b or actor_a == actor_b:
                    continue
                pair = tuple(sorted((actor_a, actor_b)))
                if pair in seen_brinkmanship_pairs:
                    continue
                seen_brinkmanship_pairs.add(pair)
                state_a = state.actors.get(actor_a)
                state_b = state.actors.get(actor_b)
                if state_a is None or state_b is None:
                    continue
                belief_a = state.metadata.get("beliefs", {}).get(f"{actor_a}:{actor_b}", {})
                belief_b = state.metadata.get("beliefs", {}).get(f"{actor_b}:{actor_a}", {})
                assessment = brinkmanship_state(
                    state_a.values,
                    state_b.values,
                    belief_a,
                    belief_b,
                )
                brinkmanship.append({
                    "actors": [actor_a, actor_b],
                    **assessment,
                })

            state.metadata["coalitions"] = coalitions
            state.metadata["multilateral_coalitions"] = reliable_multilateral
            state.metadata["bargaining"] = bargains
            state.metadata["brinkmanship"] = brinkmanship
            result = {
                "coalitions": coalitions,
                "coalition_count": len(coalitions),
                "multilateral_coalitions": reliable_multilateral,
                "multilateral_coalition_count": len(reliable_multilateral),
                "bargains": bargains,
                "accepted_bargains": sum(1 for item in bargains if item["accepted"]),
                "brinkmanship": brinkmanship,
                "high_brinkmanship_pairs": sum(
                    1 for item in brinkmanship
                    if item["equilibrium_hint"] == "high_brinkmanship"
                ),
            }
            await publish("interaction", result)
            return result
        async def action(ctx):
            decisions = ctx.phase_results["decision"].get("decisions", [])
            primary_actions = await execute_actions(session, [item["action_id"] for item in decisions])
            if step == 1:
                primary_actions = list(player_actions or []) + primary_actions
                for player in player_actions or []:
                    explanation_decisions.append({"decision_id": player.get("decision_id"),
                        "actor_id": player["actor_id"], "action_id": player["action_id"],
                        "action": player.get("effects", {}).get("action"), "control_source": "player",
                        "reasoning_factors": ["player_selected"], "options": []})

            reactions, shocks = await plan_reactions(
                session,
                primary_actions,
                simulation_id,
                seed + tick,
            )
            reaction_actions = []
            explanation_decisions.extend(reactions)
            if reactions:
                reaction_actions = await execute_actions(
                    session,
                    [item["action_id"] for item in reactions],
                )

            actions = primary_actions + reaction_actions

            scheduled_delayed = 0
            signals = []
            for executed in actions:
                if executed.get("status") != "executed":
                    continue
                effects = executed.get("effects") or {}
                source_actor_id = executed.get("actor_id")
                target_actor_id = effects.get("target_actor_id")
                action_type = effects.get("action")
                if not source_actor_id or not action_type:
                    continue

                source_state = state.actors.get(str(source_actor_id))
                if source_state is not None:
                    signal = signal_profile(
                        str(source_actor_id),
                        str(action_type),
                        float(source_state.values.get("risk_tolerance", 0.5)),
                        float(source_state.values.get("information_quality", 0.7)),
                        seed,
                        tick,
                    )
                    signals.append({
                        "actor_id": source_actor_id,
                        "target_actor_id": target_actor_id,
                        "action": action_type,
                        **signal,
                    })
                else:
                    signal = {"credibility": 0.5}

                scheduled_delayed += len(schedule_delayed_effects(
                    state.metadata,
                    str(source_actor_id),
                    str(action_type),
                    tick,
                    str(executed.get("action_id") or ""),
                ))

                if target_actor_id:
                    update_memory_from_action(
                        state.metadata,
                        observer=str(target_actor_id),
                        counterpart=str(source_actor_id),
                        action_type=str(action_type),
                        magnitude=float(effects.get("reaction_score", 1.0) or 1.0),
                    )
                    target_state = state.actors.get(str(target_actor_id))
                    if target_state is not None:
                        update_belief_from_action(
                            state.metadata,
                            observer=str(target_actor_id),
                            counterpart=str(source_actor_id),
                            action_type=str(action_type),
                            information_quality=float(target_state.values.get("information_quality", 0.7)),
                            credibility=float(signal.get("credibility", 0.5)),
                            tick=tick,
                        )

            result = {
                "actions": actions,
                "count": len(actions),
                "primary_actions": len(primary_actions),
                "reaction_actions": len(reaction_actions),
                "planned_shocks": shocks,
                "signals": signals,
                "delayed_effects_scheduled": scheduled_delayed,
            }
            await publish("action", result)
            return result
        async def cascade(ctx):
            adjacency = {}
            for key in state.metadata.get("relationships", {}):
                source, target = key.split(":", 1)
                adjacency.setdefault(source, []).append(target)
            action_results = ctx.phase_results.get("action", {}).get("actions", [])
            propagation = EventPropagation()
            actor_values = {actor_id: actor.values for actor_id, actor in state.actors.items()}
            crisis_graph = CrisisGraph()
            secondary_events = crisis_graph.advance(
                state.metadata,
                normalized,
                actor_values,
                state.metadata.get("relationships", {}),
                tick,
                seed,
            )
            all_events = list(normalized) + secondary_events
            explanation_events.extend(secondary_events)
            propagated_events = propagation.propagate(
                all_events,
                actor_values,
                state.metadata.get("relationships", {}),
                seed + tick,
            )
            shocks = ctx.phase_results.get("action", {}).get("planned_shocks", [])
            initial_effects = _action_effects_to_initial_effects(action_results)
            initial_effects.extend(
                Effect(
                    source=effect.source,
                    target=effect.target,
                    field=effect.field,
                    delta=effect.delta,
                    confidence=effect.confidence,
                    depth=effect.depth,
                    mechanism=effect.mechanism,
                    event_id=effect.event_id, effect_id=effect.effect_id,
                    parent_effect_id=effect.parent_effect_id,
                )
                for effect in propagated_events
            )
            initial_effects.extend(
                Effect(
                    source=str(shock["source"]),
                    target=str(shock["target"]),
                    field=str(shock["field"]),
                    delta=float(shock["delta"]),
                    confidence=float(shock.get("confidence", 1.0)),
                    depth=int(shock.get("depth", 0)),
                    mechanism=str(shock.get("mechanism", "unexpected_shock")),
                    event_id=f"shock:{simulation_id}:{tick}",
                )
                for shock in shocks
            )
            cascaded, truncated = CascadeEngine().run(initial_effects, adjacency)
            explanation_effects.extend(asdict(effect) for effect in cascaded)
            for effect in cascaded:
                if effect.field == "diplomatic" or effect.field == "trade":
                    state.apply_relationship_delta(effect.source, effect.target, effect.field, effect.delta)
                elif effect.target == "market:global" and effect.field.startswith("market:"):
                    market_field = effect.field.split(":", 1)[1]
                    markets = state.metadata.setdefault("markets", {})
                    markets[market_field] = float(markets.get(market_field, 0.0)) + effect.delta
                    changes.setdefault("markets", {})[market_field] = markets[market_field]
                else:
                    state.apply_delta(effect.target, effect.field, effect.delta)
                    changes.setdefault(effect.target, {})[effect.field] = changes.setdefault(effect.target, {}).get(effect.field, 0) + effect.delta
                session.add(EffectModel(simulation_id=simulation_id, tick=tick, source=effect.source, target=effect.target, field=effect.field, delta=effect.delta, confidence=effect.confidence, depth=effect.depth, mechanism=effect.mechanism))

            learning_updates = 0
            for executed in action_results:
                if executed.get("status") != "executed":
                    continue
                actor_id = str(executed.get("actor_id") or "")
                effects = executed.get("effects") or {}
                action_type = str(effects.get("action") or "")
                if not actor_id or not action_type:
                    continue

                actor_changes = changes.get(actor_id, {})
                realized = float(effects.get("expected_utility", 0.5))
                realized += float(actor_changes.get("stability", 0.0)) * 0.35
                realized += float(actor_changes.get("economic_capacity", 0.0)) * 0.25
                realized += float(actor_changes.get("security_capacity", 0.0)) * 0.20
                realized += float(actor_changes.get("diplomatic_capacity", 0.0)) * 0.15
                realized -= max(0.0, float(actor_changes.get("domestic_pressure", 0.0))) * 0.20
                update_strategy_learning(
                    state.metadata,
                    actor_id,
                    action_type,
                    max(0.0, min(1.0, realized)),
                )
                learning_updates += 1

            result = {"count": len(cascaded), "initial_count": len(initial_effects), "event_propagation": len(propagated_events), "secondary_crises": len(secondary_events), "crisis_nodes": len(state.metadata.get("crisis_graph", {}).get("nodes", {})), "reactions": ctx.phase_results.get("action", {}).get("reaction_actions", 0), "unexpected_shocks": len(shocks), "strategy_learning_updates": learning_updates, "truncated": truncated}
            await publish("cascade", result)
            return result
        async def forecast_phase(ctx):
            markets = state.metadata.get("markets", {})
            crisis_nodes = state.metadata.get("crisis_graph", {}).get("nodes", {})

            calibration_updates = 0
            pending = state.metadata.setdefault("pending_forecasts", [])
            remaining_pending = []
            for pending_forecast in pending:
                if int(pending_forecast.get("due_tick", 0)) <= tick:
                    target = str(pending_forecast["target"])
                    actor_id, field = target.split(":", 1)
                    actor_state = state.actors.get(actor_id)
                    if actor_state is not None:
                        observed_value = float(actor_state.values.get(field, 0.5))
                        update_forecast_calibration(
                            state.metadata,
                            target,
                            float(pending_forecast.get("high_probability", 0.5)),
                            observed_high=observed_value >= 0.66,
                        )
                        calibration_updates += 1
                else:
                    remaining_pending.append(pending_forecast)
            state.metadata["pending_forecasts"] = remaining_pending
            for actor_id, actor in state.actors.items():
                actor_crisis = max(
                    (
                        float(node.get("intensity", 0.0))
                        for node in crisis_nodes.values()
                        if actor_id in set(node.get("participants", []))
                        and node.get("phase") != "resolved"
                    ),
                    default=0.0,
                )
                drivers = {
                    "economic": changes.get(actor_id, {}).get("economic_capacity", 0),
                    "social": changes.get(actor_id, {}).get("domestic_pressure", 0) * -0.5,
                    "crisis": -actor_crisis * 0.12,
                    "financial_stress": -float(markets.get("financial_stress", 0.0)) * 0.08,
                    "global_trade": float(markets.get("global_trade", 0.0)) * 0.05,
                }
                prediction = forecast(
                    f"{actor_id}:stability",
                    actor.values,
                    drivers,
                    5,
                    seed + tick,
                    base_rate=actor.values.get("stability", 0.5),
                )
                probabilities = prediction["probabilities"]
                sensitivity = []
                for name, value in drivers.items():
                    alternative = forecast(f"{actor_id}:stability", actor.values,
                        {**drivers, name: 0.0}, 5, seed + tick, base_rate=actor.values.get("stability", 0.5))
                    sensitivity.append({"factor": name, "value": value,
                        "high_probability_without_factor": alternative["probabilities"]["high"],
                        "high_probability_delta": alternative["probabilities"]["high"] - probabilities["high"]})
                explanation_forecasts.append({**prediction, "driver_values": dict(drivers),
                    "sensitivity": sensitivity, "inputs": dict(actor.values), "seed": seed + tick,
                    "confidence": max(0.0, 1.0 - prediction["uncertainty"]),
                    "model_version": "forecast-v2"})
                expected = probabilities["low"] * 0.25 + probabilities["medium"] * 0.50 + probabilities["high"] * 0.75
                uncertainty = prediction["uncertainty"]
                session.add(ForecastModel(
                    simulation_id=simulation_id,
                    tick=tick,
                    target=prediction["target"],
                    horizon=prediction["horizon"],
                    expected=expected,
                    lower=max(0.0, expected - uncertainty),
                    upper=min(1.0, expected + uncertainty),
                    confidence=max(0.0, 1.0 - uncertainty),
                    drivers={
                        "drivers": prediction["drivers"],
                        "probabilities": probabilities,
                        "ensemble": prediction["ensemble"],
                        "calibration": prediction["calibration"],
                    },
                ))
                state.metadata.setdefault("pending_forecasts", []).append({
                    "target": prediction["target"],
                    "origin_tick": tick,
                    "due_tick": tick + int(prediction["horizon"]),
                    "high_probability": probabilities["high"],
                })
            result = {
                "actors": len(state.actors),
                "model_version": "forecast-v2",
                "calibration_updates": calibration_updates,
                "calibrated_targets": len(state.metadata.get("forecast_calibration", {})),
            }
            await publish("forecast", result)
            return result
        async def snapshot(ctx):
            await sync_world_state_to_db(session, state)
            compaction = compact_world_metadata(state.metadata, current_tick=tick)
            snapshot_data = state.snapshot()
            explanation = build_explanation(
                simulation_id=simulation_id, tick=tick, seed=seed + tick,
                before=state_before_tick, after=snapshot_data, events=explanation_events,
                decisions=ctx.phase_results.get("decision", {}).get("decisions", []) + explanation_decisions,
                actions=ctx.phase_results.get("action", {}).get("actions", []),
                effects=explanation_effects, forecasts=explanation_forecasts,
                parent_hash=parent_hash,
                previous_report=previous_report, phase_results=ctx.phase_results,
            )
            await persist_tick(
                session, simulation_id, state, changes, event_ids,
                {**ctx.phase_results, "explanation": explanation}, seed=seed + tick,
            )
            previous_hash = parent_hash
            snapshot_hash = await save_world_version(
                session,
                simulation_id,
                tick,
                snapshot_data,
                parent_hash=previous_hash,
                dataset_version="live",
            )
            ctx.payload["snapshot_hash"] = snapshot_hash
            ctx.payload["explanation"] = explanation
            result = {
                "state_hash": snapshot_hash,
                "parent_hash": previous_hash,
                "compaction": compaction,
            }
            await publish("snapshot", result)
            return result
        engine = SimulationTickEngine({"ingest": ingest, "state_update": state_update, "perception": perception, "decision": decision, "interaction": interaction, "action": action, "cascade": cascade, "forecast": forecast_phase, "snapshot": snapshot})
        completed = await engine.run(context)
        phase_data = completed.phase_results
        previous_report = completed.payload["explanation"]
        parent_hash = phase_data["snapshot"]["state_hash"]
        snapshot_data = state.snapshot()
        history.append(snapshot_data)
        tick_summary = {
            "type": "tick_completed",
            "simulation_id": simulation_id,
            "tick": tick,
            "state_hash": parent_hash,
            "changes": changes,
            "summary": {
                "actors": len(state.actors),
                "crisis_nodes": len(
                    state.metadata.get("crisis_graph", {}).get("nodes", {})
                ),
                "pending_forecasts": len(
                    state.metadata.get("pending_forecasts", [])
                ),
                "delayed_effects": len(
                    state.metadata.get("delayed_effects", [])
                ),
            },
        }
        if broadcast:
            await broadcast(tick_summary)
        await event_bus.publish("simulation.tick_completed", tick_summary)
    run.status = "completed"
    run.ticks = start_tick + ticks
    run.events_ingested = int(run.events_ingested or 0) + len(raw_events or [])
    run.events_new = int(run.events_new or 0) + int(new_events)
    run.events_deduplicated = int(run.events_deduplicated or 0) + int(duplicate_events)
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return {"simulation_id": simulation_id, "ticks": ticks, "history": history}
