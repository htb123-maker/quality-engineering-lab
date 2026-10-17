# Fault Injection and Defect Draft Triage

## Purpose

This runbook covers Week 12 transport faults, PostgreSQL connection budgets, and
the local defect-draft artifact. It does not authorize creating a formal issue,
changing priority, or closing a defect.

## Start the Fault-Injection Plane

```powershell
.\scripts\start_sut.ps1 -FaultInjection
```

The optional profile starts Toxiproxy on the host control port `18474`. Normal
SUT startup without `-FaultInjection` does not require the image.

Check the control API:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:18474/proxies
```

Run only the transport-fault cases:

```powershell
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
uv run --no-sync pytest tests/api/test_fault_injection.py -q -m fault_injection
```

Each xdist worker owns one proxy port from `18100` onward. Tests delete their
proxies in teardown. If Toxiproxy is unavailable, the cases skip; a skip is not
a pass and must be recorded as an environment limitation.

## Understand the Faults

| Toxic | What it proves | Expected boundary |
| --- | --- | --- |
| `latency` | Read timeout and bounded retries | Client raises after its configured attempts |
| disabled proxy | Fail-fast connection error | `httpx.ConnectError`, not a hung request |
| `timeout` | Packets stop for a bounded interval | Request times out; removing the toxic restores traffic |
| `reset_peer` | Established connections can be cut | Reconnect path is exercised |

Do not use retries to hide a product failure. Retry only reads or explicitly
idempotent operations, and keep the attempt count visible in logs.

## Inspect the Connection Budget

Configuration:

```text
QA_POSTGRES_MAX_CONNECTIONS=16
QA_POSTGRES_CONNECTION_TIMEOUT_SECONDS=2
```

All SUT database helpers use the same process-wide budget. A saturated budget
eventually returns `503 database_unavailable`; the readiness check also reports
the PostgreSQL error class. This is expected backpressure, not a reason to
increase the limit blindly.

The unit-level evidence is:

```powershell
uv run --no-sync pytest tests/unit/test_connection_budget.py -q
```

The API-level evidence is the concurrent eight-writer case in
`tests/api/test_parallel_isolation.py`.

## Read the Defect Draft

When a call-phase test fails, pytest writes:

```text
artifacts/defect-drafts/defects.jsonl
```

Each line is one `DefectDraft`. Important fields:

- `fingerprint.short_id` and `fingerprint.digest`
- `evidence.pytest_nodeid`
- `evidence.commit`
- `evidence.command`
- `evidence.first_failure`
- `evidence.allure_results_path`
- `requires_human_approval`
- `automatically_created_issue`

Inspect it through the typed store:

```powershell
uv run --no-sync python -c "from pathlib import Path; from qa_core.reporting import JsonlDefectDraftStore; s=JsonlDefectDraftStore(Path('artifacts/defect-drafts/defects.jsonl')); print(len(s.read_all()))"
```

Search exact duplicates first. Then compare test id and error signature. Do not
deduplicate on a short visible message alone.

## Human Approval

Automation may collect evidence, compute a fingerprint, classify the boundary,
search for candidates, and generate a draft.

A named human must approve any transition to `new`, `confirmed`, priority,
owner, `duplicate`, `rejected`, `deferred`, `wont_fix`, `verified`, or
`closed`. The lifecycle helper rejects an empty approver and has no automatic
path to `closed`.

## Exit Criteria

- Fault is removed and the affected request passes again.
- The failure has a stable test identity, fingerprint, and evidence path.
- The primary boundary is classified as product, test, environment, or
  infrastructure.
- A formal issue exists only after human approval.
