# CODING.md — PARSE Build Protocol v5.0

> Read this file before ANY code work on PARSE. Non-negotiable.

## Project Overview

**PARSE** — **P**honetic **A**nalysis & **R**eview **S**ource **E**xplorer

Two-mode browser-based phonetic workstation for linguists:
- **Annotate** — per-speaker segmentation, IPA/ortho annotation, AI-assisted concept location
- **Compare** — cross-speaker cognate analysis, borrowing adjudication, BEAST2 pipeline

**Key docs:**
- `PROJECT_PLAN.md` — full spec, schemas, UI design (v5.0, 1395 lines)
- `INTERFACES.md` — shared types, events, function signatures
- `AGENTS.md` — coding standards, file structure, what NOT to do
- `tasks/lessons.md` — mistakes to not repeat
- **Repo:** `TarahAssistant/PARSE`

## Architecture: Timestamps Are The Bible

Every annotation is a time-stamped segment with 4 tiers:

```
Tier 1 (top):    IPA          "jek"
Tier 2:          Ortho        "یەک"
Tier 3:          Concept      "1:one"
Tier 4 (bottom): Speaker      "Fail01"
```

All downstream operations derive from timestamps. No annotation exists without a timestamp.

## Data Architecture: Hybrid (Option C)

- **Annotations** (always live): per-speaker JSON files, read directly by Compare
- **Enrichments** (computed on demand): cognate sets, similarity scores, borrowing flags in `parse-enrichments.json`
- Compare reads live annotations and overlays enrichments on top
- Enrichments have a visible "last computed" timestamp

## Sub-Agent Rules

1. **File ownership is strict** — each sub-agent writes ONLY its assigned files
2. **Read `INTERFACES.md` before writing any JS** — all modules follow the interface contract
3. **Read `AGENTS.md` for coding standards** — `soundfile` not `wave`, vanilla JS, pathlib, etc.
4. **Read `PROJECT_PLAN.md`** for schemas, data models, and constraints
5. **Do NOT modify any file outside your assigned output files**
6. **`git diff --staged` before every commit**

## Build Waves (v5.0)

### Wave 10 — File Restructure (prerequisite, sequential)

| Task | Action | Notes |
|------|--------|-------|
| Move shared JS | `js/*.js` → `js/annotate/*.js` | All existing Annotate JS files |
| Extract shared | `annotation-store.js`, `project-config.js`, `spectrogram-worker.js` → `js/shared/` | Used by both modes |
| Rename Python | `thesis_server.py` → `server.py`, `generate_*.py` → shorter names | See §14 in plan |
| Move AI suggestions | `generate_ai_suggestions.py` → `python/ai/suggestions.py` | Refactor for provider abstraction |
| Create directories | `js/shared/`, `js/compare/`, `python/ai/`, `python/compare/`, `config/`, `docs/` | New v5.0 structure |
| Move docs | `BUILD_SESSION.md`, `SPEAKERS.md`, etc. → `docs/` | Keep AGENTS.md, CODING.md, PROJECT_PLAN.md in root |
| Update HTML imports | `parse.html` script paths: `js/annotate/parse.js`, `js/shared/...` | Must not break existing functionality |

**CRITICAL:** Test that `parse.html` still loads and works after restructure. Annotate mode must not break.

### Wave 11 — Shared Infrastructure (parallel, high priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **K1** | Tagging/filtering system | `js/shared/tags.js` | Nothing |
| **K2** | Shared audio player (WAV region playback) | `js/shared/audio-player.js` | Nothing |
| **K3** | AI client (JS ↔ Python server) | `js/shared/ai-client.js` | Server API |
| **K4** | AI provider abstraction | `python/ai/provider.py`, `python/ai/__init__.py` | Nothing |
| **K5** | STT pipeline | `python/ai/stt_pipeline.py` | K4 |
| **K6** | IPA transcription | `python/ai/ipa_transcribe.py` | K4 |
| **K7** | Config files | `config/ai_config.json`, `config/phonetic_rules.json`, `config/sil_contact_languages.json` | Nothing |

