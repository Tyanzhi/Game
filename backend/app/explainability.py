"""Deterministic explanations of recorded simulation output; never infer missing causes."""
from copy import deepcopy
from math import isfinite

from .realtime_pipeline import state_hash

VERSION = "explainability-v2"
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
                if left is None and kind in {"relationship", "market"}:
                    left = 0.0
                if _number(left) and _number(right) and abs(right - left) > 1e-12:
                    result.append({"kind": kind, "entity": entity, "field": field,
                                   "before": left, "after": right, "delta": right - left,
                                   "text": f"{entity}: {FIELDS.get(field, field)} — {left:.4g} → {right:.4g}."})
    return sorted(result, key=lambda item: (-abs(item["delta"]), item["kind"], item["entity"], item["field"]))


def build_explanation(*, simulation_id, tick, seed, before, after, events, decisions,
                      actions, effects, forecasts, parent_hash=None, previous_report=None, phase_results=None):
    """All arguments must describe this tick. Inputs are copied; state is never mutated."""
    changes = _deltas(before, after)
    uncertainties = [
        "Вероятности и уверенность — оценки модели, а не гарантии или доказанная точность.",
        "Модель использует эвристические правила; её уверенность не является измеренной точностью на реальных исходах.",
    ]
    observed = [{"event_id": e.event_id, "description": e.description, "status": e.status,
                 "event_type": e.event_type, "actor_ids": list(e.actors),
                 "timestamp": e.timestamp.isoformat(), "confidence": e.confidence,
                 "source_ids": list(e.source_ids), "source_urls": list(e.source_urls),
                 "provenance": deepcopy(e.metadata or {}), "category": "EXTERNAL_EVIDENCE"}
                for e in events if hasattr(e, "source_ids")]
    generated = [{"event_id": e.event_id, "description": e.description,
        "event_type": e.event_type, "actor_ids": list(e.actors),
        "provenance": deepcopy(e.metadata or {}), "category": "MODEL_INTERPRETATION"}
        for e in events if not hasattr(e, "source_ids")]
    phase_results = phase_results or {}
    for index, shock in enumerate(phase_results.get("action", {}).get("planned_shocks", [])):
        generated.append({**deepcopy(shock), "event_id": f"shock:{simulation_id}:{tick}",
            "description": "Случайный шок модели: " + str(shock.get("event_type", shock.get("parent_event"))),
            "category": "MODEL_INTERPRETATION", "seed": seed, "index": index})
    if not observed:
        uncertainties.append("В этом тике нет новых внешних свидетельств; изменения относятся к симуляции.")
    decision_texts = []
    for row in decisions:
        choice = row.get("selected_action", row.get("action", "unknown"))
        reasons = row.get("reasoning_factors") or []
        decision_texts.append({**deepcopy(row), "text":
            f"{row['actor_id']}: {ACTIONS.get(choice, choice)}. "
            + ("Причины: " + "; ".join(reason_text(reason) for reason in reasons) + "." if reasons
               else "Причины выбора не записаны; объяснение отсутствует.")})
    forecast_texts = []
    for row in forecasts:
        probabilities = row.get("probabilities", {})
        distribution = "; ".join(f"{LEVELS.get(k, k)}: {v:.1%}" for k, v in sorted(probabilities.items()) if _number(v))
        uncertainty = row.get("uncertainty")
        confidence = row.get("confidence", 1.0 - uncertainty if _number(uncertainty) else None)
        confidence_label = ("высокая" if confidence >= 0.7 else "средняя" if confidence >= 0.4 else "низкая") if _number(confidence) else "не записана"
        previous = next((f for f in (previous_report or {}).get("forecasts", [])
            if f.get("target") == row.get("target") and f.get("horizon") == row.get("horizon")
            and f.get("model_version") == row.get("model_version")), None)
        comparisons = [{"outcome": key, "before": old, "after": probabilities[key],
            "delta": probabilities[key] - old,
            "text": f"{LEVELS.get(key, key)}: {old:.1%} → {probabilities[key]:.1%} ({(probabilities[key] - old) * 100:+.2f} п.п.)."}
            for key, old in (previous or {}).get("probabilities", {}).items()
            if key in probabilities and _number(old) and _number(probabilities[key])]
        driver_changes = [{"factor": name, "before": old, "after": value, "delta": value - old}
            for name, value in row.get("driver_values", {}).items()
            if _number(value) and _number(old := (previous or {}).get("driver_values", {}).get(name)) and value != old]
        sensitivities = sorted(row.get("sensitivity", []), key=lambda s: -abs(s["high_probability_delta"]))
        factor_text = [f"Если вклад фактора «{DRIVERS.get(s['factor'], s['factor'])}» равен нулю, "
            f"вероятность высокой стабильности составит {s['high_probability_without_factor']:.1%} "
            f"({s['high_probability_delta'] * 100:+.2f} п.п.). Остальные входы и seed сохранены."
            for s in sensitivities if abs(s["high_probability_delta"]) > 1e-12]
        forecast_texts.append({**deepcopy(row), "category": "MODEL_FORECAST",
            "confidence": confidence, "confidence_label": confidence_label,
            "comparison": comparisons, "previous_tick": (previous_report or {}).get("tick") if previous else None,
            "driver_changes": driver_changes, "sensitivity_text": factor_text,
            "comparison_note": "Сравниваются скользящие горизонты одинаковой длины; дата исхода смещается на один тик." if previous else "Предыдущего сопоставимого прогноза нет.",
            "text":
            f"{row['target']}, горизонт {row['horizon']} тиков: {distribution or 'распределение не записано'}. "
            + (f"Неопределённость модели: {uncertainty:.1%}. " if _number(uncertainty) else "Неопределённость не записана. ")
            + f"Уверенность: {confidence_label}."})
    counterfactuals = [{"actor_id": row["actor_id"], "results": deepcopy(row["counterfactuals"]),
                       "category": "MODEL_COUNTERFACTUAL", "text": [
                           f"Вместо «{ACTIONS.get(c.get('baseline_action'), c.get('baseline_action'))}» "
                           f"вариант «{ACTIONS.get(c.get('alternative_action'), c.get('alternative_action'))}»: "
                           f"изменение расчётной полезности {c.get('utility_delta', 0):+.3f}, риска {c.get('risk_delta', 0):+.3f}. "
                           "Это сравнение оценок планировщика, а не вероятность реального события."
                           for c in row["counterfactuals"]]}
                      for row in decisions if row.get("counterfactuals")]
    if not counterfactuals:
        uncertainties.append("Контрфактическое сравнение для этого тика не рассчитано.")
    if not changes:
        uncertainties.append("Сравнимые числовые изменения не найдены; это не означает отсутствие всех событий.")
    effect_rows = deepcopy(effects)
    by_id = {e.get("effect_id"): e for e in effect_rows if e.get("effect_id")}
    action_map = {a.get("action_id"): a for a in actions}
    evidence = {e["event_id"]: e for e in (previous_report or {}).get("evidence_catalog", [])}
    evidence.update({e["event_id"]: e for e in observed + generated})
    chains = []
    for effect in effect_rows:
        path, seen = [], set()
        current = effect
        while current:
            key = current.get("effect_id")
            if key in seen:
                break
            seen.add(key)
            path.append(current)
            current = by_id.get(current.get("parent_effect_id"))
        path.reverse()
        action = action_map.get(effect.get("action_id"), {})
        origin = evidence.get(effect.get("event_id"), {})
        root_event_id = origin.get("provenance", {}).get("root_event_id")
        root_evidence = evidence.get(root_event_id, origin)
        effect["source_ids"] = root_evidence.get("source_ids", [])
        effect["source_urls"] = root_evidence.get("source_urls", [])
        effect["root_event_id"] = root_event_id or effect.get("event_id")
        effect["reaction_to_action_id"] = action.get("effects", {}).get("reaction_to_action_id")
        prefix = []
        if origin:
            prefix.append(origin.get("description", origin["event_id"]))
        if effect.get("reaction_to_action_id"):
            prefix.append("Ответ на действие " + effect["reaction_to_action_id"])
        if action:
            prefix.append(f"{action['actor_id']}: {ACTIONS.get(action.get('effects', {}).get('action'), 'действие')}")
        elif effect.get("action_id"):
            prefix.append("Отложенное действие " + effect["action_id"])
        steps = [f"{e['target']}: {FIELDS.get(e['field'], e['field'])} {e['delta']:+.4g} ({MECHANISMS.get(e['mechanism'], e['mechanism'])})" for e in path]
        chains.append({"effect_id": effect.get("effect_id"), "effect_path": [e.get("effect_id") for e in path],
            "event_id": effect.get("event_id"), "action_id": effect.get("action_id"),
            "text": " → ".join(prefix + steps)})
    unexplained = []
    for change in changes:
        matched = [e for e in effect_rows if effect_matches(e, change)]
        change["effect_ids"] = [e.get("effect_id") for e in matched]
        change["explained_delta"] = sum(e["delta"] for e in matched)
        change["residual_delta"] = change["delta"] - change["explained_delta"]
        change["causes"] = [chain["text"] for chain in chains if chain["effect_id"] in change["effect_ids"]]
        if abs(change["residual_delta"]) > 1e-9:
            unexplained.append({"entity": change["entity"], "field": change["field"], "delta": change["residual_delta"]})
    if unexplained:
        uncertainties.append(f"Для {len(unexplained)} изменений остался незаписанный вклад; причины не достраиваются догадкой.")
    if phase_results.get("cascade", {}).get("truncated"):
        uncertainties.append("Каскад достиг лимита 1000 эффектов; дальнейшее распространение не рассчитано.")
    summary = (f"Тик {tick} завершён: записано {len(changes)} изменений показателей и {len(actions)} действий. "
               + (changes[0]["text"] if changes else "Числовые показатели не изменились.")
               + f" Внешних событий: {len(observed)}; прогнозов модели: {len(forecasts)}.")
    return {
        "version": VERSION, "simulation_id": simulation_id, "tick": tick, "seed": seed,
        "before_hash": state_hash(before), "after_hash": state_hash(after), "parent_hash": parent_hash,
        "summary": summary, "observed_data": observed, "changes": changes,
        "model_events": generated, "evidence_catalog": list(evidence.values()),
        "causal_chains": chains, "unexplained_changes": unexplained,
        "world_state_before": deepcopy(before), "world_state_after": deepcopy(after),
        "model_versions": {"explainability": VERSION, "forecast": "forecast-v2"},
        "metadata_changes": {key: {"before": deepcopy(before.get("metadata", {}).get(key)), "after": deepcopy(value)}
            for key, value in after.get("metadata", {}).items() if value != before.get("metadata", {}).get(key)},
        "actor_decisions": decision_texts, "actions": deepcopy(actions),
        "cascade_effects": effect_rows, "forecasts": forecast_texts,
        "alternative_scenarios": counterfactuals, "key_uncertainties": uncertainties,
        "why_it_happened": [
            f"{effect['source']} → {effect['target']}: {FIELDS.get(effect['field'], effect['field'])}, "
            f"эффект {effect['delta']:+.4g}; механизм {effect['mechanism']}, глубина {effect['depth']}."
            for effect in effects
        ],
        "limitations": {"complete_causal_provenance": not unexplained and all(e.get("action_id") or e.get("event_id") for e in effects), "scientific_validation": False},
    }


