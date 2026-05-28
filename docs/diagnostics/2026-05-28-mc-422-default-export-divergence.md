# MC-422-A diagnostic: default-mode export divergence vs anchored mode (#562)

This is a diagnostic-only PR for MC-422-A. It documents the current divergence points between `build_review_data` and `build_review_data_anchored` so MC-422-B/C/D/E can patch the correct seams. Sub-bug D is intentionally excluded; MC-422-D owns clarifier de-duplication via #561 Option 1 plus export-time de-dup.

## Summary table

| sub-bug | symptom from #562 | root cause category | confidence |
|---|---|---|---|
| A | Default-mode `forms[i].ipa` is empty for every speaker-form slot; anchored mode has near-complete IPA coverage. | (a) missing/skipped code path in `build_review_data`: default mode reads `ipa` from the concept-tier interval itself instead of cross-joining the IPA tier. | High |
| B | Default-mode Arabic/Persian reference forms are all empty; anchored mode carries 81/82 forms. | (c) data dependency plus caller/config drift: the production sync path points default export at the repo-local empty contact config, while the post-MC-418 workspace has a populated cache that is not used; the current default helper also ignores provider entries keyed as `script`. | High |
| C | Default-mode `forms[i].ortho` can be English `concept_en` / concept-tier text instead of speaker orthography. | (a) missing/skipped code path in `build_review_data`: default mode falls back to the concept-tier interval `text` field; anchored mode cross-joins the ortho tier. | High |
| E | Default mode emits all 10 workspace speakers; deployed anchored output has 6 speakers. | (a) missing caller parameter / deployment filter: exporter supports `speaker_filter`, but `scripts/sync_review_tool.sh` does not pass `--speakers`. | High |

Root-cause categories follow the handoff: (a) missing/skipped code path in `build_review_data`; (b) bug in a shared helper used by both modes; (c) data dependency.

## Sub-bug A — IPA tier cross-join broken in default mode

**Symptom.** #562 reports default-mode IPA coverage at 0/1020 while deployed anchored output has 485/492 speaker-form IPA strings populated.

**Anchored-mode behavior.** `build_review_data_anchored` explicitly selects a concept-tier interval, computes its `[start_sec, end_sec]`, then cross-joins the speaker's `ipa` tier with `_crosstier_text(payload, "ipa", matched_ids, start_sec, end_sec)` at `python/export_review_data.py:849-860`. The emitted form takes `"ipa": ipa_text or ""` at `python/export_review_data.py:871-874`. The cross-tier helper searches overlapping tier intervals, prefers intervals whose `conceptId`/`concept_id` is in the concept-id set, and returns their `text` field at `python/export_review_data.py:614-678`.

**Default-mode behavior.** `build_review_data` picks `interval = intervals[0]`, derives time bounds, and calls `_form_from_interval(...)` at `python/export_review_data.py:1064-1085`. `_form_from_interval` then reads `ipa = _interval_field(interval, "ipa", "ipa_text")` and emits `"ipa": "" if ipa is None else str(ipa)` at `python/export_review_data.py:577-600`. It never calls `_crosstier_text` for IPA. In the live workspace, concept intervals carry `concept_id`/`text`/time metadata while IPA text lives in a separate `tiers.ipa` interval, so the default-mode path has no IPA source to read.

**Root cause category.** (a) Missing/skipped code path in `build_review_data`.

**Recommended fix sketch.**
- Share the anchored-mode cross-tier lookup for default mode after the concept interval and time bounds are selected.
- Populate default-mode form IPA from `_crosstier_text(payload, "ipa", {concept_id}, start_sec, end_sec)` before falling back to interval-local legacy fields.
- Keep the interval-local read only as backward compatibility for tests/old fixtures where concept intervals already embed `ipa`.

**Suggested regression test target.** `python/test_export_review_data.py::BuildReviewDataTests::test_default_mode_cross_joins_ipa_tier` — fixture concept interval has no `ipa`, separate `tiers.ipa` overlap has text, default output `forms[0].ipa` must equal that text.

## Sub-bug B — Arabic/Persian reference forms missing in default mode

**Symptom.** #562 reports default-mode `arabic.form` and `persian.form` as 0/102 while deployed anchored output carries 81/82 for each contact language.

**Anchored-mode behavior.** `build_review_data_anchored` does not recompute contact-language forms. It preserves the legacy anchor concept identity and copies `legacy_c["arabic"]` / `legacy_c["persian"]` into the output at `python/export_review_data.py:904-910`. A read-only check of `/home/lucas/gh/ardeleanlucas/review_tool` at `HEAD=2ac21dd` showed the deployed anchor has 81/82 Arabic and 81/82 Persian forms.

