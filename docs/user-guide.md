# User Guide

> Last updated: 2026-05-07
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
- Concept display and sorting controls, including source/survey-aware sidebar ordering when `source_item` / `source_survey` values are present
- Speaker-scoped ConceptSidebar tag/filter controls for selective review (the duplicate Annotate right-drawer concept filter was removed)
- Survey/source badges and optional color coding from `survey-overlap.json`
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
- language resolution from request payload first, then `annotation.metadata.language_code`, before Whisper auto-detect
- tunable task / VAD / beam-size settings through config
- nested word-level timestamps in `segments[].words[]`
- an editable STT lane in Annotate mode: the first manual STT edit lazily migrates cached STT segments into `record.tiers.stt`, after which STT supports the same inline edit / split / merge / delete affordances as IPA and ORTH

This is the main starting point for locating lexical material in long recordings.

#### ORTH

The speaker-level ORTH job (`computeType='ortho'`) now defaults to the Hugging Face Transformers `HFWhisperProvider` on Razhan (`razhan/whisper-base-sdh`) for Southern Kurdish orthographic transcription; cite Razhan model usage with [Hameed, Ahmadi, Hadi, and Sennrich 2025, *Automatic Speech Recognition for Low-Resourced Middle Eastern Languages*](https://sinaahmadi.github.io/docs/articles/hameed2025ASR-ME.pdf), Interspeech 2025, doi:[10.21437/Interspeech.2025-2296](https://doi.org/10.21437/Interspeech.2025-2296).

Current runtime truth:
- `ortho.backend` defaults to `"hf"`; `ortho.model_path` should be a HF repo id such as `razhan/whisper-base-sdh` or a local HF-format directory.
- Legacy ORTH through faster-whisper/CTranslate2 remains available with `ortho.backend="faster-whisper"` plus an explicit local CT2 directory. CT2-looking directories are rejected by `backend="hf"` with an actionable error.
- Provider-side Whisper decoding maps Razhan/DOLMA `sd`/`sdh` requests to `fa`; PARSE project and annotation metadata should still keep Southern Kurdish as `sdh`.
- HF ORTH uses 30-second low-level `WhisperForConditionalGeneration.generate()` chunks for whole-file transcription, resamples non-16 kHz in-memory clips, keeps concept-window timing from caller-supplied windows, and avoids `return_timestamps=True` in concept-window generation.
- HF ORTH applies decode-level anti-cascade guards: `condition_on_previous_text=False`, `compression_ratio_threshold=1.8`, `no_repeat_ngram_size=3`, `repetition_penalty=1.2`, deterministic temperature/sample settings, and explicit prompt ids only when a caller opts in; legacy `compute_type`/VAD options are logged as ignored by HF.
- Full-file, concept-window, and per-lexeme HF ORTH now suppress configured `ortho.initial_prompt` by default so short clips do not parrot the decoder prime. See [ORTH initial prompt suppression](./orth-initial-prompt-suppression.md) for the 2026-05-07 regression audit.
- Concept-window STT/ORTH/IPA clips deliberately avoid English concept-ID/gloss seeding where Whisper-style decoding is involved; language resolves from payload first, then `annotation.metadata.language_code`, with a warning before auto-detect.
- Long ORTH jobs observe backend cancellation cooperatively. When cancellation arrives after some windows were written, PARSE can persist partial ORTH output and return `status: partial_cancelled` with `cancelled_at_interval` metadata.

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
- cancellation that immediately stops frontend polling, marks the current speaker cancelled and later speakers skipped, and fire-and-forget posts `POST /api/compute/{jobId}/cancel` so backend ORTH can exit cooperatively when it reaches a cancellation check

If a batch report row says **Lost contact after start**, PARSE is telling you that the backend job was created and the browser lost transport later. Use the preserved backend job id to reattach or reconcile before treating that row as a true speaker-level pipeline failure.

If a batch is manually cancelled, treat the browser state as authoritative for queue control: the UI stops polling immediately and discards late success payloads, while backend ORTH may still finish its current chunk/window before returning `cancelled` or `partial_cancelled`. For full-pipeline runs, PARSE unloads HF ORTH before wav2vec2 IPA and checks available GPU memory before starting IPA, reducing the long-audio VRAM collision that previously crashed batches.
A key detail is that preflight distinguishes **"has intervals"** from **"full WAV coverage"** via fields such as:

- `duration_sec`
- `coverage_start_sec`
- `coverage_end_sec`
- `coverage_fraction`
- `full_coverage`

That distinction matters in real fieldwork, where older runs may have seeded a tier without truly covering the full recording.

#### Concept-scoped pipeline reruns

The transcription run modal now supports three run modes for pipeline-style reruns:

- **Full speaker** (`run_mode: "full"`) — preserves whole-speaker behavior.
- **Concept windows** (`run_mode: "concept-windows"`) — reruns selected steps over concept-tier windows.
- **Edited only** (`run_mode: "edited-only"`) — reruns selected steps only for concept intervals already marked `manuallyAdjusted`.

Scoped modes hide whole-file-only actions such as Normalize and ORTH refine-lexemes where they do not make sense, can preview the manually adjusted concepts, and use backend `affected_concepts` metadata to refresh processed rows opportunistically. The run grid is mode-aware: in `concept-windows` or `edited-only`, an IPA cell can be shown as runnable when stale full-mode `pipeline_state.ipa.can_run` is false but ORTH/concept-tier presence is observable (`ortho.intervals > 0` or `ortho.can_run`); full-speaker IPA without ORTH and pure-empty concept-window speakers remain blocked. After IPA, ORTH, STT, or BND compute completion, PARSE still reloads the completed speaker annotation from disk so intervals written by concept-window or edited-only runs become visible even when the scoped row refresh succeeds. If an edited-only run has no matching edited concepts, PARSE returns a structured no-op instead of starting an empty job.

#### Tagged-concepts-only run mode

The transcription run modal also exposes a fourth scope filter targeting tag membership. When one or more global tag labels are selected, IPA / ORTH / Full pipeline runs restrict the rerun set to concepts that carry those tags on the selected speakers. This is meant for review-driven sweeps such as "rerun every concept I tagged `needs-second-pass`" or "rerun only the borrowing-suspect set on speakers KLQ-03..05".

Behavior worth knowing before you trigger a tagged-only run:

- Match semantics default to `any`: a concept matches if it carries at least one of the selected tags. Switch to `all` to require every selected tag on the same concept; in that mode, unknown or ambiguous tag labels are rejected up-front so an AND query never silently degrades to "intersection over the resolved subset".
- Ambiguous labels (the same label resolved to multiple tag ids in the global vocabulary) are rejected before any rerun work runs. Resolve the label by id or rename in the vocabulary and resubmit. This guarantees the rerun never spends GPU on a concept set the reviewer did not explicitly approve.
- Tagged-only runs are tracked jobs: the global header shows active progress, then briefly shows complete/error/cancelled terminal chips before auto-dismiss. The post-run batch report lists per-concept results and surfaces per-concept errors (concept missing on the speaker, speaker locked, runner failure) inside the report rather than aborting the whole batch. Successful tagged ORTH/IPA results are persisted into the selected speakers' annotations; ORTH results also rebuild affected `ortho_words` so word-level displays do not desync after a partial rerun.

The same tag-resolution backend is reused by the read-only `POST /api/concepts/by-tag` endpoint, so the modal preview and any agent or script that wants to know "which concepts would this rerun touch" share one source of truth.

### Manual review and timing correction

Automation in PARSE is intentionally review-first.

Annotate mode supports:

- inline lane editing on STT / IPA / ORTH with context-menu split, merge-with-next, and delete actions; the ORTHOGRAPHIC editor prefers direct `tiers.ortho` text before falling back to imported/derived `ortho_words`, and saves still write through the reviewed `tiers.ortho` path
- single-lexeme **Rerun ORTH** and **Rerun IPA** actions that start tracked `lexeme_rerun_ortho` / `lexeme_rerun_ipa` compute jobs through `/api/lexeme/run_ortho` or `/api/lexeme/run_ipa`, offer pad choices `0.0`, `0.2` (default), and `0.5`, and auto-save the confirmed tier text back into the selected interval
- concept-window and edited-only STT / ORTH / IPA action-menu reruns that use the same pad vocabulary, so hard tokens can widen acoustic context without changing the reviewed interval bounds
- per-speaker undo/redo with merge recovery and operation-labelled toasts
- draggable lexeme timestamp editing plus waveform drag-select quick retime for the active concept
- quick-retime cancel/Escape dismissal before commit
- identity-only concept lookup: the active concept matches annotation rows by `concept_id` only, so legacy rows without `concept_id` remain visibly unannotated until reimported or saved through the concept-id gate
- server-normalized Save Annotation and rerun refresh: success copy, confirmed rerun text, and visual bounds come back from the saved annotation, including `concept`, `ipa`, `ortho`, and `ortho_words`/BND changes; after ORTH partial reruns, the displayed lexeme word comes from the overlapping Tier-2 word whose midpoint best matches the concept window
- strict header status badges: `Annotated` means concept plus IPA or strict `ortho`, while `Complete` requires concept plus IPA plus strict `ortho`; auto-imported `ortho_words` can help display BND/word text but no longer counts as reviewed orthography
- per-lexeme speaker notes saved as `(speaker, concept_id, user_note)` and persisted when changed from Annotate
- Mark Done flushes pending inline edits first, so confirmation does not silently discard an unsaved ORTH/IPA/STT edit
- concept intervals extending past the source-audio duration render gracefully instead of crashing the annotation view
- speaker-local concept tag membership in `AnnotationRecord.concept_tags`; the shared tag vocabulary remains project-wide, but tag filters/counts in Annotate are scoped to the active speaker
- transport-bar volume control with current default 100%
- manual boundary correction
- constant timestamp-offset detect/apply workflows for CSV↔audio misalignment; apply results report both shifted tier intervals and shifted concepts
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

When you choose **Confirm & Use**, PARSE writes the chosen candidate into `AnnotationRecord.confirmed_anchors[concept_id]`. Those confirmations survive Praat/TextGrid round-trips and improve the cross-speaker signal for later speakers. Annotate also exposes a numeric waveform playhead chip with two-decimal precision plus the transport readout, which makes anchor confirmation less dependent on eyeballing the waveform alone.

## Compare Mode (`/compare`)

Compare mode is the cross-speaker analysis workspace for historical and comparative work.

### What you see in Compare mode

The current Compare interface provides:

- a **concept × speaker matrix** for side-by-side lexical review
- source-aware sidebar badges and sorting from `concepts.csv` `source_survey` / `source_item` values
- survey-overlap chips, color coding, and per-speaker survey choices from `survey-overlap.json`; the Current survey badge updates from the active speaker/context rather than stale global copy
- grouped source-item variant rows when multiple concepts share the same `source_item`, with A/B/C realization pills in speaker forms
- per-speaker canonical realization picks persisted under `manual_overrides.canonical_realizations`
- manual concept merge/unmerge overrides persisted under `manual_overrides.concept_merges`, combining forms for review without rewriting source concepts or annotation intervals; merge overrides are Compare-mode-only and do not collapse Annotate navigation
- right-click concept duplication that rewrites the selected row to `X (A)` and appends a new `X (B)` row with the same `source_item` / `source_survey` and a fresh numeric id; repeated calls on the same source item produce `(C)`, `(D)`, … so n-ary variants are built up by repeating the duplicate action rather than as a single batched operation
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
3. Review grouped source-item variants and choose canonical speaker-specific realizations when a form has multiple IPA/ORTH observations
4. Use concept merge/unmerge when two source concepts should be compared as one analytical row, while preserving the original concept ids underneath
5. Duplicate a concept into multiple variant rows when a single source item needs parallel lexical realizations rather than a reversible Compare-only merge; the first duplicate produces an `X (A)` / `X (B)` pair, and repeating the action on any row sharing that `source_item` extends the variant series with `(C)`, `(D)`, … until the alphabet is exhausted
6. Accept, split, merge, or cycle cognate groups
7. Mark speaker-level irregularities or flags where needed
8. Consult enrichment overlays and contact-language evidence
9. Preserve manual adjudications for export

The goal is not just visualization — it is structured decision-making for downstream comparative analysis.

### Cross-survey concept linking

Surveys often elicit the same gloss under different `source_item` numbers (KLQ-12 and JBIL-204 both meaning "rain"). Compare mode treats those as separate concept rows by default, but the right-side **Survey Values** panel lets a reviewer explicitly link them so survey-overlap chips, color coding, and downstream comparison data treat them as one analytical row without rewriting `concepts.csv`.

There are three ways linking can happen:

1. **Automatic on import.** When a new speaker is onboarded with a survey CSV, PARSE checks each incoming concept against existing concepts that already carry an explicit primary survey link. Strict matches on canonical gloss are linked automatically. Fuzzy candidates (parenthetical-stripped or comma-token matches) are never auto-linked.
2. **Manual per concept.** Use the right-panel **Survey Values** section to add or remove one cross-survey link at a time. Each row corresponds to one survey-overlap entry: pick the survey, type the `source_item`, and confirm. PARSE writes the change into the `concept_survey_links` sidecar inside `survey-overlap.json` (not `concepts.csv`), so the link can be removed cleanly without touching the source-data row. Trying to remove a link that lives in `concepts.csv` (a legacy primary-survey link) returns a 409 with a message asking the reviewer to migrate that link first via the bulk relink flow.
3. **Bulk relink-by-gloss review.** When two surveys overlap heavily, the per-concept dialog is too slow. The **Review cross-survey relink groups** action runs a dry-run consolidation by canonical gloss and shows two lists:
   - **Strict groups** are concept rows that resolve to the same canonical gloss across surveys. Accepting a group keeps one concept id (`keep_concept_id`), unions the survey links of the rest into it, rewrites annotation/enrichment references, and removes the merged rows. PARSE writes a backup of `concepts.csv`, `parse-enrichments.json`, and any annotation files it touches before applying. If anything fails mid-apply, the backups are restored automatically.
   - **Fuzzy candidates** (parenthetical-stripped or comma-token matches) are surfaced for manual decision only. PARSE never applies a fuzzy candidate automatically, even when the reviewer confirms a strict group; the reviewer must choose to merge them through the per-concept tool.

What this is *not*: cross-survey linking does not collapse Annotate navigation, does not retime any interval, and does not change the underlying `concepts.csv` row identity for the concepts that stay. It is a sidecar-level join used by Compare-mode display, color coding, and survey-aware sorting.

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

The local `lingpy_wordlist` / CLDF-family providers now match doculect identifiers by exact case-insensitive equality (with whitespace / dash / underscore folding), not substring containment. That prevents contact-language buckets such as Arabic from accidentally absorbing unrelated doculects like Avar, Karelian, or Hungarian simply because their identifiers contain `ar`.

Each reference form row has a checkbox. Those selections persist to `sil_contact_languages.json._meta.form_selections`, and only the selected forms contribute to the similarity score.

Bare-string reference forms are no longer routed by Unicode guessing alone. Each configured contact language now carries an ISO 15924 `script` hint, so PARSE can decide deterministically whether a raw form should land in the IPA-like slot or the script-text slot. Explicit provider labels (`ipa` / `script`) still win over the hint, and the Unicode-block regex remains only as a fallback for legacy or hint-less entries.

On a fresh workspace, the first run of **Borrowing detection (CLEF)** now opens a guided **Configure CLEF** modal instead of failing on a missing config file. The modal lets you:

- pick 1–2 primary contact languages
- search a bundled SIL/ISO language catalog
- enable or disable provider groups before auto-population
- inspect provider coverage/warnings when a populate run returns partial or empty results
- save the language setup only, or **Save & populate** immediately

The saved config lives at `config/sil_contact_languages.json`; optional extra catalog entries can be provided through `config/sil_catalog_extra.json`.

If a workspace was populated before the 2026-04-25 exact-match fix in `lingpy_wordlist`, rerun CLEF populate with overwrite so any forms previously misbucketed by substring-matched doculect ids are replaced with the corrected provider output.

### Current provider set (10)

| Provider | Source type |
|---|---|
| `csv_override` | Local CSV overrides |
| `lingpy_wordlist` | LingPy wordlist data |
| `pycldf` | Local CLDF datasets via `pycldf` |
| `pylexibank` | Installed Lexibank datasets via `pylexibank` |
| `asjp` | ASJP database |
| `cldf` | CLDF datasets |
| `wikidata` | Wikidata lexemes |
| `wiktionary` | Wiktionary entries and translation tables |
| `literature` | Published/workspace literature references |
| `grok_llm` | Final LLM-assisted fallback (xAI/Grok, not Grokipedia.com) |

### Current CLEF endpoints

- `GET /api/clef/config` — read the current CLEF language configuration
- `GET /api/clef/catalog` — read the bundled CLEF language catalog, including per-language ISO 15924 script hints
- `GET /api/clef/sources-report` — read corpus-wide provider provenance for populated reference forms
- `POST /api/clef/config` — save the CLEF language configuration
- `POST /api/clef/form-selections` — persist which reference forms should count toward similarity scoring
- `POST /api/clef/clear` — dry-run-capable clearing of selected CLEF reference forms and optional provider caches
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
- Adobe Audition marker CSV/TSV uploads to `POST /api/onboard/speaker`; when PARSE detects `Name`/`Start` headers after concepts-style parsing fails, it seeds CSV-order `concept` and `ortho_words` intervals with preserved cue timestamps, integer PARSE concept ids, and `import_index` / `audition_prefix` trace metadata. The same upload can include a companion `commentsCsv` file whose rows are joined by physical row index into per-lexeme import notes, and bracket/bare/malformed-prefix cue rows are imported rather than dropped. See [Audition CSV speaker import](./runtime/audition-csv-import.md).

This matters for thesis workflows where the richest aligned source may be an already processed speaker package or an Audition cue export rather than a brand-new pipeline run.

## Recommended user path

If you are starting from scratch:

1. Read [Getting Started](./getting-started.md)
2. Launch PARSE and configure `ai_config.json`
3. Import or hydrate one speaker
4. Work through Annotate mode until timestamps are trustworthy
5. Move to Compare mode for cognate and borrowing decisions
6. Use [AI Integration](./ai-integration.md) when configuring providers or the built-in assistant
7. Use [API Reference](./api-reference.md) if you are automating any part of the workflow
