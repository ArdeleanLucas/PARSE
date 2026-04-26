---
agent: parse-back-end
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - none — research-only, no code changes, runs in parallel with PR #68 review
related_skills:
  - parse-rebuild-health-audit
  - codebase-inspection
  - systematic-debugging
---

# parse-back-end while-waiting task — backend test failure audit + mcp_adapter architecture audit

**Why this exists:** PR #68 (chat_tools.py decomposition PR 1, the cherry-pick replay onto rebuild) is awaiting coordinator review per the wait-rule in the amended PR #59. Use the wait window for two short research items that are useful regardless of when PR 2 unblocks.

**Hard rules:**

- No code changes. Two output docs only.
- No new PRs against `python/` source files.
- Do NOT start chat_tools PR 2 until parse-gpt explicitly signals PR #68 is reviewed.
- Working environment guard from PR #59 still applies — verify rebuild clone + remote before any push.

## Task A — Classify the 8 failing rebuild backend tests

PR #64's gate evidence captured `658 passed / 8 failed / 2 skipped / 1 warning` for the rebuild backend at `f9aa3db1aa`. The 8 failures haven't been classified, so the parity gate is comparing against a baseline that itself fails.

### Deliverable

One markdown file:
`.hermes/handoffs/parse-back-end/2026-04-26-rebuild-backend-test-failure-audit.md`

### Procedure

1. From the rebuild clone (`/home/lucas/gh/tarahassistant/PARSE-rebuild`), check out current `origin/main` (after PR #61's merge — i.e., wherever main is now, not necessarily `f9aa3db1aa`). Note the SHA in the audit doc.
2. Run `python3 -m pytest python/ -x --tb=short` and capture the 8 failures (names + full traceback summaries).
3. For each failure, classify into ONE of:
   - **accepted-quirk** — the failure is intentional, listed (or should be listed) in `docs/plans/option1-phase0-shared-contract-checklist.md` §3 "Known accepted oracle quirks." If you add new entries to that list, do it as a comment in the audit doc, not as an edit to the checklist (parse-gpt owns that file).
   - **real-bug** — actual regression or oversight; needs a follow-up issue or fix PR. Note the suspected cause based on traceback + git blame.
   - **fixture-issue** — the test depends on a workspace fixture, env var, or external resource that's missing or misconfigured in CI. Note what's missing.
4. Produce an output table: test name, classification, one-line note. Add a summary count at the top.
5. If any test classifies as **real-bug**, separately list it in a "follow-up actions" section at the bottom — but **do not file the follow-up issues yourself** (coordinator filing is parse-gpt's job).

### Acceptance

- All 8 failures classified
- SHA of the rebuild HEAD used for the audit recorded at the top
- Doc length: keep under 200 lines

## Task B — `python/ai/mcp_adapter.py` architecture audit

`mcp_adapter.py` is 2050 LoC, untouched in the rebuild, and named in PR #59's prompt as the next backend monolith after `chat_tools.py`. Pre-loading the architecture knowledge now means the next prompt can be precise instead of speculative.

### Deliverable

One markdown file:
`.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-architecture-audit.md`

### Procedure

1. Read `python/ai/mcp_adapter.py` end-to-end. No edits.
2. Inventory:
   - **Public surface**: classes, functions, and methods exported. What does `python/server.py` import from it? What does `python/external_api/catalog.py` import from it?
   - **Tool exposure layers**: per the README claim, mcp_adapter exposes "32 native + 36 with workflow macros + `mcp_get_exposure_mode`". Where is each layer constructed? Which methods compute each count?
   - **Coupling to `chat_tools.py`**: PR #68 split chat_tools into per-domain modules. Does mcp_adapter import from `chat_tools` (the registry) or from the new `python/ai/tools/` modules directly? If the former, that import is a future refactor target — note it.
   - **Coupling to `workflow_tools.py`**: how are workflow macros wired in? Same import pattern as chat tools, or different?
3. Propose decomposition seams. Group the file's contents into 3–5 candidate modules under a future `python/ai/mcp/` directory:
   - Suggested file names
   - Approximate LoC per file
   - Risk per file (low/medium/high)
   - Test surface that would need to follow each module
4. Identify which seam should be PR 1 (lowest risk, smallest behavior surface — same logic that made the read-only tools PR #229's first slice).
5. Note any existing `python/test_mcp_*.py` or `python/adapters/test_mcp_adapter.py` tests, and where their assertions would need to relocate post-decomposition.

### Acceptance

- Public surface inventory complete
- 32/36/`mcp_get_exposure_mode` counts confirmed (or discrepancy noted)
- 3–5 candidate modules proposed with LoC + risk
- PR 1 candidate seam identified
- Doc length: 200–400 lines is reasonable; do not pad

## Convention

Both files go under `.hermes/handoffs/parse-back-end/` per the convention parse-gpt established in PR #67. One commit per file is fine; one PR for both is also fine — your call.

## Out-of-band notes

- If running `pytest python/ -x` locally takes more than 5 minutes, switch to running the failing tests by name only (collect failures from CI's last gate run, then re-run those by `pytest python/test_X.py::test_Y` form). Don't burn time on the green tests.
- If the architecture audit reveals that mcp_adapter has *more* coupling to `chat_tools.py` than expected, flag it loudly in the doc — that means the chat_tools decomposition (PRs 2–4 of #59's plan) and the mcp_adapter decomposition need to be sequenced carefully, not parallelized.
- Resume PR 2 of chat_tools the moment parse-gpt signals PR #68 is reviewed/merged. These two research docs do not count as PR 2 progress.
