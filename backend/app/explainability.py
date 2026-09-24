"""Deterministic explanations of recorded simulation output; never infer missing causes."""
from copy import deepcopy
from math import isfinite

from .realtime_pipeline import state_hash

VERSION = "explainability-v1"
ACTIONS = {
    "observe": "сбор информации",
    "diplomatic_outreach": "дипломатический контакт",
    "economic_adjustment": "экономическая корректировка",
    "defensive_posture": "усиление оборонной позиции",
    "public_statement": "публичное заявление",
}
FIELDS = {
    "stability": "стабильность", "economic_capacity": "экономический потенциал",
    "domestic_pressure": "внутреннее давление", "security_capacity": "потенциал безопасности",
    "diplomatic_capacity": "дипломатический потенциал", "information_quality": "качество информации",
    "diplomatic": "дипломатические отношения", "economic": "экономические отношения",
    "military": "военные отношения", "trade": "торговля", "energy": "энергетика",
    "global_trade": "мировая торговля", "energy_price": "цена энергии",
    "financial_stress": "финансовое напряжение", "commodity_supply": "предложение сырья",
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _deltas(before, after):
    result = []
    groups = [
        ("actor", before.get("actors", {}), after.get("actors", {})),
        ("relationship", before.get("metadata", {}).get("relationships", {}),
         after.get("metadata", {}).get("relationships", {})),
        ("market", {"global": before.get("metadata", {}).get("markets", {})},
         {"global": after.get("metadata", {}).get("markets", {})}),
    ]
    for kind, old, new in groups:
        for entity in sorted(set(old) | set(new)):
            for field in sorted(set(old.get(entity, {})) | set(new.get(entity, {}))):
                left, right = old.get(entity, {}).get(field), new.get(entity, {}).get(field)
                if _number(left) and _number(right) and abs(right - left) > 1e-12:
                    result.append({"kind": kind, "entity": entity, "field": field,
                                   "before": left, "after": right, "delta": right - left,
                                   "text": f"{entity}: {FIELDS.get(field, field)} — {left:.4g} → {right:.4g}."})
    return sorted(result, key=lambda item: (-abs(item["delta"]), item["kind"], item["entity"], item["field"]))


def build_explanation(*, simulation_id, tick, seed, before, after, events, decisions,
                      actions, effects, forecasts, parent_hash=None):
    """All arguments must describe this tick. Inputs are copied; state is never mutated."""
    changes = _deltas(before, after)
    uncertainties = [
        "Вероятности и уверенность — оценки модели, а не гарантии или доказанная точность.",
        "Полная связь effect → event → evidence пока не записывается движком; отсутствующие причины не восстановлены догадкой.",
    ]
    observed = [{"event_id": e.event_id, "description": e.description, "status": e.status,
                 "event_type": e.event_type, "actor_ids": list(e.actors),
                 "timestamp": e.timestamp.isoformat(), "confidence": e.confidence,
                 "source_ids": list(e.source_ids), "source_urls": list(e.source_urls),
                 "provenance": deepcopy(e.metadata or {})} for e in events]
    if not observed:
        uncertainties.append("В этом тике нет новых внешних свидетельств; изменения относятся к симуляции.")
    decision_texts = []
    for row in decisions:
        choice = row.get("selected_action", row.get("action", "unknown"))
        reasons = row.get("reasoning_factors") or []
        decision_texts.append({**deepcopy(row), "text":
            f"{row['actor_id']}: {ACTIONS.get(choice, choice)}. "
            + ("Записанные факторы: " + "; ".join(map(str, reasons)) + "." if reasons
               else "Причины выбора не записаны; объяснение отсутствует.")})
    forecast_texts = []
    for row in forecasts:
        probabilities = row.get("probabilities", {})
        distribution = "; ".join(f"{k}: {v:.1%}" for k, v in sorted(probabilities.items()) if _number(v))
        uncertainty = row.get("uncertainty")
        forecast_texts.append({**deepcopy(row), "category": "MODEL_FORECAST", "text":
            f"{row['target']}, горизонт {row['horizon']} тиков: {distribution or 'распределение не записано'}. "
            + (f"Неопределённость модели: {uncertainty:.1%}." if _number(uncertainty) else "Неопределённость не записана.")})
    counterfactuals = [{"actor_id": row["actor_id"], "results": deepcopy(row["counterfactuals"]),
                       "category": "MODEL_COUNTERFACTUAL"}
                      for row in decisions if row.get("counterfactuals")]
    if not counterfactuals:
        uncertainties.append("Контрфактическое сравнение для этого тика не рассчитано.")
    if not changes:
        uncertainties.append("Сравнимые числовые изменения не найдены; это не означает отсутствие всех событий.")
    summary = (f"Тик {tick} завершён: записано {len(changes)} изменений показателей и {len(actions)} действий. "
               + (changes[0]["text"] if changes else "Числовые показатели не изменились.")
               + f" Внешних событий: {len(observed)}; прогнозов модели: {len(forecasts)}.")
    return {
        "version": VERSION, "simulation_id": simulation_id, "tick": tick, "seed": seed,
        "before_hash": state_hash(before), "after_hash": state_hash(after), "parent_hash": parent_hash,
        "summary": summary, "observed_data": observed, "changes": changes,
        "actor_decisions": decision_texts, "actions": deepcopy(actions),
        "cascade_effects": deepcopy(effects), "forecasts": forecast_texts,
        "alternative_scenarios": counterfactuals, "key_uncertainties": uncertainties,
        "why_it_happened": [
            f"{effect['source']} → {effect['target']}: {FIELDS.get(effect['field'], effect['field'])}, "
            f"эффект {effect['delta']:+.4g}; механизм {effect['mechanism']}, глубина {effect['depth']}."
            for effect in effects
        ],
        "limitations": {"complete_causal_provenance": False, "scientific_validation": False},
    }
