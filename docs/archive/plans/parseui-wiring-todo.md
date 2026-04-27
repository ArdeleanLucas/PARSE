# ParseUI Wiring TODO — historical archive

> **Status:** Historical plan only — do **not** use this file as the live execution guide.
> **Original branch context:** `feat/annotate-ui-redesign`
> **Why archived:** this file predates the current `origin/main` state, the strict branch policy in `AGENTS.md`, and multiple merged ParseUI wiring slices.
> **Already landed since this plan was written:** annotate prefill/save/mark/badge, compare real speaker forms/reference/reviewed count, import modal, notes persistence, compute run/refresh basic wiring, decisions load/save basics, manage tags bulk-selection, spectrogram worker TS port (MC-297).
> **Current source of truth:** `docs/plans/parseui-current-state-plan.md`
> **Rule:** For new work, start from `origin/main` and use the live client/server contract (`src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`), `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)) rather than the raw endpoint suggestions below.

---

<details>
<summary>Original task checklist (collapsed — all items either landed or superseded)</summary>

## Priority 1 — Core Annotation Workflow (thesis-critical)

- ~~TASK 1 — Fix stale CONCEPTS / SPEAKERS references~~ → landed
- ~~TASK 2 — Load IPA/ortho from annotationStore~~ → landed
- ~~TASK 3 — Wire Save Annotation button~~ → landed
- ~~TASK 4 — Wire Mark Done button~~ → landed
- ~~TASK 5 — Fix Missing badge reactivity~~ → landed
- ~~TASK 6 — Stale comment cleanup~~ → landed

## Priority 2 — Compare Mode Real Data

- ~~TASK 7 — Replace MOCK_FORMS with real annotation data~~ → landed
- ~~TASK 8 — Wire Reference forms from enrichmentStore~~ → landed
- ~~TASK 9 — Wire Accept / Flag concept buttons~~ → landed
- ~~TASK 10 — Wire Notes field persistence~~ → landed
- ~~TASK 11 — Wire per-speaker Flag toggle~~ → landed
- ~~TASK 12 — Wire reviewed count~~ → landed

## Priority 3 — Actions Menu (Pipeline Triggers)

- ~~TASK 13 — Wire Actions menu items~~ → partially landed (import modal done; normalize/STT/pipeline still need server route verification per `parseui-current-state-plan.md`)

## Priority 4 — Compare Compute

- ~~TASK 14 — Wire Compute panel Run + Refresh~~ → landed (basic wiring)
- TASK 15 — Wire Cognate decision buttons → open (decisions story needs unification, see current-state plan §3)

## Priority 5 — Tags Mode

- ~~TASK 16 — Wire concept checkboxes in ManageTagsView~~ → landed

## Priority 6 — Spectrogram

- ~~TASK 17 — Port spectrogram worker to TypeScript~~ → landed (MC-297, PR #31)

## Right rail Save buttons

- ~~TASK 18 — Wire right rail Save buttons~~ → partially landed (annotate save done; compare decisions save depends on TASK 15)

</details>

---

> **parse-gpt / ParseBuilder:** Do not reopen completed tasks from this file.
> Follow `docs/plans/parseui-current-state-plan.md` for remaining work.
