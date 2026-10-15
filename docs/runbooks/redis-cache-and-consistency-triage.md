# Redis Cache and Consistency Triage

## Purpose

Diagnose a catalog read that returns the wrong value, a cache that never hits, a
background job that never finishes, or an event stream that stays silent. Since
Week 10 the SUT answers three different questions on the same request path:

- What is in Redis right now?
- What is in PostgreSQL right now?
- Which of the two produced the response?

## Key map

| Key | Type | Written by | Lifetime |
| --- | --- | --- | --- |
| `cache:catalog:{slug}` | String (JSON) | Read path on a miss, worker on `catalog.cache_refresh` | `QA_CATALOG_CACHE_TTL_SECONDS` (60s) |
| `cache:catalog:{slug}:absent` | String (JSON) | Read path when the workspace does not exist | `QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS` (10s) |
| `cache:stats:{slug}:hit` / `:hit_negative` / `:miss` / `:db_reads` / `:invalidations` | String (counter) | Read path, write path | 3600s idle |
| `jobs:queue` | List | `POST .../catalog/cache/refresh` | No TTL; drained by the worker |
| `jobs:delayed` | Sorted set | Same endpoint with `delay_seconds` | No TTL; promoted when due |
| `job:{job_id}` | String (JSON) | Queue, worker | `QA_JOB_TTL_SECONDS` (900s) |
| `jobs:stats:processed` / `jobs:stats:failed` | String (counter) | Worker after each job | No TTL; monotone counters |

The response headers are the fast signal: `X-Cache: HIT | MISS | HIT-NEGATIVE |
BYPASS`, plus `X-Cache-TTL` with the remaining TTL in seconds.

## Inspect

```powershell
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli --scan --pattern "cache:catalog:*"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli TTL "cache:catalog:atlas"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli GET "cache:stats:atlas:db_reads"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli LLEN jobs:queue
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli ZCARD jobs:delayed
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli --scan --pattern "job:*"
docker compose -f apps/compose/compose.yaml logs --tail 100 api
```

The same information through the shared helpers, which is what the tests assert
on:

```powershell
uv run --no-sync python -c @"
from qa_core.cache import CatalogCacheProbe
from qa_core.config.settings import get_settings

settings = get_settings()
probe = CatalogCacheProbe(str(settings.redis_url), 'atlas')
entry = probe.entry()
print('cached:', bool(entry), 'ttl:', entry.ttl_seconds if entry else None)
print('stats:', probe.stats())
print('keys:', probe.keys())
"@
```

## Symptoms

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `X-Cache: MISS` on every read | A write ran between the reads, the key expired, or the TTL was configured to 1s | Compare `cache:stats:{slug}:miss` with `:db_reads`; both grow on a real miss |
| `X-Cache: BYPASS` | Redis is unreachable, so the read fell back to PostgreSQL | Check `/health/ready` `checks.redis`, then `docker compose logs redis` |
| A read returns a value that the database no longer has | The database was changed behind the API (direct SQL, batch job) and the entry has not expired yet | Expected stale window: delete `cache:catalog:{slug}` or wait for the TTL; see `tests/integration/test_redis_cache.py` |
| A read still returns the old value right after a successful write | The invalidation did not run for that workspace | Check `cache:stats:{slug}:invalidations` (must move) and confirm the write targeted the same slug |
| Unexpected `404` for a workspace that exists | A negative entry is still alive | `GET cache:catalog:{slug}:absent`; it expires within `QA_CATALOG_CACHE_NEGATIVE_TTL_SECONDS` |
| `db_reads` grows for a slug that does not exist | The negative entry expired between calls, or the client used a different slug each time | Read the same slug twice in one test; a fresh slug always costs one database read |
| Redis key count keeps growing | Cache keys and counters that no test owns | Namespace teardown purges `cache:catalog:{slug}*`; the remaining keys carry TTLs. Job records expire after `QA_JOB_TTL_SECONDS` |
| Job stays `queued` forever | Worker disabled or crashed | `GET /api/v1/jobs` must report `worker_enabled: true`; the API log must contain `Job worker started` |
| Job reports `failed` | The work could not complete (for example the workspace was deleted) | Read `job:{job_id}` and inspect `error`; `workspace_not_found` means the workspace disappeared while queued |
| `POST .../cache/refresh` answers `429` | The refresh shares the catalog write rate-limit budget | Wait for `Retry-After`, or send a fresh `X-QA-Client-Id` in tests |
| `GET /api/v1/jobs/{id}` answers `403` | The job belongs to another workspace | Read the job with a token of the workspace that queued it |
| WebSocket handshake answers `401` / `403` / `426` | Missing token / other workspace / no upgrade headers | 426 means an ordinary GET reached the event route |
| Event stream connects but stays silent | The client is not reading frames, or the event was produced before the connection existed | Events are only pushed to connected subscribers; a subscriber that stops reading loses events by design |
| Event stream closes right after connecting | The client key or version was wrong, or the account token expired mid-stream | Check the API log line `Event subscriber detached` |
| Integration run is slower than usual | A test waited on a fixed `sleep` instead of a deadline | Use `JobClient.wait`, `wait_for_final_record`, and `CatalogCacheProbe.wait_until_expired` |

## Clean a workspace by hand

```powershell
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli DEL `
  "cache:catalog:atlas" "cache:catalog:atlas:absent"

docker compose -f apps/compose/compose.yaml exec -T redis redis-cli DEL `
  "cache:stats:atlas:hit" "cache:stats:atlas:hit_negative" `
  "cache:stats:atlas:miss" "cache:stats:atlas:db_reads" `
  "cache:stats:atlas:invalidations"
```

Never delete `jobs:stats:*` while triaging a counter difference: the tests
compare before-and-after deltas, so a reset in the middle of a run makes the
failure harder to read. Queue counters are monotone on purpose, the same way
`pg_stat_database.deadlocks` is.

## Safety

- Redis here holds local test data, refresh tokens, idempotency records, cache
  entries, and job records only. Do not point `QA_REDIS_URL` at a shared cache.
- `FLUSHALL` is never needed for triage and destroys the seeded idempotency and
  auth evidence used by other suites.
