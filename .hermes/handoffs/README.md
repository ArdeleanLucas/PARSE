# `.hermes/handoffs/` convention

This directory is the canonical coordinator-owned task queue for PARSE lanes.

## Layout

```text
.hermes/handoffs/
  parse-builder/    # historical directory for parse-front-end
  parse-back-end/
  parse-gpt/        # historical directory for parse-coordinator
```

Each queued task file lives at:

```text
.hermes/handoffs/<agent>/<YYYY-MM-DD>-<slug>.md
```

## Lifecycle

- `queued` — file created; task is ready to be picked up
- `in-progress` — the lane has started actively executing it
- `done` — move the file into `.hermes/handoffs/<agent>/done/`

## Required front matter

```yaml
---
agent: parse-front-end
queued_by: parse-coordinator
queued_at: 2026-04-26T16:00:00Z
status: queued
related_prs:
  - 58
---
```

## Body format

Keep the body structure aligned with the old queue-prompt docs:

1. Goal
2. Why this is the next task now
3. Grounded context
4. Specific task / scope boundary
5. Required validation
6. What comes after this task

## Migration rule

- New queueing should happen here, not through merge-to-main `docs: queue ...` PRs.
- Human-facing lane names are `parse-front-end`, `parse-back-end`, and `parse-coordinator`; preserve the historical on-disk directories unless a dedicated migration PR changes them.
- Historical queue-prompt PRs remain the audit trail and are indexed in `docs/reports/2026-04-26-historical-queue-prompt-prs.md`.
- If a lane already has an old-pattern queue PR open, that PR can serve as historical context, but the durable task source should move here.