LEVELS = {"low": "низкая стабильность", "medium": "средняя стабильность", "high": "высокая стабильность"}
DRIVERS = {"economic": "экономические изменения", "social": "внутреннее давление",
    "crisis": "интенсивность кризиса", "financial_stress": "финансовое напряжение", "global_trade": "мировая торговля"}
MECHANISMS = {"action": "прямой эффект действия", "diplomatic_action": "дипломатическое действие",
    "relationship_cascade": "распространение по отношениям", "event_propagation": "воздействие события",
    "network_propagation": "сетевое распространение", "market_propagation": "воздействие на рынок",
    "delayed_effect": "отложенное последствие", "accepted_bargain": "принятое соглашение",
    "unexpected_shock": "случайный шок модели", "shock_secondary_effect": "вторичный эффект шока"}
REASONS = {"player_selected": "решение выбрано пользователем; его личные мотивы модель не оценивает",
    "intelligence_uncertainty_response": "информационный сигнал при качестве информации ниже 0,55",
    "security_threshold_response": "сигнал безопасности или превышение порога угрозы",
    "economic_pressure_response": "экономический сигнал при экономическом потенциале выше 0,25",
    "low_escalation_response": "интенсивность ответа ниже 0,34 допускает дипломатический контакт",
    "political_signal_response": "выбрано публичное заявление после проверки правил информации, безопасности и экономики",
    "uncertainty_response": "низкое качество информации и сохранённый случайный выбор переключили ответ на наблюдение",
    "third_party_intervention": "модель допустила вмешательство третьего актора; форма ответа зависит от дипломатических отношений"}


def reason_text(reason):
    return REASONS.get(str(reason), str(reason).replace("_", " "))


def effect_matches(effect, change):
    if change["kind"] == "market":
        return effect["target"] == "market:global" and effect["field"] == "market:" + change["field"]
    if change["kind"] == "relationship":
        return f"{effect['source']}:{effect['target']}" == change["entity"] and effect["field"] == change["field"]
    return effect["target"] == change["entity"] and effect["field"] == change["field"] and effect["field"] not in {"diplomatic", "trade"}
