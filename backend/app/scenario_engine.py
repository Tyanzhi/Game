"""Isolated intervention scenarios; no canonical state writes."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite
from .cascade_engine import CascadeEngine, Effect
from .explainability import build_explanation
from .forecasting_engine import forecast
from .integration_state import TRACKED_FIELDS


@dataclass
class ScenarioResult:
    scenario_id: str
    history: list
    baseline_history: list
    comparisons: list


class ScenarioEngine:
    def run(self, baseline, assumptions, ticks=5, scenario_id="scenario", seed=0):
        if not isinstance(baseline, dict) or not isinstance(baseline.get("actors"), dict):
            raise ValueError("baseline must contain an actors snapshot")
        if not isinstance(assumptions, list) or len(assumptions) > 100:
            raise ValueError("assumptions must contain at most 100 interventions")
        ticks = max(1, min(120, int(ticks)))
        interventions = []
        for index, item in enumerate(assumptions):
            if not isinstance(item, dict):
                raise ValueError("assumption must specify actor_id, field and delta")
            actor, field, delta = item.get("actor_id"), item.get("field"), item.get("delta")
            if actor not in baseline["actors"] or field not in TRACKED_FIELDS:
                raise ValueError("unknown assumption actor or field")
            if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not isfinite(delta) or abs(delta) > 1:
                raise ValueError("delta must be finite and between -1 and 1")
            interventions.append(Effect(actor, actor, field, float(delta),
                mechanism="scenario_assumption", event_id=f"assumption:{scenario_id}:{index}"))

        def branch(branch_id, initial):
            state = deepcopy(baseline)
            state.setdefault("metadata", {})
            history, previous = [], None
            for step in range(1, ticks + 1):
                before = deepcopy(state)
                state["tick"] = int(baseline.get("tick", 0)) + step
                adjacency = {}
                for key in state["metadata"].get("relationships", {}):
                    source, target = key.split(":", 1)
                    adjacency.setdefault(source, []).append(target)
                effects, truncated = CascadeEngine().run(deepcopy(initial) if step == 1 else [], adjacency)
                for effect in effects:
                    actor = state["actors"].get(effect.target)
                    if actor is not None:
                        actor[effect.field] = float(actor.get(effect.field, 0)) + effect.delta
                forecasts = []
                for actor_id, values in state["actors"].items():
                    prediction = forecast(f"{actor_id}:stability", values, {}, 5, seed + state["tick"])
                    forecasts.append({**prediction, "inputs": dict(values), "driver_values": {}, "seed": seed + state["tick"]})
                report = build_explanation(simulation_id=branch_id, tick=state["tick"], seed=seed + state["tick"],
                    before=before, after=state, events=[], decisions=[], actions=[],
                    effects=[asdict(e) for e in effects], forecasts=forecasts,
                    parent_hash=previous["after_hash"] if previous else None, previous_report=previous,
                    phase_results={"cascade": {"truncated": truncated}})
                report["assumptions"] = deepcopy(assumptions if initial else [])
                report["key_uncertainties"].append("Сценарий проверяет заданные вмешательства и их каскад. Новые решения акторов и внешние события в этой ветви не моделируются.")
                history.append({"state": deepcopy(state), "explanation": report})
                previous = report
            return history

        control = branch(scenario_id + "-baseline", [])
        history = branch(scenario_id, interventions)
        comparisons = []
        for left, right in zip(control, history):
            comparison = []
            for base, alternative in zip(left["explanation"]["forecasts"], right["explanation"]["forecasts"]):
                old, new = base["probabilities"]["high"], alternative["probabilities"]["high"]
                comparison.append({"target": base["target"], "baseline_probability": old,
                    "alternative_probability": new, "delta": new - old,
                    "text": f"{base['target']}: высокая стабильность без вмешательства {old:.1%}, при заданных условиях {new:.1%} ({(new-old)*100:+.2f} п.п.)."})
            right["explanation"]["alternative_scenarios"] = [{"actor_id": "scenario", "results": comparison,
                "text": [c["text"] for c in comparison], "category": "MODEL_COUNTERFACTUAL"}]
            comparisons.append({"tick": right["state"]["tick"], "forecasts": comparison})
        return ScenarioResult(scenario_id, history, control, comparisons)

    async def generate(self, baseline, assumptions, **kwargs):
        return self.run(baseline, assumptions, **kwargs).__dict__
