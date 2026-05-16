# MC-400 HFWhisperProvider cleanup: runtime warnings, confidence provenance, and closeout

**MC Task:** MC-400 — HFWhisperProvider structural cleanup / Lane MC-400-A  
**Status:** post-A3 implementation spec.
**Grounding point:** `origin/main` at `5763691` before PR-A3 implementation.

## 0. Status (post-A3 PR)

MC-400 is now split into shipped backend/UI scaffolding plus the PR-A3 runtime cure:

| PR / lane | Status | What shipped |
| --- | --- | --- |
| PR #487 / #490 | ✓ shipped | Pre-research/spec versions of this document. |
| PR #494 / Lane C | ✓ shipped | Strict sectioned `OrthoHFConfig`, `ai_config` migrator, removal of faster-whisper-only HF compatibility keys, and mixed-shape tolerance for built-in defaults. |
| PR #495 / Lane B | ✓ shipped | Typed `ConfidenceScore(value, source, n_tokens)`, ORTH confidence triplet wire-forwarding, OpenAPI/frontend typing, and the UI fallback marker. |
| PR-A3 / Lane A | ✓ implemented in this PR | Single-owner `model.generation_config`, encoder attention-mask routing, load-time compatibility probe, and removal of the runtime warning path that made Lane B's fallback marker fire on healthy intervals. |

The current steady-state contract is:

- non-empty real clips should serialize `confidence_source: "avg_logprob"` with `confidence_n_tokens > 0`,
- empty or failed clips should still serialize `confidence_source: "constant_fallback"` with `confidence_n_tokens: 0`,
- the four target runtime warnings are eliminated by construction:
  - `output_scores` / generation flags are no longer invalid per-call kwargs,
  - encoder `attention_mask` is requested and forwarded,
  - duplicate `SuppressTokensLogitsProcessor` construction is avoided by keeping decode policy on the model config,
  - legacy faster-whisper-only options are rejected/migrated by Lane C instead of ignored at runtime.

## 1. Problem statement

The native Hugging Face ORTH provider is the empirically preferred Razhan SDH path, but before PR-A3 it still passed generation policy as per-call `generate()` kwargs. Transformers treated at least `output_scores` as invalid in the active runtime, which risked `generated.scores` being absent. After PR #495, that absence was visible as `confidence_source: "constant_fallback"` on every interval; PR-A3 fixes the root cause rather than hiding the marker.

## 2. Current file map and grounded line ranges

| File | Current role after PR-A3 | Relevant ranges after PR-A3 |
| --- | --- | --- |
| `python/ai/providers/hf_whisper.py` | Provider orchestration, config consumption, model cache, audio payload handling, prompt/max-token per-call inputs only. | `_load_model` configures and probes at 208-240; `_configure_generation_config` owns decode policy at 242-258; `_transcribe_audio_payload` requests/forwards masks and calls `generate()` with input tensors only at 343-372. |
| `python/ai/providers/hf_whisper_probe.py` | Cheap startup compatibility probe for scores-bearing generation. | `compatibility_probe` at 48-83. |
| `python/ai/providers/hf_whisper_config.py` | Strict sectioned ORTH HF config reader and CT2/legacy-schema rejection. | Shipped in PR #494; unchanged by PR-A3. |
| `python/ai/provider.py` | `ConfidenceScore` and confidence triplet helpers. | Shipped in PR #495; unchanged by PR-A3. |
| `python/test_hf_whisper_provider.py` | Runtime-warning cure and probe contract tests. | Extended by PR-A3 for GenerationConfig ownership, attention masks, probe success/failure, and non-fallback confidence. |

## 3. Target ORTH HF schema

The runtime schema is the strict sectioned shape shipped in PR #494:

```json
{
  "ortho": {
    "backend": "hf",
    "model": {"repo_id": "razhan/whisper-base-sdh", "device": "cuda"},
    "generation": {
      "task": "transcribe",
      "language": "sd",
      "condition_on_prev_tokens": false,
      "compression_ratio_threshold": 1.8,
      "no_repeat_ngram_size": 3,
      "repetition_penalty": 1.2
    },
    "decoding": {"initial_prompt": "<optional caller-controlled prompt>", "refine_lexemes": false}
  }
}
```

