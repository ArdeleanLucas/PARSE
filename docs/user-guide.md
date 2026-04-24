# User Guide

> Last updated: 2026-04-24
>
> This guide focuses on the current PARSE workstation as described in the latest repository README: the unified React shell, Annotate route `/`, Compare route `/compare`, CLEF, the AI chat dock, and processed-speaker workspace hydration.

PARSE is organized around two tightly linked research modes:

- **Annotate** — per-speaker segmentation, transcription, timing correction, and anchor confirmation
- **Compare** — cross-speaker lexical comparison, cognate adjudication, borrowing review, and export preparation

The same workspace, tag system, and backend data model support both.

<!-- TODO: Add an Annotate-mode screenshot here: waveform, tiers, transcription lanes, and chat dock visible together. -->
<!-- TODO: Add a Compare-mode screenshot here: concept × speaker matrix, cognate controls, and CLEF panel. -->

## Workflow at a glance

A typical PARSE session moves through these stages:

1. Import or hydrate a speaker into the active workspace
2. Normalize the audio if needed
3. Run STT, ORTH, and acoustic IPA support jobs
4. Review and correct boundaries in Annotate mode
5. Use **Search & anchor lexeme** when concept locations are difficult to find
6. Switch to Compare mode for cross-speaker adjudication
7. Consult **CLEF** when borrowing or contact influence is in question
8. Export LingPy TSV or NEXUS for downstream analysis

## Annotate Mode (`/`)

Annotate mode is the per-speaker workstation for turning long recordings into time-aligned annotation data.

### What you see in Annotate mode

The current Annotate surface includes:

- **WaveSurfer 7 waveform review** for long recordings
- **Four annotation tiers**:
  - IPA
  - orthography
  - concept
  - speaker
- **Stacked transcription lanes** under the waveform for:
  - STT
  - IPA
  - ORTH
- **Synchronized horizontal scrolling** between waveform and lanes
- **Clip-bounded playback** for the selected region
- A global **Space** play/pause hotkey
- Concept display and sorting controls
- Tag/filter controls for selective review
- The shared **AI chat dock**

### Annotate jobs and automation

PARSE's annotation workflow is designed around explicit, inspectable support jobs rather than opaque one-click automation.

#### Audio normalization

Normalization runs through `/api/normalize` and supports in-place working-audio generation.

Use it when:

- source levels are inconsistent
- the recording needs a stable working copy for later STT/alignment
- you want the workspace to reflect a reproducible audio-prep stage

#### STT

The speaker-level STT job (`/api/stt`) provides:

- progress and error reporting
- automatic language detection from project metadata when available
- tunable task / VAD / beam-size settings through config
- nested word-level timestamps in `segments[].words[]`

This is the main starting point for locating lexical material in long recordings.

#### ORTH

The speaker-level ORTH job (`computeType='ortho'`) is backed by **Razhan** (`razhan/whisper-base-sdh`) for full-waveform Kurdish orthographic transcription.

The current defaults keep VAD off so the whole recording is covered unless you deliberately retune it.

#### Forced alignment

Tier 2 forced alignment uses `torchaudio.functional.forced_align` against wav2vec2 to tighten word windows and optionally emit phoneme spans.

This is the step that turns coarse word timing into more reviewable alignment.

#### Acoustic IPA fill

The current IPA path is **acoustic wav2vec2-only**.

When word-level STT cache is available, `computeType='ipa_only'` uses the full forced-alignment path word by word. If that cache is missing, PARSE falls back to coarse ORTH-interval slices.

### Batch transcription workflow

Annotate mode also supports a batch runner for one or many speakers.

The current batch flow includes:

- preflight pipeline-state checks
- overwrite warnings
- explicit ordered steps: **normalize → STT → ORTH → IPA**
- step-level failure isolation
- rerun-failed support
- a walk-away batch report with expandable tracebacks
- explicit **empty-step detection** for runs that technically completed but wrote no intervals
- skip-breakdown counters and exception samples for steps that ran but still produced no usable output

A key detail is that preflight distinguishes **"has intervals"** from **"full WAV coverage"** via fields such as:

- `duration_sec`
- `coverage_start_sec`
- `coverage_end_sec`
- `coverage_fraction`
- `full_coverage`

That distinction matters in real fieldwork, where older runs may have seeded a tier without truly covering the full recording.

### Manual review and timing correction

Automation in PARSE is intentionally review-first.

Annotate mode supports:

- draggable lexeme timestamp editing
- manual boundary correction
- constant timestamp-offset detect/apply workflows for CSV↔audio misalignment
- manual fallback from a trusted single pair when automated offset detection is weak

This is one of the main places where PARSE differs from purely transcription-first tools: timestamps are not treated as disposable by-products.

## Lexical Anchor Alignment System

The **Lexical Anchor Alignment System** is one of PARSE's core research features.

It exists because elicitation recordings are often long, noisy, and full of repeated prompts, commentary, and repairs. Manually scanning hours of audio to find each target concept across many speakers is too slow and too inconsistent.

### The two signals

PARSE combines two signals to rank candidate time ranges.

#### Signal A — within-speaker repetition detection

Elicited items are often produced two to four times in close succession. PARSE looks for phonetically similar clusters within a 30-second window and scores them using normalized Levenshtein distance on IPA strings.

#### Signal B — cross-speaker concept matching

PARSE compares unassigned segments against verified annotations from other speakers for the same concept using a four-strategy cascade:

- exact orthographic
- fuzzy orthographic
- phonetic rule-based
- positional prior

