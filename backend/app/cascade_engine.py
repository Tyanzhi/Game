from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Effect:
    source: str
    target: str
    field: str
    delta: float
    confidence: float = 1.0
    depth: int = 0
    mechanism: str = "direct"


class CascadeEngine:
    """Propagates effects through the actor relationship graph."""

    def __init__(self, max_depth: int = 3, decay: float = 0.55, threshold: float = 0.002):
        self.max_depth = max(0, int(max_depth))
        self.decay = max(0.0, min(1.0, float(decay)))
        self.threshold = max(0.0, float(threshold))

    def run(self, effects: list[Effect], adjacency: dict[str, list[str]]):
        queue = list(effects)
        output: list[Effect] = []
        visited: set[tuple[str, str, str, int]] = set()
        truncated = False

        while queue:
            effect = queue.pop(0)
            key = (effect.source, effect.target, effect.field, effect.depth)
            if key in visited:
                continue
            visited.add(key)
            output.append(effect)

            if effect.depth >= self.max_depth:
                continue

            propagated_delta = effect.delta * effect.confidence * self.decay
            if abs(propagated_delta) < self.threshold:
                continue

            for target in adjacency.get(effect.target, []):
                if target == effect.source:
                    continue
                next_effect = Effect(
                    source=effect.target,
                    target=target,
                    field=effect.field,
                    delta=propagated_delta,
                    confidence=effect.confidence * self.decay,
                    depth=effect.depth + 1,
                    mechanism="relationship_cascade",
                )
                if len(output) + len(queue) >= 1000:
                    truncated = True
                    break
                queue.append(next_effect)

        return output, truncated
