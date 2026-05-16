# MC-400-A HFWhisperProvider cleanup: target schema, loader split, and contract tests

**MC Task:** MC-400 — HFWhisperProvider structural cleanup / Lane MC-400-A  
**PR:** A1 pre-research docs; implementation follows in PR-A2.  
**Grounding point:** `origin/main` at `ffe7e33cba0ceb4cd55c588273508478c0d3ef1c`.

## 1. Problem statement

The current native Hugging Face ORTH provider is functionally present but still carries faster-whisper-era configuration and per-call generation ownership. Live MCP evidence showed four classes of warnings during a `lexeme_rerun_ortho` call:

- legacy faster-whisper options being logged by `HFWhisperProvider` (`compute_type`, `vad_filter`, `vad_parameters`),
- `output_scores` being treated as an invalid generation flag,
- an unset encoder attention mask warning,
- duplicate Whisper suppress-token logits processors.

The silent correctness bug is more important than the log noise: if `output_scores` is ignored by `generate()`, then `generated.scores` is `None`; `python/ai/providers/hf_whisper.py:_avg_logprob_from_scores` currently returns `0.0` for missing scores, which collapses confidence to a constant fallback.

PR-A2 will make model load the single owner of generation configuration, validate the ORTH HF schema before load, and prove at startup that the active Transformers/model combination returns non-empty generation scores.

## 2. Current file map and grounded line ranges

Current source line ranges from `origin/main`:

| File | Current lines | Relevant ranges | PR-A2 action |
| --- | ---: | --- | --- |
| `python/ai/providers/hf_whisper.py` | 641 | constants/imports 1-28; CT2 path helpers 30-52; device helper 55-63; confidence helpers 66-134; `HFWhisperProvider` 137-638 | Keep provider API; move config/load/probe concerns out; reduce provider to orchestration and transcription payload handling. |
| `python/ai/providers/hf_whisper.py` | 641 | `HFWhisperProvider.__init__` 148-207 | Replace ad-hoc section parsing with `OrthoHFConfig.from_dict(...)`; keep legacy-reader compatibility; drop `ignored_legacy_options`. |
| `python/ai/providers/hf_whisper.py` | 641 | `_reject_ct2_model_path_if_present` 209-222 | Move to `hf_whisper_config.py` validation so model path rejection occurs before provider state is populated. |
| `python/ai/providers/hf_whisper.py` | 641 | `_load_model` 254-291 | Replace inline `WhisperProcessor.from_pretrained` / `WhisperForConditionalGeneration.from_pretrained` / `.to()` / `.eval()` with `load_hf_whisper(cfg)` plus `compatibility_probe(model, processor)`. |
| `python/ai/providers/hf_whisper.py` | 641 | `_resolved_language` 293-294 and `_generate_kwargs` 296-301 | Keep resolved-language helper; delete per-call `_generate_kwargs` after language/task move to `model.generation_config`. |
| `python/ai/providers/hf_whisper.py` | 641 | `_transcribe_audio_payload` 383-436 | Request/forward encoder `attention_mask`; pass only per-call inputs and optional `prompt_ids`/`max_new_tokens` to `generate()`; remove generation policy kwargs from the call. |
| `python/ai/providers/hf_whisper.py` | 641 | `transcribe` 438-498, `transcribe_window` 500-525, `transcribe_segments_in_memory` 527-609, `transcribe_clip` 611-638 | Keep public behavior and prompt-suppression semantics; consume the cleaned `_transcribe_audio_payload`. |
| `python/ai/providers/local_whisper.py` | 613 | `_RAZHAN_SDH_LANGUAGE_ALIASES` 18-28; `_normalize_whisper_language` 35-38 | Move language alias constants/function into new `_whisper_shared.py`; re-export/import from `local_whisper.py` to preserve current tests and faster-whisper behavior. |
| `python/test_hf_whisper_provider.py` | 721 | fixtures/stubs 17-203; provider tests 206-721 | Extend in-place with RED→GREEN contract tests; update existing expected generate kwargs after policy ownership moves to `model.generation_config`. |
| `python/test_local_whisper_language_normalize.py` | 21 | imports `_normalize_whisper_language` from `local_whisper` | Keep green by re-exporting the shared normalizer from `local_whisper.py`, or update only if necessary. |