The phonetic-rule layer is designed to tolerate documented Southern Kurdish alternations such as onset voicing, nucleus variation, and coda deletion.

### Confidence model

The current README documents the following scoring formula:

```text
confidence = 0.50 × phonetic + 0.25 × repetition + 0.15 × positional + 0.10 × cluster
```

The positional component uses a 45-second tolerance window derived from the cross-speaker median for each concept.

### User-facing control: Search & anchor lexeme

Annotate mode exposes this system directly as **Search & anchor lexeme**.

You provide known orthographic variants of a target form, and PARSE ranks candidate time ranges across the available tiers:

- `ortho_words`
- `ortho`
- `stt`
- `ipa`

The endpoint behind this feature is `GET /api/lexeme/search`.

Current ranking combines:

- within-speaker phonetic similarity
- any available `ortho_words` confidence weighting
- cross-speaker anchor evidence for the same `concept_id`
- contact-language variant augmentation from `config/sil_contact_languages.json`

When you choose **Confirm & Use**, PARSE writes the chosen candidate into `AnnotationRecord.confirmed_anchors[concept_id]`. Those confirmations survive Praat/TextGrid round-trips and improve the cross-speaker signal for later speakers. The Annotate control bar also exposes a numeric playhead readout (`m:ss.sss / m:ss.sss`), which makes anchor confirmation less dependent on eyeballing the waveform alone.

## Compare Mode (`/compare`)

Compare mode is the cross-speaker analysis workspace for historical and comparative work.

### What you see in Compare mode

The current Compare interface provides:

- a **concept × speaker matrix** for side-by-side lexical review
- **cognate controls** for accept, split, merge, and cycle
- per-row cognate-group editing
- speaker flags and secondary-action controls
- borrowing adjudication aided by contact-language similarity signals
- enrichment overlays for computed analysis metadata
- the **CLEF** panel
- the shared tag system
- export actions for LingPy TSV and NEXUS

### Cognate review workflow

Compare mode is where annotation data becomes comparative data.

Typical use:

1. Open a concept row across speakers
2. Review the forms side by side
3. Accept, split, merge, or cycle cognate groups
4. Mark speaker-level irregularities or flags where needed
5. Consult enrichment overlays and contact-language evidence
6. Preserve manual adjudications for export

The goal is not just visualization — it is structured decision-making for downstream comparative analysis.

## CLEF — Contact Lexeme Explorer Feature

**CLEF** provides contact-language similarity data for borrowing adjudication.

It is implemented as a provider-registry workflow under `python/compare/providers/` and surfaced in the `ContactLexemePanel` UI.

### What CLEF does in practice

When a lexical item might reflect contact influence rather than straightforward inheritance, CLEF can fetch comparison data from multiple external and local sources, then surface that evidence during Compare-mode review.

### Current provider set (10)

| Provider | Source type |
|---|---|
| `asjp` | ASJP database |
| `cldf` | CLDF datasets |
| `csv_override` | Local CSV overrides |
| `grokipedia` | LLM-assisted lookup (xAI/Grok) |
| `lingpy_wordlist` | LingPy wordlist data |
| `literature` | Published literature references |
| `pycldf_provider` | `pycldf` library |
| `pylexibank_provider` | `pylexibank` library |
| `wikidata` | Wikidata lexemes |
| `wiktionary` | Wiktionary entries |

### Current CLEF endpoints

- `POST /api/compute/contact-lexemes` — start a contact-lexeme fetch job
- `GET /api/contact-lexemes/coverage` — inspect current provider coverage

## AI Workflow Assistant in daily use

Both Annotate and Compare include the built-in AI chat dock.

In user-facing terms, it can currently help with:

### Audio setup and file management

- locating and loading `.wav` sources
- checking audio health
- guiding normalization

### Annotation workflow

- walking through the four tiers
- launching STT to locate candidate segments
- assisting with boundary correction and iterative review

### Cross-speaker analysis

- preparing Compare mode sessions
- explaining cognate controls
- helping interpret borrowing and enrichment evidence

### Export and downstream work

- guiding LingPy TSV export
- explaining export structure for later pipelines

### Troubleshooting

- diagnosing STT, IPA, normalization, and pipeline failures
- identifying missing files, metadata mismatches, or annotation gaps
- explaining server-log errors in workflow terms

The in-app assistant has read and write access to the project through its bounded PARSE tool layer, so it can stage workflow actions rather than only answering questions.

## Speaker import and workspace hydration

Recent PARSE work expanded the project beyond raw upload-only onboarding.

The current workstation and MCP adapter support **processed-speaker imports**, meaning a speaker can be hydrated into the active workspace from an existing artifact set rather than from a fresh raw upload alone.

Supported source artifacts currently include:

- a working WAV under `audio/working/<Speaker>/`
- `annotations/<Speaker>.json` or `annotations/<Speaker>.parse.json`
- `peaks/<Speaker>.json`
- optional `coarse_transcripts/<Speaker>.json`
- optional legacy transcript CSV under `imports/legacy/<Speaker>/`

This matters for thesis workflows where the richest aligned source is an already processed speaker package, not a brand-new pipeline run.

## Recommended user path

If you are starting from scratch:

1. Read [Getting Started](./getting-started.md)
2. Launch PARSE and configure `ai_config.json`
3. Import or hydrate one speaker
4. Work through Annotate mode until timestamps are trustworthy
5. Move to Compare mode for cognate and borrowing decisions
6. Use [AI Integration](./ai-integration.md) when configuring providers or the built-in assistant
7. Use [API Reference](./api-reference.md) if you are automating any part of the workflow
