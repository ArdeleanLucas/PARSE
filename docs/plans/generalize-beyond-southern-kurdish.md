# Generalize PARSE Beyond Southern Kurdish — Plan

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


**Status:** Proposed
**Author:** Lucas Ardelean (with Claude audit)
**Date:** 2026-04-20
**Related:**
- `docs/archive/desktop_product_architecture.md` (historical packaging/launch context)
- `docs/distribution_readiness_checklist.md` (release gates)
- `docs/plans/generic-comparison-data-pipeline.md` (lexical-data providers — already generic)

---

## 1) Why this document exists

PARSE is currently used as the instrument for Lucas's Southern Kurdish (SK) phylogenetics thesis, but the stated product goal is general-purpose comparative / documentary linguistics tooling. The audit below enumerates the concrete points where SK assumptions are hardcoded in the runtime, and the work needed to remove them without disrupting the thesis workflow.

This is scoped to **linguistic portability**, not desktop packaging. The Electron shell, project format, STT plumbing, and review tool are mostly language-agnostic already — the blockers are concentrated in a small number of data files and one Python module.

---

## 2) What's already generic (scope reducer)

- **Frontend (`src/`).** No SK-specific labels, dialect lists, or placeholders in `ParseUI.tsx` or compare components.
- **LLM system prompts.** `python/compare/providers/grokipedia.py` and chat/toolbox prompts are language-agnostic.
- **Data model.** Speakers, concepts, annotations, cross-speaker matches, cognate tables — all generic.
- **Phonetic-rules engine.** `python/compare/phonetic_rules.py` is a generic rule runner. Only its *default rule set* is SK-specific.
- **Comparison data pipeline.** Already designed as a pluggable provider registry (see `generic-comparison-data-pipeline.md`).

---

## 3) What is SK-specific (the actual work)

Grouped by refactor depth.

### 3a) Deep — one architectural change needed

**Orthography → IPA conversion is hardcoded to SK + Arabic script.**

- `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`):576–681` — `southern_kurdish_arabic_to_ipa()` with a 40+ character map (`_SOUTHERN_KURDISH_CHAR_MAP`), digraph table (`_SOUTHERN_KURDISH_DIGRAPHS`), and diacritic stripping.
- Call sites on the hot path:
  - `python/ai/ipa_transcribe.py` — annotation-time IPA derivation.
  - `python/compare/cross_speaker_match.py` — cross-speaker similarity matching.
- Epitran fallback in `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`):683–699` defaults to `"kur-Arab"` when language is missing/None.

**Change needed:** extract into a transliteration registry keyed by `(language, script)`. Ship the SK map as a preset (`presets/transliteration/sdh-arab.json` or similar). Call sites receive a resolver instead of calling the SK function directly.

**Why this is deep:** two hot-path call sites, plus the fallback is silently wrong for any non-Kurdish input. Cannot be solved by config alone — needs a dispatch layer.

### 3b) Moderate — needs a small abstraction

**STT stack is pinned to a single SK Whisper fine-tune.**

- `README.md:94–99` — documents `razhan/whisper-base-sdh` as the canonical model.
- `scripts/generate_ortho.py` — targets that model explicitly.
- VAD thresholds (0.35 activation, 300 ms silence) are tuned for SK elicitation data (README §4.4).

**Change needed:**
- Model registry: users pick a Whisper model per project (or auto-fill from a language → recommended-model map).
- Surface VAD knobs in project settings with SK values as one preset.

**Phonetic-rule defaults are SK alternations.**

- `config/phonetic_rules.json` — 9 rules (j↔y onset, e↔a nucleus, k/g coda deletion).
- `python/compare/phonetic_rules.py:69–77` — default rules list.

**Change needed:** ship `config/phonetic_rules.json` as empty default; move current rules to `presets/phonetic_rules/southern-kurdish.json`; add a rules editor or CSV-import to the project settings UI.

### 3c) Trivial — parameterization only

