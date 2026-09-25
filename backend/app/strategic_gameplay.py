from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .action_executor import ALLOWED_ACTIONS, execute_action
from .geo_catalog import actor_geography
from .models import (
    ActionModel,
    ActorModel,
    DecisionModel,
    EffectModel,
    RelationshipModel,
    SimulationTickModel,
    WorldStateVersionModel,
)
from .strategic_foresight import build_scenario_tree


async def _latest_world_version(session: AsyncSession, simulation_id: str):
    return (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def actor_detail(session: AsyncSession, simulation_id: str, actor_id: str) -> dict:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise ValueError(f"Unknown actor: {actor_id}")

    version = await _latest_world_version(session, simulation_id)
    metadata = dict((version.state_json or {}).get("metadata", {})) if version else {}
    relationships = (
        await session.execute(
            select(RelationshipModel).where(
                (RelationshipModel.source_actor_id == actor_id)
                | (RelationshipModel.target_actor_id == actor_id)
            )
        )
    ).scalars().all()

    decisions = (
        await session.execute(
            select(DecisionModel)
            .where(
                DecisionModel.simulation_id == simulation_id,
                DecisionModel.actor_id == actor_id,
            )
            .order_by(DecisionModel.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    active_crises = []
    for crisis_id, node in metadata.get("crisis_graph", {}).get("nodes", {}).items():
        if actor_id not in set(node.get("participants", [])) or node.get("phase") == "resolved":
            continue
        active_crises.append({"id": crisis_id, **dict(node)})

    return {
        "simulation_id": simulation_id,
        "actor": {
            "id": actor.id,
            "name": actor.name,
            "actor_type": actor.actor_type,
            "stability": float(actor.stability),
            "economic_capacity": float(actor.economic_capacity),
            "diplomatic_capacity": float(actor.diplomatic_capacity),
            "security_capacity": float(actor.security_capacity),
            "domestic_pressure": float(actor.domestic_pressure),
            "risk_tolerance": float(actor.risk_tolerance),
            "strategic_patience": float(actor.strategic_patience),
            "escalation_threshold": float(actor.escalation_threshold),
            "information_quality": float(actor.information_quality),
            "energy_security": float(actor.energy_security),
            "trade_resilience": float(actor.trade_resilience),
            "technological_capacity": float(actor.technological_capacity),
            "geography": actor_geography(actor.id, actor.name),
        },
        "relationships": [{
            "source": row.source_actor_id,
            "target": row.target_actor_id,
            "diplomatic": float(row.diplomatic or 0.0),
            "economic": float(row.economic or 0.0),
            "military": float(row.military or 0.0),
            "trade": float(row.trade or 0.0),
            "energy": float(row.energy or 0.0),
        } for row in relationships],
        "active_crises": active_crises,
        "latest_decisions": [{
            "id": row.id,
            "selected_action": row.selected_action,
            "confidence": float(row.confidence or 0.0),
            "reasoning_factors": row.reasoning_factors or [],
            "information_state": row.information_state or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in decisions],
        "beliefs": {
            key: value
            for key, value in metadata.get("beliefs", {}).items()
            if key.startswith(actor_id + ":") or key.endswith(":" + actor_id)
        },
        "strategic_memory": {
            key: value
            for key, value in metadata.get("strategic_memory", {}).items()
            if key.startswith(actor_id + ":") or key.endswith(":" + actor_id)
        },
    }


async def crisis_detail(session: AsyncSession, simulation_id: str, crisis_id: str) -> dict:
    version = await _latest_world_version(session, simulation_id)
    if version is None:
        raise ValueError(f"No state for simulation: {simulation_id}")
    metadata = dict((version.state_json or {}).get("metadata", {}))
    graph = metadata.get("crisis_graph", {})
    node = graph.get("nodes", {}).get(crisis_id)
    if node is None:
        raise ValueError(f"Unknown crisis: {crisis_id}")

    participants = list(node.get("participants", []))
    actors = []
    for actor_id in participants:
        actor = await session.get(ActorModel, actor_id)
        if actor is not None:
            actors.append({
                "id": actor.id,
                "name": actor.name,
                "stability": float(actor.stability),
                "economic_capacity": float(actor.economic_capacity),
                "security_capacity": float(actor.security_capacity),
                "domestic_pressure": float(actor.domestic_pressure),
                "geography": actor_geography(actor.id, actor.name),
            })

    edges = [
        edge for edge in graph.get("edges", [])
        if edge.get("from") == crisis_id
        or edge.get("to") == crisis_id
        or edge.get("from") in participants
        or edge.get("to") in participants
    ]
    history = [
        row for row in graph.get("history", [])
        if row.get("crisis_id") == crisis_id
    ]

    return {
        "simulation_id": simulation_id,
        "crisis_id": crisis_id,
        "crisis": dict(node),
        "participants": actors,
        "edges": edges,
        "history": history,
    }


async def scenario_tree_detail(
    session: AsyncSession,
    simulation_id: str,
    actor_id: str,
    depth: int = 3,
    branching: int = 3,
) -> dict:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise ValueError(f"Unknown actor: {actor_id}")

    version = await _latest_world_version(session, simulation_id)
    metadata = dict((version.state_json or {}).get("metadata", {})) if version else {}
    markets = metadata.get("markets", {})
    active_crisis = max(
        (
            float(node.get("intensity", 0.0))
            for node in metadata.get("crisis_graph", {}).get("nodes", {}).values()
            if actor_id in set(node.get("participants", []))
            and node.get("phase") != "resolved"
        ),
        default=0.0,
    )
    market_stress = min(
        1.0,
        abs(float(markets.get("financial_stress", 0.0)))
        + abs(float(markets.get("energy_price", 0.0))) * 0.5,
    )
    seed = int(version.tick if version else 0)
    return build_scenario_tree(
        actor_id,
        stability=float(actor.stability),
        market_stress=market_stress,
        crisis_intensity=active_crisis,
        seed=seed,
        depth=depth,
        branching=branching,
    )


async def causal_chain(
    session: AsyncSession,
    simulation_id: str,
    limit: int = 120,
) -> dict:
    rows = (
        await session.execute(
            select(EffectModel)
            .where(EffectModel.simulation_id == simulation_id)
            .order_by(EffectModel.tick.desc(), EffectModel.id.desc())
            .limit(max(1, min(500, int(limit))))
        )
    ).scalars().all()

    ordered = list(reversed(rows))
    nodes: dict[str, dict] = {}
    edges = []
    for row in ordered:
        source_key = f"entity:{row.source}"
        target_key = f"entity:{row.target}"
        nodes.setdefault(source_key, {"id": source_key, "label": row.source, "kind": "entity"})
        nodes.setdefault(target_key, {"id": target_key, "label": row.target, "kind": "entity"})
        effect_key = f"effect:{row.id}"
        nodes[effect_key] = {
            "id": effect_key,
            "label": row.field,
            "kind": "effect",
            "tick": row.tick,
            "delta": float(row.delta),
            "confidence": float(row.confidence),
            "mechanism": row.mechanism,
        }
        edges.extend([
            {"source": source_key, "target": effect_key, "kind": "causes"},
            {"source": effect_key, "target": target_key, "kind": "changes"},
        ])

    return {
        "simulation_id": simulation_id,
        "nodes": list(nodes.values()),
        "edges": edges,
        "effect_count": len(ordered),
    }


async def submit_player_action(
    session: AsyncSession,
    simulation_id: str,
    actor_id: str,
    action_type: str,
    target_actor_id: str | None = None,
    rationale: str = "player_selected",
    explain: bool = True,
) -> dict:
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported action: {action_type}")
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise ValueError(f"Unknown actor: {actor_id}")
    if target_actor_id:
        target = await session.get(ActorModel, target_actor_id)
        if target is None:
            raise ValueError(f"Unknown target actor: {target_actor_id}")
        if target_actor_id == actor_id:
            raise ValueError("Target actor must differ from source actor")

    from .integration_state import load_world_state
    before_action = await load_world_state(session, simulation_id)
    if actor_id not in before_action.actors or (target_actor_id and target_actor_id not in before_action.actors):
        raise ValueError("Actor is absent from this simulation snapshot")

    latest_tick = (
        await session.execute(
            select(SimulationTickModel)
            .where(SimulationTickModel.simulation_id == simulation_id)
            .order_by(SimulationTickModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    tick = int(latest_tick.tick if latest_tick else 0)

    nonce = uuid4().hex
    fingerprint = f"{simulation_id}:{tick}:{actor_id}:{action_type}:{target_actor_id or '-'}:{nonce}"
    decision_id = "player-decision-" + sha256(fingerprint.encode()).hexdigest()[:24]
    action_id = "player-action-" + sha256((fingerprint + ":action").encode()).hexdigest()[:24]

    decision = DecisionModel(
        id=decision_id,
        actor_id=actor_id,
        simulation_id=simulation_id,
        situation=f"player_action_tick={tick}",
        selected_action=action_type,
        confidence=1.0,
        reasoning_factors=["player_selected", rationale[:250]],
        options=[{"action": action_type, "source": "player"}],
        information_state={
            "target_actor_id": target_actor_id,
            "control_source": "player",
        },
    )
    session.add(decision)
    await session.flush()

    action = ActionModel(
        id=action_id,
        decision_id=decision_id,
        actor_id=actor_id,
        action_type=action_type,
        status="proposed",
        effects={
            "target_actor_id": target_actor_id,
            "control_source": "player",
        },
    )
    session.add(action)
    await session.flush()

    result = await execute_action(session, action_id)
    if explain:
        from .simulation import run_simulation
        await run_simulation(session, ticks=1, simulation_id=simulation_id,
            initial_state=before_action, player_actions=[{**result, "decision_id": decision_id}],
            controlled_actor_id=actor_id, disable_ai=True, mode="player")
    else:
        await session.flush()
    return {
        "simulation_id": simulation_id,
        "tick": tick,
        "decision_id": decision_id,
        **result,
    }