## 3. Target ORTH HF schema

PR-A2 introduces `python/ai/providers/hf_whisper_config.py` with a frozen dataclass API. The dataclass is the canonical runtime shape after either the old flat schema or the new sectioned schema is read.

```python
@dataclass(frozen=True)
class OrthoHFGenerationConfig:
    task: Literal["transcribe", "translate"] = "transcribe"
    language: str | None = "fa"                 # `sd`/`sdh` normalize to `fa`.
    return_dict_in_generate: bool = True
    output_scores: bool = True
    compression_ratio_threshold: float = 1.8
    no_repeat_ngram_size: int = 3
    repetition_penalty: float = 1.2
    condition_on_prev_tokens: bool = False       # legacy key: condition_on_previous_text
    temperature: float = 0.0
    do_sample: bool = False

@dataclass(frozen=True)
class OrthoHFModelConfig:
    path: str                                    # new key: ortho.model.path
    device: str = "auto"                         # normalized through resolve_compute_device("orth", ...)
    dtype: Literal["float16", "bfloat16", "float32"] = "float32"

@dataclass(frozen=True)
class OrthoHFConfig:
    backend: Literal["hf"] = "hf"
    model: OrthoHFModelConfig = OrthoHFModelConfig(path="razhan/whisper-base-sdh")
    generation: OrthoHFGenerationConfig = OrthoHFGenerationConfig()
    initial_prompt: str | None = None             # retained for explicit callers; public APIs still default to no prompt
    refine_lexemes: bool = False
```

### 3.1 Accepted source shapes

PR-A2 must accept both schemas until Lane C ships the migrator.

**New sectioned schema:**

```json
{
  "ortho": {
    "backend": "hf",
    "model": {
      "path": "razhan/whisper-base-sdh",
      "device": "cuda",
      "dtype": "float16"
    },
    "generation": {
      "task": "transcribe",
      "language": "sd",
      "return_dict_in_generate": true,
      "output_scores": true,
      "compression_ratio_threshold": 1.8,
      "no_repeat_ngram_size": 3,
      "repetition_penalty": 1.2,
      "condition_on_prev_tokens": false,
      "temperature": 0.0,
      "do_sample": false
    },
    "initial_prompt": "<optional caller-controlled prompt>",
    "refine_lexemes": false
  }
}
```

**Legacy flat schema accepted by reader only:**

```json
{
  "ortho": {
    "backend": "hf",
    "model_path": "razhan/whisper-base-sdh",
    "language": "sd",
    "device": "cuda",
    "compute_type": "float16",
    "condition_on_previous_text": false,
    "compression_ratio_threshold": 1.8,
    "no_repeat_ngram_size": 3,
    "repetition_penalty": 1.2,
    "initial_prompt": "<optional caller-controlled prompt>",
    "refine_lexemes": false,
    "vad_filter": true,
    "vad_parameters": {"min_silence_duration_ms": 500, "threshold": 0.35},
    "provider": "faster-whisper"
  }
}
```

### 3.2 Field validation and defaults

