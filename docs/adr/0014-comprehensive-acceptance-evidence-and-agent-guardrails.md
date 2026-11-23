# ADR-0014: Comprehensive Acceptance Evidence and Agent Guardrails

## Context

Week 32 is the final acceptance week. The repository already has API,
database, cache, Android, iOS, performance, recovery, CI, trend, and defect
workflows. A final demo is only credible if every completion claim is tied to
the source, test, run, or artifact that produced it.

The evidence also feeds a read-only Agent baseline. Logs, HTML, API responses,
page source, and issue text can contain untrusted instructions. A plausible
summary is not a substitute for deterministic test and platform results.

## Decision

1. Week 32 acceptance is a mapping from deliverables to repository evidence.
   Plans, prose, static checks, and skipped tests cannot satisfy a platform
   deliverable.
2. The existing quality pipeline remains the single entry point. Quality,
   Compose SUT, Android emulator, macOS iOS Simulator, performance, and Agent
   Eval are required jobs. BrowserStack remains optional because a quota block
   is external evidence, not a product pass.
3. Every required job failure produces a synthetic `FAILED` trend record when
   no JUnit file exists. A missing artifact is never omitted from the result.
4. The Week 32 Agent is deterministic and read-only. It classifies structured
   signals and evidence references only. It does not call a model, execute
   tests, modify a repository, change thresholds, create defects, merge, or
   release.
5. Missing evidence, an empty signal set, or an `UNKNOWN` signal returns
   `INSUFFICIENT_EVIDENCE`. `BLOCKED`, `NOT RUN`, and `DEFERRED` remain
   incomplete and are never promoted to `PASS`.
6. The first five monitoring agents have explicit input, tool, output,
   permission, and failure-fallback contracts in
   `ai/agents/registry.yaml`. Their tool allowlist contains read operations
   only.
7. Proposed actions always require human approval. A defect is closed only
   after a human reviews the fix, regression evidence, and affected test/run
   links.
8. Automated acceptance of a Golden Task run is reported separately from human
   suggestion adoption. The pipeline must not invent a human review when no
   reviewer evidence exists.
9. Required evidence names are explicit; a successful job without its expected
   artifact is represented as `NOT RUN` and fails the trend gate.
10. Human review is bound to the Golden Task file SHA-256 and a `valid_until`
    date. A stale or mismatched review cannot satisfy the AI gate.
11. CI and performance monitoring agents consume collected artifacts and write
    a read-only `agent-monitor.json`; their findings feed the trend gate.

## Consequences

- A green static check cannot make a failed or missing platform run disappear.
- Provider failures remain visible as `BLOCKED`, while required coverage must
  still be supplied by another accepted path such as the macOS Simulator.
- An Agent outage or malformed evidence reduces automation quality but does not
  stop deterministic tests from producing their own results.
- Golden Task accuracy, evidence-reference rate, latency, token use, and cost
  are reproducible. Human modification and adoption rates remain a separate
  review activity.
- Formal defect closure remains a human decision even when an automated
  regression is green.
