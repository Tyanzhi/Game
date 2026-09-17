from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
PHASES=('ingest','state_update','perception','decision','interaction','action','cascade','forecast','snapshot')
@dataclass
class TickContext:
    simulation_id:str; tick:int; seed:int; payload:dict[str,Any]=field(default_factory=dict); phase_results:dict[str,Any]=field(default_factory=dict)
Handler=Callable[[TickContext],Any|Awaitable[Any]]
class SimulationTickEngine:
    def __init__(self,handlers:dict[str,Handler]|None=None): self.handlers=handlers or {}
    async def run(self,context:TickContext):
        for phase in PHASES:
            h=self.handlers.get(phase)
            result={'status':'skipped'} if h is None else h(context)
            if hasattr(result,'__await__'): result=await result
            context.phase_results[phase]=result; context.payload[phase]=result
        context.phase_results['completed']=True; return context
