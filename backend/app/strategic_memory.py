from __future__ import annotations

from copy import deepcopy


DEFAULT_MEMORY = {
    "trust": 0.5,
    "hostility": 0.0,
    "norm_alignment": 0.5,
    "cooperation_count": 0,
    "pressure_count": 0,
    "last_action": None,
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def memory_key(observer: str, counterpart: str) -> str:
    return f"{observer}:{counterpart}"


def get_memory(metadata: dict, observer: str, counterpart: str) -> dict:
    store = metadata.setdefault("strategic_memory", {})
    key = memory_key(observer, counterpart)
    if key not in store:
        store[key] = deepcopy(DEFAULT_MEMORY)
    return store[key]


def update_memory_from_action(
    metadata: dict,
    observer: str,
    counterpart: str,
    action_type: str,
    magnitude: float = 1.0,
) -> dict:
    memory = get_memory(metadata, observer, counterpart)
    amount = max(0.0, min(1.0, float(magnitude)))

    if action_type == "diplomatic_outreach":
        memory["trust"] = clamp(memory.get("trust", 0.5) + 0.06 * amount)
        memory["hostility"] = clamp(memory.get("hostility", 0.0) - 0.04 * amount)
        memory["cooperation_count"] = int(memory.get("cooperation_count", 0)) + 1
    elif action_type in {"defensive_posture", "economic_adjustment"}:
        memory["trust"] = clamp(memory.get("trust", 0.5) - 0.035 * amount)
        memory["hostility"] = clamp(memory.get("hostility", 0.0) + 0.05 * amount)
        memory["pressure_count"] = int(memory.get("pressure_count", 0)) + 1
    elif action_type == "public_statement":
        memory["norm_alignment"] = clamp(memory.get("norm_alignment", 0.5) + 0.01 * amount)

    memory["last_action"] = action_type
    return memory


def decay_memory(metadata: dict, rate: float = 0.015) -> None:
    store = metadata.setdefault("strategic_memory", {})
    for memory in store.values():
        memory["trust"] = clamp(memory.get("trust", 0.5) + (0.5 - memory.get("trust", 0.5)) * rate)
        memory["hostility"] = clamp(memory.get("hostility", 0.0) * (1.0 - rate))
        memory["norm_alignment"] = clamp(memory.get("norm_alignment", 0.5) + (0.5 - memory.get("norm_alignment", 0.5)) * rate)
