# User Guide

> Last updated: 2026-04-27
>
> This guide focuses on the current PARSE workstation as described in the latest repository README: the unified React shell, Annotate route `/`, Compare route `/compare`, CLEF, the AI chat dock, and processed-speaker workspace hydration.

PARSE is organized around two tightly linked research modes:

- **Annotate** — per-speaker segmentation, transcription, timing correction, and anchor confirmation
- **Compare** — cross-speaker lexical comparison, cognate adjudication, borrowing review, and export preparation

The same workspace, tag system, and backend data model support both.

<p align="center">
  <img src="./pr-assets/dogfood-fix-153-annotate-stable.png" alt="Annotate mode in PARSE" width="48%" />
  <img src="./pr-assets/pr76-compare-table.png" alt="Compare mode in PARSE" width="48%" />
</p>

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
  - optional **Words (Tier 1)** diagnostics (off by default)
  - optional **Boundaries (Tier 2)** diagnostics (off by default)
- **Inline lane editing** across STT, IPA, and ORTH via double-click or right-click context actions
- **Synchronized horizontal scrolling** between waveform and lanes
- **Clip-bounded playback** for the selected region
- A global **Space** play/pause hotkey
- **Per-speaker undo/redo** controls in the Annotate playback bar, with `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, and `Ctrl/Cmd+Y`
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
- an editable STT lane in Annotate mode: the first manual STT edit lazily migrates cached STT segments into `record.tiers.stt`, after which STT supports the same inline edit / split / merge / delete affordances as IPA and ORTH

This is the main starting point for locating lexical material in long recordings.

#### ORTH

The speaker-level ORTH job (`computeType='ortho'`) is backed by a **local CTranslate2 conversion** of Razhan (`razhan/whisper-base-sdh`) for Southern Kurdish orthographic transcription.

Current runtime truth:
- `ortho.model_path` must be an explicit local CT2 directory
- HuggingFace repo ids are rejected here; convert first with `ct2-transformers-converter`
- ORTH defaults now keep the anti-cascade guard enabled: tuned `vad_filter=True`, `condition_on_previous_text=False`, and `compression_ratio_threshold=1.8`

#### Forced alignment

Tier 2 forced alignment uses `torchaudio.functional.forced_align` against wav2vec2 to tighten word windows and optionally emit phoneme spans.

This is the step that turns coarse word timing into more reviewable alignment.

Annotate mode now also includes two optional diagnostic lanes (both hidden by default) beneath the waveform:

- **Words (Tier 1)** — cyan boxes from `sttBySpeaker[speaker].segments[].words[]`
- **Boundaries (Tier 2)** — the forced-aligned word windows

Each Tier 2 interval is color-coded from the delta between the Tier 1 STT word and its paired Tier 2 boundary:

- green — worst edge shift under 50 ms
- amber — 50–100 ms
- red — over 100 ms, or a Tier 2 `short_clip_fallback`

When no Tier 1 partner exists, PARSE falls back to Tier 2 `confidence` coloring instead. Stacking **Words (Tier 1)** directly above **Boundaries (Tier 2)** lets you eyeball the same lexical item in both tiers without relying on color alone. Both lanes are read-only in the current build: they are meant to expose suspicious Tier 1 windows before you decide whether to correct timestamps or rerun a step, not to replace the existing interval-editing workflow.

#### Boundary refinement (BND)

The current React Annotate toolbar exposes the BND workflow directly as two gated actions:

- **Refine Boundaries (BND)** appears once the active speaker has Tier 1 STT word timestamps
- **Re-run STT with Boundaries** appears once `tiers.ortho_words` exists for that speaker

Earlier PR notes referred to this area as **Phonetic Tools**, but the verified current UI labels are the two direct actions above.

#### Acoustic IPA fill

The current IPA path is **acoustic wav2vec2-only**.

When word-level STT cache is available, `computeType='ipa_only'` uses the full forced-alignment path word by word. If that cache is missing, PARSE falls back to coarse ORTH-interval slices.

### Batch transcription workflow

Annotate mode also supports a batch runner for one or many speakers.

The current batch flow includes:

- preflight pipeline-state checks
- overwrite warnings
- explicit ordered steps: **normalize → STT → ORTH → IPA**
- per-step **Keep / Overwrite** scope toggles when selected speakers already have finalized output
- step-level failure isolation
- rerun-failed support
- a walk-away batch report with expandable tracebacks
- explicit **empty-step detection** for runs that technically completed but wrote no intervals
- skip-breakdown counters and exception samples for steps that ran but still produced no usable output
- preserved backend `jobId` + `errorPhase` metadata when a speaker started successfully but the UI later lost `/api` connectivity while polling

If a batch report row says **Lost contact after start**, PARSE is telling you that the backend job was created and the browser lost transport later. Use the preserved backend job id to reattach or reconcile before treating that row as a true speaker-level pipeline failure.
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

- inline lane editing on STT / IPA / ORTH with context-menu split, merge-with-next, and delete actions
- per-speaker undo/redo with merge recovery and operation-labelled toasts
- draggable lexeme timestamp editing
- manual boundary correction
- constant timestamp-offset detect/apply workflows for CSV↔audio misalignment
- manual fallback from a trusted single pair when automated offset detection is weak
- optional boundary diagnostics through the **Words (Tier 1)** + **Boundaries (Tier 2)** lanes and the read-only corpus script `scripts/benchmark_tier1_boundaries.py`

The benchmark script is useful when you want a workspace-level read on how far Tier 2 windows are shifting away from Tier 1 STT words without rerunning the pipeline. It reports confidence distributions, onset/offset/max-edge shift percentiles, the fraction of words whose worst edge exceeds the configured padding, and `alignment.methodCounts` from existing `.stt.json` + `.aligned.json` artifacts.

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

Populate jobs now follow the same global-job pattern as other heavy PARSE workflows:

- **Save & populate** closes the modal and moves progress into the shared header status chip
- a successful populate can trigger an automatic recompute so similarity columns refresh against the newly available reference data
- empty-populate outcomes surface explicit `no_forms` or `provider_error` banners rather than silently looking like success
- that banner includes **Retry with different providers** so you can reopen the modal directly on the auto-populate tab

The Compare table and detail views also follow the configured CLEF primaries dynamically: similarity columns are no longer hard-coded to Arabic/Persian, and the **Reference Forms** panel can render multiple forms per language.

The local `lingpy_wordlist` provider now matches doculect identifiers by exact case-insensitive equality (with whitespace / dash / underscore folding), not substring containment. That prevents contact-language buckets such as Arabic from accidentally absorbing unrelated doculects like Avar, Karelian, or Hungarian simply because their identifiers contain `ar`.

Each reference form row has a checkbox. Those selections persist to `sil_contact_languages.json._meta.form_selections`, and only the selected forms contribute to the similarity score.

Bare-string reference forms are no longer routed by Unicode guessing alone. Each configured contact language now carries an ISO 15924 `script` hint, so PARSE can decide deterministically whether a raw form should land in the IPA-like slot or the script-text slot. Explicit provider labels (`ipa` / `script`) still win over the hint, and the Unicode-block regex remains only as a fallback for legacy or hint-less entries.

On a fresh workspace, the first run of **Borrowing detection (CLEF)** now opens a guided **Configure CLEF** modal instead of failing on a missing config file. The modal lets you:

- pick 1–2 primary contact languages
- search a bundled SIL/ISO language catalog
- enable or disable provider groups before auto-population
- save the language setup only, or **Save & populate** immediately

The saved config lives at `config/sil_contact_languages.json`; optional extra catalog entries can be provided through `config/sil_catalog_extra.json`.

If a workspace was populated before the 2026-04-25 exact-match fix in `lingpy_wordlist`, rerun CLEF populate with overwrite so any forms previously misbucketed by substring-matched doculect ids are replaced with the corrected provider output.

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

- `GET /api/clef/config` — read the current CLEF language configuration
- `GET /api/clef/catalog` — read the bundled CLEF language catalog, including per-language ISO 15924 script hints
- `GET /api/clef/sources-report` — read corpus-wide provider provenance for populated reference forms
- `POST /api/clef/config` — save the CLEF language configuration
- `POST /api/clef/form-selections` — persist which reference forms should count toward similarity scoring
- `POST /api/compute/contact-lexemes` — start a contact-lexeme fetch job
- `GET /api/contact-lexemes/coverage` — inspect current provider coverage

### Sources Report, provenance, and citations

The **Sources Report** modal summarizes which providers contributed the currently populated reference forms.

This matters for academic use because CLEF no longer treats the populated form list as an opaque blob. New entries can carry per-form provenance such as `wikidata`, `wiktionary`, `asjp`, or other provider sources, while older bare-string entries remain readable as legacy `unknown` provenance until you explicitly repopulate them.

The report now also includes an **Academic citations** section for the providers that actually contributed forms in the current corpus. For each contributing provider, PARSE can surface:

- a full dataset/tool citation paragraph
- DOI and URL links where available
- provider caveat notes (for example, warnings around AI-generated or legacy unattributed data)
- **Copy citation** and, where applicable, **Copy BibTeX** actions
- an **Export BibTeX** action when at least one contributing provider has a bibliographic entry

This gives thesis workflows a direct path from populated reference forms to footnotes and reference-manager imports, instead of treating provider chips as informal provenance only.

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
