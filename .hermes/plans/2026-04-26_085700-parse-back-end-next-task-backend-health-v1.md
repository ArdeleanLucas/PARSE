# parse-back-end next task — make the full backend suite green on current rebuild main

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-26
**Owner:** parse-back-end
**Status:** queued / ready on current `origin/main`

## Goal

Open a fresh parse-back-end PR from current rebuild `origin/main` that makes the **full backend pytest suite pass** again.

This is not a docs task. It is a backend-health task grounded in the live current main line after PR #13 merged.

---

## Why this is the right next parse-back-end task

PR #13 is already merged into rebuild `main`, so the auth HTTP extraction lane is complete.

The next backend-safe high-value task is now clear because the **full backend suite is still red on current main**.

That gives parse-back-end an immediately actionable, self-contained lane that:
- stays mostly inside `python/**`
- improves actual repo health
- does not overlap Builder’s frontend-owned hook-order crash task

---

## Current grounded context

Verified before writing this prompt:

- Current rebuild `origin/main` tip:
  - `4ed1eb7` (`refactor: extract auth HTTP handlers (#13)`)
- PR #13 status:
  - merged
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/13`
- Builder’s current active implementation PR remains:
  - PR #14 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`
- Builder’s fresh next-task prompt is separate:
  - PR #17 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/17`
- Coordinator PR currently open:
  - PR #15 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/15`

### Live backend baseline on current main

I re-ran the full backend suite on the current rebuild main-equivalent state with:

```bash
PYTHONPATH=python python3 -m pytest -q
```

Result:
- **553 passed**
- **3 failed**

### Current failing tests

1. `python/test_external_api_surface.py::test_http_mcp_bridge_lists_and_executes_tools`
2. `python/test_stt_configurable_transcribe.py::test_ortho_section_defaults_cascade_guard`
3. `python/test_stt_configurable_transcribe.py::test_ortho_explicit_override_beats_defaults`

### Failure cluster A — MCP bridge test contamination / 500

Observed failure:
- `GET /api/mcp/tools?mode=all` returns `500` during the full suite
- the same test has previously been verified to pass in isolation

Strong hypothesis from earlier investigation:
- a prior test mutates cached global chat runtime state (`server._chat_tools_runtime` / `server._chat_orchestrator_runtime`) and does not restore it
- the HTTP MCP bridge then reuses poisoned singleton state and fails during the full run

Likely related surface:
- `python/test_chat_docs_root.py`
- `python/server.py::_get_chat_runtime()`
- any tests that monkeypatch `ParseChatTools`, `ChatOrchestrator`, `_project_root`, or `_chat_docs_root` while populating cached runtime singletons

### Failure cluster B — ORTH runtime/test/config contract drift

Observed failures:
- the two ORTH tests instantiate `LocalWhisperProvider(config_section="ortho")` without an explicit local CT2 `model_path`
- current runtime now hard-fails when `ortho.model_path` is empty

Current runtime behavior in `python/ai/provider.py`:
- ORTH rejects empty `ortho.model_path`
- ORTH rejects HuggingFace repo-id style `ortho.model_path`
- runtime expects an explicit local CT2 path

But current tests/docs/example-config drift from that:
- tests still expect ORTH defaults to work without explicit model path
- `config/ai_config.example.json` still documents a historical `razhan/whisper-base-sdh` style path story
- docs may still describe old ORTH defaults/behavior

This task should reconcile those surfaces without reintroducing the old silent fallback to `stt.model_path`.

---

## The specific task

Make the full backend suite green on current rebuild main by fixing the two real backend-health clusters:

### A. Fix the MCP HTTP bridge full-suite failure
Required outcome:
- `python/test_external_api_surface.py::test_http_mcp_bridge_lists_and_executes_tools` passes in the **full suite**, not only in isolation
- tests must be order-independent and hermetic

Likely work:
- isolate which earlier test pollutes cached runtime state
- restore/clear globals correctly
- or tighten runtime construction so tests do not silently share invalid singleton state

### B. Reconcile the ORTH contract and make the ORTH tests pass
Required outcome:
- both ORTH tests pass
- runtime/test/docs/example-config all reflect one coherent ORTH policy
- no silent fallback to `stt.model_path` is reintroduced

Acceptable resolution shape:
- keep the hard-fail runtime policy if that is the intended design
- update tests and docs/config/examples accordingly
- ensure the example config and comments stop claiming unsupported behavior

---

## Scope boundary

### In scope
- `python/**`
- backend tests under `python/test_*.py`
- `config/ai_config.example.json` if needed for ORTH contract coherence
- backend-facing docs only if necessary to keep the ORTH contract truthful

### Read-only unless absolutely necessary
- `src/**`
- Builder-owned frontend files
- PR #14 implementation lane

### Explicitly out of scope
- Builder’s Compare → Annotate `TranscriptionLanes` crash
- ParseUI decisions persistence work
- broad frontend refactors

---

## Required execution method

Treat this as a systematic backend debugging task:
1. reproduce each failure
2. isolate root cause
3. add/adjust regression coverage if needed
4. apply the smallest root-cause fix
5. rerun the full backend suite

Do not fix by weakening tests unless that change is the correct reflection of the intended contract.

---

## Required validation

Minimum required commands:

```bash
PYTHONPATH=python python3 -m pytest -q
python3 -m py_compile python/server.py python/ai/provider.py python/app/http/*.py
```

Also run any targeted subsets you use while iterating, but the task is not complete until the **full backend suite** is green.

---

## Recommended branch / PR guidance

Use a fresh branch from rebuild `origin/main`.

Recommended branch name:

```text
fix/backend-suite-green-after-pr13
```

Ship as a new parse-back-end PR.
Do not reopen PR #13.
Do not spill into Builder-owned frontend work.

---

## Reporting requirements

In the final parse-back-end report, include:
1. PR number + URL
2. worktree path used
3. exact root cause for the MCP bridge failure
4. exact ORTH contract decision taken
5. files changed
6. tests added/updated
7. full backend suite result
8. anything intentionally left for another lane