Legacy flat keys are no longer tolerated by the HF reader. Run the migrator from PR #494 before starting PARSE against any old workspace config:

```bash
python python/tools/migrate_ai_config_ortho.py --workspace <path>
python python/tools/migrate_ai_config_ortho.py --workspace <path> --apply
```

Agents must not run this against `/home/lucas/parse-workspace` unless Lucas explicitly asks in that moment.

## 4. Module split and ownership plan

| Target module | Status | Responsibility | Predicted LoC | PR-A3 actual |
| --- | --- | --- | ---: | ---: |
| `python/ai/providers/_whisper_shared.py` | Not needed | Language normalization stayed in `local_whisper.py`; HF imports the existing helper. | +35 | 0 |
| `python/ai/providers/hf_whisper_config.py` | ✓ shipped in PR #494 | Frozen strict config dataclasses, sectioned-schema validation, CT2 path rejection, and migration-command errors. | +220 | unchanged in PR-A3 |
| `python/ai/providers/hf_whisper_loader.py` | Not needed | Inline `_load_model` is short enough after PR-A3; a separate loader would add indirection without reducing risk. | +150 | 0 |
| `python/ai/providers/hf_whisper_probe.py` | ✓ shipped in PR-A3 | 0.1s silence compatibility probe asserting scores-bearing generation. | +80 | measured in PR body |
| `python/ai/providers/hf_whisper.py` | ✓ changed in PR-A3 | Load-time GenerationConfig ownership, probe call, attention masks, and cleaned per-call `generate()` inputs. | net 0 | measured in PR body |
| `python/test_hf_whisper_provider.py` | ✓ changed in PR-A3 | Contract tests for warnings/probe/attention/confidence steady state. | +170 | measured in PR body |

## 5. Single-owner GenerationConfig contract

Implemented in `python/ai/providers/hf_whisper.py:_configure_generation_config`.

At load time, immediately after `WhisperForConditionalGeneration.from_pretrained(...).to(...).eval()`, the provider sets the warning-safe deterministic policy:

```python
gc = model.generation_config
gc.return_dict_in_generate = True
gc.output_scores = True
gc.compression_ratio_threshold = self.compression_ratio_threshold
gc.no_repeat_ngram_size = self.no_repeat_ngram_size
gc.repetition_penalty = self.repetition_penalty
gc.condition_on_prev_tokens = self.condition_on_prev_tokens
gc.do_sample = False
# Do not set temperature when sampling is disabled; Transformers 4.57 treats
# explicit temperature with do_sample=False as an invalid generation flag.
gc.task = self.task
gc.language = self._resolved_language()
```

`_transcribe_audio_payload` now calls `model.generate()` with only:

- `input_features`,
- `attention_mask` when returned by the processor,
- `prompt_ids` only when the caller explicitly supplies a prompt or uses the config-prompt sentinel path,
- `max_new_tokens` when the public caller passes it.

The following keys must remain absent from per-call `generate()` kwargs: `output_scores`, `return_dict_in_generate`, `compression_ratio_threshold`, `no_repeat_ngram_size`, `repetition_penalty`, `condition_on_prev_tokens`, `temperature`, `do_sample`, `task`, and `language`. `temperature` remains absent entirely while `do_sample=False`; the deterministic policy is the disabled sampling flag, and setting an explicit temperature on Transformers 4.57 reintroduces the invalid-generation-flag warning.

## 6. Attention-mask contract

Implemented in `python/ai/providers/hf_whisper.py:_transcribe_audio_payload`.

The processor call is now:

```python
processor(raw_audio, sampling_rate=sample_rate, return_tensors="pt", return_attention_mask=True)
```

The returned dict-like processor output is moved to the effective device and forwarded unchanged into `generate()`, so the encoder `attention_mask` accompanies `input_features`. Prompt IDs are decoder-side context and do not replace or reshape the encoder mask.

Pinned by PR-A3 tests:

- `test_processor_called_with_return_attention_mask_true`,
- `test_prompt_ids_branch_preserves_encoder_attention_mask`,
- existing full-file and concept-window tests updated to expect mask forwarding.

## 7. Compatibility probe matrix

Implemented in `python/ai/providers/hf_whisper_probe.py:compatibility_probe(model, processor, *, language=None)` and called from `_load_model` before caching `self._processor` / `self._model`.