| Canonical field | Type | Default | Validation |
| --- | --- | --- | --- |
| `backend` | literal `"hf"` | `"hf"` | Reject non-`hf` in `OrthoHFConfig`; factory-level routing still chooses faster-whisper before this dataclass is used. |
| `model.path` | non-empty `str` | `"razhan/whisper-base-sdh"` | Reject empty strings and CT2-looking directories with the existing actionable error text. |
| `model.device` | `str` | `"auto"` | Resolve with `resolve_compute_device("orth", config_device=..., section_default="auto")`, then normalize `cuda` to `cuda:0` for HF `.to()`. |
| `model.dtype` | `float16` / `bfloat16` / `float32` | `float32` | Legacy `compute_type` maps here. `int8`, `int8_float16`, and CT2-only values raise `ValueError` for HF. |
| `generation.task` | `transcribe` / `translate` | `transcribe` | Unknown values raise `ValueError`; no silent fallback. |
| `generation.language` | `str | None` | normalized `fa` when legacy has `sd`/`sdh` | Use shared `_normalize_whisper_language`; empty string becomes `None`/auto. |
| `generation.return_dict_in_generate` | `bool` | `True` | Must remain true for confidence scoring. |
| `generation.output_scores` | `bool` | `True` | Must remain true; compatibility probe fails if ignored. |
| `generation.compression_ratio_threshold` | `float` | `1.8` | Coerce numeric; reject non-positive or non-numeric after coercion fails. |
| `generation.no_repeat_ngram_size` | `int` | `3` | Coerce int; minimum `0`. |
| `generation.repetition_penalty` | `float` | `1.2` | Coerce numeric; reject values below `1.0`. |
| `generation.condition_on_prev_tokens` | `bool` | `False` | Legacy `condition_on_previous_text` maps here. |
| `generation.temperature` | `float` | `0.0` | Deterministic default; non-zero allowed only if paired with `do_sample=true`. |
| `generation.do_sample` | `bool` | `False` | Defaults false for deterministic ORTH. |
| `initial_prompt` | `str | None` | `None` | Empty or whitespace-only string normalizes to `None`; public calls still default to suppressing config prompt unless explicitly supplied. |
| `refine_lexemes` | `bool` | `False` | Existing provider behavior retained. |

### 3.3 Unknown-key policy

- New sectioned schema: unknown top-level keys under `ortho`, unknown `model.*`, and unknown `generation.*` raise `ValueError` with the offending dotted key.
- Legacy reader compatibility: known legacy keys map to canonical fields. `vad_filter`, `vad_parameters`, and `provider` are accepted only as deprecated compatibility keys and are ignored with a one-time deprecation log per key. They do not enter `HFWhisperProvider.ignored_legacy_options`, because that attribute is removed.
- Any other legacy flat key raises `ValueError`.

## 4. Module split and ownership plan

| Target module | New / changed | Responsibility | Predicted LoC delta |
| --- | --- | --- | ---: |
| `python/ai/providers/_whisper_shared.py` | new | Razhan SDH language aliases and `_normalize_whisper_language`; optionally shared CT2/HF path messages if useful. | +35 |
| `python/ai/providers/hf_whisper_config.py` | new | Frozen config dataclasses, legacy-to-canonical loader, unknown-key validation, CT2 path rejection, dtype parsing, one-time deprecation logging. | +220 |
| `python/ai/providers/hf_whisper_loader.py` | new | Lazy import Transformers/Torch, select `torch_dtype`, instantiate processor/model, move/eval model, set `model.generation_config` exactly once. | +150 |
| `python/ai/providers/hf_whisper_probe.py` | new | 0.1s silence compatibility probe that asserts non-empty `generated.scores` and reports Transformers/model version context on failure. | +90 |
| `python/ai/providers/hf_whisper.py` | changed | Provider orchestration only: config consumption, model cache, public transcription APIs, audio payload conversion, per-call `generate()` inputs. | -120 |
| `python/ai/providers/local_whisper.py` | changed | Import/re-export shared normalizer; faster-whisper behavior unchanged. | -20 |
| `python/test_hf_whisper_provider.py` | changed | Extend stubs and assertions for schema, loader, generation config ownership, attention masks, and probe. | +230 |
| `python/test_local_whisper_language_normalize.py` | changed only if needed | Keep import compatibility green. | 0 to +5 |

**Predicted implementation size:** approximately +605 net lines, with production code moving out of `hf_whisper.py` and tests carrying most new behavioral proof. PR-A2 body must report predicted vs actual line deltas.

## 5. Single-owner GenerationConfig contract

The loader owns decode policy. PR-A2 should set the following on `model.generation_config` before the provider is considered loaded:

- `return_dict_in_generate=True`
- `output_scores=True`
- `compression_ratio_threshold=<cfg.generation.compression_ratio_threshold>`
- `no_repeat_ngram_size=<cfg.generation.no_repeat_ngram_size>`
- `repetition_penalty=<cfg.generation.repetition_penalty>`
- `condition_on_prev_tokens=<cfg.generation.condition_on_prev_tokens>`
- `temperature=0.0`
- `do_sample=False`
- `task=<cfg.generation.task>` if supported by the model config object
- `language=<cfg.generation.language>` if non-empty and supported by the model config object

