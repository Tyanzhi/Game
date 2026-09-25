from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import random


@dataclass(frozen=True)
class PropagationEffect:
    event_id: str
    source: str
    target: str
    domain: str
    field: str
    delta: float
    confidence: float
    mechanism: str
    perception: float
    depth: int = 0
    parent_event_id: str | None = None
    parent_effect_id: str | None = None

    @property
    def effect_id(self):
        return "event-effect-" + hashlib.sha256(repr((self.event_id, self.source, self.target,
            self.field, self.depth, self.parent_effect_id)).encode()).hexdigest()[:24]


@dataclass
class EventPropagation:
    max_depth: int = 3
    threshold: float = 0.003

    EVENT_PROFILES = {
        "economic_crisis": {"economic": -0.08, "trade": -0.05, "stability": -0.035, "domestic_pressure": 0.03},
        "energy_disruption": {"energy": -0.10, "economic": -0.06, "trade": -0.04, "stability": -0.025},
        "internal_crisis": {"stability": -0.09, "domestic_pressure": 0.08, "information": -0.025},
        "intelligence_failure": {"information": -0.12, "security": -0.025, "diplomatic": -0.02},
        "natural_disaster": {"stability": -0.07, "economic": -0.045, "trade": -0.025, "domestic_pressure": 0.04},
        "security_incident": {"security": -0.08, "stability": -0.025, "diplomatic": -0.055},
    }

    MARKET_PROFILES = {
        "economic_crisis": {"global_trade": -0.06, "financial_stress": 0.08},
        "energy_disruption": {"energy_price": 0.10, "global_trade": -0.04, "commodity_supply": -0.07},
        "internal_crisis": {"financial_stress": 0.025},
        "intelligence_failure": {"financial_stress": 0.015},
        "natural_disaster": {"commodity_supply": -0.06, "global_trade": -0.025},
        "security_incident": {"financial_stress": 0.035, "global_trade": -0.02},
    }

    FIELD_MAP = {
        "economic": "economic_capacity",
        "trade": "trade_resilience",
        "energy": "energy_security",
        "stability": "stability",
        "domestic_pressure": "domestic_pressure",
        "information": "information_quality",
        "security": "security_capacity",
        "diplomatic": "diplomatic_capacity",
    }

    def _perception(self, actor: dict, domain: str, relation: float, event_confidence: float, seed: int) -> float:
        info = float(actor.get("information_quality", 0.7))
        # Different actors observe the same event differently: information quality,
        # strategic distance and relationship context alter perceived magnitude.
        domain_sensitivity = {
            "economic": float(actor.get("economic_capacity", 0.7)),
            "trade": float(actor.get("trade_resilience", 0.7)),
            "energy": float(actor.get("energy_security", 0.7)),
            "security": float(actor.get("security_capacity", 0.7)),
            "stability": 1.0 - float(actor.get("stability", 0.7)),
            "diplomatic": 1.0 - float(actor.get("strategic_patience", 0.5)),
            "information": 1.0 - info,
            "domestic_pressure": float(actor.get("domestic_pressure", 0.2)),
        }.get(domain, 0.5)
        relation_bias = 1.0 + max(-0.25, min(0.25, -relation * 0.35))
        deterministic_noise = random.Random(seed).uniform(0.88, 1.12)
        return max(0.1, min(1.4, (0.55 + 0.45 * info) * (0.55 + 0.45 * domain_sensitivity) * relation_bias * event_confidence * deterministic_noise))

    def propagate(self, events, actors: dict[str, dict], relationships: dict[str, dict], seed: int = 0) -> list[PropagationEffect]:
        output: list[PropagationEffect] = []
        queue: list[tuple] = []

        for event in events:
            profile = self.EVENT_PROFILES.get(event.event_type)
            if not profile:
                continue
            involved = tuple(event.actors)
            for market_field, market_delta in self.MARKET_PROFILES.get(event.event_type, {}).items():
                output.append(PropagationEffect(
                    event.event_id, "system", "market:global", "market", f"market:{market_field}",
                    market_delta * event.confidence, event.confidence, "market_propagation", event.confidence
                ))
            for actor_id, actor in actors.items():
                relation = 0.0
                for source_id in involved:
                    rel = relationships.get(f"{actor_id}:{source_id}", {})
                    relation = max(relation, abs(float(rel.get("diplomatic", 0.0))))
                for domain, base in profile.items():
                    perception = self._perception(actor, domain, relation, event.confidence, seed + int(hashlib.sha256(f"{event.event_id}:{actor_id}:{domain}".encode()).hexdigest()[:8], 16))
                    delta = base * perception
                    if abs(delta) >= self.threshold:
                        field = self.FIELD_MAP[domain]
                        queue.append((PropagationEffect(event.event_id, "system", actor_id, domain, field, delta, event.confidence * perception, "event_propagation", perception), involved))
        visited = set()
        while queue:
            effect, involved = queue.pop(0)
            key = (effect.event_id, effect.target, effect.field, effect.depth)
            if key in visited:
                continue
            visited.add(key)
            output.append(effect)
            if effect.depth >= self.max_depth:
                continue
            propagated = effect.delta * 0.42 * effect.confidence
            if abs(propagated) < self.threshold:
                continue
            for actor_id, actor in actors.items():
                if actor_id == effect.target or actor_id in involved:
                    continue
                rel = relationships.get(f"{actor_id}:{effect.target}", {})
                link = abs(float(rel.get("diplomatic", 0.0))) + abs(float(rel.get("economic", 0.0)))
                if link <= 0.05:
                    continue
                confidence = min(1.0, effect.confidence * (0.75 + min(link, 1.0) * 0.2))
                next_effect = PropagationEffect(
                    effect.event_id, effect.target, actor_id, effect.domain, effect.field,
                    propagated * (0.7 + min(link, 1.0) * 0.3), confidence,
                    "network_propagation", effect.perception * 0.8, effect.depth + 1, effect.event_id, effect.effect_id
                )
                queue.append((next_effect, involved))
        return output
