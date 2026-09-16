# WORLD ENGINE Architecture

## Vertical slice

REAL WORLD DATA
→ INGESTION
→ NORMALIZED EVENT
→ VALIDATION
→ WORLD STATE
→ ACTOR PERCEPTION
→ DECISION
→ SIMULATION TICK
→ FORECAST
→ LIVE UI

## Source of truth

The deterministic simulation state is authoritative. LLM outputs are advisory and structured. Every AI action is schema-validated, rule-validated, and world-state validated before execution.

## Initial domains

1. Diplomacy
2. Economy
3. Strategic security/conflict
4. Energy
5. News/events
6. Forecasting

## Initial actors

The MVP uses a small configurable set of major state/institutional actors. The actor list is configuration, not a political ranking.

## Reproducibility

Every simulation run records:

- simulation_id
- model_version
- dataset_version
- random_seed
- parameters
- timestamp

## Security

External text is untrusted input. Raw retrieved content must be sanitized and converted into structured facts/claims before reaching decision logic. Secrets are never committed to the repository.
