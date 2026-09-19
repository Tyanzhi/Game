# WORLD ENGINE Production Runtime

## Runtime topology

Production is split into independent roles:

- **Netlify frontend** — React/Vite Stage 7 UI.
- **API** — FastAPI HTTP/WebSocket service.
- **Live worker** — persistent world-intelligence scheduler.
- **PostgreSQL** — durable world state, events, forecasts and calibration.
- **Redis** — cross-process runtime event bus for realtime WebSocket delivery.
- **Migration job** — Alembic upgrade before API/worker startup.

Do not run the live scheduler inside multiple API replicas. In production keep:

```
EMBEDDED_LIVE_SCHEDULER=0
```

and run `python -m app.live_worker` as a dedicated worker process.

## Required environment

Backend:

```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
APP_ROLE=api
AUTO_CREATE_SCHEMA=0
EMBEDDED_LIVE_SCHEDULER=0
CORS_ALLOWED_ORIGINS=https://geopolitica20261.netlify.app
LIVE_INTELLIGENCE_INTERVAL_SECONDS=300
LIVE_SIMULATION_ID=live-world
```

Frontend build:

```
VITE_API_URL=https://<production-api-host>
VITE_WS_URL=wss://<production-api-host>
```

## Local production-equivalent boot

```bash
export POSTGRES_PASSWORD='replace-with-a-strong-secret'
docker compose -f docker-compose.prod.yml up -d --build
```

Readiness:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Expected services:

```bash
docker compose -f docker-compose.prod.yml ps
```

The migration container should exit successfully; PostgreSQL, Redis, API and live-worker should remain healthy/running.

## Deployment order

1. Provision PostgreSQL and Redis.
2. Deploy the backend image from `backend/Dockerfile`.
3. Run `alembic upgrade head` once against the production database.
4. Start API with `AUTO_CREATE_SCHEMA=0` and `EMBEDDED_LIVE_SCHEDULER=0`.
5. Start one live-worker with the same database/Redis environment.
6. Confirm `/health/ready`.
7. Set Netlify `VITE_API_URL` and `VITE_WS_URL`.
8. Deploy the Netlify frontend.
9. Confirm browser HTTP requests, WebSocket connection and Live Intelligence status.

## Scaling

Redis carries runtime events from worker/API processes to WebSocket subscribers. This removes the old requirement that the scheduler and WebSocket hub live inside one Python process.

For the initial production deployment, keep a single live-worker. Multiple live-workers would independently poll the same sources; the in-process cycle lock only prevents overlap inside one worker process, not across hosts. Horizontal worker leader election is a later hardening step.

## Health semantics

- `GET /health/live` — process is alive.
- `GET /health/ready` — database and Redis dependencies are reachable.
- `GET /health` — application/runtime status and Live Intelligence snapshot.

## Live intelligence

The dedicated worker continuously advances the persistent `live-world` timeline. It ingests live evidence, advances the simulation, persists forecasts/calibration and publishes realtime messages through Redis. The API subscribes to that bus and forwards messages to Stage 7 WebSocket clients.
