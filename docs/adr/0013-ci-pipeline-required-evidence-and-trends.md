# ADR-0013: CI Required Evidence, Optional Cloud, and Bounded Trends

## Context

Week 31 needs one commit to trigger API, Android, iOS, performance, report, and
quality-gate execution. External providers and macOS runners can be unavailable
even when repository code is correct.

## Decision

1. Quality, Compose SUT, Linux Android emulator, macOS iOS Simulator, and
   performance smoke are required jobs.
2. BrowserStack cloud execution is optional evidence because the weekly gate
   accepts either a macOS Runner or a device cloud. A quota-blocked cloud run is
   recorded as `BLOCKED` and does not replace the required Simulator result.
3. A required job failure synthesizes a `FAILED` trend record even if the job
   produced no JUnit file.
4. Trend history uses bounded GitHub Actions cache and uploaded JSON/HTML.
   Missing cache produces one valid point, not a false pass.
5. Formal GitHub Issues creation requires an explicit human approver. Local
   pytest failures create drafts only.

## Consequences

- A provider outage does not hide missing iOS coverage when the Simulator also
  fails.
- A required job cannot disappear from the trend by failing before JUnit output.
- Cloud success is still archived, while cloud quota failure is traceable.
- Cache is not a permanent analytics database.
- Agents and CI cannot create or close defects without human approval.
