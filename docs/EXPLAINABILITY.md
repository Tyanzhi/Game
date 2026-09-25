# Explainability contract (v2)

Every persisted simulation tick carries `phase_log.explanation`, generated deterministically from recorded engine data. No LLM is used. Tick APIs expose the report and the UI offers Russian brief, analytical and technical views beside simulation controls.

## Recorded information

- Before/after snapshots and hashes, tick seed, parent hash and model versions.
- External FACT/CLAIM/HYPOTHESIS evidence with source IDs, URLs and timestamps, separated from generated crises, random shocks and forecasts.
- Primary and reaction decisions, actual selection factors, input values, alternatives, resource feasibility, utility/risk components and multi-horizon planning results. Player choices are explicitly attributed to the user; motives are not invented.
- Event/action IDs and parent effect IDs through event and relationship propagation. Delayed effects retain their originating action. Accepted bargaining effects are recorded. Independent origins are not deduplicated together.
- Numeric actor, relationship and market deltas with contributing effects and a residual check. Unrecorded contributions are explicitly flagged. Metadata before/after records retain crisis graph, belief, memory and scheduling changes.
- Forecast probability distributions, separate heuristic confidence, uncertainty, ensemble output and inputs. Matching targets/models/horizons compare to the preceding persisted tick, including after restart. These are rolling horizons, not the same outcome date.
- Sequential recalculation attributes probability drift to state, each driver and seed; contributions sum to the observed probability change. Leave-one-driver-out calculations show sensitivity with other inputs and seed held fixed.
- Readable planning counterfactuals report utility/risk differences, not fabricated event probabilities.

## Isolated intervention scenarios

`POST /api/scenarios/counterfactual` accepts `baseline` with `actors`, optional `metadata` and `tick`, `assumptions` containing `{actor_id, field, delta}`, `ticks`, `seed` and optional unique `scenario_id`. It calculates control and intervention copies with identical seeds, cascade rules and forecast models. Both histories and explanations are persisted as separate runs and appear in the simulation picker. No canonical actors are mutated by this endpoint. Duplicate IDs return 409; invalid assumptions return 422.

This intervention model does not simulate fresh actor decisions or ingest new external events. Reports state that boundary. Planning comparisons and intervention comparisons are different kinds of counterfactual evidence and are labeled accordingly.

## Coverage and limitations

Reports cover normal simulation runs, live cycles using `run_simulation`, direct player actions, player turns and intervention scenarios. Player turns inherit the parent snapshot and tick number; parent snapshot content remains immutable. Historical reports are not fabricated for old ticks.

The legacy in-memory `/api/events` and `/api/world/state` interfaces are separate from persisted simulations and remain a Stage 8 consolidation task. Full isolation of normal decisions/actions from canonical ORM rows, a comprehensive run manifest and scientific calibration remain separate architecture work. Explainability does not establish those properties. Confidence is a model heuristic, not demonstrated empirical accuracy.

## Verification

Regression tests check deterministic text and state immutability, CLAIM preservation, effect lineage across independent origins, exact delta reconciliation, forecast attribution sums, restart comparisons, player/reaction coverage, continued tick numbering, and isolated intervention forecasts. Full backend/PostgreSQL migration checks, frontend build, runtime checks and production smoke are required for release.