**Default-mode behavior.** `build_review_data` loads a contact config via `_load_contact_languages(contact_config)` at `python/export_review_data.py:993-998`, resolves each concept with `_contact_forms_for_concept(contact_langs, concept_id, full_label)` at `python/export_review_data.py:1104`, and emits those results at `python/export_review_data.py:1105-1111`. `_contact_forms_for_concept` looks under language codes `ar` and `fa`, then tries only `(concept_id, label)` keys at `python/export_review_data.py:318-352`.

**Cached-output answer.** The post-MC-418 live workspace **does** have contact-lexeme cached output: read-only inspection of `/home/lucas/parse-workspace/config/sil_contact_languages.json` found 232 Arabic concept entries and 180 Persian concept entries. However, the production sync script defaults `CONTACT_CONFIG` to the repo-local file, not the workspace file, at `scripts/sync_review_tool.sh:20-22`, and only forwards that path when the exporter advertises `--contact-config` at `scripts/sync_review_tool.sh:36-42`. The repo-local `config/sil_contact_languages.json` is an empty cache for Arabic and Persian (`"concepts": {}`) at `config/sil_contact_languages.json:2-10`, so default-mode sync predictably emits empty forms. Separately, the current extractor only accepts `form` or bare string entries at `python/export_review_data.py:298-315`; workspace cache entries from some providers use `script`, so simply pointing at the workspace cache still undercounts until that shape is normalized.

**Root cause category.** (c) Data dependency / config-path drift, with a default-only extraction-shape gap. This is not a shared anchored/default helper bug because anchored mode bypasses the contact fetcher and copies the legacy anchor's populated `arabic`/`persian` objects.

**Recommended fix sketch.**
- Change the sync/export default so production review-tool sync reads the post-MC-418 workspace contact cache (`$PARSE_WORKSPACE/config/sil_contact_languages.json`) when present, or explicitly pass that path from `scripts/sync_review_tool.sh`.
- Extend `_extract_form_from_contact_entry` to accept provider entries with `script` as an orthographic form source, not just `form`.
- Re-run `python/compare/contact_lexeme_fetcher.py` only if the workspace cache is judged stale after the path/extractor fixes; the cache is present, but coverage with the current extractor is only partial.

**Suggested regression test target.** `python/test_export_review_data.py::BuildReviewDataTests::test_contact_language_forms_use_workspace_cache_and_script_entries` plus a shell-script test asserting `scripts/sync_review_tool.sh` forwards the workspace contact config by default.

## Sub-bug C — Ortho field falls back to English concept text

**Symptom.** #562 shows default-mode output such as `{"speaker": "Fail02", "ipa": "", "ortho": "hair", ...}` where `hair` is the English label, not Kurdish orthography.

**Anchored-mode behavior.** `build_review_data_anchored` cross-joins the selected concept interval to the speaker's `ortho` tier with `_crosstier_text(payload, "ortho", matched_ids, start_sec, end_sec)` at `python/export_review_data.py:855-860`, then emits `"ortho": ortho_text or ""` at `python/export_review_data.py:871-875`. The same `_crosstier_text` overlap/concept-id preference described above lives at `python/export_review_data.py:614-678`.

**Default-mode behavior.** Default mode again delegates to `_form_from_interval(...)` at `python/export_review_data.py:1064-1085`. `_form_from_interval` reads `ortho = _interval_field(interval, "ortho", "orthography", "text")` and emits it directly at `python/export_review_data.py:591-600`. On current PARSE annotations, the concept-tier interval `text` is the English concept label (`hair`, `one`, etc.), while Kurdish orthography lives in `tiers.ortho`, so the fallback order actively converts a missing cross-tier ortho join into an English string.

**Root cause category.** (a) Missing/skipped code path in `build_review_data`.

**Recommended fix sketch.**
- Use the same `_crosstier_text(payload, "ortho", ...)` lookup in default mode that anchored mode uses.
- Treat concept-tier `text` as concept identity/debug metadata, not as orthographic output, for migrated PARSE workspaces.
- Preserve explicit interval-local `ortho`/`orthography` fields only as a backward-compatible fallback for old fixtures/imports.

**Suggested regression test target.** `python/test_export_review_data.py::BuildReviewDataTests::test_default_mode_cross_joins_ortho_tier_and_does_not_emit_concept_text` — fixture concept interval `text="hair"`, overlapping `tiers.ortho.text="موو"`, output `ortho` must be `موو`, not `hair`.