`HFWhisperProvider._transcribe_audio_payload` should call `model.generate()` with only:

- `input_features`,
- `attention_mask` when the processor returns one,
- `prompt_ids` only when the caller explicitly supplies a prompt (including the existing config-prompt sentinel path),
- `max_new_tokens` when the public caller passes it.

The following must not appear in per-call kwargs after PR-A2: `output_scores`, `return_dict_in_generate`, `compression_ratio_threshold`, `no_repeat_ngram_size`, `repetition_penalty`, `condition_on_prev_tokens`, `temperature`, `do_sample`, `task`, `language`.

## 6. Attention-mask contract

`_transcribe_audio_payload` currently calls:

```python
processor(raw_audio, sampling_rate=sample_rate, return_tensors="pt")
```

PR-A2 changes this to request the mask:

```python
processor(raw_audio, sampling_rate=sample_rate, return_tensors="pt", return_attention_mask=True)
```

Then the returned `attention_mask`, if present, must be forwarded to `model.generate()`. When `prompt_ids` are supplied, the prompt token ids are still a decoder prompt; the encoder attention mask remains the processor-returned mel/audio mask. If a prompt-token companion mask is needed by the active Transformers API, it should be constructed with `torch.ones_like(prompt_ids)` under a distinct key supported by that API; do not overload the encoder `attention_mask` with prompt shape.

## 7. Compatibility probe matrix

`python/ai/providers/hf_whisper_probe.py:compatibility_probe(model, processor) -> None` should run once at startup/load against a 0.1s silence clip. It should call the same processor/model path used by real ORTH, with `return_attention_mask=True`, and assert that:

1. `generate()` returns an object with `sequences`,
2. `generated.scores` exists,
3. `len(generated.scores) > 0`.

| Probe result | Meaning | Runtime behavior |
| --- | --- | --- |
| non-empty `scores` | Active Transformers/model honors `model.generation_config.output_scores=True`. | Provider load succeeds. |
| missing `scores` attribute | GenerationConfig ownership is not honored or return shape is incompatible. | Raise `RuntimeError` naming Transformers version and model path. |
| `scores is None` | The silent-confidence fallback would recur. | Raise `RuntimeError`; do not serve ORTH with constant confidence. |
| empty scores tuple/list | Decode path returned no score steps. | Raise `RuntimeError`; include decoded sequence shape if available. |
| processor/generate exception | Model stack incompatible with the probe call. | Raise `RuntimeError` chained from original exception, with model path and Transformers version. |

The probe should be cheap and deterministic: a zero-valued `float32` numpy array with `1600` samples at `16000 Hz` is enough.

## 8. ai_config migration table

Lane C owns the migrator, but PR-A2 owns a backwards-compatible reader. Mapping for PR-A2:

| Old key | New key | PR-A2 behavior |
| --- | --- | --- |
| `ortho.backend` | `ortho.backend` | Must be `hf` for `OrthoHFConfig`; factory routes other backends elsewhere. |
| `ortho.model_path` | `ortho.model.path` | Accepted and mapped. |
| `ortho.device` | `ortho.model.device` | Accepted and mapped. |
| `ortho.compute_type` | `ortho.model.dtype` | Accepted for `float16`, `bfloat16`, `float32`; CT2-only compute types rejected for HF. |
| `ortho.language` | `ortho.generation.language` | Accepted and normalized through shared Whisper language helper. |
| `ortho.task` | `ortho.generation.task` | Accepted and validated. |
| `ortho.condition_on_previous_text` | `ortho.generation.condition_on_prev_tokens` | Accepted and mapped. |
| `ortho.compression_ratio_threshold` | `ortho.generation.compression_ratio_threshold` | Accepted and mapped. |
| `ortho.no_repeat_ngram_size` | `ortho.generation.no_repeat_ngram_size` | Accepted and mapped. |
| `ortho.repetition_penalty` | `ortho.generation.repetition_penalty` | Accepted and mapped. |
| `ortho.initial_prompt` | `ortho.initial_prompt` | Accepted; public calls still control whether the config prompt is used. |
| `ortho.refine_lexemes` | `ortho.refine_lexemes` | Accepted and mapped. |
| `ortho.vad_filter` | Lane C removes | Accepted as deprecated compatibility key; ignored with one-time log. |
| `ortho.vad_parameters` | Lane C removes | Accepted as deprecated compatibility key; ignored with one-time log. |
| `ortho.provider` | Lane C removes | Accepted as deprecated compatibility key; ignored with one-time log. |

