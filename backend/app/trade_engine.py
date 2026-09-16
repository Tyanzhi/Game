"""Trade-network engine. Edges are value flows and resilience channels."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TradeEdge:
    source: str
    target: str
    value: float
    dependency: float
    resilience: float

def network(edges: list[dict]) -> dict:
    normalized=[]
    for e in edges:
        value=max(0.0,float(e.get('value',0))); dep=max(0.0,min(1.0,float(e.get('dependency',0))))
        normalized.append(TradeEdge(str(e.get('source','')),str(e.get('target','')),value,dep,max(0.0,min(1.0,1-dep))))
    exposure={}
    for e in normalized:
        exposure[e.source]=exposure.get(e.source,0)+e.value*e.dependency
        exposure[e.target]=exposure.get(e.target,0)+e.value*e.dependency
    return {'edges':[e.__dict__ for e in normalized],'exposure':exposure,'total_value':sum(e.value for e in normalized)}
