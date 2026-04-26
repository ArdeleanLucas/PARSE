---
agent: parse-back-end
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - none — research-only, no code changes
related_skills:
  - codebase-inspection
  - systematic-debugging
  - parse-expose-chat-tool
---

# parse-back-end while-waiting #2 — sister-bug audit + chat_tools PR 2 pre-research

PR #77 awaiting parse-gpt review/merge. chat_tools PR 2 still gated on wait-rule lift per PR #78 task 2. Two short research tasks to use the wait window without touching python/ source files or starting PR 2.

## Hard rules

- No code changes to python/ source files
- No PR 2 of chat_tools until parse-gpt explicitly signals via wait-rule lift handoff
- Outputs go under .hermes/handoffs/parse-back-end/
- Working environment guard from AGENTS.md applies

## Task A — Sister-bug audit

PR #77 fixed _display_readable_path at chat_tools.py:5316-5321. The bug pattern was str(path.relative_to(...)) returning backslash on Windows when persisted to disk. Audit for other instances.

### Deliverable

.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-path-separator-sister-bugs.md

### Procedure

1. grep -nE "str\(.*\.relative_to" python/ai/chat_tools.py
2. grep -nE "str\(.*Path" python/ai/chat_tools.py
3. Same greps on python/ai/tools/ (PR #68 modules) and python/adapters/mcp_adapter.py
4. Classify each match: persisted-to-disk / logged-only / path-comparison-only
5. Output table with file:line, function, current expression, classification, recommended fix
6. No fixes — research only. Real-bugs become candidates for follow-up small PRs.

### Acceptance

- All str(path...) patterns audited and classified
- Real-bug count noted at top with proposed remediation order
- Doc 100-200 lines

## Task B — chat_tools PR 2 pre-research

PR 2 of chat_tools decomposition is the next backend implementation task once wait-rule lifts. Pre-load line numbers and module structure now.

### Deliverable

.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr2-pre-research.md

### Procedure

1. Locate the 8 PR 2 tools in current chat_tools.py:
   stt_start, stt_word_level_start, forced_align_start, ipa_transcribe_acoustic_start, audio_normalize_start, pipeline_state_read, pipeline_state_batch, pipeline_run
2. Record line range, LoC, dependencies on chat_tools.py private state, coupling to PR #68 modules
3. Propose grouped-module structure following PR #68 pattern
4. Estimate LoC reduction in chat_tools.py for PR 2 alone (currently 5428)
5. Map test surface per proposed file

### Acceptance

- 8 tools located with line ranges
- Module structure proposed with bundling rationale
- LoC reduction estimated
- Test surface mapped
- Dependencies flagged
- Doc 150-300 lines

## Out-of-band notes

- Zero real-bugs in Task A is still useful — record the negative result
- If PR 2 grouping doesn't fit cleanly, surface as deviation note, do not silently re-scope
- Do NOT start chat_tools PR 2 even if wait-rule lift seems imminent. Lift signal is an explicit handoff PR.
- Stand down again after both docs land
