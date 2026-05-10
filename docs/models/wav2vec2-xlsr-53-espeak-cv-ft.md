# `facebook/wav2vec2-xlsr-53-espeak-cv-ft`

The IPA (Tier 3 acoustic phoneme transcription) model for PARSE. A multilingual wav2vec2-XLSR-53 fine-tune trained to emit espeak-style IPA phonemes via CTC. Used for both the concept-window IPA path and the full-mode 3-tier IPA path that combines G2P + torchaudio forced alignment + wav2vec2 CTC.

## Identity

| Field | Value |
|---|---|
| HuggingFace repo | [`facebook/wav2vec2-xlsr-53-espeak-cv-ft`](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft) |
| Base model | `facebook/wav2vec2-large-xlsr-53` (317M params) |
| Architecture | wav2vec2 large + CTC head over an espeak IPA phoneme vocabulary |
| Output type | IPA phoneme string (e.g. `tʃəlɪvərd`), no orthographic forms |
| Language code mapping | **None — this is a single multilingual checkpoint with a fixed phoneme vocabulary.** The model has no language-conditioning input. The `language` value passed by callers does not reach the model's forward pass; it is consumed elsewhere in the pipeline (espeak-ng G2P for forced-align targets) — see "Empirical evidence — Phase 0". |
| License | See model card on HuggingFace. |

## Where it's used in PARSE

| Compute path | Provider class | Entry point |
|---|---|---|
| Concept-window IPA (per-concept clip decode) | `ai.forced_align.Aligner` | [`python/server_routes/annotate.py:_run_step_on_concept_windows`](../../python/server_routes/annotate.py) → `_transcribe_ipa_window_structured` → `Aligner.transcribe_window_structured` |
| Full-file IPA — Tier 2 forced alignment + Tier 3 acoustic decode | `ai.forced_align.Aligner` | [`python/ai/ipa_transcribe.py:transcribe_words_with_forced_align`](../../python/ai/ipa_transcribe.py) → `_align_segments` (G2P + torchaudio.functional.forced_align) + `Aligner.transcribe_window` per word |
| Per-lexeme IPA rerun | `ai.forced_align.Aligner` | [`python/ai/ipa_transcribe.py:transcribe_slice_structured`](../../python/ai/ipa_transcribe.py) → `Aligner.transcribe_window_structured` |
| Auto-route fallback when no ortho/ortho_words exist | `ai.forced_align.Aligner` | `_compute_speaker_ipa` → `_compute_speaker_ipa_concept_windows` |

The model is loaded once per process via `Aligner.load(model_name=...)`; the long-lived persistent worker reuses the cached `_PRELOADED_ALIGNER` to avoid the 1.2 GB weight reload between speakers.

## Configuration

Block in `config/ai_config.json` (the example template — the live `ai_config.json` is gitignored). The `ipa` block is informational; the live code path is hard-wired through the `wav2vec2` block at the bottom of the config:

```json
"ipa": {
  "engine": "wav2vec2",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "model_only": true
},
"wav2vec2": {
  "provider": "wav2vec2-ipa",
  "model": "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
  "device": "cuda",
  "force_cpu": false,
  "allow_wsl_cuda": false,
  "chunk_size": 150
}
```

Knob-by-knob:

| Knob | Default | Effect | Notes |
|---|---|---|---|
| `wav2vec2.model` | `facebook/wav2vec2-xlsr-53-espeak-cv-ft` | HF repo id used by `Aligner.load`. | Changing this means changing the phoneme vocabulary. Other espeak-vocabulary checkpoints in the same family (e.g. MMS phoneme heads) would slot here, but PARSE's CTC alignment vocab is keyed to this specific checkpoint's tokenizer. |
| `wav2vec2.device` | `cuda` | Target device hint. The provider normalizes and resolves through `resolve_device(...)`. | On WSL2 hosts, see `allow_wsl_cuda` below. |
| `wav2vec2.force_cpu` | `false` | Hard force CPU regardless of CUDA availability. | Used historically when the WSL2 host had unstable CUDA on this model. |
| `wav2vec2.allow_wsl_cuda` | `false` | Off by default for WSL safety. Set true only on machines where `torch.cuda.is_available()` is confirmed and wav2vec2 should run on CUDA. | The default-off setting is what causes the production code path to run on CPU on Lucas's WSL2 RTX 5090 host even when the GPU is otherwise available — see "Known limitations". |
| `wav2vec2.chunk_size` | `150` | Forced-alignment segment batch size in `transcribe_words_with_forced_align`. | Caps peak GPU memory across long recordings; smaller values trade throughput for headroom. |
| `language` (call-site, not config) | `None` then `'ku'` fallback | Passed through `_compute_speaker_ipa` → `_compute_speaker_ipa_concept_windows` → `_run_step_on_concept_windows` → `_transcribe_ipa_window_structured`, and through `transcribe_words_with_forced_align(language=...)` for full-mode. | **Phase 0 below** — for the concept-window and per-lexeme paths, the language argument is dropped at the `Aligner.transcribe_window` boundary via the PR #355 TypeError fallback. For full-mode it is consumed by the espeak-ng G2P step that produces forced-alignment target tokens; it does not reach the wav2vec2 acoustic decode itself. |

