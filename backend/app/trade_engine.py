from __future__ import annotations
from dataclasses import dataclass

def clamp(v: float) -> float: return max(0.0, min(1.0, float(v)))

@dataclass(frozen=True)
class TradeLink:
    source: str
    target: str
    volume: float
    dependency: float
    resilience: float

def step(links: list[TradeLink], shocks: dict[tuple[str,str], float] | None = None) -> dict:
    shocks = shocks or {}
    out = []
    for link in links:
        shock = clamp(shocks.get((link.source, link.target), 0.0))
        effective = link.volume * (1.0 - shock * (1.0 - link.resilience))
        disruption = shock * link.dependency
        out.append({"source": link.source, "target": link.target, "volume": effective, "disruption": disruption, "dependency": link.dependency})
    return {"links": out, "total_volume": sum(x["volume"] for x in out), "systemic_disruption": sum(x["disruption"] for x in out)}
