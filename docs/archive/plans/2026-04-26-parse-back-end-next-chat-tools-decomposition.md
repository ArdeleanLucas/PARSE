> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# parse-back-end — next task: chat_tools.py decomposition

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


**Lane:** Agent B (backend)
**Date queued:** 2026-04-26
**Rebuild oracle SHA at queue time:** `f9aa3db1aa`
**Live oracle SHA at queue time:** `ArdeleanLucas/PARSE@0951287a81`
**Branch from:** `origin/main`
**Estimated PR count:** 4 (one per tool group, in order)

---

## Working environment — read this before you do anything

**Push PRs to the rebuild repo, NEVER to the live oracle.** Your first attempt
at this task ([PR #229 on ArdeleanLucas/PARSE](https://github.com/ArdeleanLucas/PARSE/pull/229))
shipped against the wrong repo. The work was good; the venue was wrong. Two
earlier refactor PRs (#225, #226) had the same problem and had to be reverted
in oracle commit `0951287` — *revert: move refactor PRs out of live PARSE (#228)*.
Do not make this the third occurrence.

Before opening any PR for this task, verify all three of the following:

1. **Working clone** is the rebuild clone:
   ```
   $ pwd
   /home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
   ```
   NOT `/home/lucas/gh/ArdeleanLucas/PARSE` (oracle, capital).
   NOT `/home/lucas/gh/ardeleanlucas/parse` (oracle, lowercase duplicate).
   NOT any worktree under `/home/lucas/gh/worktrees/PARSE/...` whose `.git`
   gitfile resolves to either oracle clone above. Worktrees inherit the parent
   clone's remote — your PR #229 worktree (`/home/lucas/gh/worktrees/PARSE/chat-tools-tools-package-pr1`)
   was a child of the oracle clone, which is why the push went to the wrong remote.
   Always check:
   ```
   $ git remote -v
   origin\tgit@github.com:TarahAssistant/PARSE-rebuild.git (fetch)   # CORRECT
   origin\tgit@github.com:TarahAssistant/PARSE-rebuild.git (push)
   ```
   If the URL says `ArdeleanLucas/PARSE`, **stop**. Switch to
   `/home/lucas/gh/tarahassistant/PARSE-rebuild` (or create a worktree under
   `/home/lucas/gh/worktrees/PARSE-rebuild/...`) before continuing.

2. **Branch is off rebuild's `origin/main`**, not oracle's. The two repos have
   different SHAs even when they look superficially similar:
   ```
   $ git fetch origin main --quiet && git rev-parse --short=10 origin/main
   # The hash here must match https://github.com/TarahAssistant/PARSE-rebuild/commits/main
   ```

3. **PR target is the rebuild repo:**
   ```
   $ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...
   ```
   The `--repo` flag is mandatory. Without it, gh will infer the remote from
   the local clone's origin and you'll repeat the PR #229 mistake. If you ever
   see a PR URL like `https://github.com/ArdeleanLucas/PARSE/pull/...`, **close
   it immediately** and replay the same commit onto rebuild.

### Recovery path for PR #229

PR #229 should be **closed without merging on oracle**, then its single commit
`a2d22b20fc3aea8d319e35d0d1c6b121481f1cd7` should be **cherry-picked onto a fresh
branch off rebuild's `origin/main`** and opened as PR 1 of this task on the
rebuild repo:

```
$ cd /home/lucas/gh/tarahassistant/PARSE-rebuild
$ git fetch origin main --quiet
$ git remote add oracle git@github.com:ArdeleanLucas/PARSE.git 2>/dev/null || true
$ git fetch oracle refactor/chat-tools-tools-package-pr1 --quiet
$ git checkout -B refactor/chat-tools-extract-read-only-bundles origin/main
$ git cherry-pick a2d22b20fc3aea8d319e35d0d1c6b121481f1cd7
$ # cherry-pick should apply cleanly: rebuild's chat_tools.py is byte-identical
$ # to oracle's at the time PR #229 was branched.
$ npm run typecheck && npm run test -- --run && python3 -m pytest python/ -x
$ git push -u origin HEAD
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main \
    --title "refactor(chat_tools): extract read-only chat tool bundles" \
    --body-file <body-pointing-at-PR-229-as-source>
$ gh pr close 229 --repo ArdeleanLucas/PARSE --comment \
    "Replayed onto the isolated refactor lane at TarahAssistant/PARSE-rebuild#NNN per docs/rebuild-context.md."
$ git push oracle :refactor/chat-tools-tools-package-pr1   # delete oracle branch
```

Only after that replay PR is open on rebuild do you start PR 2 of this task.

All commits, tests, gates, and screenshots referenced below assume you are in
the rebuild clone with the rebuild remote.

---

## Why this task

`python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) is **6408 LoC, byte-identical to the live oracle**, and is the single largest untouched monolith in the rebuild. After PR #57 (speech/suggestion HTTP handlers) lands, it will be the dominant remaining structural risk.

Three reasons it matters now:

1. **It's the AI/MCP surface.** Every chat tool the React shell calls and every tool exposed via `mcp_adapter.py` is registered here. The Option-3 desktop pivot is gated on this surface being stable and modular — splitting it later is more expensive because `mcp_adapter.py` (2050 LoC, also untouched) and `python/external_api/catalog.py` both consume its registry shape.
2. **It blocks parallel work on AI features.** Any future "expose new chat tool" or "add workflow macro" PR currently has to serialize against this file. Splitting it into per-tool handlers unblocks parallel autonomy.
3. **It's the next file the parity inventory will need to verify.** `option1-parity-inventory.md` §5.2 lists the AI/chat shell as a P1 surface — without per-tool boundaries, parity evidence is impossible to scope.

This task pulls each tool's spec + handler into its own file under `python/ai/tools/`, leaves `chat_tools.py` as a thin registry that imports from `tools/` and exposes the existing `ParseChatTools` interface unchanged, and adds per-tool unit tests.

The pattern is documented in the `parse-expose-chat-tool` skill — read it before starting.

---

## Scope

### In scope

1. Create `python/ai/tools/` package with `__init__.py`, a `_registry.py` for the spec aggregation, and one file per tool.
2. Move each tool's spec dict and its handler function (currently inlined in `chat_tools.py` as `_handle_<tool_name>` or similar) into its own file under `python/ai/tools/`.
3. Reduce `chat_tools.py` to a registry/orchestrator that imports specs and handlers from `python/ai/tools/`, wires them into the existing `ParseChatTools` class, and re-exports `ChatToolExecutionError`, `ChatToolValidationError`, `ParseChatTools` for callers (`python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`), `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`), `python/ai/chat_orchestrator.py`).
4. Add one test file per extracted tool: `python/ai/tools/test_<tool_name>.py`. Each test file covers the tool's happy path, its argument validation errors, and at least one execution-error case.
5. Update `python/ai/workflow_tools.py` only if it directly imports from `chat_tools.py` internals; do not change its public shape.

### Out of scope

- Any change to the tool list exposed via `mcp_adapter.py` (count must remain 32 native + 36 with workflow macros + `mcp_get_exposure_mode`, per `README.md` claims).
- Any change to tool behavior, argument schema, return shape, or error wording.
- Touching `mcp_adapter.py`, `provider.py`, `chat_orchestrator.py`, or `workflow_tools.py` beyond import-path updates.
- Touching `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) beyond import-path updates if the registry export shape changes.
- Touching the React shell (`src/`) — frontend lane owns that.
- Renaming any tool. Tool names are part of the chat-tool ABI and the MCP catalog.

---

## Tool inventory + grouping (revised after PR #229)

`chat_tools.py` registers 50 tools (verified via `ParseChatTools(...).tool_names()`).
PR #229 established a grouped-modules pattern (3 module files for ~17 read-only
tools) instead of the originally-proposed one-file-per-tool layout. **The
grouped-modules pattern is endorsed for the rest of this task** — it is more
idiomatic Python, reduces import noise, and the agent demonstrated it works.
Test coverage requirement is unchanged: each tool still gets covered by at
least one dedicated test case (per-module test files are fine; do not collapse
multiple tools' tests into a single `it`/`def test`).

### PR 1 — Read-only context, preview, and job-status tools (already shipped on oracle as PR #229; replay to rebuild per Working environment §Recovery path)

Modules created in `python/ai/tools/`:
- `project_read_tools.py` — `project_context_read`, `annotation_read`, `speakers_list`, `spectrogram_preview`, `read_audio_info`, `read_csv_preview`, `read_text_preview`
- `preview_tools.py` — preview/inspection helpers (the agent's actual split; verify file contents)
- `job_status_tools.py` — `stt_status`, `stt_word_level_status`, `forced_align_status`, `ipa_transcribe_acoustic_status`, `compute_status`, `audio_normalize_status`, `jobs_list`, `job_status`, `job_logs`, `jobs_list_active`

Result: `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) 6408 → 5428 LoC (−980).

### PR 2 — Acoustic starters + pipeline orchestration

Suggested module: `python/ai/tools/acoustic_pipeline_tools.py` (or split into
`acoustic_starters.py` + `pipeline_tools.py` if the line count exceeds ~600).
Tools to extract:
- `stt_start`, `stt_word_level_start`, `forced_align_start`, `ipa_transcribe_acoustic_start`, `audio_normalize_start`
- `pipeline_state_read`, `pipeline_state_batch`, `pipeline_run`

Risk: medium. These are write-side operations that kick off long jobs. Tests
must cover argument validation + the early-return paths; do not actually invoke
GPU/STT pipelines in CI.

### PR 3 — Offset / import / memory bundles

Suggested modules:
- `python/ai/tools/offset_tools.py` — timestamp offset detect / apply / pair flows
- `python/ai/tools/import_tools.py` — processed/onboard speaker import, tag import prep
- `python/ai/tools/memory_tools.py` — `parse_memory_read`, `parse_memory_write`

Risk: medium-high. Onboarding tools have workspace-path coupling (see
`parse-mcp-large-file-onboarding-timeouts` skill). Use the same fixture pattern
PR #229 established for path-dependent tests.

### PR 4 — Comparative / enrichment / export bundles

Suggested modules:
- `python/ai/tools/compare_tools.py` — concept comparison + cognate adjudication
- `python/ai/tools/enrichment_tools.py` — CLEF / contact-lexeme enrichments
- `python/ai/tools/export_tools.py` — LingPy TSV + NEXUS exports

Risk: high. CLEF and export tools have the most external-API and on-disk
side effects. Most likely to surface oracle-vs-rebuild parity drift if any
exists.

### Acceptance after all 4 PRs land on rebuild

- `wc -l python/ai/chat_tools.py  # registry/orchestrator entrypoint` ≤ 2500 (previously: ~60% reduction goal; PR #229 alone delivered 15%)
- `python/ai/tools/` contains ~10 grouped-domain module files + per-domain `test_*.py` files
- `ParseChatTools(...).tool_names()` still returns 50 tools, in the same order
- MCP catalog tool count unchanged: 32 native + 36 with workflow macros + `mcp_get_exposure_mode`
- `mcp_adapter.py`, `provider.py`, `chat_orchestrator.py`, `workflow_tools.py` unchanged in size and behavior (only import-path updates allowed)

---

---

## Per-PR procedure

Each of the 4 PRs follows the same pattern. Use Group 1 as the worked example; repeat for Groups 2–4.

### Step 1 — Create the per-domain module file (grouped-modules pattern from PR #229)

Each domain module under `python/ai/tools/` should contain:

```python
# python/ai/tools/<domain>_tools.py — example shape
"""Chat tools: read-only project context (speakers, annotations, spectrogram preview)."""

from typing import Any, Dict, List
# any other imports the module needs

TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "speakers_list",
        "description": "...",   # copy verbatim from chat_tools.py
        "parameters": { ... },
    },
    {
        "name": "annotation_read",
        "description": "...",
        "parameters": { ... },
    },
    # ... rest of the domain's tool specs
]


def handle_speakers_list(workspace_root: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Signature must match the existing _handle_speakers_list in chat_tools.py."""
    ...


def handle_annotation_read(workspace_root: str, args: Dict[str, Any]) -> Dict[str, Any]:
    ...


HANDLERS = {
    "speakers_list": handle_speakers_list,
    "annotation_read": handle_annotation_read,
    # ... rest
}
```

The handler signature must match what `ParseChatTools.execute` currently dispatches to. Read the dispatch site in `chat_tools.py` first to confirm signature shape (positional args vs **kwargs, sync vs async).

### Step 2 — Wire each new module into chat_tools.py via thin delegating wrappers

PR #229 established the wiring pattern: `chat_tools.py` keeps the
`ParseChatTools` class and its public methods, but each `_handle_<tool>` body
becomes a one-line delegation to the new module's handler. Example:

```python
# python/ai/chat_tools.py — registry/orchestrator after extraction
from ai.tools import project_read_tools as _project_read

class ParseChatTools:
    ...
    def _handle_speakers_list(self, args):
        return _project_read.handle_speakers_list(self.workspace_root, args)

    def _handle_annotation_read(self, args):
        return _project_read.handle_annotation_read(self.workspace_root, args)
```

And the tool-spec table is built from the modules' `TOOL_SPECS` lists during
`ParseChatTools.__init__`. PR #229's actual implementation is the canonical
reference — read it before starting PR 2.

No separate `_registry.py` module is needed; PR #229 demonstrated the wiring
works without one.

### Step 3 — Slim chat_tools.py

Replace the inlined spec dicts and `_handle_*` functions for this group with:

```python
from ai.tools import _registry as _tools_registry

# In ParseChatTools.__init__ or where the tool table is built:
self._tool_specs.extend(_tools_registry.all_specs())
self._tool_handlers.update(_tools_registry.all_handlers())
```

Important constraints:
- The public class `ParseChatTools` must remain in `chat_tools.py` with the same public methods.
- `ChatToolExecutionError` and `ChatToolValidationError` must remain importable from `python.ai.chat_tools` (existing callers depend on this — `grep -rn "from ai.chat_tools" python/ src/` first).
- The combined tool list returned by `ParseChatTools.list_tools()` (or equivalent) must be identical in name, order is acceptable as long as MCP catalog tests pass.

### Step 4 — Tests

For each new file `python/ai/tools/<tool>.py`, create `python/ai/tools/test_<tool>.py` covering:

1. **Spec shape:** `TOOL_SPEC` has `name`, `description`, `parameters` keys; name matches filename.
2. **Happy path:** call `handle()` against a fixture workspace, assert return shape matches what the existing `python/test_chat_tools_*.py` (if any) expects.
3. **Validation error:** missing required arg → `ChatToolValidationError`.
4. **Execution error path:** at least one realistic failure (e.g. workspace not found, file unreadable). Use existing fixture patterns from `python/test_*.py`.

If existing `python/test_chat_tools*.py` tests cover the tool already, add a parallel test in `python/ai/tools/test_<tool>.py` that exercises the per-file handler directly. Do not delete the existing tests.

### Step 5 — Verify

Run:

```bash
pytest python/ai/tools/ python/ -x -k "chat_tools or tools"
pytest python/test_external_api_surface.py
pytest python/test_optional_websocket_dependency.py  # catches import-side-effect regressions
```

All must be green. No skips added.

Then start the dev server and run a sanity check via the chat panel: invoke at least one tool from the extracted group and verify the MCP catalog still lists all expected tools (`curl localhost:8766/api/external/mcp/tools` or equivalent).

### Step 6 — PR

PR title: `refactor(chat_tools): extract <group-name> tools into python/ai/tools/`
PR body must include:
- Before/after `wc -l python/ai/chat_tools.py  # registry/orchestrator entrypoint`
- List of extracted files
- Output of `pytest python/ai/tools/ -v` (truncated to passing summary)
- Confirmation that MCP catalog tool count is unchanged
- Any tool grouping deviations from this prompt + reasoning

---

## Acceptance (cumulative across all 4 PRs)

- `wc -l python/ai/chat_tools.py  # registry/orchestrator entrypoint` ≤ 2500 (down from 6408 — about a 60% reduction)
- `python/ai/tools/` contains one file per chat tool, each with a paired test
- `python/ai/tools/_registry.py` is the single aggregation point
- `mcp_adapter.py` is unchanged in size and behavior; tool count exposed via MCP is unchanged
- All existing `python/test_*.py` tests pass without modification
- All new `python/ai/tools/test_*.py` tests pass
- Dev server boots; chat panel can invoke at least one tool from each group (manual smoke test, screenshots in PR 4 body)

---

## Test gates (every PR)

- `pytest python/ -x` — green
- `pytest python/ai/tools/ -v` — green, no skips added
- `python -c "from ai.chat_tools import ParseChatTools, ChatToolExecutionError, ChatToolValidationError"` — succeeds
- `python -c "from adapters.mcp_adapter import build_adapter; print(len(build_adapter().list_tools()))"` — returns the same tool count as on `origin/main` before this PR
- `npm run typecheck` — green (catches if TS types coupled to backend tool shapes drift)

---

## Conventions

- One commit per tool extraction is acceptable but not required; one commit per logical step (extract, registry update, tests, fix imports) is preferred.
- PR title format: `refactor(chat_tools): extract <group-name> tools into python/ai/tools/`
- Co-author line: `Co-Authored-By: parse-back-end <noreply@anthropic.com>`
- Do not merge your own PRs. Coordinator (parse-gpt) reviews and merges.

---

## Skill references

Use these installed Hermes skills:

- `parse-expose-chat-tool` — encodes the 3-file pattern (spec + handler + test) and the dispatch contract in `chat_tools.py`. Read first; the extracted files should look like the inverse of an "expose new chat tool" PR.
- `test-driven-development` — write the per-tool test file before cutting the handler out, use it as a regression detector during the cut.
- `systematic-debugging` — for any tool whose handler has subtle workspace-path or env-var coupling. `chat_tools.py` has a number of these.
- `parse-mc-workflow` — file an MC item for this work before opening PR 1, append outcomes after each PR lands.

---

## What "done" looks like at the end of all 4 PRs

- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) ≤ 2500 LoC
- `python/ai/tools/` contains ~37 tool modules + `_registry.py` + per-tool tests
- All existing tests still green
- New per-tool tests green
- MCP catalog tool count unchanged (32 native, 36 with workflow macros + `mcp_get_exposure_mode`)
- ParseChatTools, ChatToolExecutionError, ChatToolValidationError still importable from `ai.chat_tools` for unchanged caller compatibility

---

## Out-of-band notes

- **Do not modify `mcp_adapter.py` in this task.** It will be the next backend monolith after `chat_tools.py` lands. Splitting it now would conflict with the parity work this task enables.
- Always branch from `git fetch origin main --quiet && git rev-parse origin/main`, never from local HEAD. The disk state of the rebuild clone may be on a stale branch from prior agent runs.
- If a tool handler depends on private state inside `chat_tools.py` (a module-level cache, a closure over `__init__` args), pull that state into the new module as module-level state, OR pass it as a constructor arg if it must remain shared. Document the choice in the PR body.
- If any existing test relies on patching `ai.chat_tools._handle_<tool>` directly, update those patches to target the new module path. Do not delete the tests.
- The docs PR carrying this prompt (#59) does not need to merge for you to act on this task. It is the queueing artifact, not a precondition.
- After PR 1 (the PR #229 replay) opens on rebuild, **wait for coordinator review before starting PR 2.** This prevents stacking the same lane-violation mistake across multiple PRs in parallel.