The probe:

1. builds a 0.1s zero-valued `float32` clip (`1600` samples at `16000 Hz`),
2. calls the same processor path with `return_attention_mask=True`,
3. calls `model.generate(**inputs)` without per-call decode policy,
4. asserts `generated.sequences` exists,
5. asserts `generated.scores` exists and is non-empty,
6. raises `RuntimeError` naming model path, Transformers version, and the specific failure when compatibility breaks.

| Probe result | Meaning | Runtime behavior |
| --- | --- | --- |
| non-empty `scores` | Active Transformers/model honors `model.generation_config.output_scores=True`. | Provider load succeeds. |
| missing `scores` attribute | GenerationConfig ownership is not honored or return shape is incompatible. | Raise `RuntimeError` naming Transformers version and model path. |
| `scores is None` | The silent-confidence fallback would recur. | Raise `RuntimeError`; do not serve ORTH with constant confidence. |
| empty scores tuple/list | Decode path returned no score steps. | Raise `RuntimeError`; include decoded sequence shape if available. |
| processor/generate exception | Model stack incompatible with the probe call. | Raise `RuntimeError` chained from original exception, with model path and Transformers version. |

Pinned by PR-A3 tests:

- `test_compatibility_probe_passes_on_silence_clip`,
- `test_compatibility_probe_raises_when_scores_path_broken`,
- `test_compatibility_probe_raises_when_scores_empty_tuple`,
- `test_compatibility_probe_runs_at_load_time`.

## 8. ai_config migration table

Lane C owns the migrator and shipped it in PR #494. Runtime mapping remains:

| Old flat key | New sectioned location | Notes |
| --- | --- | --- |
| `backend` | `ortho.backend` | unchanged; must be `hf` for the HF reader |
| `model_path` | `ortho.model.repo_id` | migrated before runtime |
| `language` | `ortho.generation.language` | runtime normalizes `sd`/`sdh` to `fa` |
| `device` | `ortho.model.device` | resolved through PARSE compute-device resolver |
| `condition_on_previous_text` | `ortho.generation.condition_on_prev_tokens` | Transformers spelling |
| `compression_ratio_threshold` | `ortho.generation.compression_ratio_threshold` | single owner is `model.generation_config` |
| `temperature` | **not set while `do_sample=false`** | Transformers 4.57 warns on explicit temperature when sampling is disabled; deterministic decode is owned by `do_sample=false`. |
| `no_repeat_ngram_size` | `ortho.generation.no_repeat_ngram_size` | single owner is `model.generation_config` |
| `repetition_penalty` | `ortho.generation.repetition_penalty` | single owner is `model.generation_config` |
| `initial_prompt` | `ortho.decoding.initial_prompt` | prompt remains caller-controlled at runtime |
| `refine_lexemes` | `ortho.decoding.refine_lexemes` | unchanged value |
| `task` | `ortho.generation.task` | validates to `transcribe` or `translate` |
| `vad_filter`, `vad_parameters`, `provider`, `compute_type` | dropped | faster-whisper/CT2 leftovers; not honored by HF runtime |

## 9. Contract test list

| Test name | Contract pinned | Status |
| --- | --- | --- |
| `test_strict_reader_rejects_legacy_flat_schema_with_actionable_message` | Legacy flat schema fails with the migrator command. | ✓ shipped in PR #494 |
| `test_mixed_shape_defaults_accept_sectioned_and_ignore_flat_siblings` | Built-in defaults may carry flat siblings but sectioned values win. | ✓ shipped in PR #494 |
| `test_generation_config_owner_is_model_not_per_call` | Decode policy lives on `model.generation_config`; per-call kwargs stay clean. | ✓ shipped in PR-A3 |
| `test_processor_called_with_return_attention_mask_true` | Processor requests encoder masks. | ✓ shipped in PR-A3 |
| `test_prompt_ids_branch_preserves_encoder_attention_mask` | Prompt IDs do not replace the encoder mask. | ✓ shipped in PR-A3 |
| `test_compatibility_probe_passes_on_silence_clip` | Probe observes non-empty scores on the healthy path. | ✓ shipped in PR-A3 |
| `test_compatibility_probe_raises_when_scores_path_broken` | Probe fails loudly for `scores is None`. | ✓ shipped in PR-A3 |
| `test_compatibility_probe_raises_when_scores_empty_tuple` | Probe fails loudly for empty scores. | ✓ shipped in PR-A3 |
| `test_compatibility_probe_runs_at_load_time` | Provider does not cache a model if the probe fails. | ✓ shipped in PR-A3 |
| `test_real_generation_produces_avg_logprob_source_not_fallback` | Healthy scores produce `source="avg_logprob"` and `n_tokens > 0`. | ✓ shipped in PR-A3 |
| `test_no_transformers_invalid_flag_warning_on_load_or_generate` | Stubbed load/generate emits none of the target warning substrings. | ✓ shipped in PR-A3 |

