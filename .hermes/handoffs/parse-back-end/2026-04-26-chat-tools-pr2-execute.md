---
agent: parse-back-end
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #81 (wait-rule lift) signal — content is sufficient, do not wait for merge on main
  - PR #83 (pre-research) is the implementation source of truth
related_prs:
  - 59  (original chat_tools decomposition prompt)
  - 68  (PR 1 cherry-pick replay — pattern to follow)
  - 77  (path-separator fix MC-323 — already merged, your win)
  - 80  (while-waiting #2 queue)
  - 81  (wait-rule lift signal)
  - 83  (PR 2 pre-research — read this first)
related_skills:
  - parse-expose-chat-tool
  - parse-mc-workflow
  - test-driven-development
  - systematic-debugging
---

# parse-back-end next implementation — chat_tools PR 2 (execute)

**Why this exists:** Wait-rule is cleared (PR #81 is the explicit signal — don't wait for it to merge on main, the gate is open). Pre-research is done (PR #83 has the full plan). This handoff aligns the two and tells you to ship.

## TL;DR

Execute the 2-module split documented in [PR #83's pre-research](https://github.com/TarahAssistant/PARSE-rebuild/pull/83) (`.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr2-pre-research.md`). Follow the PR #68 grouped-modules + thin-delegating-wrapper pattern. Predicted reduction: chat_tools.py 5428 → ~4910 LoC.

## Working environment

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo mandatory
```

Per AGENTS.md (PR #74) — three prior wrong-repo PRs documented. Your PR #77 was on the right repo; keep it that way.

## Execution plan (from PR #83 pre-research, ready to ship)

### Module 1 — `python/ai/tools/acoustic_starter_tools.py`

Tools to extract:

| Tool | chat_tools.py spec lines | chat_tools.py handler lines | Gross LoC |
|---|---:|---:|---:|
| `stt_start` | 636-657 | 2261-2302 | 64 |
| `stt_word_level_start` | 658-681 | 2312-2338 | 51 |
| `forced_align_start` | 682-716 | 2344-2401 | 93 |
| `ipa_transcribe_acoustic_start` | 717-742 | 2407-2451 | 71 |
| `audio_normalize_start` | 1236-1261 | 2610-2641 | 58 |

**Total: ~337 LoC. Risk: medium.**

Why these belong together: all are stateful job starters with the same dry-run/start pattern, all depend on callback wiring supplied through `ParseChatTools.__init__`, and `stt_word_level_start` is a thin semantic wrapper over `stt_start` so splitting them apart would create awkward cross-module calls.

### Module 2 — `python/ai/tools/pipeline_orchestration_tools.py`

Tools to extract:

| Tool | chat_tools.py spec lines | chat_tools.py handler lines | Gross LoC |
|---|---:|---:|---:|
| `pipeline_state_read` | 1096-1120 | 2466-2478 | 38 |
| `pipeline_state_batch` | 1121-1151 | 2480-2538 | 90 |
| `pipeline_run` | 1152-1235 | 2540-2600 | 145 |

**Total: ~273 LoC. Risk: medium.**

Why these belong together: all are about pipeline preflight/orchestration (not individual acoustic jobs), share `_pipeline_state` + `full_pipeline` mental model, and `pipeline_state_batch` aggregates the same step family that `pipeline_run` launches.

### Why a 2-module split (not a single bundle)

Combined gross LoC = ~610. The amended PR #59 prompt's soft ceiling is ~600 per module before splitting. A single bundle would land just over that ceiling and reduce review honesty. The 2-module split is the cleanest reviewable shape.

### Coupling note (from your PR #83 audit)

`pipeline_state_batch` currently falls back to `self._tool_speakers_list({})`, which is a thin wrapper around the PR #68 `project_read_tools.py` module. **In the extracted `pipeline_orchestration_tools.py`, prefer the underlying `project_read_tools` helper directly** rather than bouncing through an in-class wrapper for internal composition.

## Procedure

**Step 0 — Re-derive line numbers from current `origin/main`** (do not trust this prompt's table; rebuild has moved since PR #83 was researched):

```
git fetch origin --quiet
git checkout -B refactor/chat-tools-pr2-acoustic-pipeline origin/main
grep -nE "_handle_(stt_start|stt_word_level_start|forced_align_start|ipa_transcribe_acoustic_start|audio_normalize_start|pipeline_state_read|pipeline_state_batch|pipeline_run)" python/ai/chat_tools.py
```

**Step 1 — Create `python/ai/tools/acoustic_starter_tools.py`** following the PR #68 pattern:

```python
"""Chat tools: stateful acoustic-job starters (STT, forced-align, IPA acoustic, normalize)."""

from typing import Any, Dict, List

TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "stt_start", "description": "...", "parameters": {...}},
    # ... 4 more, copy verbatim from chat_tools.py
]


def handle_stt_start(tools, args: Dict[str, Any]) -> Dict[str, Any]:
    """Signature must match _handle_stt_start in chat_tools.py."""
    ...

# ... 4 more handlers


HANDLERS = {
    "stt_start": handle_stt_start,
    "stt_word_level_start": handle_stt_word_level_start,
    "forced_align_start": handle_forced_align_start,
    "ipa_transcribe_acoustic_start": handle_ipa_transcribe_acoustic_start,
    "audio_normalize_start": handle_audio_normalize_start,
}
```

**Step 2 — Create `python/ai/tools/pipeline_orchestration_tools.py`** with the same structure for the 3 pipeline tools.

**Step 3 — Slim `chat_tools.py`** with thin delegating wrappers:

```python
from ai.tools import acoustic_starter_tools as _acoustic
from ai.tools import pipeline_orchestration_tools as _pipeline

class ParseChatTools:
    ...
    def _handle_stt_start(self, args):
        return _acoustic.handle_stt_start(self, args)

    def _handle_pipeline_run(self, args):
        return _pipeline.handle_pipeline_run(self, args)
    # ... rest of the 8 wrappers
```

**Special case for `stt_word_level_start`**: currently delegates to `_tool_stt_start(args)`. After extraction it should delegate to the **shared module helper** (`_acoustic.handle_stt_start(self, args)`), not bounce back through the old in-class wrapper.

**Step 4 — Add tests:**

Existing tests provide most coverage:
- `python/ai/test_acoustic_alignment_mcp_tools.py` — covers `stt_word_level_start`, `forced_align_start`, `ipa_transcribe_acoustic_start`, dry-run, missing-callback for forced-align
- `python/ai/test_pipeline_chat_tools.py` — covers all 3 pipeline tools, step normalization, invalid-step rejection, callback-required errors
- `python/adapters/test_mcp_adapter.py` — MCP exposure counts/metadata, dry-run for `stt_start` + `audio_normalize_start`

**Coverage gaps to add** (per PR #83 audit):
- `stt_start` itself is much less directly exercised than `stt_word_level_start` — add direct test in new `python/ai/tools/test_acoustic_starter_tools.py`
- `audio_normalize_start` is mostly covered via adapter metadata/dry-run, not a dedicated chat-tools starter suite — add direct test

Do NOT modify the existing test files unless an import path needs updating; add new `python/ai/tools/test_acoustic_starter_tools.py` + `test_pipeline_orchestration_tools.py` for new direct coverage.

**Step 5 — Validate:**

```bash
pytest python/ai/test_acoustic_alignment_mcp_tools.py python/ai/test_pipeline_chat_tools.py python/adapters/test_mcp_adapter.py -v
pytest python/ai/tools/test_acoustic_starter_tools.py python/ai/tools/test_pipeline_orchestration_tools.py -v
pytest python/ -x  # full backend gate
```

All must be green. Verify `ParseChatTools(...).tool_names()` still returns 50 tools and the MCP catalog tool count is unchanged.

## Acceptance

- `wc -l python/ai/chat_tools.py` ≤ ~4910 (~500-520 LoC reduction)
- 2 new module files: `acoustic_starter_tools.py`, `pipeline_orchestration_tools.py`
- 2 new test files: `test_acoustic_starter_tools.py`, `test_pipeline_orchestration_tools.py`
- All existing `python/ai/test_*.py` and `python/adapters/test_*.py` tests pass without modification
- ParseChatTools, ChatToolExecutionError, ChatToolValidationError still importable from `ai.chat_tools`
- MCP catalog tool count unchanged (32 native + 36 with workflow macros + `mcp_get_exposure_mode`)
- `pipeline_state_batch` uses `project_read_tools` helper directly, not via in-class wrapper

## Conventions

- Branch: `refactor/chat-tools-pr2-acoustic-pipeline` (or split into 2 branches if you prefer one PR per module — both acceptable, but if 2 PRs, ship them in order: acoustic first, pipeline second since `pipeline_state_batch` references `project_read_tools` in a way that's cleanest with a green base)
- PR title: `refactor(chat_tools): extract acoustic starters and pipeline orchestration (PR 2)`
- Co-author line: `Co-Authored-By: parse-back-end <noreply@anthropic.com>`
- Do not merge your own PR
- File MC item before opening PR (per `parse-mc-workflow` skill)

## Out of scope

- **Sister-bug fix at `chat_tools.py:2271`** (`_tool_stt_start` payload-only path-separator) — your audit identified it as the highest-priority sister candidate. Do NOT fold it into PR 2; ship it as a separate small PR after PR 2 lands. (Same reasoning as why PR 1 didn't fix the path-separator bug — keep extraction PRs surgical.)
- **mcp_adapter.py decomposition** — that's the next backend monolith after chat_tools is fully decomposed (PRs 2/3/4 of the chat_tools sequence). parse-gpt's PR #84 will queue the env_config.py extraction handoff after PR 2 lands.
- **Touching FastMCP private API** (`mcp._tool_manager._tools`) — your PR #72 audit flagged this as fragile. Do not touch in PR 2.

## After this lands

Coordinator (parse-gpt) will:
1. Review and merge
2. Verify chat_tools.py LoC drop matches projection (~500-520)
3. Queue chat_tools PR 3 (offset/import/memory bundles per the original PR #59 grouping)

Don't start PR 3 until parse-gpt explicitly signals via a new handoff. Same wait-rule discipline as before — but the rule is now standard practice, not a one-off response to a wrong-repo incident.

## If you hit unexpected complications

- If the gross LoC after grep + line-derivation differs significantly from PR #83's estimates (>15%), surface in PR body — don't silently re-scope.
- If `pipeline_state_batch`'s `project_read_tools` coupling reveals a deeper dependency than the audit suggested, prefer keeping the in-class wrapper bounce in PR 2 (preserve behavior) and surface the cleanup as a follow-up.
- If any test in the existing suite fails after the extraction, **stop and diagnose before pushing**. The 2 real-bug fixes from #77 just landed; another regression here would be very visible.
