from dataclasses import dataclass
@dataclass
class Fact:
    fact_id: str; value: str; confidence: float; source_ids: list
class Perception:
    def __init__(self,facts): self.facts={f.fact_id:f for f in facts}
class PerceptionEngine:
    def build(self, actor_id, facts, information_quality): return Perception([Fact(f['fact_id'],f['value'],f['confidence'],f.get('source_ids',[])) for f in facts])
