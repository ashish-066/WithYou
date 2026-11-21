# Deploying Alex

What runs where, how to run the whole stack in containers, and what a hosting
platform must provide. The hosting platform itself is not chosen yet; the
platform-specific parts (infrastructure as code, CD pipeline) come once it is.

## Images

All images are built from the **repo root** (the Python services share
`shared/`). Base images are pinned by digest.

| Image | Build | Runs | Health |
|---|---|---|---|
| api | `docker build -f avatar/Dockerfile --target api .` | `uvicorn main:app` on 8001 | liveness `GET /health`, readiness `GET /ready` (Redis + Postgres; 503 when either is down) |
| agent | `docker build -f avatar/Dockerfile --target agent .` | `python -m agents.entrypoint start` | `GET :8081/` (200 once connected to LiveKit), `GET :8081/worker` (active jobs) |
| worker | `docker build -f worker/Dockerfile .` | `python worker.py` | `python -m core.readiness` (set up, consumer group joined, heartbeat < 60 s old) |
| frontend | `docker build -f frontend/Dockerfile .` | nginx on 8080, serves the build and proxies `/api` | `GET /healthz` |

All run as a non-root user. Images contain no `.env` files (`.dockerignore`);
configuration comes from environment variables (see `avatar/.env.example`,
`worker/.env.example`, and `docs/SECRETS.md` for where secrets live).

The **migration step** uses the api image: `python -m alex_db.migrate`. Run it
before starting a new version; in production the services refuse to start on
an out-of-date schema.

## Full stack locally

```bash
docker compose up --build
```

Open http://localhost:8080. It uses `avatar/.env` and `worker/.env` for the
API keys, its own Redis (password, AOF on) and Postgres (volumes `redis-data`,
`postgres-data`), and a separate Docker daemon (`sandbox-docker`) for
candidate code. Only the frontend port is published, on 127.0.0.1.

- Create an account: sign up at `/login`, or
  `docker compose exec api python -m scripts.create_user --platform-admin ...`.
- Don't run this and the host processes (mprocs, `agents.entrypoint dev`) at the
  same time against one LiveKit project: LiveKit may dispatch a call to the
  other stack's agent, which reads a different Redis.
- `docker compose down` waits for running interviews to finish (agent drain, up
  to an hour). `docker compose kill agent` ends them immediately.
- `docker compose down -v` also deletes the local data volumes.

## Production requirements

### Same origin for the frontend and API

The app calls relative `/api/...` URLs and the session cookie is
`SameSite=Strict`, so the browser must see the frontend and API on **one
origin**. Either run the frontend image (its nginx proxies `/api/` to
`API_UPSTREAM`), or, with a CDN or static host, add a rule that forwards
`/api/*` to the API with the `/api` prefix removed. Set `CORS_ORIGINS` to the
public origin.

### Client IP

Set `TRUSTED_PROXY_HOPS` on the API to the number of proxies that append to
`X-Forwarded-For` in front of it: 1 for the frontend nginx alone, 2 for nginx
behind a cloud load balancer. Rate limits key on that IP. Too low makes all
users share one limit; too high lets clients forge their IP.

### TLS and headers

TLS terminates at the load balancer or CDN; redirect HTTP to HTTPS there. The
frontend nginx sets HSTS, CSP, `X-Frame-Options: DENY`, `nosniff`,
`Referrer-Policy` and `Permissions-Policy`. The CSP allows LiveKit Cloud
(`CSP_CONNECT_SRC`, default `wss://*.livekit.cloud https://*.livekit.cloud`)
and `cdn.jsdelivr.net`, where the code editor loads from. A self-hosted
LiveKit server needs its URL added to `CSP_CONNECT_SRC`.

### Rolling deploys without dropping interviews

- **Agent:** on SIGTERM it stops taking new interviews and waits up to
  `AGENT_DRAIN_TIMEOUT_SECONDS` (default 3600) for running ones to end. The
  platform's termination grace period must be **longer** than that (e.g.
  ECS `stopTimeout` is capped at 120 s, so run agents on EC2/Kubernetes with
  `terminationGracePeriodSeconds: 3700`, or accept that a deploy ends calls).
  Start new agents before stopping old ones.
- **Worker:** on SIGTERM it finishes the message it is processing, then exits;
  messages it had read but not started stay pending and are reclaimed by other
  workers. A second SIGTERM stops it immediately. Grace period: 120 s.
- **API:** stateless (live calls are in Redis); uvicorn finishes open requests
  within 30 s. Route traffic by `GET /ready`.

### Code sandbox

With `SANDBOX_MODE=docker` (required in production) the worker runs each test
case in a throwaway container with no network, read-only root, no
capabilities, and memory/CPU/process limits. It uses the Docker daemon at
`DOCKER_HOST`:

- Run that daemon on **separate, isolated hosts** (a dedicated node pool or VM),
  reachable only from the workers, over TLS (`DOCKER_HOST=tcp://...:2376`,
  `DOCKER_TLS_VERIFY=1`, `DOCKER_CERT_PATH`). Never mount the application host's
  `/var/run/docker.sock` into the worker: that gives the worker root on that host.
- Prefer gVisor on those hosts (`SANDBOX_RUNTIME=runsc`).
- `SANDBOX_IMAGE` must be pinned by digest in production (the worker refuses
  to start otherwise). The worker pulls it at start-up.

### Placement and scaling

- Agents in the same region as the LiveKit Cloud project (latency and voice
  quality). Scale on active jobs (`/worker`) or CPU; the LiveKit worker reports
  itself full at 70% load.
- Workers: scale on the backlog of `interview:requests` for group `brain-workers`
  (`XINFO GROUPS interview:requests`: `lag` and `pending`).
- Managed Postgres with point-in-time recovery, and managed Redis with a
  password, TLS (`rediss://`) and persistence (see `docs/BACKUPS.md`).

### Environments

dev, staging and production each get their own LiveKit project, API keys,
database, Redis, bucket and `AUTH_SECRET`. Nothing is shared between them.

## Updating base images

Base images are pinned as `tag@sha256:digest` in the Dockerfiles and
`docker-compose.yml`. To update: `docker pull <tag>`, read the new digest with
`docker image inspect --format '{{index .RepoDigests 0}}' <tag>`, replace it,
and rebuild and test. The sandbox image digest is also in `SANDBOX_IMAGE`.

## AWS

The chosen host is AWS (Mumbai), starting with the pilot layout in
[AWS_SETUP.md](AWS_SETUP.md): Terraform in `infra/terraform`, server-side deploy in
`deploy/`, and the GitHub workflow `.github/workflows/deploy.yml`.