K1, K2, K4, K7 are fully independent. K3 needs API endpoint definitions. K5, K6 depend on K4's interface.

### Wave 12 — Compare Mode Core (parallel, high priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **L1** | Compare HTML shell + main entry | `compare.html`, `js/compare/compare.js` | Shared JS |
| **L2** | Concept × speaker table | `js/compare/concept-table.js` | L1 |
| **L3** | Cognate controls (accept/split/merge/cycle) | `js/compare/cognate-controls.js` | L2 |
| **L4** | Enrichments layer read/write | `js/compare/enrichments.js` | Nothing |
| **L5** | Server API endpoints | Update `python/server.py` | K4, K5 |

L1 can start immediately with shared modules. L2 depends on L1's DOM structure. L3 depends on L2. L4 is independent.

### Wave 13 — Compare Pipeline (parallel, medium priority)

| Stream | Task | Output Files | Deps |
|--------|------|--------------|------|
| **M1** | Cognate computation (LexStat wrapper) | `python/compare/cognate_compute.py` | K7 (config) |
| **M2** | Cross-speaker matching | `python/compare/cross_speaker_match.py` | K5 (STT) |
| **M3** | Auto-offset detection | `python/compare/offset_detect.py` | K5 (STT) |
| **M4** | Phonetic variation rules engine | `python/compare/phonetic_rules.py` | K7 (config) |
| **M5** | Borrowing adjudication panel | `js/compare/borrowing-panel.js` | L2 |
| **M6** | Speaker import wizard | `js/compare/speaker-import.js` | K3 (AI client) |

M1, M4 are independent. M2, M3 depend on STT pipeline. M5 depends on concept table. M6 depends on AI client.

### Wave 14 — Integration + Polish (sequential, after waves 11-13)

| Task | Files Modified | Notes |
|------|----------------|-------|
| Wire tags into Annotate sidebar | `js/annotate/parse.js` | Tag toggle per concept |
| Wire tags filter into Compare | `js/compare/compare.js` | Filter by tagged items |
| Mode switcher (Annotate ↔ Compare) | Both HTML files | Navigation links/buttons |
| Enrichments ↔ Compare UI wiring | Multiple Compare JS | Cognate badges, similarity bars populate from enrichments |
| Save history implementation | `js/compare/enrichments.js` | Version snapshots, no overwrites |
| Export: wordlist.tsv | `python/compare/cognate_compute.py` | LingPy-compatible format |
| Export: decisions.json | `js/compare/enrichments.js` | Reviewer decisions + cognate sets |
| Update INTERFACES.md | `INTERFACES.md` | All new events for Compare mode |

## Execution Order

```
Step 0: Update INTERFACES.md with v5.0 events (Compare, tags, enrichments, AI)
Step 1: Wave 10 — file restructure (MUST complete before anything else)
Step 2: Spawn Wave 11 (K1-K7) — shared infrastructure
Step 3: Spawn Wave 12 (L1-L5) alongside Wave 11 — Compare skeleton
Step 4: Spawn Wave 13 (M1-M6) as dependencies resolve
Step 5: Wave 14 — integration wiring (sequential, careful)
Step 6: Review + test + fix integration bugs
```

**Practical:** Waves 11+12 can run mostly in parallel (up to 12 tasks). Wave 13 starts as soon as dependencies from 11 resolve. Wave 14 is sequential.

## Sub-Agent Prompt Template

Each sub-agent prompt MUST include:

1. **Standard preamble (always first):**
   > "Before writing any code, read these files in order:
   > 1. `/home/lucas/.openclaw/workspace/parse/CODING.md`
   > 2. `/home/lucas/.openclaw/workspace/parse/AGENTS.md`
   > 3. `/home/lucas/.openclaw/workspace/parse/INTERFACES.md`
   > Then follow whatever additional reading those docs direct you to."
2. Module purpose (one paragraph)
3. Exact output file path(s)
4. Interface contract (relevant events + shared data)
5. Relevant schema (from PROJECT_PLAN.md)
6. Specific edge cases and constraints
7. **"Do NOT modify any file outside your assigned output files"**

## What Runs Where

