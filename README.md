# WORLD ENGINE

Living Geopolitical Simulation — an autonomous, data-driven geopolitical world engine.

## Product

WORLD ENGINE is a browser-based living-world simulation combining real-world data ingestion, structured world state, autonomous AI actors, scientific models, simulation, forecasting, and interactive visualization.

## Repository structure

- `frontend/` — React + TypeScript client
- `backend/` — FastAPI service
- `simulation/` — deterministic simulation engine
- `ai/` — actor reasoning, schemas, model gateway
- `data-pipeline/` — source adapters and event normalization
- `docs/` — architecture and product documentation
- `tests/` — automated tests
- `infrastructure/` — deployment and operations

## Core principle

The LLM is not the authoritative world-state engine. Structured state, deterministic rules, validation, and simulation control the world. AI interprets evidence and proposes decisions that must pass validation before execution.

## Development

The first vertical slice is:

`data → event → world state → AI actor → decision → simulation tick → forecast → live UI`


## Live World Intelligence

When the FastAPI service starts, WORLD ENGINE launches a live-intelligence loop.

Default cadence:

```
LIVE_INTELLIGENCE_INTERVAL_SECONDS=300
```

The interval can be changed with the environment variable above. Each cycle:

1. pulls recent world-news data from GDELT;
2. periodically refreshes macroeconomic indicators from World Bank;
3. validates, deduplicates and normalizes external data;
4. links events to known simulation actors;
5. classifies events into crisis/event domains understood by the simulation;
6. persists new evidence;
7. runs a live simulation tick when new evidence is available;
8. updates actor decisions, crisis propagation, markets and probabilistic forecasts.

Live endpoints:

- `GET /api/live-intelligence/status`
- `GET /api/live-intelligence/events`
- `GET /api/live-intelligence/outlook`
- `POST /api/live-intelligence/run-now`

The outlook contains model-generated possible future crisis branches, expected actor actions and probabilistic forecasts. These are simulation outputs with uncertainty, not assertions that future events will occur.

## Turn mode

The game turn endpoint is:

```
POST /api/simulations/{simulation_id}/turns
```

A turn resolves in this order:

```
player action
→ resource/AP validation
→ action execution
→ AI decisions for all non-player actors
→ reactions and third parties
→ crisis/event propagation
→ delayed effects
→ forecasts
→ new simulation state
```

The actor controlled by the player is excluded from AI decision generation during that turn.


## Live Prediction Center

The live timeline uses a persistent simulation id (default: `live-world`) instead of creating an isolated simulation for every monitoring cycle. This lets crisis state, beliefs, strategic memory, pending forecasts and forecast calibration evolve across successive real-world updates.

Prediction Center endpoints:

- `GET /api/live-intelligence/prediction-center`
- `GET /api/simulations/{simulation_id}/prediction-center`

The center exposes:

- simultaneous 1 / 7 / 30 tick horizons;
- actor-level probabilistic stability outlooks;
- baseline, stabilization, escalation and economic-shock futures;
- probabilistic causal graph edges derived from active crises and recent effects;
- Brier calibration statistics accumulated after observed outcomes;
- market-stress and active-crisis deltas versus the previous snapshot.

Alternative futures share the same deterministic forecast noise so scenario differences come from assumptions/drivers rather than random variation.

The Stage 7 frontend renders these outputs as a horizon switcher, scenario matrix, calibration panel and causal graph. New live evidence advances the same `live-world` timeline, so the displayed probabilities can change as new events are ingested.


## Stage 7 Alert & Operations Center

The Operations Center turns simulation state into an operator-facing alert queue rather than requiring the user to inspect every subsystem manually.

Endpoints:

- `GET /api/simulations/{simulation_id}/operations-center`
- `GET /api/simulations/{simulation_id}/alerts/history`
- `POST /api/simulations/{simulation_id}/alerts/{alert_id}/state`
- `GET /api/live-intelligence/operations-center`
- `GET /api/live-intelligence/alerts/history`

Alert generation combines active crisis intensity/escalation/contagion, market stress, actor stability/domestic pressure/information quality and forecast uncertainty. Alerts are assigned a deterministic severity and operational posture.

Alert lifecycle is persistent:

```
open → acknowledged → open
  ↘
   resolved automatically when the underlying condition disappears
```

Acknowledgement state, operator note, first/last seen tick, occurrence count and recent resolution history are persisted in PostgreSQL.

Crisis alerts carry evidence provenance where available: originating external event, confidence, independent-source count, mean source quality and source URLs. Model-generated alerts are explicitly marked as model-state or model-forecast evidence.

The Stage 7 frontend renders:

- critical/high/open/acknowledged/resolved counters;
- operational posture;
- active alert queue;
- evidence/provenance and external source links;
- operator runbooks;
- acknowledge/reopen controls;
- actor/crisis navigation;
- command brief, priorities and recommended actions;
- watch actors and crises;
- recently resolved alert history.

The Operations Center is an analytical/operator interface. Forecasts and alert severity are model outputs with uncertainty, not assertions that future events are certain.
