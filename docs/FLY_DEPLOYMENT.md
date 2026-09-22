# Fly.io Production Deployment

WORLD ENGINE supports Fly.io as a production runtime in addition to the existing Railway deployment.

## Topology

One Fly App uses two process groups from the same backend image:

- `api` — FastAPI HTTP/WebSocket service.
- `worker` — dedicated live intelligence worker.

Fly process groups run on separate Machines and only the `api` process is attached to the public HTTP service.

Database and event bus remain external managed services:

- Fly.io Managed Postgres → `DATABASE_URL`
- Fly Upstash Redis → `REDIS_URL`

The deploy release command runs `alembic upgrade head` once before Machines are updated.

## Initial setup

Install and authenticate flyctl, then from `backend/`:

```bash
fly auth login
fly launch --no-deploy --copy-config
```

If `world-engine` is already taken globally, create a unique app name and either update `app` in `backend/fly.toml` or pass `-a <app-name>` on Fly commands.

## Managed Postgres

Create a Fly Managed Postgres cluster from the Fly dashboard or CLI and attach it to the app as `DATABASE_URL`.

The application normalizes standard `postgres://` / `postgresql://` URLs to the asyncpg SQLAlchemy form internally.

## Redis

Create a Fly Upstash Redis database in the same primary region where practical. Set the returned private Redis URL as the `REDIS_URL` app secret.

## Required secrets

```bash
fly secrets set \
  DATABASE_URL='<managed-postgres-url>' \
  REDIS_URL='<upstash-redis-url>'
```

Optional model secrets can be added separately:

```bash
fly secrets set AI_PROVIDER_KEY='...' AI_MODEL='...'
```

Do not commit secrets to `fly.toml`.

## Deploy

From `backend/`:

```bash
fly deploy
```

The deployment sequence is:

```
build Docker image
→ release Machine: alembic upgrade head
→ api Machine rolling update
→ worker Machine rolling update
→ /health/ready
```

## Scaling

Keep at least one API Machine running because Stage 7 uses persistent HTTP/WebSocket traffic.

The worker may be scaled above one Machine because Redis leader election protects the live-intelligence loop:

```bash
fly scale count api=1 worker=1
```

A second worker can be added for standby/failover:

```bash
fly scale count worker=2
```

Only the Redis lease leader executes live intelligence cycles.

## Verify

```bash
fly status
fly checks list
fly logs
curl --fail https://<app-name>.fly.dev/health/ready
curl --fail https://<app-name>.fly.dev/api/live-intelligence/status
curl --fail https://<app-name>.fly.dev/api/live-intelligence/operations-center
```

Then set the frontend production endpoints:

```
VITE_API_URL=https://<app-name>.fly.dev
VITE_WS_URL=wss://<app-name>.fly.dev
```

Stage 7 will then use Fly.io instead of the Railway endpoint.
