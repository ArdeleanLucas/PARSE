> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# PARSE-rebuild Tags parity evidence — 2026-04-26

**Date:** 2026-04-26  
**Oracle repo:** `ArdeleanLucas/PARSE`  
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38`  
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`  
**Rebuild SHA:** `cdb316ca4b739b0ad496f1b58a50a7a3f2082cb4`

---

## TL;DR

**Tags parity PASS (7/7 flows).**

Rebuild current-main matched oracle current-main on the full P0 Tags workflow exercised here:
1. clean baseline render
2. create tag
3. rename tag
4. filter tags by search
5. select tag and open assignment panel
6. assign concept `hair (#1)`
7. reload survival

Both oracle and rebuild ended with identical persisted state for the test tag:
- tag label: `tags-parity-renamed`
- tag color: `#ec4899`
- assigned concepts: `['1']`
- visible left-panel count after reload: `tags-parity-renamed 1`

---

## Evidence harness

### Oracle runtime
- Frontend: `http://127.0.0.1:5173/`
- Backend: `http://127.0.0.1:8766/`
- Code provenance already re-grounded separately to canonical `parse/main`

### Rebuild parity runtime
- Frontend: `http://127.0.0.1:15174/`
- Backend: `http://127.0.0.1:18776/`
- Rebuild backend port patch was local-only in a detached temp worktree for side-by-side parity; **no runtime port changes are proposed for the repo**

### Workspace data
Both sides were exercised against the same real thesis workspace data rooted at:
- `/home/lucas/parse-workspace`

---

## P0 Tags matrix

| # | Flow | Oracle | Rebuild | Grounded evidence |
|---|---|---|---|---|
| 01 | Baseline render | PASS | PASS | Both reset to Tags mode with `Tags · 4` and baseline tags `Review needed`, `Confirmed`, `Problematic`, `custom-sk-concept-list` |
| 02 | Create tag | PASS | PASS | Created `tags-parity-*` tag; tag count increased `4 -> 5` |
| 03 | Rename tag | PASS | PASS | Renamed created tag to `tags-parity-renamed` |
| 04 | Filter by tag search | PASS | PASS | Typing `renamed` reduced visible tag list to `Tags · 1` |
| 05 | Select tag panel | PASS | PASS | Selecting `tags-parity-renamed` opened the right-hand assignment panel with heading `tags-parity-renamed` |
| 06 | Assign `hair (#1)` | PASS | PASS | After clicking the right-panel `hair (#1)` row, persisted tag state contained `concepts: ['1']` |
| 07 | Reload survival | PASS | PASS | After reload, both sides still showed `Tags · 5`, row `tags-parity-renamed 1`, and persisted `concepts: ['1']` |

---

## Exact observed final state

### Oracle final persisted state
- `count`: `5`
- `renamedExists`: `true`
- `renamedColor`: `#ec4899`
- `renamedConcepts`: `['1']`
- `hasHair`: `true`

### Rebuild final persisted state
- `count`: `5`
- `renamedExists`: `true`
- `renamedColor`: `#ec4899`
- `renamedConcepts`: `['1']`
- `hasHair`: `true`

---

## Screenshots

- [Oracle final Tags state](docs/pr-assets/pr-tags-parity-oracle-final.png)
- [Rebuild final Tags state](docs/pr-assets/pr-tags-parity-rebuild-final.png)

### Screenshot hash note

- Oracle final screenshot SHA256: `d9f70ff979055d0801c6c82fdb8b86d74948e735608581112e78886316bb4c53`
- Rebuild final screenshot SHA256: `d9f70ff979055d0801c6c82fdb8b86d74948e735608581112e78886316bb4c53`

These hashes are **identical**. That means the final visible oracle/rebuild screenshots are byte-identical, which is consistent with exact visual parity, but it also means the usual “distinct screenshot hash” sanity heuristic is not informative here. The primary grounding for this report is therefore the browser interaction trace plus the persisted tag-store state on each origin.

---

## Interpretation

This closes the previously deferred Tags / enrichments management parity surface from `option1-parity-inventory.md` §5.1 at the P0 workflow level exercised here.

Important adjacent context:
- This report does **not** change the separate canonical-main `/annotate` regression already identified in the runtime audit.
- It does confirm that the rebuild Tags surface, post-`ManageTagsView` extraction, is behaviorally aligned with oracle on the tested workflows.