## 9. Contract test list for PR-A2

All new tests should extend `python/test_hf_whisper_provider.py` unless a small shared-normalizer test adjustment is unavoidable.

| Test name | Contract pinned |
| --- | --- |
| `test_unknown_ortho_key_raises_at_load` | Unknown canonical schema key raises `ValueError` and names the offending key. |
| `test_legacy_vad_and_provider_keys_are_compat_ignored_once` | Legacy `vad_filter`, `vad_parameters`, and `provider` do not reach provider state and emit one-time deprecation lines instead of per-load faster-whisper warning spam. |
| `test_compute_type_float16_sets_model_dtype` | Legacy `compute_type: "float16"` maps to loader dtype and calls `from_pretrained(..., torch_dtype=torch.float16)` / yields `model.dtype == torch.float16` on CUDA-capable test stubs. |
| `test_unsupported_hf_compute_type_rejected` | CT2-only compute types such as `int8_float16` fail early for HF. |
| `test_generation_config_owner_is_model_not_per_call` | `model.generation_config` receives decode policy; `generate()` per-call kwargs are limited to input tensors, optional prompt ids, and optional max tokens. |
| `test_compatibility_probe_passes_on_silence_clip` | Probe runs through processor/generate and observes non-empty scores. |
| `test_compatibility_probe_raises_when_scores_path_broken` | Probe fails loudly when scores are missing/empty, preventing constant confidence. |
| `test_processor_called_with_return_attention_mask_true` | Processor is called with `return_attention_mask=True`. |
| `test_encoder_attention_mask_forwarded_to_generate` | The encoder `attention_mask` returned by processor is forwarded to `generate()`. |
| `test_prompt_ids_branch_does_not_replace_encoder_attention_mask` | Prompt path adds `prompt_ids` without dropping/replacing the encoder attention mask. |
| `test_generation_policy_kwargs_removed_from_transcribe_segments_in_memory` | Concept-window path shares the cleaned per-call kwargs. |
| `test_local_whisper_language_normalizer_remains_compatible` | `sd`/`sdh` → `fa` behavior remains import-compatible for faster-whisper tests. |

Regression tests to keep green:

- `python/test_orth_no_parrot_regression.py`,
- `python/test_compute_speaker_ortho.py`,
- `python/test_ipa_cuda_sanity.py`,
- `python/server_routes/test_annotate_concept_window_no_prompt.py`,
- existing `python/test_hf_whisper_provider.py` coverage.

## 10. PR-A2 validation plan

PR-A2 should use RED→GREEN for the new contract tests, then run at minimum:

```bash
PYTHONPATH=python python3 -m pytest python/test_hf_whisper_provider.py python/test_orth_no_parrot_regression.py python/test_compute_speaker_ortho.py -v
PYTHONPATH=python python3 -m pytest python/server_routes/ -q
PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'
uvx ruff check python/ --select E9,F63,F7,F82
git diff --check
```

The handoff also requests frontend gates despite no frontend changes; if dependency state permits, run:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
npm run build
```

Live smoke must be isolated:

- workspace: `/tmp/parse-isolation-MC-400-A`,
- backend port: `18766`,
- no `/home/lucas/parse-workspace`, no default `8766`, no browser/screenshots/parse-run,
- MCP HTTP bridge call(s) against `/api/mcp/tools/lexeme_rerun_ortho`,
- prove the four target warnings are absent and three lexeme confidence values are not all identical.

## 11. Out-of-scope guardrails

- Do not introduce the Lane B typed `ConfidenceScore` dataclass.
- Do not write the Lane C ai_config migrator or remove `vad_filter`, `vad_parameters`, or `provider` from live config compatibility.
- Do not delete `local_whisper.py`.
- Do not change frontend contracts, OpenAPI, or MCP tool schema.
- Do not weaken or bypass the prompt-suppression/no-parrot regression behavior.