## Sub-bug E — Default mode emits extra speakers

**Symptom.** #562 reports default mode emitting 10 speakers while deployed anchored output has 6, with the four extras named as `Khan01`, `Khan03`, `Khan04`, and `Fail02`.

**Anchored/deployed behavior.** Current `build_review_data_anchored` starts from `_project_speakers(workspace)` and applies `_apply_speaker_filter` only when a caller passes `speaker_filter` at `python/export_review_data.py:766-768`; it then records the selected list in metadata at `python/export_review_data.py:914-918`. Therefore, the six-speaker list is **not hardcoded in current exporter code**. It lives in the deployed anchored `review_data.json` metadata at `/home/lucas/gh/ardeleanlucas/review_tool` `HEAD=2ac21dd`: `['Fail01', 'Saha01', 'Mand01', 'Qasr01', 'Kalh01', 'Khan02']`.

**Default-mode behavior.** `build_review_data` follows the same project-speaker start and optional filter at `python/export_review_data.py:984-986`, then emits `metadata.speakers = list(speakers)` at `python/export_review_data.py:1115-1118`. The CLI exposes `--speakers` at `python/export_review_data.py:1303-1313` and passes it to both anchored and default builders at `python/export_review_data.py:1361-1375`. The current sync script builds `EXPORT_ARGS=(--workspace "$PARSE_WORKSPACE" --out "$REVIEW_TOOL_CLONE")`, may add `--contact-config`, and may add `--skip-audio`, but never adds `--speakers` at `scripts/sync_review_tool.sh:38-46`. A read-only check of `/home/lucas/parse-workspace/project.json` found 10 project speakers, so omitted `--speakers` means all 10 ship.

**Root cause category.** (a) Missing caller parameter / skipped deployment filter. The exporter already has a filter helper and tests for it; production sync just does not apply the anchored deployment subset.

**Recommended fix sketch.**
- Add an explicit speaker subset to `scripts/sync_review_tool.sh` or its environment contract before syncing default-mode review data.
- For strict anchored parity, use the six deployed speakers: `Fail01`, `Saha01`, `Mand01`, `Qasr01`, `Kalh01`, `Khan02`.
- If MC-422-E intentionally includes `Fail02`, document that as a deliberate post-anchor expansion, not as anchored parity, because deployed anchored metadata excludes `Fail02`.

**Suggested regression test target.** `python/test_export_review_data.py::SpeakerFilterTests::test_sync_review_tool_applies_default_review_subset` or an equivalent shell-script test that proves the sync script forwards `--speakers` and that `Fail02`/`Khan01`/`Khan03`/`Khan04` do not appear when anchored parity mode is requested.

## Cross-cutting findings

1. A single default-mode tier-join fix should cover both A and C. Anchored mode's IPA and ortho correctness comes from the same `_crosstier_text` pattern at `python/export_review_data.py:614-678` and calls at `python/export_review_data.py:859-860`; default mode skips both by routing through `_form_from_interval` at `python/export_review_data.py:577-600`.
2. The default-mode tests currently overfit old/minimal fixtures. `_make_workspace` documents and constructs concept intervals that embed `ipa` and `ortho` directly at `python/test_export_review_data.py:45-50` and `python/test_export_review_data.py:77-95`, so existing default-mode tests can pass while migrated live annotations store IPA/ortho in separate tiers.
3. Contact-language export has two independent gates: select the populated cache path and accept provider output shapes (`form`, bare string, and `script`). Fixing only one will not reproduce anchored coverage.
4. The speaker-subset behavior is already implemented in the exporter (`_apply_speaker_filter` at `python/export_review_data.py:169-192` and CLI `--speakers` at `python/export_review_data.py:1303-1313`); the gap is the review-tool sync invocation.

## Sequencing recommendation for MC-422 fix lanes

1. MC-422-B and MC-422-C should share one default-mode cross-tier join helper/use site for IPA and ortho, then split assertions by field.
2. MC-422-B for contact refs can proceed independently of A/C, but should first wire the correct cache path and `script` extraction before spending time re-running the fetcher.
3. MC-422-D remains separate and out of scope here.
4. MC-422-E should decide whether it wants strict anchored parity (6 speakers, excluding `Fail02`) or an intentional curated expansion (7 speakers, including `Fail02`) before hardcoding a list in `scripts/sync_review_tool.sh`.
