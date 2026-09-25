from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .models import ActorModel
from .simulation import run_simulation
from .strategic_foresight import ACTION_RESOURCE_COSTS, resource_feasibility
from .strategic_gameplay import submit_player_action
from .strategic_overview import strategic_overview
from .integration_state import load_world_state


ACTION_POINT_COSTS = {
    "observe": 1,
    "diplomatic_outreach": 1,
    "public_statement": 1,
    "economic_adjustment": 2,
    "defensive_posture": 2,
}


async def play_turn(
    session: AsyncSession,
    *,
    parent_simulation_id: str,
    actor_id: str,
    action_type: str,
    target_actor_id: str | None,
    seed: int,
    action_points: int = 2,
    broadcast=None,
) -> dict:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise ValueError(f"Unknown actor: {actor_id}")

    cost = ACTION_POINT_COSTS.get(action_type)
    if cost is None:
        raise ValueError(f"Unsupported action: {action_type}")
    if cost > max(0, int(action_points)):
        raise ValueError(
            f"Not enough action points: action costs {cost}, available {action_points}"
        )

    feasibility = resource_feasibility(
        action_type,
        {
            "economic_capacity": actor.economic_capacity,
            "security_capacity": actor.security_capacity,
            "diplomatic_capacity": actor.diplomatic_capacity,
        },
    )
    if not feasibility["feasible"]:
        raise ValueError("Action exceeds actor resource capacity")

    before_player = await load_world_state(session, parent_simulation_id)
    player_result = await submit_player_action(
        session,
        simulation_id=parent_simulation_id,
        actor_id=actor_id,
        action_type=action_type,
        target_actor_id=target_actor_id,
        rationale="turn_loop_player_action",
        explain=False,
    )

    child_simulation_id = (
        f"turn-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-"
        f"{uuid4().hex[:8]}"
    )
    ai_result = await run_simulation(
        session,
        ticks=1,
        seed=int(seed),
        simulation_id=child_simulation_id,
        raw_events=None,
        broadcast=broadcast,
        controlled_actor_id=actor_id,
        initial_state=before_player,
        player_actions=[player_result],
        parent_simulation_id=parent_simulation_id,
    )
    await session.commit()
    overview = await strategic_overview(session, child_simulation_id)

    return {
        "parent_simulation_id": parent_simulation_id,
        "simulation_id": child_simulation_id,
        "controlled_actor_id": actor_id,
        "action_points_start": int(action_points),
        "action_points_spent": cost,
        "action_points_remaining": max(0, int(action_points) - cost),
        "resource_costs": ACTION_RESOURCE_COSTS.get(action_type, {}),
        "resource_feasibility": feasibility,
        "player_action": player_result,
        "ai_turn": ai_result,
        "overview": overview,
    }
