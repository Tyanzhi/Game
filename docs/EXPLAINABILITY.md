# Explainability is an architectural requirement

Every significant simulation result must have an explanation derived from recorded
engine inputs and outputs. An LLM must not invent post-hoc causes. This requirement
applies to manual simulations, live cycles, player turns and future scenario branches.

## Implemented first slice

`app/explainability.py` builds deterministic Russian text and structured records.
The simulation captures the before-state, primary decisions and alternatives,
executed actions/reactions, cascade effects, normalized evidence and forecasts.
The snapshot phase stores the report transactionally in
`SimulationTickModel.phase_log.explanation`. The tick API exposes it as `explanation`;
no schema migration or historical backfill is needed. Before/after hashes use the
same algorithm as saved world versions. The report does not mutate world state.

The World Engine Analysis panel supports tick selection and brief, analytical and
technical detail. It distinguishes external FACT/CLAIM/HYPOTHESIS records from
model decisions and forecasts. Old ticks without reports are explicitly labeled.
Reports retain full details; the UI caps long lists and exposes the full technical
record. Forecast horizon, uncertainty, model version and available drivers are shown.

## Required follow-up, not claimed complete

- Propagate evidence/event/action IDs through every effect and retain parent effect
  IDs across cascades and compaction. A list of effects is not a complete causal graph.
- Record explanation inputs for player actions and reaction decisions as completely
  as primary AI decisions, including alternatives and constraints.
- Translate every internal rationale/factor code into human-readable, versioned text.
- Provide readable counterfactual comparisons from isolated ScenarioEngine branches.
  Current planning comparisons are heuristic utility/risk deltas, not measured
  changes in real-world event probabilities.
- Compare forecasts at matching targets/horizons across ticks and distinguish
  forecast drift from realized outcome changes.
- Persist evidence cutoff, freshness, source health, all model versions and the run
  manifest. Explicitly describe missing information and computed sensitivity drivers.
- Cover created/deleted entities, queued delayed effects, all domain engines and
  temporal graph changes. Numeric deltas alone cannot cover those cases.
- Verify all output remains bound to its branch after Stage 8 isolation work.

## Acceptance

Each report must answer what happened, recorded reasons, actors and choices,
alternatives, consequences, likely scenarios and conditions that could change them.
Store provenance, before/after values, confidence separate from probability,
uncertainty and model versions. Unsupported sections state their limitations.
No API route, passing smoke test or fluent text establishes scientific validity.

Tests cover deterministic output, input immutability, preservation of CLAIM status,
absence of invented causes and per-tick persistence/hash/seed integrity. Full CI and
browser verification are required before production release.
