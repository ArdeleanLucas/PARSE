---
name: daily-log-after-each-job
description: Mandatory closeout routine — update daily logs after every completed job with plan, actions, evidence, and current state.
version: 1.0.0
author: ParseGPT
license: MIT
metadata:
  hermes:
    tags: [logging, operations, closeout, mandatory]
---

# Daily Log After Each Job

Use this skill **immediately after completing any user-requested job**.

## Why
- Preserves reproducible audit trails for technical and research work.
- Prevents context loss across long PARSE and OpenClaw sessions.
- Keeps both per-day narrative logs and the global rolling log in sync.

## Log Targets

1. **Daily detailed report (task log directory):**
   - `~/.hermes/task-log/YYYY-MM-DD-<slug>.md`
   - Create for non-trivial jobs (multi-step work, debugging, deployments, cross-agent supervision).

2. **Rolling master log (always append):**
   - `~/.hermes/task-log.md`

3. **Profile daily memory note (always append):**
   - `~/.hermes/profiles/parse-gpt/memory/YYYY-MM-DD.md`

## Required Entry Structure

For each completed job, record:
- **Goal** (one line)
- **Plan** (numbered)
- **What was done** (concrete actions)
- **Evidence** (commands/tests/commit IDs/files)
- **Deviations** (if any)
- **Current state / next handoff**

## Execution Steps

1. Determine date and a concise slug for the task.
2. Read existing target files first.
3. Create or append the detailed report under `~/.hermes/task-log/` when warranted.
4. Append a concise summary block to `~/.hermes/task-log.md`.
5. Append the same-day profile note in `~/.hermes/profiles/parse-gpt/memory/YYYY-MM-DD.md`.
6. Re-read written sections to verify persistence.

## Pitfalls

- `read_file()` returns content with `LINE_NUM|` prefixes for inspection. Do **not** round-trip that text directly back into files with `write_file()` or you will pollute logs with embedded line numbers.
- If you need to rewrite an existing log file, either strip the `LINE_NUM|` prefixes first or use a tool/path that reads raw file contents (for example Python file I/O in `execute_code` or shell/Python via `terminal`).
- After any append or rewrite, re-read the affected lines and verify the file did not gain duplicated numbering, broken markdown, or malformed redactions.

## Content Rules

- Prefer factual, tool-grounded statements over narrative fluff.
- Include exact file paths and command names.
- Include pass/fail counts for tests when applicable.
- Redact secrets/tokens; never paste credential values.
- Keep language professional and concise.

## Quick Checklist Before Closing a Task

- [ ] Detailed per-task report created/updated (if non-trivial)
- [ ] `~/.hermes/task-log.md` appended
- [ ] profile memory daily file appended
- [ ] evidence included (tests, commits, outputs)
- [ ] no secrets leaked