- **Python scripts** — written in sandbox, **executed on user's machine** (needs audio file access)
- **JS modules + HTML** — written in sandbox, **deployed to project directory** for dev server
- **opencode_task sandbox** — `/home/lucas/.openclaw/workspace/parse/`

## Key Schemas

### Annotation File (`annotations/<Speaker>.parse.json`)

```json
{
  "version": 1,
  "project_id": "sk-thesis-2026",
  "speaker": "Fail01",
  "source_audio": "audio/working/Fail01/Faili_M_1984.wav",
  "source_audio_duration_sec": 7200.0,
  "tiers": {
    "ipa": { "type": "interval", "display_order": 1, "intervals": [{ "start": 506.2, "end": 506.9, "text": "jek" }] },
    "ortho": { "type": "interval", "display_order": 2, "intervals": [{ "start": 506.2, "end": 506.9, "text": "یەک" }] },
    "concept": { "type": "interval", "display_order": 3, "intervals": [{ "start": 506.2, "end": 506.9, "text": "1:one" }] },
    "speaker": { "type": "interval", "display_order": 4, "intervals": [{ "start": 0, "end": 7200.0, "text": "Fail01" }] }
  },
  "metadata": { "language_code": "sdh", "created": "2026-03-26T10:00:00Z", "modified": "2026-03-26T11:00:00Z" }
}
```

### Enrichments (`parse-enrichments.json`)

```json
{
  "computed_at": "2026-03-26T10:00:00Z",
  "config": {
    "contact_languages": ["ar", "fa"],
    "speakers_included": ["Fail01", "Kalh01", "Mand01"],
    "concepts_included": [1, 2, 5, 12],
    "lexstat_threshold": 0.6
  },
  "cognate_sets": { "1": { "A": ["Fail01","Kalh01"], "B": ["Mand01"] } },
  "similarity": { "1": { "Fail01": { "ar": 0.12, "fa": 0.05 } } },
  "borrowing_flags": {},
  "manual_overrides": {}
}
```

### AI Config (`config/ai_config.json`)

```json
{
  "stt": { "provider": "faster-whisper", "model_path": "", "language": "sd", "device": "cuda", "compute_type": "float16" },
  "ipa": { "provider": "local", "model": "epitran" },
  "llm": { "provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY" },
  "specialized_layers": []
}
```

## Data Pipeline Order

### Annotate pipeline (per-speaker):
```
1. normalize_audio.py    → audio/original/ → audio/working/
2. source_index.py       → ffprobe audio/working/ → source_index.json
3. peaks.py              → soundfile audio/working/ → peaks/*.json
4. coarse_transcripts.py → coarse transcripts → transcripts/*.json
5. ai/suggestions.py     → transcripts + review_data → ai_suggestions.json
```

### Compare pipeline (cross-speaker):
```
1. ai/stt_pipeline.py         → full-file STT on new speaker (background, GPU)
2. compare/offset_detect.py   → auto-detect timestamp offsets
3. compare/phonetic_rules.py  → apply phonetic variation rules
4. compare/cross_speaker_match.py → repetition detect + cross-speaker matching
5. compare/cognate_compute.py → LexStat → enrichments.json
6. Export: wordlist.tsv → LingPy → BEAST2 XML (TBD scripts)
```

## Pre-Build Checklist

- [ ] INTERFACES.md updated with v5.0 events (Compare, tags, enrichments, AI endpoints)
- [ ] Wave 10 file restructure complete
- [ ] `parse.html` still loads and works after restructure

## Post-Build Checklist

1. `python3 -m py_compile python/*.py python/ai/*.py python/compare/*.py` — all compile
2. `node --check js/shared/*.js js/annotate/*.js js/compare/*.js` — all pass syntax
3. Review each file for interface compliance
4. Test: Annotate mode unchanged (annotations save, regions work, suggestions appear)
5. Test: Compare mode loads concept × speaker table
6. Test: Cognate controls work (accept/split/merge/cycle)
7. Test: STT pipeline runs on new speaker import
8. Test: Enrichments compute and display
9. `git diff --staged` before committing
10. Push to `TarahAssistant/PARSE`
