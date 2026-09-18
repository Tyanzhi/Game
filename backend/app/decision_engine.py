from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import DecisionModel, ActionModel, ActorModel
from uuid import uuid4

async def decide_all(session: AsyncSession, simulation_id: str) -> list[dict]:
    actors = (await session.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    result = []
    for actor in actors:
        action_id = f'action-{uuid4().hex}'
        decision_id = f'decision-{uuid4().hex}'
        selected = 'observe' if actor.information_quality < 0.8 else 'public_statement'
        session.add(DecisionModel(id=decision_id, actor_id=actor.id, simulation_id=simulation_id, situation='baseline', selected_action=selected, confidence=0.6, reasoning_factors=[], options=[]))
        session.add(ActionModel(id=action_id, decision_id=decision_id, actor_id=actor.id, action_type=selected, status='proposed', effects={}))
        result.append({'decision_id': decision_id, 'action_id': action_id, 'actor_id': actor.id, 'action': selected})
    await session.flush()
    return result
