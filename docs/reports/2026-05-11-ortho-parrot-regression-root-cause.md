# MC-370-B ORTH concept-window initial-prompt regression root cause

**MC Task:** MC-370 — Pre-existing backend test failures / Lane MC-370-B

## Current status on `origin/main`

The handoff expected `python/test_orth_no_parrot_regression.py::test_concept_window_outputs_never_include_configured_initial_prompt` to fail for pads `0.0`, `0.2`, and `0.5`. Re-running the handoff's required reproduction command on current `origin/main` (`ab9b679`) now passes all nine parameterizations:

```bash
PYTHONPATH=python python3 -m pytest -vv python/test_orth_no_parrot_regression.py
# 9 passed, 1 warning
```

No production-code change is needed for MC-370-B on the current mainline.

## Leak path

The regression fixture uses an `HFWhisperProvider` with a distinctive configured `ortho.initial_prompt` and a prompt-sensitive fake model. If `prompt_ids` reaches `model.generate(...)`, the fake decoder returns `<DISTINCTIVE-MARKER-PROMPT> parroted output`; if no prompt is seeded, it returns `clean lexical decode`.

The relevant provider path is `python/ai/providers/hf_whisper.py::_transcribe_audio_payload(...)`:

1. `initial_prompt` defaults to the sentinel `_USE_CONFIG_PROMPT`.
2. If callers do not override it, the provider resolves `prompt = self.initial_prompt`.
3. A non-empty prompt is converted with `processor.get_prompt_ids(...)`.
4. The provider passes `prompt_ids` into `model.generate(...)`.
5. On short concept-window clips, Whisper may echo that priming text as transcription output.

The concept-window ORTH route reaches this provider through `python/server_routes/annotate.py::_run_step_on_concept_windows(...)`, called by `_compute_speaker_ortho_concept_windows(...)`.

## Existing fix on current main

Current `python/server_routes/annotate.py::_run_step_on_concept_windows(...)` suppresses configured prompts at the concept-window source:

```python
# Pass initial_prompt=None to suppress the configured ortho prompt; this is
# required to prevent Whisper from echoing it on short concept clips.
initial_prompt = None
...
result = provider.transcribe_clip(clip_np, initial_prompt=initial_prompt, language=language)
```

That caller override prevents `HFWhisperProvider` from using its configured ORTH `initial_prompt`, so `prompt_ids` is not sent to generation for short concept windows. The existing regression test proves this for pads `0.0`, `0.2`, and `0.5`; it also verifies that `tiers.ortho` stores the picked midpoint lexeme while `tiers.ortho_words` preserves the full aligned word list.

## Historical note

`git blame` shows the source-level suppression comment came from commit `017c1dac` and the `initial_prompt = None` behavior predates it in the current route helper. PR #300 added the regression documentation/test, and PR #302 touched the concept-window ORTH path. The handoff appears stale relative to the current `origin/main` state.

## Proposed follow-up

No follow-up implementation lane is needed unless the regression reappears on a different branch or CI base. If it does, the small fix surface is the caller-side `initial_prompt=None` override in `_run_step_on_concept_windows(...)`, not output-string filtering.

**Update 2026-05-13:** The conclusion above was correct on `ab9b679`, where the handoff reproduction passed and no production-code change was needed on that mainline. It was invalidated within 48 hours when the concept-window no-parrot regression resurfaced; the bisect target lives in PR #429 or earlier-merged related work, with the recovery documented in PR #431's bisect output.

The landed 2026-05-13 fix chain is: MC-384-T / PR #431 added the Tier-2 fallback contract so alignment failure preserves the no-parrot pick, then MC-384-U / PR #432 restored the torch-tensor contract at the forced-alignment boundary so numpy arrays no longer reach the `.numel()` consumer. For current canonical behavior, see `docs/architecture/compute.md` §Tier-1 vs Tier-2 ORTH.
