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
    mechanism: str = 'direct'
class CascadeEngine:
    def run(self, effects, adjacency):
        return list(effects), False
