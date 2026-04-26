# PARSE-rebuild parse-back-end — next task: ORTH runtime contract reconciliation

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Base:** current `origin/main` at `c5aee8b` (`fix(compare): bundle frontend contract hardening (#34)`)
**Task owner:** `parse-back-end`
**Priority:** high docs/runtime coherence
**Scope:** backend/runtime/docs/config/script coherence for the ORTH pipeline — **no frontend UI redesign**

## Why this is the right next task now

Current rebuild `origin/main` is functionally healthy, but the ORTH pipeline contract is still described inconsistently across runtime, config template, docs, and helper script surfaces.

The core backend runtime policy today is:
- `ortho.model_path` must be an explicit **local CT2 path**
- empty `ortho.model_path` hard-fails
- a HuggingFace repo id like `razhan/whisper-base-sdh` hard-fails
- ORTH defaults now use the anti-cascade guard:
  - `vad_filter=True`
  - tuned `vad_parameters`
  - `condition_on_previous_text=False`
  - `compression_ratio_threshold=1.8`

But several tracked docs/config/script surfaces still describe the **old** behavior:
- HF repo id accepted in `ortho.model_path`
- `vad_filter=false` as the default
- helper script trying HF repo id first

That makes this a clean backend-owned next task: reconcile the ORTH contract without reopening frontend lanes.

## Current grounded evidence

### Runtime truth

`python/ai/provider.py` currently says:
- `_DEFAULT_AI_CONFIG["ortho"]["model_path"] = ""`
- `ortho.model_path` must be a local CT2 directory
- HF repo ids are explicitly rejected
- `vad_filter=True`
- tuned ORTH anti-cascade defaults are active

Relevant runtime lines observed:
- `python/ai/provider.py:86-128`
- `python/ai/provider.py:1047-1075`

### Tests backing the runtime policy

These current-main tests pass together from a fresh detached `origin/main` worktree:

```bash
PYTHONPATH=python python3 -m pytest -q \
  python/test_stt_configurable_transcribe.py::test_ortho_section_defaults_cascade_guard \
  python/ai/test_ortho_provider_fallback.py -q
```

That means current `origin/main` already encodes the new ORTH policy in runtime/tests.

### Mismatched tracked surfaces

1. `config/ai_config.example.json`
   - still says `model_path` may be a HuggingFace repo id or local CT2 path
   - still sets `"model_path": "razhan/whisper-base-sdh"`
   - still says `vad_filter` defaults to false

2. `docs/getting-started.md`
   - still shows:
     - `"model_path": "razhan/whisper-base-sdh"`
     - `"vad_filter": false`
   - still explains ORTH as if VAD-off full-waveform coverage is the default

3. `docs/ai-integration.md`
   - still shows `"model_path": "razhan/whisper-base-sdh"`
   - still says source is `HuggingFace (local CT2 path or repo id)`

4. `docs/user-guide.md`
   - still says ORTH defaults keep VAD off so the whole recording is covered

5. `scripts/generate_ortho.py`
   - still tries:
     - `"razhan/whisper-base-sdh"`
     - then local CT2 cache path
   - still documents HF repo-id-first behavior that no longer matches runtime policy

## Specific task

Create **one fresh parse-back-end implementation PR** from current `origin/main` that reconciles the ORTH contract.

### Required implementation direction

1. **Preserve the runtime policy.**
   - Do **not** restore silent fallback to `stt.model_path`.
   - Do **not** re-allow HuggingFace repo ids in `ortho.model_path` just to make docs easier.
   - The fix should align docs/config/script surfaces to the current hard-fail CT2-only runtime policy.

2. **Fix tracked config + docs.**
   At minimum reconcile:
   - `config/ai_config.example.json`
   - `docs/getting-started.md`
   - `docs/ai-integration.md`
   - `docs/user-guide.md`

   They should explain clearly that:
   - `ortho.model_path` must point at a local CT2 conversion directory
   - `razhan/whisper-base-sdh` is the historical/source model name, not a directly acceptable runtime `model_path`
   - current ORTH defaults use the anti-cascade guard (`vad_filter=True`, tuned params, `condition_on_previous_text=False`, `compression_ratio_threshold=1.8`)

3. **Reconcile the helper script.**
   Inspect `scripts/generate_ortho.py` and choose one of these:
   - update it to match the CT2-only contract, or
   - explicitly deprecate/archive it if it is no longer a trustworthy supported flow

   Do not leave it teaching the opposite runtime policy.

4. **Keep scope backend/docs/config/script only.**
   - no React UI work
   - no compare/annotate component churn
   - no overlap with Builder PRs `#41` or `#43`
   - no overlap with parse-back-end worktree cleanup PR `#42`

## In scope

- `python/ai/provider.py` only if a tiny clarification/comment update is truly needed
- `python/ai/test_ortho_provider_fallback.py`
- `python/test_stt_configurable_transcribe.py`
- `config/ai_config.example.json`
- ORTH-related docs under `docs/`
- `scripts/generate_ortho.py`

## Out of scope

- frontend files under `src/`
- PR `#42` worktree cleanup lane
- Builder annotate parity lanes (`#41`, `#43`)
- broad generalization-beyond-SK work beyond the immediate ORTH contract mismatch

## Validation requirements

Run and report at least:

```bash
PYTHONPATH=python python3 -m pytest -q \
  python/ai/test_ortho_provider_fallback.py \
  python/test_stt_configurable_transcribe.py
python3 -m py_compile python/ai/provider.py scripts/generate_ortho.py
PYTHONPATH=python python3 -m pytest -q
./node_modules/.bin/tsc --noEmit
git diff --check
```

If you do not touch frontend code, you do **not** need to make this a frontend task — but still keep `tsc --noEmit` and `git diff --check` in the report for repo hygiene.

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from current `origin/main`.

In the PR body, include:
- the exact ORTH runtime truth you preserved
- the exact stale docs/config/script claims you corrected
- whether `scripts/generate_ortho.py` was aligned or deprecated
- exact tests run
- confirmation that this stayed non-overlapping with PRs `#42`, `#41`, and `#43`

## Academic / fieldwork considerations

- ORTH output is linguistically important source data; silent model substitution is unacceptable.
- Research users need the setup instructions to describe the actual runtime contract, especially when local CT2 conversion is required.
- A clear CT2-only ORTH contract improves reproducibility and avoids false confidence in mismatched orthographic tiers.
