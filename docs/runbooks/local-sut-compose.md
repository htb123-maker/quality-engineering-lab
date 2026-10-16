# Local SUT Docker Compose Runbook

## Purpose

Start and verify the local system under test (SUT) used by API, database, cache,
and later mobile end-to-end tests.

The local stack contains:

- A Python HTTP API on `http://127.0.0.1:18000` that serves read-only business
  data, local authentication, cached catalog reads, background jobs, and a
  WebSocket event stream.
- PostgreSQL 16 on `127.0.0.1:15432`.
- Redis 7 on `127.0.0.1:26379`.

Since Week 10 Redis carries more than auth state: the catalog cache
(`cache:catalog:*`), its counters, the background job queue (`jobs:queue`,
`jobs:delayed`), and one record per job (`job:*`). Triage lives in
`docs/runbooks/redis-cache-and-consistency-triage.md`.

Since Week 11 the API also enforces a capability-based role model, scopes object
ids to their tenant, and keeps two write budgets (`ratelimit:write:*`) plus a
per-account sign-in failure counter (`auth:signin-failures:*`) in Redis. Triage
lives in `docs/runbooks/authorization-and-input-security-triage.md`.

The credentials in `.env.example` and Compose defaults are local development
values. They must never be reused for a shared or production environment.

## Prerequisites

- Docker Desktop or Docker Engine with the Compose v2 plugin.
- Docker daemon running.
- Project virtual environment created with `uv sync`.

Check Docker:

```powershell
docker version
docker compose version
```

## Start

From the repository root:

```powershell
.\scripts\start_sut.ps1
```

The script validates the Compose file, starts the services, waits for health,
and runs API, PostgreSQL, and Redis checks. Use `-SkipBuild` after the API image
has already been built and only configuration or SQL bind mounts changed.

## Verify

Host-side API and dependency checks:

```powershell
uv run --no-sync python scripts/check_sut.py --json
```

Read-only schema and seed verification through `psql`:

```powershell
.\scripts\verify_sut_database.ps1
```

Read-only schema contract check. The init scripts only run on an empty volume,
so this is what catches a database that has drifted from
`apps/compose/postgres/init/001_schema.sql`:

```powershell
uv run --no-sync python scripts/check_schema.py
```

```text
PASS Schema tables: tables=3, expected=3, names=catalog_items,users,workspaces
PASS Schema views: views=1, expected=1, names=workspace_catalog_summary
PASS Schema contract: tables=3, views=1, violations=0
Schema check: PASS
```

Integration tests:

```powershell
uv run --no-sync pytest tests/integration -q `
  --alluredir=artifacts/allure-results

uv run --no-sync pytest tests/api -q --alluredir=artifacts/allure-results
```

Parallel API runs use one PostgreSQL namespace per pytest worker, so the
read-only seed workspaces stay untouched:

```powershell
.\scripts\run_api_parallel.ps1 -Workers 4
```

The script finishes by running `scripts/check_sut.py`, which reports the seed
identity and fails when a test namespace such as `qa-ns-*` was left behind. A
stale namespace from an interrupted run is removed automatically at the start
of the next API session. See
`docs/runbooks/parallel-data-isolation-failures.md` for triage.

On Windows hosts where Smart App Control blocks the `psycopg` binary
extension, run the same integration tests through the locked Linux dependency
set:

```powershell
.\scripts\run_integration_linux.ps1
```

The script starts the Compose SUT, exports the frozen dependency list, and runs
`tests/integration` in a one-off Linux container attached to the Compose
network. This verifies the real PostgreSQL and Redis services without changing
the Windows security policy.

Expected key results:

```text
SUT ready: True
Day 5 database verification: PASS
Schema check: PASS
44 passed
```

`tests/integration` covers the read-only schema contract, transaction and
savepoint semantics, isolation-level visibility, a real row-lock wait with
`pg_locks` evidence, a real deadlock (`40P01`), `EXPLAIN (ANALYZE, BUFFERS)`
index evidence, cache-versus-database staleness, TTL-driven refresh,
negative caching, the background job lifecycle, and membership writes that must
land in PostgreSQL (role change, member removal, owner protection, and injection
containment). Lock-wait and deadlock triage lives in
`docs/runbooks/database-lock-and-deadlock-triage.md`.

Week 10 added these routes to the SUT:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/workspaces/{slug}/catalog` | Cached read; answers `X-Cache` and `X-Cache-TTL` |
| `POST` | `/api/v1/workspaces/{slug}/catalog/cache/refresh` | Queue a background cache refresh (202 + job id) |
| `GET` | `/api/v1/workspaces/{slug}/events` | WebSocket upgrade; pushes workspace events |
| `GET` | `/api/v1/jobs` | Queue depth and worker counters |
| `GET` | `/api/v1/jobs/{job_id}` | One job record, scoped to its workspace |

