# PARSE Legacy Entrypoint Inventory

**Purpose:** Enumerate current references to legacy entrypoints (`parse.html`, `compare.html`, `localhost:8766` legacy UI paths) and identify which phase should handle each reference.

**Scope date:** 2026-04-09
**Repo scanned:** `/home/lucas/gh/ardeleanlucas/parse`

---

## A. User-facing / operator-facing references clarified in Phase 3

| Path | Current state after Phase 3 | Why it matters | Handled in |
|---|---|---|---|
| `README.md` | Now distinguishes React/Vite routes (`:5173`) from legacy fallback pages (`:8766/parse.html`, `/compare.html`) | Primary onboarding doc no longer implies legacy is canonical | **Phase 3** |
| `python/server.py` | Startup banner now separates React dev guidance from Python-served legacy fallback pages | Server output no longer implies legacy is the only frontend path | **Phase 3** |
| `desktop/README.md` | Now labels `:8766/parse.html` as legacy fallback and documents React/Vite targets on `:5173` | Desktop scaffold instructions now match the current frontend architecture | **Phase 3** |
| `desktop/dev-launch.js` | `--help` now explains that `:5173` is the current React UI and that the `:8766/parse.html` default is legacy fallback | CLI help is operator-facing and now clarifies React vs legacy | **Phase 3** |
| `desktop/main.js` | Load-failure guidance now points users toward the React/Vite route when appropriate | Runtime failure UX now reduces entrypoint confusion | **Phase 3** |
| `start_parse.sh` | Still opens `review_tool_dev.html`, but now explicitly labels itself as a legacy launcher and points users to React/Vite for current UI work | Linux/macOS launcher remains user-visible but is no longer mislabeled as current PARSE | **Phase 3 review**, possibly Phase 5 if replaced |
| `Start Review Tool.bat` | Still opens `review_tool_dev.html`, but now explicitly labels itself as legacy and points users to React/Vite for current UI work | Windows launcher remains user-visible but is no longer mislabeled as current PARSE | **Phase 3 review**, possibly Phase 5 if replaced |

---

## B. Runtime legacy files/links that remain until C7 and must be handled in Phase 5

| Path | Current reference | Why it matters | Planned phase |
|---|---|---|---|
| `parse.html` | Top-nav links to `parse.html` and `compare.html` | Actual legacy UI still present and navigable | **Phase 5 / C7** |
| `compare.html` | Top-nav links to `parse.html` and `compare.html` | Actual legacy UI still present and navigable | **Phase 5 / C7** |
| `js/` | Legacy frontend module tree still exists | Root of the legacy runtime | **Phase 5 / C7** |
| `vite.config.ts` | Comment notes `/compare` is kept on SPA route while legacy `compare.html` still exists | Signals current hybrid transition | **Leave until C7**, then update |

---

## C. Historical/specification references that should usually be preserved, not blindly rewritten

| Path | Current reference type | Why it exists | Planned action |
|---|---|---|---|
| `PROJECT_PLAN.md` | Architecture/spec lists `parse.html` and `compare.html` as project files | Historical/spec document, not live operator guidance | Keep unless Lucas wants spec refresh |
| `CODING.md` | Restructure waves mention preserving `parse.html` / `compare.html` | Historical implementation protocol | Keep or annotate later |
| `INTERFACES.md` | Contracts and notes refer to `parse.html` / `compare.html` boot flows | Interface/history document | Keep unless interface docs are modernized intentionally |
| `docs/desktop_product_architecture.md` | Describes current/legacy desktop architecture with `parse.html`/`compare.html` | Useful architectural history | Keep, but may need explicit “legacy/current state” labels later |
| `docs/plans/react-vite-pivot.md` | Pivot plan explicitly references replacing `parse.html` / `compare.html` and deleting them in C7 | This is the migration plan itself | Keep |

---

## D. React/Vite references that define the new active workflow

| Path | Current reference | Why it matters | Planned action |
|---|---|---|---|
| `docs/bugs.md` | Repro uses `http://localhost:5173` | Confirms current active React dev path | Keep |
| `docs/archive/plans/oda/coordination.md` | Browser checklist uses `http://localhost:5173/compare` | Archived 2026-04-20 — task complete | Archived |
| `docs/archive/plans/oda/phase-0.md` | `curl http://localhost:5173/api/config` | Archived 2026-04-20 — task complete | Archived |
| `docs/archive/plans/oda/oda-core.md` | Requires `curl localhost:5173/api/config` | Archived 2026-04-20 — task complete | Archived |
| `docs/archive/plans/oda/b9-compare-mode.md` | Validate at `http://localhost:5173/compare` | Archived 2026-04-20 — task complete | Archived |

---

## E. Non-UI `localhost:8766` references that are not themselves legacy UI problems

These do **not** automatically need rewriting just because they mention `:8766`.
They often refer to the API backend, which remains valid.

| Path | Reference type | Action |
|---|---|---|
| `src/api/client.ts` | Documents Vite proxy to backend `http://localhost:8766` | Keep |
| `docs/plans/react-vite-pivot.md` | Describes Vite proxy and backend API on `:8766` | Keep |
| `docs/archive/plans/oda/b7-export.md` | Calls export API on `:8766/api/export/*` | Archived 2026-04-20 — task complete |

---

## Recommended handling summary

### Change in Phase 3
- `README.md`
- `python/server.py` startup messaging
- `desktop/README.md`
- `desktop/dev-launch.js` help text
- `desktop/main.js` failure guidance
- `start_parse.sh` (at minimum label as legacy/special-purpose)
- `Start Review Tool.bat` (at minimum label as legacy/special-purpose)
- any additional operator-facing launcher/docs found during implementation

### Change in Phase 5 / C7
- `parse.html`
- `compare.html`
- `js/`
- follow-up updates to any nav links or runtime assumptions tied to those files

### Preserve for now
- `PROJECT_PLAN.md`
- `CODING.md`
- `INTERFACES.md`
- `docs/desktop_product_architecture.md`
- `docs/plans/react-vite-pivot.md`
- Oda planning docs using `:5173`

---

## Notes
- This inventory distinguishes **legacy UI entrypoint references** from **legitimate backend API references**.
- The presence of `localhost:8766` alone is not a bug; it is only a Phase 3 problem when it is presented as the primary frontend UI path.
- `docs/plans/repo-state-cleanup-and-architecture-unification.md` intentionally discusses legacy entrypoints as part of the cleanup plan and is therefore not treated as a stale legacy reference.
