---
agent: parse-back-end
queued_by: parse-coordinator
queued_at: 2026-04-29T01:00:00+02:00
status: done
completed_at: 2026-04-29T07:03:15Z
completed_by_pr: 182
related_prs:
  - 168
  - 174
  - 175
  - 176
  - 177
  - 182
cross_lane_exception: one small parse-front-end settings-tab change is intentionally included so this can ship as one PR
---

# parse-back-end — CLEF Grok LLM rename, Wiktionary translation tables, warnings, and Settings tab

## Goal

Ship one PR titled `feat(clef): rename grokipedia→grok_llm, extend wiktionary, settings tab` that:

1. Renames the misnamed `grokipedia` provider to `grok_llm` while preserving it as the final LLM fallback.
2. Extends `wiktionary` to parse translation-table templates (`{{t|...}}` / `{{t+|...}}`) before falling back to IPA-pronunciation extraction.
3. Softens provider preflight warning copy for normal sparse-coverage cases.
4. Adds a small CLEF Configure **Settings** tab with provider API-key entry and dry-run/confirm-backed delete-all CLEF data access.

## Why this is next

The last 24 hours shipped CLEF source UX, clear/reset semantics, provider-warning surfacing, exact doculect matching, and xAI auth alignment. The remaining naming/source-quality gap is that `grokipedia` is actually an xAI/Grok LLM provider, while real Wiktionary translation tables contain high-value Arabic/CKB/Persian forms that the current provider does not extract.

## Scope boundary

- **In scope:** `python/compare/providers/**`, provider tests, `src/components/compute/clef/ClefConfigModal.tsx`, `src/components/compute/clef/types.ts`, relevant docs/screenshots.
- **Cross-lane exception:** the CLEF Settings tab is intentionally included here to keep provider auth/reset UX in one PR.
- **Out of scope:** real Grokipedia.com scraping, `FetchResult.citations` contract expansion, unrelated chat tools, broad annotate/wavesurfer changes, runtime config output (`config/sil_contact_languages.json`).

## Required validation

- `grep -rn 'grokipedia' python/ src/` returns only intended historical/remnant references.
- Targeted provider tests for Wiktionary translation-table extraction and Grok LLM auth/priority pass.
- `npx vitest run` and `./node_modules/.bin/tsc --noEmit` pass for the Settings tab change.
- `uvx ruff check python/ --select E9,F63,F7,F82` passes before push.
- Live Wiktionary smoke returns Arabic forms for at least 5/10 sampled concepts.
- PR uses `--repo ArdeleanLucas/PARSE`; after refetch, GitHub reports fresh mergeability.

## Completion note