There is no per-call decode tuning surface (no beam, temperature, prompt, pad). The CTC head is greedy-decoded with `argmax`; the only audio-shape lever is `pad_sec` carried by the concept-window runner (default `0.2` s).

## Tuning guide

No tuning sweep has been run on this model in PARSE; see "Empirical evidence" for the language-hint validation only. Specifically: **changing the `language` value passed at the API boundary does not change wav2vec2 IPA output on the concept-window or per-lexeme paths** (Phase 0 + Phase 1, this session).

If a window is transcribed as English-pattern phonology when the actual speech is Kurdish, the proximate cause is acoustic — the recording itself contains English (researcher prompts, code-switched speech, ambient English) — or the bound is wrong (silence, off-target audio). The wav2vec2 CTC head will report what it hears; a language hint is not a knob that recovers Kurdish from English-language audio because no such knob exists in this model.

## Empirical evidence

### MC-361 — language hint validation — 2026-05-10

Trigger: PR #355 ("[MC-361-A] fix(ipa): resolve speaker language via metadata fallback") added `_transcription_language_from_payload_or_annotation` for the IPA compute path so the resolved language flows through to `_run_step_on_concept_windows(... language=...)`, into `_transcribe_ipa_window_structured(provider, window, *, language=...)`, and into `transcribe_words_with_forced_align(... language=...)`. The Fail01 IPA tier on disk contains conspicuous English-pattern phonology (e.g. concept *two* → `soʊwʌdɪdjuːɪkspleɪnsoʊfɑː`, "so what did you explain so far"), which raised the question of whether the language fallback fix actually changes wav2vec2 output for those concepts.

Two phases were run this session in `/tmp/parse-isolation-mc-361-validation/` in-process against `/usr/bin/python3` (the same interpreter `parse-run` uses), with no PARSE server running. The aligner loaded on **CPU** because `wav2vec2.allow_wsl_cuda=false` is the configured default and the `Aligner.load()` resolver routes WSL hosts to CPU under that flag.

```
Phase 0   Provider signature inspection + TypeError probe       proves language= is dropped at the model boundary
Phase 1   V0 (None) vs V1 (sdh) vs V_ku vs V_en on 4 Fail01     proves language hint does not change model output
```

#### Phase 0 — Provider signature inspection

Exact signatures from the loaded production module:

```
Aligner.transcribe_window           (self, audio_16k: 'Any') -> 'str'
Aligner.transcribe_window_structured (self, audio_16k: 'Any') -> 'Dict[str, Any]'
```

Direct call probe:

```
aligner.transcribe_window(window, language="sdh")
  → TypeError: Aligner.transcribe_window() got an unexpected keyword argument 'language'

aligner.transcribe_window_structured(window, language="sdh")
  → TypeError: Aligner.transcribe_window_structured() got an unexpected keyword argument 'language'
```

PR #355's `_transcribe_ipa_window_structured` wraps each call in a try/except TypeError that retries without `language=`:

```python
try:
    structured = structured_fn(window, language=language)
except TypeError as exc:
    message = str(exc)
    if 'language' not in message and 'unexpected' not in message:
        raise
    structured = structured_fn(window)         # ← language silently dropped
```

So on the production `Aligner` provider, the second branch always fires. The language value reaches PARSE's IPA call frame but does not reach the wav2vec2 model's forward pass. The `_LanguageAwareIpaProvider` adapter introduced by the same PR re-encloses the language in a fresh provider object, but its sole `transcribe_window_structured` method calls back into the same `_transcribe_ipa_window_structured`, so the TypeError fallback fires there too.