| File | SK-ism | Change |
|---|---|---|
| `python/server.py:245` | `language = ... or "sdh"` default | Require language in project config; no default |
| `config/ai_config.example.json:6` | `"language": "ku"` | Leave empty or use `"und"` in the example |
| `python/import_review_data.py:23–24` | `PROJECT_NAME = "Southern Kurdish Dialect Comparison"` | CLI flags `--project-name` / `--project-id` |
| `docs/ONBOARDING_PLAN.md` | Bakes `"code": "sdh"` into spec | Use `<lang>` placeholder with SK as example |
| `README.md`, `CITATION.cff` | Frames PARSE as an SK thesis tool | Reframe as general-purpose; keep SK as the flagship case study |

---

## 4) Milestone placement

Maps to the gates in `docs/distribution_readiness_checklist.md`.

| Work | Alpha (internal) | Beta (external testers) | Public |
|---|---|---|---|
| 3c parameterization (defaults, project metadata, docs) | optional | **must** | must |
| 3b STT model registry + VAD preset | optional | **must** | must |
| 3b phonetic-rules defaults → preset | optional | **must** (if any tester works on a non-SK language) | must |
| 3a transliteration registry refactor | not required | **strongly recommended** | **must** — silent wrong-language IPA is a correctness bug |

**Rationale for Beta gating of 3a:** external testers on non-SK data would get SK-biased IPA back without realising it. That's a data-integrity issue, not a UX one, and it's exactly the kind of bug that erodes trust in beta.

---

## 5) Suggested work breakdown

Sized to match the orchestration pattern already in use (MC-### tickets, ~2–6 h each). Numbering is suggestion — let the ticket system assign real IDs.

1. **Kill scattered language defaults.** Remove `"sdh"`/`"ku"`/`"kur-Arab"` fallbacks; require language in project config; update example configs. (~2 h, trivial)
2. **Parameterize `import_review_data.py`** project name/id via CLI flags. (~1 h, trivial)
3. **Phonetic-rules: empty default + SK preset.** Move `config/phonetic_rules.json` content to `presets/phonetic_rules/southern-kurdish.json`; ship empty default; document loader. (~2 h, moderate)
4. **STT model registry.** Replace hardcoded `razhan/whisper-base-sdh` with a `language → recommended-model` map; project setting overrides. (~4 h, moderate)
5. **VAD preset surfacing.** Expose activation threshold + silence duration in project settings; SK values become one preset. (~2 h, moderate)
6. **Transliteration registry.** Extract `southern_kurdish_arabic_to_ipa()` into `python/ai/transliteration/` with a resolver keyed by `(language, script)`. Update both call sites. Ship SK-Arabic as one preset. Add tests for the resolver and at least one second preset (stub is fine). (~6 h, deep)
7. **Docs reframe.** Update `README.md`, `CITATION.cff`, `docs/ONBOARDING_PLAN.md` to general-purpose framing with SK as example. (~2 h, trivial)
8. **Distribution checklist update.** Add a "linguistic portability" section to `distribution_readiness_checklist.md` tied to the Beta gate. (~30 min)

**Total:** ~19–20 h. Work items 1–3 and 7–8 can run in parallel; 4–6 have no hard dependency on each other but share the project-settings UI surface.

---

## 6) Open questions

- **Which second language is the validation target?** Picking one non-SK language (Central Kurdish? Persian? something unrelated like Tagalog?) as the "does generalization actually hold" test would catch dispatch bugs in item 6 that SK alone won't.
- **Does the thesis workflow tolerate the defaults going away?** Item 1 will force the thesis project config to declare language explicitly. Acceptable if we add a one-time migration; unacceptable if it means re-running analyses. Needs Lucas's call.
- **Preset distribution.** Do presets live in the repo (`presets/`) or in a user-writable app-data directory the desktop shell seeds on first run? The desktop architecture doc favours app-owned user-data — worth a short decision note.

---

## 7) Non-goals

- Unicode/script-detection beyond what's needed for preset dispatch. No auto-detecting scripts from raw strings.
- Full i18n of the UI. Labels stay English; only the *linguistic content* the user works on is generalized.
- Building out additional language presets beyond SK in this plan. Stubs or a "bring your own" path is enough; community/user-contributed presets can come later.