Week 11 added these routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/auth/permissions` | The caller's role and capability list |
| `GET` | `/api/v1/workspaces/{slug}/members` | Member list (needs `members:read`) |
| `POST` | `/api/v1/workspaces/{slug}/members` | Invite a member (needs `members:write`) |
| `PATCH` | `/api/v1/workspaces/{slug}/members/{user_id}` | Change a role; `owner` is never assignable |
| `DELETE` | `/api/v1/workspaces/{slug}/members/{user_id}` | Remove a member; owners are protected |
| `GET` | `/api/v1/workspaces/{slug}/catalog/items/{item_id}` | Read one item; foreign ids answer 404 |

Cache and queue knobs come from the Compose environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `QA_CATALOG_CACHE_TTL_SECONDS` | `60` | Positive cache entry lifetime |
| `QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS` | `10` | Negative entry lifetime for unknown slugs |
| `QA_JOB_TTL_SECONDS` | `900` | Job record lifetime |
| `QA_JOB_WORKER_ENABLED` | `1` | Start the in-process worker thread |
| `QA_JOB_WORKER_POLL_SECONDS` | `0.25` | Queue poll interval |
| `QA_WS_SUBSCRIBER_QUEUE_SIZE` | `64` | Per-subscriber event backlog before events are dropped |
| `QA_WS_POLL_SECONDS` | `0.2` | Event stream poll interval |

Week 11 security knobs:

| Variable | Default | Meaning |
| --- | --- | --- |
| `QA_RATE_LIMIT_WRITE_MAX` | `20` | Writes per client id per window |
| `QA_RATE_LIMIT_PRINCIPAL_MAX` | `40` | Writes per authenticated principal per window |
| `QA_RATE_LIMIT_WRITE_WINDOW_SECONDS` | `60` | Window shared by both buckets |
| `QA_AUTH_SIGNIN_FAILURE_MAX` | `10` | Failed password grants per (client, account) before 429 |
| `QA_AUTH_SIGNIN_FAILURE_WINDOW_SECONDS` | `60` | Sign-in lockout window, stored as the Redis key TTL |
| `QA_MAX_REQUEST_BYTES` | `65536` | Largest request body; larger bodies answer 413 |

Run the environment-aware API, Android, and iOS smoke matrix:

```powershell
uv run --no-sync python scripts/run_smoke_matrix.py
```

The summary is written to `artifacts/smoke-matrix.json`. A missing Android
device or a Windows iOS environment produces an explicit skip, not a false
pass. See `docs/runbooks/failed-quality-gate.md` for triage.

## Inspect

```powershell
docker compose -f apps/compose/compose.yaml ps

docker compose -f apps/compose/compose.yaml logs --tail 100 api
docker compose -f apps/compose/compose.yaml logs --tail 100 postgres
docker compose -f apps/compose/compose.yaml logs --tail 100 redis
```

Read-only SQL can be executed directly:

```powershell
docker compose -f apps/compose/compose.yaml exec -T postgres `
  psql -U qa -d qa -c "SELECT * FROM workspace_catalog_summary ORDER BY workspace_id;"
```

## Stop

Keep database and Redis volumes:

```powershell
.\scripts\stop_sut.ps1
```

Delete local test data:

```powershell
.\scripts\stop_sut.ps1 -RemoveVolumes
```

PostgreSQL initialization scripts only run when the `postgres-data` volume is
empty. After changing `001_schema.sql` or `002_seed.sql`, recreate the volume:

```powershell
.\scripts\stop_sut.ps1 -RemoveVolumes
.\scripts\start_sut.ps1
```

## Troubleshooting

### Docker command not found

Install Docker Desktop or Docker Engine with Compose v2 and reopen the terminal.

### Port already allocated

Set alternate host ports in `.env`, then restart:

```dotenv
QA_API_PORT=28000
QA_POSTGRES_PORT=25432
QA_REDIS_PORT=36379
```

Update the matching host-side URLs or run the check script with explicit
`--api-base-url`, `--postgres-dsn`, and `--redis-url` arguments.
The start and stop scripts automatically pass the root `.env` file to Compose.
When invoking `docker compose` directly with an override file, include
`--env-file .env`.

### API is live but ready is degraded

Run `docker compose logs postgres redis api`. The readiness response names the
failing dependency without exposing credentials.

### Seed data is missing

The PostgreSQL entrypoint does not replay init scripts against a non-empty
volume. Recreate the local volume with `stop_sut.ps1 -RemoveVolumes`, then start
the stack again.

### Docker Hub returns EOF or layer retries

When Docker Desktop inherits a Windows proxy that cannot forward registry
traffic, `docker compose up` may fail before any container starts.

On this workstation the verified recovery path is:

1. Stop Docker Desktop.
2. Back up `$env:APPDATA\Docker\settings-store.json`.
3. Set `ProxyHTTPMode` to `disabled`.
4. Start Docker Desktop and wait for the Linux engine.
5. Pull the three base images from an accessible registry mirror.
6. Re-tag the images with the names used by Compose.

```powershell
docker desktop stop

$settingsPath = Join-Path $env:APPDATA "Docker\settings-store.json"
Copy-Item $settingsPath "$settingsPath.bak" -Force

$settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
$settings | Add-Member `
  -NotePropertyName ProxyHTTPMode `
  -NotePropertyValue disabled `
  -Force
$settings | ConvertTo-Json -Depth 10 |
  Set-Content $settingsPath -Encoding utf8

docker desktop start

docker pull docker.1panel.live/library/python:3.12-slim
docker pull docker.1panel.live/library/postgres:16-alpine
docker pull docker.1panel.live/library/redis:7-alpine

docker tag docker.1panel.live/library/python:3.12-slim python:3.12-slim
docker tag docker.1panel.live/library/postgres:16-alpine postgres:16-alpine
docker tag docker.1panel.live/library/redis:7-alpine redis:7-alpine
```

The mirror is an environment workaround, not a project dependency. It can be
replaced with another trusted OCI registry when network conditions change.

## Safety

- This stack is for local test data only.
- Do not point `QA_POSTGRES_DSN` at a production database.
- The verification SQL runs in a read-only transaction.
- Do not place secrets in `.env.example`.