The full-mode IPA path is the one place language is actually consumed: `transcribe_words_with_forced_align(audio, segments, ..., language=language_str or 'ku', ...)` forwards into `_g2p_word(word_text, language=language)`, which produces espeak-ng phonemizations of the orthographic word text used as the **target** sequence for `torchaudio.functional.forced_align`. Changing `language` there changes the G2P phonemes (English `head` → `/h ɛ d/`; Kurdish `سەر` → different phonemes), which changes the per-word boundary refinement, which changes the audio sub-windows fed to wav2vec2. The wav2vec2 acoustic decode itself is unchanged.

#### Phase 1 — V0 vs V1 on 4 Fail01 concept windows

Same audio, same loaded aligner, four `_transcribe_ipa_window_structured` calls per window with different `language=` values. Per-window output (verbatim from `phase1_results.json`):

| Concept | Window (s)        | Live on disk (English-leak)            | V0 (`None`) | V1 (`sdh`) | V (`ku`) | V (`en`) |
|---------|-------------------|----------------------------------------|-------------|------------|----------|----------|
| one     | [5.700, 6.310]    | `anɡøsɹɛviː`                           | `mɡɛsmɪ`    | `mɡɛsmɪ`   | `mɡɛsmɪ` | `mɡɛsmɪ` |
| two     | [11.745, 12.340]  | `soʊwʌdɪdjuːɪkspleɪnsoʊfɑː`            | `pleɪnsoʊf` | `pleɪnsoʊf`| `pleɪnsoʊf` | `pleɪnsoʊf` |
| three   | [16.313, 17.148]  | `vɛntənɑːəztɪŋlɛftəɪksplaɪnɪzdʒʌs`     | `tɪŋlaftiː` | `tɪŋlaftiː`| `tɪŋlaftiː` | `tɪŋlaftiː` |
| tree    | [1495.426, 1496.042]| `brambram`                           | `br`        | `br`       | `br`     | `br`     |

Result: `V0 == V1 == V_ku == V_en` on every window. Four language values, identical CTC output, four times. The `language` kwarg is inert at this layer.

The V0/V1 outputs differ from the live-on-disk values because the live data was generated in CUDA on a different runtime configuration (full-mode 3-tier path, GPU); this session ran the concept-window path on CPU. That difference is acoustic-layer (device/path), not language-layer.

#### Phonological judgment — V1 is not "more Kurdish" than V0

Even though all four V1 outputs are identical to V0, the more important question for PR #355 is whether the V1 phonemes resemble Kurdish at all. They do not:

- *one* → `mɡɛsmɪ` — English-leaning vowels (`ɛ`, `ɪ`); no `/q/`, `/x/`, `/ʕ/`, `/ɣ/`.
- *two* → `pleɪnsoʊf` — `eɪ`, `oʊ`: canonical English diphthongs; `ʊ`, `f` cluster reading "explain so f".
- *three* → `tɪŋlaftiː` — `ɪŋ`, `ft`, `iː`: English-pattern reading "thinking left-y".
- *tree* → `br` — short, no vowels resolved on the 0.6 s window.

The model is honestly transcribing English-pattern audio. The Fail01 concept-window audio at these timestamps appears to contain English speech (researcher-side English explanation captured on the same channel as the speaker), and wav2vec2-xlsr-53-espeak-cv-ft has no setting that would make it ignore the audio it actually hears. PR #355's language-fallback fix does not address this class of defect — it cannot, because the model has no language conditioning input.

#### Verdict

PR #355's language hint is a no-op at the wav2vec2 IPA model output for concept-window and per-lexeme paths (V0 == V1 across all language codes tested). The PR is not harmful — the TypeError fallback is correct defensive code and the test suite around `_LanguageAwareIpaProvider` legitimately proves the language string flows through PARSE's Python helpers up to the model boundary — but the user-visible English-leak on Fail01 concept windows will not change after merging. The fix is upstream of the IPA model in the dataflow, but downstream of the actual root cause (English-language audio on Kurdish concept windows).

