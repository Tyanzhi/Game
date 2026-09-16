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
