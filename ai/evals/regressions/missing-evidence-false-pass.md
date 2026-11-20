# Agent Regression: Missing Evidence Was Classified As PASS

## History

The initial draft considered only observed `FAILED` states. With an empty
artifact set it returned `PASS`.

## Correction

Agent v1 now checks evidence presence and `UNKNOWN` signal state before normal
classification. Missing evidence returns `INSUFFICIENT_EVIDENCE` and requires
human review.

## Guarded Cases

- `GT-025`: unknown quality signal and no evidence.
- `GT-026`: PASS signal but no evidence artifact.
- `GT-027`: artifact present but no signal set.
- `GT-028` to `GT-030`: partial evidence with one unknown required signal.

## Human Review

The correction was accepted because the expected failure is safe: the agent
reports insufficient evidence instead of claiming a pass. The agent still has
no write, merge, defect-close, or release authority.
