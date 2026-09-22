from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random


@dataclass
class CrisisNode:
    crisis_id: str
    root_event_id: str
    event_type: str
    phase: str
    intensity: float
    duration: int
    tick_started: int
    participants: tuple[str, ...]
    escalation: float = 0.0
    contagion: float = 0.0
    uncertainty: float = 0.0


class CrisisGraph:
    """
    Multi-tick crisis lifecycle.

    A crisis is a graph, not a single random modifier. Each tick it can:
    - intensify or decay;
    - move through lifecycle phases;
    - generate secondary events;
    - expand to connected actors;
    - terminate or branch into a new crisis.
    All branching is deterministic for a given seed.
    """

    PHASES = ("emerging", "escalating", "peak", "contained", "decaying", "resolved")

    INTERACTIONS = {
        ("economic_crisis", "energy_disruption"): 0.06,
        ("economic_crisis", "internal_crisis"): 0.05,
        ("internal_crisis", "security_incident"): 0.07,
        ("diplomatic_crisis", "security_incident"): 0.06,
        ("economic_crisis", "natural_disaster"): 0.04,
        ("intelligence_failure", "security_incident"): 0.05,
        ("diplomatic_crisis", "economic_crisis"): 0.025,
    }

    BRANCHES = {
        "economic_crisis": ("internal_crisis", "security_incident"),
        "energy_disruption": ("economic_crisis", "internal_crisis"),
        "internal_crisis": ("security_incident", "economic_crisis"),
        "intelligence_failure": ("security_incident", "diplomatic_crisis"),
        "natural_disaster": ("economic_crisis", "internal_crisis"),
        "security_incident": ("diplomatic_crisis", "internal_crisis"),
        "diplomatic_crisis": ("security_incident", "economic_crisis"),
    }

    def _rng(self, seed: int, crisis_id: str, tick: int) -> random.Random:
        raw = f"{seed}:{crisis_id}:{tick}".encode()
        stable = int(hashlib.sha256(raw).hexdigest()[:16], 16)
        return random.Random(stable)

    def _phase(self, intensity: float, age: int) -> str:
        if intensity < 0.08:
            return "resolved"
        if intensity < 0.22:
            return "decaying" if age > 2 else "contained"
        if intensity < 0.55:
            return "emerging" if age <= 1 else "escalating"
        if intensity < 0.82:
            return "escalating"
        return "peak"

    def advance(
        self,
        state_metadata: dict,
        events,
        actors: dict[str, dict],
        relationships: dict[str, dict],
        tick: int,
        seed: int,
    ) -> list:
        graph = state_metadata.setdefault("crisis_graph", {"nodes": {}, "edges": [], "history": []})
        nodes = graph.setdefault("nodes", {})
        generated = []

        for event in events:
            if event.event_type not in self.BRANCHES:
                continue
            cid = f"crisis:{event.event_id}"
            if cid not in nodes:
                nodes[cid] = CrisisNode(
                    cid, event.event_id, event.event_type, "emerging",
                    max(0.1, min(1.0, event.confidence)),
                    1, tick, tuple(event.actors),
                    uncertainty=1.0 - event.confidence,
                ).__dict__

        interaction_delta: dict[str, float] = {cid: 0.0 for cid in nodes}
        active_items = [
            (cid, raw)
            for cid, raw in nodes.items()
            if raw.get("phase") != "resolved"
        ]
        for index, (cid_a, raw_a) in enumerate(active_items):
            participants_a = set(raw_a.get("participants", ()))
            for cid_b, raw_b in active_items[index + 1:]:
                interaction_key = tuple(sorted((raw_a.get("event_type"), raw_b.get("event_type"))))
                base_strength = self.INTERACTIONS.get(interaction_key, 0.0)
                if base_strength <= 0:
                    continue

                participants_b = set(raw_b.get("participants", ()))
                overlap = participants_a & participants_b
                connectivity = 1.0 if overlap else 0.0
                if not overlap:
                    for actor_a in participants_a:
                        for actor_b in participants_b:
                            rel = relationships.get(f"{actor_a}:{actor_b}", {})
                            reverse = relationships.get(f"{actor_b}:{actor_a}", {})
                            link = max(
                                abs(float(rel.get("diplomatic", 0.0))) + abs(float(rel.get("economic", 0.0))),
                                abs(float(reverse.get("diplomatic", 0.0))) + abs(float(reverse.get("economic", 0.0))),
                            )
                            connectivity = max(connectivity, min(1.0, link / 1.5))

                if connectivity <= 0.1:
                    continue

                strength = base_strength * connectivity * (
                    0.5 + 0.5 * min(float(raw_a.get("intensity", 0.0)), float(raw_b.get("intensity", 0.0)))
                )
                interaction_delta[cid_a] += strength
                interaction_delta[cid_b] += strength
                graph["edges"].append({
                    "from": cid_a,
                    "to": cid_b,
                    "tick": tick,
                    "mechanism": "crisis_interaction",
                    "strength": round(strength, 6),
                })

        for cid, raw in list(nodes.items()):
            age = max(0, tick - int(raw["tick_started"]))
            rng = self._rng(seed, cid, tick)
            intensity = float(raw["intensity"])
            phase = raw["phase"]

            # External pressure and actor interdependence can sustain a crisis.
            connected = set(raw.get("participants", ()))
            network_pressure = 0.0
            for actor_id in connected:
                for key, rel in relationships.items():
                    if key.startswith(actor_id + ":") or key.endswith(":" + actor_id):
                        network_pressure += abs(float(rel.get("diplomatic", 0.0))) * 0.002

            drift = rng.uniform(-0.09, 0.10) + network_pressure + interaction_delta.get(cid, 0.0)
            if phase == "decaying":
                drift -= 0.06
            intensity = max(0.0, min(1.0, intensity + drift))

            # Crisis contagion reaches connected actors without forcing identical effects.
            if connected:
                for actor_id in actors:
                    if actor_id in connected:
                        continue
                    link = max(
                        abs(float(relationships.get(f"{actor_id}:{p}", {}).get("diplomatic", 0.0)))
                        + abs(float(relationships.get(f"{actor_id}:{p}", {}).get("economic", 0.0)))
                        for p in connected
                    )
                    if link > 0.25 and rng.random() < min(0.65, intensity * link * 0.7):
                        connected.add(actor_id)
                        graph["edges"].append({
                            "from": cid,
                            "to": actor_id,
                            "tick": tick,
                            "mechanism": "crisis_contagion",
                            "strength": round(intensity * link, 6),
                        })

            phase = self._phase(intensity, age)
            raw["intensity"] = round(intensity, 6)
            raw["phase"] = phase
            raw["duration"] = age + 1
            raw["participants"] = sorted(connected)
            raw["escalation"] = round(max(0.0, intensity - 0.35), 6)
            raw["contagion"] = round(min(1.0, len(connected) / max(1, len(actors))), 6)
            raw["uncertainty"] = round(max(0.0, min(1.0, float(raw.get("uncertainty", 0.0)) * 0.9)), 6)

            if phase == "resolved":
                continue

            branches = self.BRANCHES.get(raw["event_type"], ())
            if branches and rng.random() < min(0.45, intensity * 0.35):
                branch_type = branches[rng.randrange(len(branches))]
                branch_id = f"{cid}:branch:{age}"
                if branch_id not in nodes:
                    participants = tuple(sorted(connected))
                    nodes[branch_id] = CrisisNode(
                        branch_id, raw["root_event_id"], branch_type,
                        "emerging", max(0.08, intensity * rng.uniform(0.28, 0.55)),
                        1, tick, participants,
                        escalation=intensity * 0.25,
                        contagion=raw["contagion"],
                        uncertainty=min(1.0, raw["uncertainty"] + 0.1),
                    ).__dict__
                    graph["edges"].append({
                        "from": cid,
                        "to": branch_id,
                        "tick": tick,
                        "mechanism": "secondary_crisis",
                        "strength": raw["intensity"],
                    })
                    generated.append(
                        type("SyntheticEvent", (), {
                            "event_id": f"{branch_id}:event:{tick}",
                            "event_type": branch_type,
                            "actors": participants,
                            "confidence": max(0.35, 1.0 - raw["uncertainty"]),
                            "description": f"Secondary crisis generated from {raw['event_type']}",
                            "metadata": {"crisis_id": branch_id, "parent_crisis_id": cid},
                        })()
                    )

            graph["history"].append({
                "crisis_id": cid,
                "tick": tick,
                "phase": phase,
                "intensity": raw["intensity"],
                "participants": raw["participants"],
                "interaction_pressure": round(interaction_delta.get(cid, 0.0), 6),
            })

        return generated
