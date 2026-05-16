# `razhan/whisper-base-sdh`

The default ORTH (orthographic transcription) model for Southern Kurdish in PARSE. A Whisper base fine-tune trained on Southern Kurdish (Sorani / SDH) speech that emits Arabic-script Kurdish text.

## Identity

| Field | Value |
|---|---|
| HuggingFace repo | [`razhan/whisper-base-sdh`](https://huggingface.co/razhan/whisper-base-sdh) |
| Base model | `openai/whisper-base` (74M params) |
| Architecture | Whisper encoder-decoder, 30 s log-mel input, BPE decoder |
| Output script | Arabic-script Kurdish |
| Language code | The repo card uses `sd`/`sdh`; the underlying Whisper tokenizer accepts `fa` (Persian). PARSE's provider auto-maps `sd` → `fa` so token IDs resolve. |
| License | See model card on HuggingFace. |

## Where it's used in PARSE

| Compute path | Provider class | Entry point |
|---|---|---|
| Per-lexeme rerun | `HFWhisperProvider` | [`python/ai/providers/hf_whisper.py:transcribe_segments_in_memory`](../../python/ai/providers/hf_whisper.py) via `python/ai/stt_pipeline.py:run_ortho_on_interval` |
| Concept-window bulk rerun ("Run all concepts" / "Run edited concepts") | `HFWhisperProvider` | `transcribe_clip` from `python/server_routes/annotate.py:_run_step_on_concept_windows` |
| Full-file ORTH (whole-speaker compute) | `HFWhisperProvider` | `transcribe` chunked at 30 s, called by `_compute_speaker_ortho` |
| Refine-lexemes pass inside full-mode ORTH | `HFWhisperProvider` | `transcribe_clip` from `_short_clip_refine_lexemes` |

The provider is selected by `ortho.backend` in `config/ai_config.json` — `"hf"` (default) loads `HFWhisperProvider`; `"faster-whisper"` loads `LocalWhisperProvider` against a CT2 conversion of the same model.

## Configuration

Config schema was sectioned in PR #494. Legacy flat `ortho` configs must be migrated before PARSE starts: run `python python/tools/migrate_ai_config_ortho.py --workspace <path>` for a dry-run, then add `--apply` to write. The migrator creates a timestamped `ai_config.json.bak-…` backup before changing the local file.

Block in `config/ai_config.json`:

```json
"ortho": {
  "backend": "hf",
  "model": {"repo_id": "razhan/whisper-base-sdh", "device": "cuda"},
  "generation": {
    "language": "sd",
    "condition_on_prev_tokens": false,
    "compression_ratio_threshold": 1.8,
    "no_repeat_ngram_size": 3,
    "repetition_penalty": 1.2
  },
  "decoding": {
    "initial_prompt": "",
    "refine_lexemes": false
  }
}
```

Knob-by-knob:

| Knob | Default | Effect | Notes |
|---|---|---|---|
| `ortho.backend` | `hf` | Selects the provider class (`hf` = Hugging Face Transformers, `faster-whisper` = CT2 / faster-whisper). | The `hf` backend is what receives empirical attention here. The `faster-whisper` backend exists for parity testing and legacy CT2 opt-in. |
| `ortho.model.repo_id` | `razhan/whisper-base-sdh` | HF repo id or local HF-format directory. | Replaces legacy `model_path`; CT2 directories are still detected and rejected with the same actionable error text because they belong only on the faster-whisper backend. |
| `ortho.generation.language` | `sd` | Whisper language code. Auto-mapped to `fa` for the underlying tokenizer. | Override per-call via the `language` kwarg on the provider's transcribe methods. |
| `ortho.model.device` | `cuda` | `cuda` / `cuda:0` / `cpu` / `auto`. | The provider normalizes CUDA requests through the PARSE compute-device resolver. |
| `compute_type` | — | **Deprecated for HF.** The HF runtime stays FP32 today. | Future fp16 work should be a new MC after the milk/two/that/Khan02-cid-4 quality A/B; the faster-whisper backend still honors this CT2 knob. |
| `vad_filter`, `vad_parameters` | — | **Deprecated for HF.** Provider-level VAD is gone from the HF path. | If VAD is needed, it belongs in the upstream interval pipeline. The faster-whisper backend still honors these keys when explicitly selected. |
| `ortho.generation.condition_on_prev_tokens` | `false` | Whisper's "condition the next chunk on the previously generated text" feature. False is correct for short-clip ORTH — leaking the previous chunk's text causes loops on clip boundaries. | Renames legacy `condition_on_previous_text`; the cascade-fix rationale is unchanged. |
| `ortho.generation.compression_ratio_threshold` | `1.8` | Whisper long-form fallback threshold; rejects high-compression hallucinations and retries with higher temperature when long-form decoding is active. | Owned by `model.generation_config` at provider load. |
| `ortho.generation.no_repeat_ngram_size` | `3` | Bans any 3-gram from appearing twice in the output. | Functional on the HF backend's `model.generate` path. |
| `ortho.generation.repetition_penalty` | `1.2` | Logit penalty for repeating tokens. | Functional on the HF backend's `model.generate` path. |
| `ortho.decoding.initial_prompt` | `""` (empty after the 2026-05-07 incident; previously had a Kurdish primer) | Text fed as decoder prefix via `processor.get_prompt_ids(...)` only when a caller opts in. | See the "Empirical evidence" section below — seeding caused the model to parrot the prompt verbatim on short clips, and incidentally enabled three other defect classes. Default to leaving it empty unless a specific use case requires seeding. |
| `ortho.decoding.refine_lexemes` | `false` | Run a second-pass concept-window decode for weak/missing lexemes after full-file ORTH. | Independent of pad / prompt — see `_short_clip_refine_lexemes` for behavior. |

The per-call API for ORTH bulk and per-lexeme rerun also accepts a `pad` field with allowed values `{0.0, 0.2, 0.5}` and default `0.2`. This widens the audio window passed to the encoder relative to the user-selected interval. See "Tuning guide" below.

## Tuning guide

**Symptom: rerun output looks like a rote textbook sentence followed by the actual word.**
That's the model parroting `ortho.initial_prompt`. Fix at the call site by passing `initial_prompt=None` (the default for all public methods after PR #299). Do not put a non-empty string in `ortho.initial_prompt` unless you understand the trade-off — see the empirical section below.

**Symptom: short clip clips a final consonant or stop release.**
Increase pad. Default `0.2` widens the window by 0.2 s on each side; bump to `0.5` for cases where the lexeme bound is tight against an articulator release. Beyond `0.5` you start pulling in neighboring words and the model produces phrase output instead of single-lexeme output.

**Symptom: rerun returns multi-word output for a single lexeme.**
Decrease pad. Try `0.0`. The saved bound may also be wider than the actual phoneme — inspect the audio.

**Symptom: stuck-token loop in saved data (e.g. `"چۆی ژەی ژەی ژەی ژەی…"`).**
Re-run with the current code path; the prompt-suppression fix (PR #299) appears to incidentally remediate stuck loops. See "Empirical evidence — Southern Kurdish — 2026-05-07" for the cross-defect remediation data.

**Symptom: dittography (e.g. `"تو تو"`, `"هاتن هاتن"`).**
Same as above. Re-run on current code; usually resolves.

**Symptom: Latin characters appear in Kurdish output.**
Same as above. Counter-intuitively, the Arabic-script `initial_prompt` was *causing* this drift, not protecting against it. Removing the prompt fixes the Latin drift.

**Symptom: full-file ORTH chunks each prefixed with a paragraph.**
The full-file path was parroting `ortho.initial_prompt` until PR #299 landed. Re-run on current code path. Already-saved data from before PR #299 needs the parrot-prefix-strip cleanup utility (`tools/strip_ortho_parrot.py`).

**Settings that won't help (empirically tested, do not introduce):**

- `max_new_tokens` cap: when `prompt_ids` is set, HF Whisper consumes the prompt as decoder prefix and the cap doesn't clamp the parrot output. Caps are not a parrot fix; suppressing the prompt at the call site is.
- Beam search (any beam count), temperature sampling, `return_timestamps=True`: ten different decode strategies were tested on the milk lexeme at 0 pad and all returned identical output. The encoder representation is what determines acoustic accuracy at tight bounds; only widening the audio context (pad) can change it.

## Empirical evidence

### Southern Kurdish — 2026-05-07

This subsection captures the empirical work that produced the current default settings. PARSE PRs landed: ArdeleanLucas/PARSE#298, ArdeleanLucas/PARSE#299, ArdeleanLucas/PARSE#300, ArdeleanLucas/PARSE#301, ArdeleanLucas/PARSE#302. Data cleanup utility: `tools/strip_ortho_parrot.py`.

#### Trigger

A user-visible bug — per-lexeme ORTH rerun on Saha01 milk (1.014 s) returned six clauses of textbook Kurdish prefacing the actual word — was traced to a single root cause: `HFWhisperProvider._transcribe_audio_payload` was reading `self.initial_prompt` from config and unconditionally seeding it into `model.generate(prompt_ids=...)`, regardless of caller intent. The kwarg `initial_prompt` exposed by `transcribe_clip` was being silently discarded (`_ = initial_prompt`).

#### Phases

Five phases of read-only empirical work against the live PC workspace and audio. All phases loaded the production `HFWhisperProvider` directly with the live `ortho` config section.

```
Phase 1   V0 vs V1-V4 on 4 Saha01 lexemes                      proves parrot is suppressible
Phase 2A  Concept-window path with pad=0.8                     proves the action-menu path silently parrots too
Phase 2B  Full-file path on a 60 s slice                       proves the full-file path parrots every chunk
Phase 3   Pad sweep [0.00 … 1.50 s] on milk/two/that           characterizes pad's effect on accuracy
Phase 4A  Khan02 cross-speaker pad sweep                       confirms pad behavior is acoustic, not Saha-specific
Phase 4B  Decode-strategy sweep on milk @ 0 pad                proves search/sampling tweaks cannot recover acoustics
Phase 4C  V1 + pad=0.2 stress test on 40 random Saha01         characterizes V1's natural cleanliness ceiling
Phase 5   V1 on 45 intervals across 5 lanes                    confirms V1 incidentally remediates 3 other defect classes
```

A parallel corpus audit catalogued the saved-data defect taxonomy across all 10 speakers and 4 tiers (17,004 intervals total).

#### Phase 1 — V0 vs V1 baseline

Result on milk (`[3624.000, 3625.014]`, 1.014 s):

```
V0  current code, prompt seeded         56 tokens   <PARROT> + شید
V1  initial_prompt=None                  8 tokens   شید
V2  initial_prompt seeded + token cap   56 tokens   <PARROT> + شید   (cap doesn't apply to prompt prefix)
V3  no prompt + token cap                8 tokens   شید
V4  no prompt + cap + 0.05 pad           8 tokens   شید
```

V1 alone fixed the bug in every test case (4 lexemes). The token cap is a non-fix; it was dropped from the design.

#### Phase 2 — three production paths affected

Per-lexeme rerun, concept-window bulk path, and full-file path were all separately demonstrated to seed the prompt. A 60 s slice through `provider.transcribe()` produced a parrot prefix on every 30 s chunk. Cross-referenced corpus audit:

```
Fail01 ortho   523/523  parrot    full-file path, 100% poisoned
Fail02 ortho   132/132  parrot    full-file path, 100% poisoned
Khan01 ortho   287/287  parrot    full-file path, 100% poisoned (+ 184 in ortho_words tier)
Khan02 ortho     0/503  clean     concept-window path, generated under faster-whisper backend
Khan03 ortho     0/283  clean     concept-window path, generated under faster-whisper backend
Khan04 ortho     0/401  clean     concept-window path, generated under faster-whisper backend
Saha01 ortho     0/497  clean     concept-window path, generated under faster-whisper backend
```

The clean speakers were clean only because their ORTH had been generated before PR #218 changed the default ORTH backend from `faster-whisper` to HF Transformers. The old `local_whisper.py` path honored the `initial_prompt=None` kwarg correctly; the new HF path silently dropped it.

#### Phase 3 — pad sweep on milk, two, that

```
milk  saved=شیر خاردم شیر  bounds 1.014s
  pad=0.00   شید             ← clipped trailing 'r'
  pad=0.05   شید             ← still clipped
  pad=0.20   شیر             ← correct
  pad=0.50   خاردن شیر       ← partial verb + correct word
  pad=0.80   شیر خاردم شیر   ← full saved phrase emerges
  pad=1.50   شیر ژێ خاردم    ← pulls in adjacent context

two   saved=دو              bounds 0.664s
  pad=0.00   دو              ← correct
  pad=0.20   دەو             ← extra vowel inserted
  pad=0.50   دو              ← correct
  pad=1.50   دۊ دۊ ڤەو       ← gibberish, wraps neighbors

that  saved=ئەو ەو           bounds 0.699s
  pad=0.00–0.20  ئەو         ← single 'that'
  pad=0.50–1.50  ئەو ڤێ      ← picks up Persian neighbor
```

Pad effects are not monotonic. `two` is best at 0.0 / 0.5 / 0.8 and worst at 0.2. `milk` is wrong at 0.0–0.05 and best at 0.2. No single pad is universally optimal, which motivated the user-facing pad knob.

#### Phase 4A — Khan02 cross-speaker pad sweep

```
cid 513 'نە'   pad sweep:  نە / نە / نە / نە / نە                       ← stable
cid 12  'باوک'  pad sweep:  باوک / باوک / باوک / باوک / باوک              ← stable
cid 4   'کەش'   pad sweep:  قەش / کەش / کەش / قەش / کەش                  ← q vs k flips
cid 599 stuck   pad sweep:  قەش / بش / گەش / گەش / گەش                   ← saved was stuck loop
```

Most lexemes are pad-insensitive. A few exhibit a sub-phoneme acoustic ambiguity that flips with pad value. Pad behavior generalizes across speakers (not Saha-specific).

#### Phase 4B — decode-strategy sweep on milk @ 0 pad

```
V1 greedy (no prompt)                       شید
beam=2                                      شید
beam=5                                      شید
beam=8                                      شید
temperature=0.2 + sampling                  شید
temperature=0.4 + sampling                  شید
return_timestamps=True (greedy)             شید
return_timestamps=True + beam=5             شید
max_new_tokens=8                            شید
max_new_tokens=8 + beam=5                   شید
```

Ten strategies, identical output. The encoder representation of the 1 s clip puts overwhelming probability mass on `د` over `ر`. Search alternatives, sampling diversity, and length caps cannot re-rank what the encoder doesn't propose. Acoustic context (pad) is the only lever.

#### Phase 4C — V1 + pad=0.2 stress test on 40 random Saha01 lexemes

```
EXACT match (V1 == saved):       10  (25.0%)
V1 ⊆ saved  (V1 fragment):       13  (32.5%)
saved ⊆ V1  (V1 + extra):          0  (0.0%)
different  (no containment):      17  (42.5%)
empty:                              0  (0.0%)
parrot prefix:                      0  (0.0%)

saved word counts: min=1 max=86 mean=6.10
V1    word counts: min=1 max=8  mean=1.52
```

Of the "different" rows, a substantial share are V1 cleaning up saved data that contained stuck-token loops or dittographies. Genuine acoustic mis-decodes are ~5–8 of 40 (~15–20 %), most are 1–2 character variants. V1 does not introduce empty outputs, parrot prefixes, or extra junk in any of the 40 cases.

#### Phase 5 — cross-defect remediation test

```
Lane 1  Khan02/ortho stuck-loops          10/10 clean
Lane 2  Saha01/ortho dittographies        10/10 clean
Lane 3  Khan03/ortho mixed-script Latin    5/5  clean
Lane 4  Qasr01/concept fresh decode       10/10 clean
Lane 5  Mand01/concept fresh decode       10/10 clean
                                          ────────────
                                          45/45 clean
```

All three non-parrot defect classes share a root cause with the parrot. With the prompt suppressed, all four classes resolve. The Latin-script result on Khan03 was the surprise: the configured Arabic-script prompt was *causing* the Latin drift, not protecting against it (probably through encoder-decoder confusion when the prompt's tokens dominate generation budget on weak audio anchors).

#### Settings rationale

| Setting | Default | Justification |
|---|---|---|
| `initial_prompt` (per call) | `None` | Phase 1, 2A, 2B, 5 — load-bearing for parrot suppression and incidentally for stuck-loop / dittography / Latin remediation. |
| `pad` (per call) | `0.2` | Phase 3, 4A — empirical sweet spot for single-lexeme accuracy on this model. 0.0 for clean utterances, 0.5 for cases needing surrounding context. UI exposes `{0.0, 0.2, 0.5}`. |
| `max_new_tokens` | not set, not exposed | Phase 1 V2 — does not clamp parrot, does not improve accuracy. |
| `temperature`, `do_sample`, `num_beams`, `return_timestamps` | unchanged from defaults, not exposed | Phase 4B — none recover acoustic accuracy at tight bounds. Exposing them would be theatrical. |

## Known limitations

- **Tight clips lose final consonants**: at pad 0.0 the encoder cannot anchor a stop release at the trailing edge of a 1 s clip and may commit to an acoustically similar wrong character. Phase 3 milk `'شید' → 'شیر'` is the example. Default pad 0.2 mitigates; tight-bound use cases require manual review.
- **Per-lexeme accuracy is not transcript-quality**: Phase 4C exact-match rate against pre-existing saved annotations is 25%. Many "different" rows are V1 producing cleaner output than saved (which had stuck loops); genuine acoustic mis-decodes are ~15–20% of the 40-sample test. Single-syllable Kurdish lexemes are the easy case for this model; multi-syllable and long-vowel lexemes are harder.
- **Concept-window-only model output is single-lexeme by default**: pad=0.2 over a ~1 s saved bound produces a single-word decode. To get multi-word output, save a wider bound or run at pad=0.5+. The model has no notion of "expected output length" — it transcribes whatever audio it sees.
- **No VAD trim on the HF backend**: the `vad_filter` / `vad_parameters` config knobs are honored only by the faster-whisper backend. Edge silence is fed to the encoder as-is on the HF backend. In practice this has not produced visible artifacts under default settings, but if it becomes a problem the fix would be either VAD pre-processing in the provider or moving to long-form decoding.
- **Mixed-script drift was real before the fix**: Phase 5 confirmed it resolves for the speakers tested (Khan03), but no formal cross-language test exists. If you encounter Latin tokens in Kurdish output on a fresh decode, file an empirical-evidence subsection note here.

## References

- Model card: [`razhan/whisper-base-sdh`](https://huggingface.co/razhan/whisper-base-sdh) on HuggingFace.
- Whisper paper: Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision*, arXiv:2212.04356.
- PARSE incident-and-fix: [`docs/orth-initial-prompt-suppression.md`](../orth-initial-prompt-suppression.md).
- PARSE high-level provider mapping: [`docs/ai-integration.md`](../ai-integration.md).
- Engineering PRs: [#298](https://github.com/ArdeleanLucas/PARSE/pull/298), [#299](https://github.com/ArdeleanLucas/PARSE/pull/299), [#300](https://github.com/ArdeleanLucas/PARSE/pull/300), [#301](https://github.com/ArdeleanLucas/PARSE/pull/301), [#302](https://github.com/ArdeleanLucas/PARSE/pull/302).
- Mission Control: MC-346 (BE prompt suppression), MC-347 (FE pad selector), MC-348 (coord docs), MC-349 (umbrella), MC-350 (parrot data cleanup), MC-351 (BE pad parity), MC-352 (FE pad parity).
- Data-cleanup utility: `tools/strip_ortho_parrot.py` (idempotent, dry-run by default).