The fix's only operational effect on real model output is in the **full-mode** IPA path, where `transcribe_words_with_forced_align(language=...)` changes the espeak-ng G2P targets used for forced alignment. Whether that meaningfully improves boundary refinement on this corpus is **not measured this session** (full-mode requires an ortho/ortho_words tier and a long Tier 2 + Tier 3 run that risks the recurring wav2vec2 CPU-thread / WSL-CUDA segfault class).

### Phases not measured this session

- **Phase 2 — full-mode IPA G2P language sweep**: would require running `transcribe_words_with_forced_align` with `language='ku'` vs `language='en'` on a stable ortho_words tier and comparing the per-word IPA outputs. Not run this session — the test machinery for full-mode 3-tier is not in the isolated workspace, and the run is long enough to compete with Lucas's GPU.
- **Phase 3 — concept-window stress test on 20 random Fail01 concepts**: would characterize the English-leak rate quantitatively rather than on 4 windows. Not run this session — Phase 1's V0==V1 across 4 windows + the model's lack of a language input together make a 20-window expansion redundant for the PR-merge question.

## Known limitations

- **No language conditioning input**: this is a single multilingual checkpoint. Per Phase 0/1, no value of `language=` passed at the API boundary changes the CTC output. Anyone reading PR #355's tests should know they prove the language string flows through PARSE's helpers; they do not prove and cannot prove the model uses it, because the model has no place to use it.
- **CPU by default on WSL hosts**: `wav2vec2.allow_wsl_cuda=false` routes the production aligner to CPU on Lucas's WSL2 RTX 5090 host even when CUDA is reported available. Concept-window decode is fast enough on CPU for short clips; full-file 3-tier on a 9000 s recording is not. If you flip `allow_wsl_cuda=true`, you re-enter the historical segfault class on this WSL2 host — see `python/ai/forced_align.py:_configure_torch_cpu_thread_limits` for the related thread-pool guard. Phase 1 this session ran on CPU and did not segfault.
- **Encoder representation is fixed at 16 kHz mono**: the audio loader resamples to mono 16 kHz. Recordings with strong stereo separation or background channel content (e.g. researcher microphone bleed-through) lose any chance of channel-based separation before the model sees the audio.
- **English-language audio in Kurdish concept windows is not recoverable by language hint**: when a saved concept bound contains English speech (researcher prompt, code-switching, off-mic explanation captured on the same channel), the model will transcribe English-pattern phonemes. Fixing this requires fixing the bound (re-time the concept window) or the audio (separate the channels), not the language string.
- **Phase 0 was the only test**: PR #355's per-PR test suite (`test_compute_speaker_ipa_language_fallback.py`) verifies that PARSE's IPA compute call frame resolves and forwards the language string — a real, useful invariant — but uses a fake provider that accepts the kwarg. The empirical question of whether a real `Aligner` accepts and uses the kwarg is answered here for the first time.

## References

- Model card: [`facebook/wav2vec2-xlsr-53-espeak-cv-ft`](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft) on HuggingFace.
- XLSR-53 paper: Conneau et al., *Unsupervised Cross-lingual Representation Learning for Speech Recognition*, arXiv:2006.13979.
- wav2vec 2.0 paper: Baevski et al., *wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations*, arXiv:2006.11477.
- PARSE high-level provider mapping: [`docs/ai-integration.md`](../ai-integration.md).
- ORTH companion doc: [`docs/models/razhan-whisper-base-sdh.md`](razhan-whisper-base-sdh.md).
- Engineering PRs touching IPA: [#355 (this PR — language fallback at the call frame)](https://github.com/ArdeleanLucas/PARSE/pull/355). Earlier wav2vec2-IPA work has been folded into the main `forced_align` and `ipa_transcribe` modules referenced above.
- Mission Control: MC-361 — Fail01 IPA English-leak / Lane MC-361-A.
- Code paths: `python/ai/forced_align.py` (Aligner load + `transcribe_window` + `transcribe_window_structured` + `align_segments`), `python/ai/ipa_transcribe.py` (`transcribe_slice_structured`, `transcribe_intervals`, `transcribe_words_with_forced_align`), `python/server_routes/annotate.py` (`_transcribe_ipa_window_structured`, `_LanguageAwareIpaProvider`, `_compute_speaker_ipa`, `_compute_speaker_ipa_concept_windows`, `_transcription_language_from_payload_or_annotation`).
- Validation artifact (this session): `/tmp/parse-isolation-mc-361-validation/phase1_results.json`.