Regression suites to keep green:

- `python/test_orth_no_parrot_regression.py`,
- `python/test_compute_speaker_ortho.py`,
- `python/test_ipa_cuda_sanity.py`,
- `python/server_routes/test_annotate_concept_window_no_prompt.py`,
- `python/server_routes/`,
- full backend pytest with no `-k 'not …'` deselection.

## 10. PR-A3 validation plan

Use RED→GREEN for HF provider tests, then run:

```bash
PYTHONPATH=python python3 -m pytest python/test_hf_whisper_provider.py python/test_orth_no_parrot_regression.py python/test_compute_speaker_ortho.py -v
PYTHONPATH=python python3 -m pytest python/server_routes/ -q
PYTHONPATH=python python3 -m pytest -q
uvx ruff check python/ --select E9,F63,F7,F82
./node_modules/.bin/tsc --noEmit
npm run test -- --run
npm run build
git diff --check
```

The full backend command intentionally has no `-k 'not …'` exclusion. The old deselect pattern for `test_ortho_section_defaults_cascade_guard` / `test_ortho_explicit_override_beats_defaults` is removed from MC-400 validation.

Mandatory live MCP smoke for PR-A3:

- workspace: `/tmp/parse-isolation-MC-400-A3/`,
- backend port: `18766`,
- no `/home/lucas/parse-workspace`, no default `8766`, no browser/screenshots/parse-run,
- POST `/api/mcp/tools/lexeme_rerun_ortho`,
- PR body must include stderr excerpt proving the four target warning patterns are absent,
- PR body must include JSON excerpt with `confidence_source: "avg_logprob"` and `confidence_n_tokens > 0` on a real clip,
- PR body must include one deliberate empty/failed negative case preserving `confidence_source: "constant_fallback"`.

## 11. Out-of-scope guardrails

- Do not modify `python/ai/providers/hf_whisper_config.py` in PR-A3.
- Do not modify the migrator.
- Do not modify `ConfidenceScore` or downstream wire-forwarding from PR #495.
- Do not honor `compute_type` / dtype in the HF backend.
- Do not create `hf_whisper_loader.py`.
- Do not delete `local_whisper.py`.
- Do not change frontend contracts, OpenAPI, or MCP tool schema in PR-A3.
- Do not weaken or bypass prompt-suppression/no-parrot regression behavior.
- Do not migrate or boot `/home/lucas/parse-workspace`.

## 12. Future work

Honoring HF model dtype remains future MC work, contingent on an explicit fp16-vs-fp32 quality A/B against the established Southern Kurdish empirical baseline: Saha01 milk / two / that plus Khan02 `cid=4`. Until that evidence exists, PARSE keeps the current fp32 HF runtime behavior and the Lane C migrator removes legacy `compute_type`.

## MC-400 closeout

PR-A3 is the closeout lane for the original runtime warning/confidence-collapse issue:

- decode policy is no longer passed as per-call generation kwargs,
- encoder attention masks are requested and forwarded,
- startup fails fast if the active Transformers/model stack cannot return non-empty `generated.scores`,
- healthy non-empty ORTH clips should settle on `confidence_source: "avg_logprob"`,
- `constant_fallback` remains available only for genuinely empty/failed decode paths, so Lane B's UI marker remains meaningful.

The PR body is the canonical evidence bundle for this closeout: local tests, full backend sweep without deselection, frontend gates, isolated MCP stderr/JSON excerpts, negative fallback case, and predicted-vs-actual LoC.