This handoff was executed and merged as [PR #182](https://github.com/ArdeleanLucas/PARSE/pull/182) (`680a97f`). The original prompt is retained below as audit evidence; this file now lives under `parse-back-end/done/` and should not be treated as an active queued task.

## Original detailed prompt retained for executor

<task_context>
You are parse-back-end. This task crosses into parse-front-end territory for one small ClefConfigModal change — that's deliberate; Lucas wants ONE PR, do not split.
</task_context>

<tone_context>
Lucas prefers terse, action-oriented responses with no fluff. Beta-quality preferred over perfection. You push PRs, Lucas merges — never self-merge. Don't claim a doc/feature is correct without grep-verifying.
</tone_context>

<background>
Working directory: /home/lucas/gh/worktrees/clef-grok-llm-and-wiktionary-tables/
Repo target: ArdeleanLucas/PARSE (public)

Setup:
  cd /home/lucas/gh/tarahassistant/PARSE-rebuild
  git fetch origin --quiet --prune
  git worktree add -f /home/lucas/gh/worktrees/clef-grok-llm-and-wiktionary-tables origin/main
  cd /home/lucas/gh/worktrees/clef-grok-llm-and-wiktionary-tables
  git checkout -b feat/clef-grok-llm-and-wiktionary-tables

Verify before any commit: `git remote -v` shows ArdeleanLucas/PARSE.

State (audit 2026-04-29):
- Runtime serves source from /tmp/parse-runtime/python/; provider _CONFIG_DIR resolves to /tmp/parse-runtime/config/ at runtime.
- Lexibank datasets (seabor, ids, abvd, diacl, liusinitic) already cloned in /tmp/parse-runtime/config/lexibank_data/. pylexibank/pycldf/lingpy importable in /usr/bin/python3.
- /tmp/parse-runtime/config/auth_tokens.json has direct_api_key + direct_api_key_provider="xai".
- Existing "grokipedia" provider is misnamed: it is an LLM IPA generator hitting api.x.ai/v1/chat/completions, NOT an encyclopedia. Empirical test 2026-04-29 confirmed Grokipedia.com has zero non-Latin/borrowing data on /page/Hair (575 KB HTML, no Arabic/Persian/Kurdish, no JSON-LD multilingual blocks). Decision: drop the encyclopedia idea entirely.
- Wiktionary's en.wiktionary.org/wiki/<concept> DOES contain translation tables ({{t|ar|شَعْر}}, {{t+|ckb|قژ}}) for many of the contact languages we care about. The existing python/compare/providers/wiktionary.py already hits that endpoint but only extracts IPA pronunciation templates, not the translation tables — that's the high-value gap.
- ClefConfigModal currently has 2 tabs ("languages", "populate") in src/components/compute/clef/types.ts. ProviderApiKeyForm.tsx already exists but is not surfaced in a Settings tab. Backend /api/clef/clear endpoint already exists (_api_post_clef_clear in python/server_routes/clef.py).

Relevant files:
- python/compare/providers/grokipedia.py             (rename to grok_llm.py)
- python/compare/providers/registry.py               (PROVIDER_PRIORITY + _provider_preflight_warnings)
- python/compare/providers/wiktionary.py             (add translation-table extraction)
- python/compare/providers/test_wiktionary.py        (add tests)
- python/compare/providers/test_grokipedia_auth.py   (rename + adjust imports)
- src/components/compute/clef/ClefConfigModal.tsx    (Settings tab, inline SectionStrip)
- src/components/compute/clef/types.ts               (extend ClefConfigModalTab)
</background>

<rules>
AGENTS.md guards (mandatory):
- `--repo ArdeleanLucas/PARSE` on every gh invocation
- `git fetch origin --quiet --prune` before any mergeable status claim
- Screenshot LINKS via markdown to docs/pr-assets/, NOT inline embeds

Standard validation commands:
- npx vitest run
- ./node_modules/.bin/tsc --noEmit
- npm run build
- PYTHONPATH=python python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults'
- uvx ruff check python/ --select E9,F63,F7,F82   (MANDATORY pre-push)
- python python/server.py   (server boot smoke)

Task-specific rules:
- ONE PR. Cross-lane scope is deliberate. Do not split into two.
- Do NOT implement a real Grokipedia.com encyclopedia provider. The decision is final and evidence-backed (see <background>).
- Do NOT add a `citations` field to FetchResult in this PR. contact_lexeme_fetcher writes only `forms`; expanding the contract is a separate future PR.
- grok_llm stays in PROVIDER_PRIORITY but moves to the LAST position (after "literature"). Do NOT delete the module.
- Grep src/ python/ for any string-literal "grokipedia" outside the renamed file's own internals — update or note them.
- Wiktionary translation-table extraction must:
  - Parse `{{t|<lang>|<form>|...}}` AND `{{t+|<lang>|<form>|...}}`.
  - Use the existing _WIKTIONARY_FRAGMENTS map for lang_code → wikitext lang fragment matching.
  - Yield orthographic forms verbatim, no IPA conversion. Skip `{{t-needed}}` and forms containing `{`.
  - Run BEFORE the existing IPA-template path inside `_lookup`; IPA stays as fallback.
  - Tests use static wikitext fixtures. NO live HTTP in tests.
- Friendlier preflight wording in registry.py _provider_preflight_warnings:
  - asjp: "ASJP's built-in 40-concept Swadesh map covers {N} of your {M} requested concepts (this is normal — ASJP is a small reference set, not a coverage gap)."
  - wikidata: same shape — "Wikidata's built-in concept→QID map covers {N} of your {M} requested concepts ..."
  - lingpy_wordlist/pycldf MISSING datasets: "no local CLDF datasets found under {data_dir}. Drop a Lexibank dataset clone into that directory to enable this provider."
  - pylexibank not installed: keep but soften "(install with `pip install pylexibank` if you want to use installed dataset packages)".
  - grok_llm no key: "grok_llm: no xAI or OpenAI API key configured. Open the Settings tab in CLEF Configure to add one, or skip this provider."
- Settings tab UI:
  - Add `"settings"` to ClefConfigModalTab union.
  - SectionStrip (inline in ClefConfigModal.tsx) renders three pills: "1. Languages" | "2. Sources" | "3. Settings".
  - Settings panel: <ProviderApiKeyForm/> at top (reuse as-is); below it a "Danger zone" section with a "Delete all CLEF data" button.
  - Default tab on open stays initialTab="languages". Verify the user-reported "wrong default tab" repro (open modal twice in a row); if no repro, leave default unchanged and note in PR description.
  - Delete-all button: visually de-emphasized (slate-200 border + slate-700 text, NOT red until hover); confirm via window.confirm or existing dialog primitive (do not introduce a new dialog dep); on success, refresh the modal's status query.
- Tests:
  - `test_translation_table_extraction` in test_wiktionary.py — t/t+ parsing for ar+ckb+fa, multi-form, noise stripping.
  - `test_grok_llm_in_priority_last` — grok_llm appears LAST in PROVIDER_PRIORITY and in registry's _providers dict.
  - Rename-only update for test_grokipedia_auth.py → test_grok_llm_auth.py; keep the actual test logic.
- DO NOT touch tiers/, annotate-views/, wave-surfer/, ai_config.json, chat tools.

Acceptance:
- `grep -rn 'grokipedia' python/ src/` returns only intended remnants (changelog/comments referencing the rename history).
- Live wiktionary smoke for at least 5 of 10 sampled concepts × Arabic returning forms (capture in PR description). Run via:
  PYTHONPATH=python python3 -c "from compare.providers.wiktionary import WiktionaryProvider; p=WiktionaryProvider(); [print(r.concept_en, r.language_code, r.forms) for r in p.fetch(['hair','water','book','mother','tea','bread','house','mosque','tax','pen'], ['ar','ckb','fa'], {})]"
- All 3 active CI gates green (Schema / Frontend CI / Backend CI). Parity Diff Harness no-op.
- Fresh mergeStateStatus=CLEAN.
- One PR on ArdeleanLucas/PARSE.
- docs/pr-assets/clef-settings-tab.png + docs/pr-assets/clef-delete-confirm.png linked in PR description via markdown.
</rules>

<examples>
Translation-table extractor sketch (Python):

    import re
    TRANS_RE = re.compile(r'\{\{t\+?\|([a-z]{2,3})\|([^|}]+)(?:\|[^}]*)?\}\}')

    def _extract_translations(wikitext, lang_code, fragments):
        forms, seen = [], set()
        for wt_lang, form in TRANS_RE.findall(wikitext):
            form = form.strip()
            if not form or '{' in form:
                continue
            if any(frag.startswith(wt_lang) or wt_lang.startswith(frag) for frag in fragments):
                if form not in seen:
                    seen.add(form); forms.append(form)
        return forms

ClefConfigModalTab extension (TS) — types.ts:

    export type ClefConfigModalTab = "languages" | "populate" | "settings";

SectionStrip pill rendering (TSX) — ClefConfigModal.tsx inline:

    const LABELS = {
      languages: "1. Languages",
      populate: "2. Sources",
      settings: "3. Settings",
    } as const;
    {(["languages","populate","settings"] as ClefConfigModalTab[]).map((entry) => (
      <button key={entry} onClick={() => onSelect(entry)}>{LABELS[entry]}</button>
    ))}
</examples>

<task>
Ship ONE PR titled `feat(clef): rename grokipedia→grok_llm, extend wiktionary, settings tab` covering all four scope items:

1. Rename grokipedia → grok_llm:
   - Move python/compare/providers/grokipedia.py → grok_llm.py.
   - Rename class GrokipediaProvider → GrokLlmProvider.
   - PROVIDER_PRIORITY: replace "grokipedia" with "grok_llm" at LAST position.
   - registry.py: update import + _providers key + warning text.
   - Rename test_grokipedia_auth.py → test_grok_llm_auth.py with updated imports.
   - Drop unused grokipedia_api PyPI dep from requirements files (grep first).

2. Extend Wiktionary provider for translation tables (the high-value change):
   - Add translation-table extractor per <examples>.
   - Wire into _lookup BEFORE the IPA path; IPA stays as fallback.
   - Update docstring.
   - Tests with static wikitext fixtures, no live HTTP.

3. Friendlier preflight wording in registry.py per <rules>.

4. Settings tab in ClefConfigModal:
   - "settings" added to ClefConfigModalTab.
   - SectionStrip renders 3 pills.
   - Settings panel: ProviderApiKeyForm + Delete-all button + confirm.
   - Verify default-tab repro; document outcome in PR.
</task>

<thinking_steps>
1. Set up worktree per <background>.
2. Backend rename pass (file move, class rename, registry priority shift, test file rename, drop unused dep). Run pytest + ruff. Commit.
3. Wiktionary extension: add translation-table parser, wire into _lookup, add fixture-based tests. Run pytest. Commit.
4. Friendlier preflight wording in registry.py. Run pytest. Commit.
5. Frontend Settings tab: types.ts, ClefConfigModal.tsx, ProviderApiKeyForm wiring, delete-all button + confirm. Run vitest + tsc. Commit.
6. Live verification: parse-run, open CLEF Configure modal, screenshot Settings tab and delete-confirm dialog into docs/pr-assets/. Commit screenshots.
7. Wiktionary live smoke (10 concepts × ar/ckb/fa) per <rules>. Capture output for PR description.
8. Full validation suite. Push branch.
9. Open PR with --repo ArdeleanLucas/PARSE explicit.
10. git fetch origin --quiet --prune && gh pr view <N> --repo ArdeleanLucas/PARSE --json mergeable,mergeStateStatus,statusCheckRollup.
11. Reply per <output_format>.
</thinking_steps>

<output_format>
Reply with:
- PR # + URL (must contain ArdeleanLucas/PARSE)
- Commit SHA(s)
- 3 active CI gate statuses (Schema / Frontend CI / Backend CI). Parity Diff Harness no-op.
- Fresh mergeStateStatus after refetch
- Local validation summary (test counts, ruff result, build status)
- Wiktionary smoke output (one line per concept × language)
- Screenshot links (markdown form, NOT image embeds)
- Default-tab repro outcome: "no repro found, default unchanged" OR "repro confirmed, fix applied: <description>"
</output_format>
