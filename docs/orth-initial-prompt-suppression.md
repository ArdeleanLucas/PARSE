# ORTH initial prompt suppression

## Symptom

Short-clip ORTH output could be prefixed verbatim with the configured `ortho.initial_prompt` from `config/ai_config.json`:

```text
کوڕ و کچ. مال و باخ. ئاو و خاک. هاتن و چوون. ئەم زمانە کوردیە.
```

The visible failure was not a decode-strategy issue. Beam size, temperature, timestamp handling, and `max_new_tokens` changes did not remove the prefix; the configured prompt itself was reaching Whisper generation for calls that should have been unseeded.

## Affected paths

Three ORTH entry points were affected before the 2026-05-07 fix:

1. **Per-lexeme rerun** — `python/server_routes/lexeme_rerun.py` calls the ORTH interval runner, which uses `python/ai/stt_pipeline.py` and then `HFWhisperProvider.transcribe_segments_in_memory()`. On pre-fix `main`, `python/ai/providers/hf_whisper.py:508-561` forwarded each in-memory interval to `_transcribe_audio_payload()` without a caller-controlled prompt override.
2. **Concept-window rerun** — `python/server_routes/annotate.py` calls `_run_step_on_concept_windows()` and passes `initial_prompt=None` to `provider.transcribe_clip(...)`; pre-fix `python/ai/providers/hf_whisper.py:588-607` discarded that kwarg with `_ = initial_prompt`, so the suppression request was ineffective.
3. **Full-file ORTH** — `python/server_routes/annotate.py` calls `_compute_speaker_ortho()` and then `provider.transcribe(...)`; pre-fix `python/ai/providers/hf_whisper.py:424-479` chunked the full audio and called `_transcribe_audio_payload()` per chunk with the provider's configured prompt.

## Root cause

`HFWhisperProvider.transcribe_clip()` accepted an `initial_prompt` kwarg but discarded it. `_transcribe_audio_payload()` then read `self.initial_prompt` unconditionally and added `prompt_ids` to `model.generate()` whenever the provider config contained a prompt. `HFWhisperProvider.transcribe()` and `transcribe_segments_in_memory()` used the same helper, so full-file ORTH, concept-window reruns, and per-lexeme reruns all inherited the configured prompt unless the config prompt was empty.

## Regression history

PR #218 changed the default ORTH backend from the previous `faster-whisper` backend to the Hugging Face Transformers backend. The older faster-whisper path in `python/ai/providers/local_whisper.py` honored the caller's `initial_prompt` override, so `initial_prompt=None` suppressed seeding there. The HF replacement exposed the same-looking kwarg but did not honor it, causing a silent behavioral regression.

## Empirical evidence

Corpus audit on 2026-05-07, considering full-file, concept-window, and per-lexeme ORTH paths:

```text
Fail01 ortho   523/523  parrot prefix    full-file path, 100% poisoned
Fail02 ortho   132/132  parrot prefix    full-file path, 100% poisoned
Khan01 ortho   287/287  parrot prefix    full-file path, 100% poisoned
Khan02 ortho     0/503  clean            generated under faster-whisper backend
Khan03 ortho     0/283  clean            generated under faster-whisper backend
Khan04 ortho     0/401  clean            generated under faster-whisper backend
Saha01 ortho     0/497  clean            generated under faster-whisper backend
```

The clean speakers were clean because their ORTH had been generated before the HF backend became the default. Running ORTH on those same speakers under the regressed HF default would have started writing prompt-prefixed text into saved annotations.

Additional V1 stress evidence: a post-fix stress pass on 40 random Saha01 lexemes produced 0 prompt parrots. This was the key sanity check that prompt suppression survived short-clip reruns instead of only fixing the full-file path.

## Fix shape

- `HFWhisperProvider._transcribe_audio_payload()` accepts caller-controlled `initial_prompt` using a sentinel for "use config default"; `None` means "no prompt".
- The three public HF ORTH entry points default to no prompt per call: `transcribe_clip(...)`, `transcribe_segments_in_memory(...)`, and `transcribe(...)`. Callers that intentionally want the configured seed must opt in explicitly.
- `python/ai/stt_pipeline.py` renames the misleading interval helper from `run_stt_on_interval` to `run_ortho_on_interval` and passes `initial_prompt=None` into the provider.
- `python/server_routes/annotate.py` keeps concept-window and full-file ORTH calls unseeded with `initial_prompt=None`.
- `python/app/http/lexeme_rerun_handlers.py` adds a symmetric `pad` field for ORTH and IPA reruns with allowed values `{0.0, 0.2, 0.5}` and default `0.2`.
- The React rerun dialog exposes the same three pad choices and sends the selected value when users choose one.

## Pad rationale

A single-lexeme pad sweep on milk, two, and that lexemes showed the trade-off clearly: `pad=0.0` clipped some final consonants and caused near-neighbor decodes; `pad=0.2` stabilized most short lexemes without pulling adjacent words; `pad=0.5` and larger windows increasingly included neighboring speech. The default `0.2` is therefore the empirical sweet spot for Razhan `whisper-base-sdh` single-lexeme reruns, while the UI knob lets a user widen context for hard tokens.

## Data cleanup

Saved Fail01, Fail02, and Khan01 ORTH annotations are poisoned and require cleanup. That cleanup is intentionally separate from the backend, frontend, and coordinator PRs in this incident. The current cleanup target is a Mac-side utility; link its committed location here once it lands.

## Open follow-ups

- Decide whether `ortho.initial_prompt` should remain in `config/ai_config.json` now that production callers no longer pass it implicitly.
- Audit `python/ai/providers/local_whisper.py` for matching default behavior across `transcribe_clip()`, `transcribe_segments_in_memory()` if present, and `transcribe()`.
- Consider a future rerun-dialog enhancement to persist the last-used pad and add an expected-length hint such as lexeme, phrase, or clause.

## Update 2026-05-13: regression cycle + Tier-2 fallback contract

The no-parrot regression resurfaced on 2026-05-13 when `python/test_orth_no_parrot_regression.py::test_concept_window_outputs_never_include_configured_initial_prompt` failed across pad values `0.0`, `0.2`, and `0.5`. The prompt-suppression call path still set `initial_prompt=None`, but Tier-2 forced alignment crashed because a numpy ndarray reached an aligner consumer that called the torch-only `.numel()` method.

The failure compounded with a silent fallback path: after Tier-2 raised, the concept-window ORTH code could leak the raw Tier-1 decode instead of preserving the midpoint no-parrot pick selected before alignment. MC-384-T (PR #431) added the defense-in-depth contract that Tier-2 alignment failure preserves the no-parrot pick, and MC-384-U (PR #432) fixed the root cause by restoring the torch-tensor contract at the Tier-2 boundary with an `isinstance` assertion and sentinel test.

Current contract: ORTH no-parrot suppression must survive Tier-2 failure. A forced-alignment exception may degrade `tiers.ortho_words`, but it must not reintroduce configured-prompt text into `tiers.ortho`.
