# WORLD ENGINE instructions for Codex

Read [`docs/ENGINEERING_CONSTITUTION.md`](docs/ENGINEERING_CONSTITUTION.md) before changing the simulation, live-world data flow, forecasts, scenarios, API contracts, deployment, or frontend interpretation of model output. This is the project's engineering standard. The audit and percentages in that document are dated assessments, not proof of current production state; verify affected code and deployments before making claims.

## Product and data invariants

- The canonical live world has one authoritative persistent state. A user run, game turn, research scenario, or counterfactual must use an isolated branch and must not update canonical actors, relationships, or live-world versions. Only the authorized live orchestrator may advance canonical state. Treat the current `sync_world_state_to_db()` path as a known isolation risk until fixed and tested.
- Preserve reproducibility: record the actual seed, input evidence and cutoff, initial and parent state hashes, code/data/ontology/model versions, and deterministic output hashes. Identical inputs and seed should reproduce the same result; external calls must be captured or normalized reproducibly.
- Keep evidence, reported claims, normalized events, inferred effects, simulation states, and forecasts distinct. Preserve provenance from a changed state field back through effect, event, evidence, and source. Label forecasts with horizon, uncertainty, version, and evaluation status; never present a probability as a fact.
- Domain engines return typed, bounded effects. The orchestrator applies state changes. LLM output is schema-validated advisory input, never an authoritative state mutation. Game theory and IR lenses are versioned hypotheses that require empirical evaluation.
- No new silent exception handling, unbounded in-memory history, fake production data, empty successful responses, or placeholder methods on production routes. Put unfinished experiments behind an explicit feature flag and mark them clearly in UI and docs.

## Current work order

Work on Stage 8 Core Integrity before significant product expansion: (1) canonical world state, (2) branch isolation, (3) functional Scenario Engine, (4) temporal Knowledge Graph, (5) bounded domain engines, (6) run manifests and reproducibility, (7) durable, idempotent ingestion and event publication, (8) release SHA synchronization, (9) authentication and limits for mutation routes. Choose a small, reviewable slice of this sequence for each task; do not claim Stage 8 is done because a component exists in name.

The frontend may show a small working mechanism while Stage 8 proceeds. Browser-only examples must be explicitly labelled as synthetic, must work when the API is offline, and must never imply scientific validation or update live state. Keep selection, action, result, and causal explanation visibly connected. Public API-backed features require the real integration and appropriate tests.

## Verification for each change

1. Check the relevant invariants and state exactly what changed. For behavior changes, add focused unit tests; add integration tests when crossing storage, API, worker, or frontend/backend boundaries. Never add a test that only restates the implementation.
2. For simulation state changes, verify same input/seed gives the same hash, branch execution leaves live state unchanged, duplicate evidence/event has one effect, and the parent hash chain remains valid, as applicable.
3. For backend changes, run relevant compile, lint/type checks, tests and migration checks available in this checkout. For frontend changes, run the TypeScript build and exercise affected interactions. Use `npm ci` only when a lockfile exists. Report any missing dependency, unrun gate, or failing check rather than claiming green CI.
4. Keep APIs typed and versioned when introducing public contracts. Ensure errors and costs are observable and state/queues are bounded. Update the engineering document or adjacent documentation when contracts, assumptions, or limitations change.
5. Never claim a production release or deployed SHA is current without checking it. API, worker, and migrations should share one verified release SHA. Do not push, deploy, or change external environments unless the current user request authorizes it.

The full Stage 8 acceptance table, later stages, forecasting validation, historical replay, scaling, security, observability, and release rules remain in [`docs/ENGINEERING_CONSTITUTION.md`](docs/ENGINEERING_CONSTITUTION.md). Where the standard describes future architecture, implement incrementally and keep existing limitations visible until tests demonstrate that they are resolved.
