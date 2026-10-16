# Authorization and Input Security Triage

## Purpose

Diagnose a request that was *rejected* when it should have been accepted, or
*accepted* when it should have been rejected. Since Week 11 the SUT answers four
different questions on every authenticated call, and the status code is the
fastest way to tell them apart:

| Status | Error code | Means | Owner |
| --- | --- | --- | --- |
| 401 | `authentication_required` | No credential was presented | test or client |
| 401 | `invalid_token` | Signature, issuer, expiry, or the user row is gone | auth layer |
| 403 | `permission_denied` | Authenticated, but the role lacks the capability, or the object belongs to another tenant | permission layer |
| 403 | `owner_protected` | A write tried to change or delete an owner membership | permission layer |
| 403 | `role_escalation_forbidden` | An admin tried to grant `admin` | permission layer |
| 403 | `self_modification_forbidden` | A caller tried to edit or remove its own membership | permission layer |
| 404 | `member_not_found` / `item_not_found` | The id is not visible in this workspace: unknown *or* another tenant's | product |
| 413 | `payload_too_large` | Body exceeded `QA_MAX_REQUEST_BYTES` | test |
| 415 | `unsupported_media_type` | JSON API received another media type | test |
| 429 | `rate_limited` | Write budget or sign-in failure budget is spent | environment or security control |

## Capability map

The SUT decides with capabilities, not role strings. `GET /api/v1/auth/permissions`
returns the caller's own list, which is the quickest way to see what a role can
do without reading code.

| Capability | owner | admin | member | viewer |
| --- | --- | --- | --- | --- |
| `catalog:read` | yes | yes | yes | yes |
| `catalog:write` | yes | yes | yes | no |
| `catalog:refresh` | yes | yes | yes | no |
| `events:read` | yes | yes | yes | yes |
| `jobs:read` | yes | yes | yes | yes |
| `members:read` | yes | yes | yes | no |
| `members:write` | yes | yes | no | no |
| `audit:read` | yes | yes | no | no |

## Key map

| Key | Written by | Lifetime |
| --- | --- | --- |
| `ratelimit:write:client:{sha256(client_id)}` | Write endpoints | `QA_RATE_LIMIT_WRITE_WINDOW_SECONDS` (60s) |
| `ratelimit:write:principal:user:{user_id}` | Write endpoints | Same window |
| `auth:signin-failures:{sha256(client|email)}` | Failed password grants | `QA_AUTH_SIGNIN_FAILURE_WINDOW_SECONDS` (60s) |

The principal bucket exists because `X-QA-Client-Id` is caller-controlled: a
client that rotates the header still spends its per-user budget, and
`X-RateLimit-Scope: principal` says so on the refusal.

## Inspect

```powershell
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli --scan --pattern "ratelimit:*"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli GET "ratelimit:write:principal:user:1"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli TTL "ratelimit:write:principal:user:1"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli --scan --pattern "auth:signin-failures:*"
docker compose -f apps/compose/compose.yaml logs --tail 100 api | Select-String "Rate-limit|Sign-in"
```

The same information through the shared helpers, which is what the tests assert
on:

```powershell
uv run --no-sync python -c @"
from qa_core.config.settings import get_settings
from qa_core.security import SignInThrottleProbe, principal_budget_key

settings = get_settings()
probe = SignInThrottleProbe(str(settings.redis_url))
print('key:', principal_budget_key(1))
print('failures:', probe.failures(client_id='manual', email='owner@atlas.example'))
print('ttl:', probe.ttl_seconds(client_id='manual', email='owner@atlas.example'))
"@
```

## Symptoms

| Symptom | Likely cause | Action |
| --- | --- | --- |
| A role that should be allowed gets 403 | Capability missing from `ROLE_CAPABILITIES` in `app.py` | Fix the registry, then run `tests/unit/test_role_matrix.py`; the mirror in `qa_core/security/roles.py` must be updated in the same change |
| A role that should be denied gets 200 | Handler compares roles itself instead of asking `has_capability` | Replace the literal comparison with a capability check |
| A cross-tenant read returns 200 | `_workspace_scope` was skipped, or the query dropped the `workspace_id` predicate | Check the handler's scope call and the repository predicate, e.g. `tests/api/test_bola_idor.py` |
| Another tenant's `item_id` returns 403 instead of 404 | Item read path leaks existence through the status code | Return `item_not_found` for both unknown and foreign ids |
| 403 arrives for *every* member change | The caller is an admin and the target is an owner, or the caller is editing itself | Check `owner_protected` / `self_modification_forbidden` in the response body before changing code |
| Writes start failing with 429 in unrelated tests | A principal or client bucket was left spent | Confirm the namespace pool clears `ratelimit:write:principal:*` on release; clear it manually with `DEL` while triaging |
| `Retry-After` is missing on a 429 | The 429 was not produced by a budget | Check the body: `rate_limited` from a budget always carries `Retry-After`; only budgets do |
| Login returns 429 although the password is correct | The account has spent its failed-attempt budget | Read the TTL of `auth:signin-failures:*`, wait it out, or clear the key in a test |
| Login never trips the throttle | `QA_AUTH_SIGNIN_FAILURE_MAX` is 0, or Redis is down and the control fails open | Check `.env` and the API log for `Sign-in throttle` warnings |
| 413 on a request body that looks small | The JSON is padded by a test helper, or `QA_MAX_REQUEST_BYTES` was lowered | Compare `Content-Length` with the configured limit |
| 415 where 400 used to appear | Week 11 split the two: malformed body is 400, unreadable media type is 415 | Update the expectation; OAuth2 endpoints still answer 400 `invalid_request` |
| Traversal-looking slug reaches PostgreSQL | `WORKSPACE_SLUG_PATTERN` was bypassed | Slugs must be validated before the query; see `tests/api/test_input_security.py` |

## Failure classification

`qa_core.api_errors.classify_response` maps every documented code to one owner:

- `test`: 400 body problems, 413, 415, 422 — the caller sent something unusable.
- `auth`: 401 and the OAuth2 grant errors.
- `permission`: every 403 in the table above.
- `product`: 404/409 for objects the API knows about.
- `environment`: 429, 503 — pacing and infrastructure.

When a failing run shows `test` for a security assertion, the expectation is
usually wrong, not the server. When it shows `permission`, read the error code
before touching the SUT: `owner_protected` and `role_escalation_forbidden` are
intentional refusals.

## Reset a polluted budget

```powershell
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli DEL "ratelimit:write:principal:user:1"
docker compose -f apps/compose/compose.yaml exec -T redis redis-cli --scan --pattern "ratelimit:write:client:*" | ForEach-Object { docker compose -f apps/compose/compose.yaml exec -T redis redis-cli DEL $_ }
```

```sql
-- Confirm a membership change actually landed, instead of trusting the 200.
SELECT id, workspace_id, email, role, status
FROM users
WHERE workspace_id = :workspace_id
ORDER BY id;
```
