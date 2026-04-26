# Compare parity evidence — 2026-04-26

**Date:** 2026-04-26
**Oracle repo:** `ArdeleanLucas/PARSE`
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38`
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`
**Rebuild SHA:** `12fcc36`
**Fixture:** compare workspace seeded from `/home/lucas/parse-workspace`

---

## Method

- Created fresh detached current-main worktrees for oracle and rebuild.
- Seeded each with the same compare fixture files: `project.json`, `source_index.json`, `concepts.csv`, `parse-enrichments.json`, and `annotations/`.
- Symlinked heavy read-only assets (`audio/`, `peaks/`, `coarse_transcripts/`) into the temp worktrees.
- Started oracle and rebuild stacks sequentially on the standard local ports using the Windows conda Python for the backend and Vite for the frontend.
- Ran the Compare flows in-browser and verified persistence through reload plus direct `GET /api/enrichments` / `localStorage` inspection.

Temp worktrees used:
- oracle: `/tmp/parse-oracle-parity-current`
- rebuild: `/tmp/parse-rebuild-parity-current`

---

## Status legend

- **PASS** — oracle and rebuild produced the same intended behavior for the flow
- **DEVIATION** — behavior differed, but the difference is currently accepted / blocked by setup constraints
- **FAIL** — parity diverged materially between oracle and rebuild

---

## Evidence matrix

| Flow | Oracle result | Rebuild result | Status | Evidence |
|---|---|---|---|---|
| Concept × speaker table render | Loaded 521 concepts / 10 speakers, row table visible | Loaded same 521 concepts / 10 speakers, same row table visible | **PASS** | `.hermes/reports/parity/compare/01-table-render.txt` |
| Cognate accept | `Accept grouping` wrote `cognate_decisions['1']='accepted'` and survived reload | Click produced no persisted change; decision stayed on prior baseline | **FAIL** | `.hermes/reports/parity/compare/02-cognate-accept.txt` |
| Cognate split | `Split` wrote `cognate_decisions['1']='split'` and survived reload | Click produced no persisted change; decision stayed on prior baseline | **FAIL** | `.hermes/reports/parity/compare/03-cognate-split.txt` |
| Cognate merge | `Merge` wrote `cognate_decisions['1']='merge'` after split and survived reload | Decision-row cluster appears inert, so merge transition could not be reproduced | **FAIL** | `.hermes/reports/parity/compare/04-cognate-merge.txt` |
| Cognate cycle through colors | Per-cell manual group button cycled visibly and persisted | Per-cell manual group button cycled visibly and persisted | **PASS** | `.hermes/reports/parity/compare/05-cognate-cycle-visual.txt` |
| Borrowing/form mark | Per-speaker flag toggled and persisted through reload | Per-speaker flag toggled and persisted through reload | **PASS** | `.hermes/reports/parity/compare/06-borrowing-flag.txt` |
| Notes persistence on one concept | Concept note persisted via localStorage through reload | Same concept note path persisted via localStorage through reload | **PASS** | `.hermes/reports/parity/compare/07-concept-notes.txt` |
| Enrichment edit on one cell | Manual cognate-cell edit persisted in `manual_overrides.cognate_sets` | Same manual cognate-cell edit path persisted in `manual_overrides.cognate_sets` | **PASS** | `.hermes/reports/parity/compare/08-cell-enrichment-persistence.txt` |

---

## Key observation

The major Compare parity divergence is **narrower than a full compare-shell failure**:

- The **table render**, **cell-level cognate cycling**, **manual per-form flagging**, **concept notes**, and **cell-level enrichment persistence** all behaved compatibly between oracle and rebuild.
- The specific divergence is the **top-level decision row** (`Accept grouping`, `Split`, `Merge`) for concept-level cognate decisions:
  - **Oracle current-main** writes `enrichments.cognate_decisions[conceptId]` and those writes survive reload.
  - **Rebuild current-main** left the same decision baseline untouched when those buttons were clicked during browser testing.

That means Compare parity is **mostly intact**, but the rebuild still has a real browser-visible contract gap in the concept-level cognate decision action row.

---

## Additional caveats

- The concept-level Notes surface is currently **browser-local** (`localStorage`) on both oracle and rebuild. This is parity, but it is not shared-backend persistence.
- By the time the rebuild pass ran, the rebuild temp workspace had the same persisted compare-state baseline as the oracle pass for the tested concept (`cognate_decisions` and some manual overrides). This did not block parity comparison, but it means rebuild cycle/flag checks started from a matched non-pristine state rather than a blank baseline.
- No browser console JavaScript errors were observed on the tested flows for either oracle or rebuild.

---

## Owner recommendation

- **Primary follow-up owner:** parse-builder / compare parity lane
- **Reason:** the observed divergence is a frontend-visible Compare action-row persistence problem. Cell-level enrichment writes still work, so the likely gap is in the rebuild wiring around the top-level cognate decision buttons rather than the entire enrichments persistence stack.
