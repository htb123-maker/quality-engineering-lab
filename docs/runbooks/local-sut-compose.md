# Local SUT Docker Compose Runbook

## Purpose

Start and verify the local system under test (SUT) used by API, database, cache,
and later mobile end-to-end tests.

The local stack contains:

- A read-only Python HTTP API on `http://127.0.0.1:18000`.
- PostgreSQL 16 on `127.0.0.1:15432`.
- Redis 7 on `127.0.0.1:16379`.

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

Integration tests:

```powershell
uv run --no-sync pytest tests/integration -q `
  --alluredir=artifacts/allure-results

uv run --no-sync pytest tests/api -q -m smoke `
  --alluredir=artifacts/allure-results
```

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
4 passed
1 passed
```

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
QA_REDIS_PORT=26379
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
