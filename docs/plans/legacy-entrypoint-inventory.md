# PARSE Legacy Entrypoint Inventory

**Purpose:** Enumerate current references to legacy entrypoints (`parse.html`, `compare.html`, `localhost:8766` legacy UI paths) and identify which phase should handle each reference.

**Scope date:** 2026-04-09
**Repo scanned:** `/home/lucas/gh/ardeleanlucas/parse`

---

## A. User-facing / operator-facing references that should be cleaned up in Phase 3

| Path | Current reference | Why it matters | Planned phase |
|---|---|---|---|
| `README.md` | Describes Annotate as `parse.html`, Compare as `compare.html`; browser section points to `http://localhost:8766/parse.html` and `/compare.html` | Primary onboarding doc still points users to legacy UI | **Phase 3** |
| `python/server.py` | Startup banner prints `http://localhost:{PORT}/parse.html` and `/compare.html` | Server output still tells users legacy is canonical | **Phase 3** |
| `desktop/README.md` | Default desktop URLs still reference `http://127.0.0.1:8766/parse.html` and `/compare.html` | Desktop-oriented instructions still privilege legacy pages | **Phase 3** |
| `Start Review Tool.bat` | Opens `http://localhost:8766/review_tool_dev.html` | Legacy launcher path remains user-visible; needs explicit archival/legacy labeling | **Phase 3 review**, possibly Phase 5 if replaced |

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
| `docs/plans/oda/coordination.md` | Browser checklist uses `http://localhost:5173/compare` | Confirms React Compare validation path | Keep |
| `docs/plans/oda/phase-0.md` | `curl http://localhost:5173/api/config` | Confirms Vite dev workflow | Keep |
| `docs/plans/oda/oda-core.md` | Requires `curl localhost:5173/api/config` | Confirms Vite dev workflow | Keep |
| `docs/plans/oda/b9-compare-mode.md` | Validate at `http://localhost:5173/compare` | Confirms React Compare workflow | Keep |

---

## E. Non-UI `localhost:8766` references that are not themselves legacy UI problems

These do **not** automatically need rewriting just because they mention `:8766`.
They often refer to the API backend, which remains valid.

| Path | Reference type | Action |
|---|---|---|
| `src/api/client.ts` | Documents Vite proxy to backend `http://localhost:8766` | Keep |
| `docs/plans/react-vite-pivot.md` | Describes Vite proxy and backend API on `:8766` | Keep |
| `docs/plans/oda/b7-export.md` | Calls export API on `:8766/api/export/*` | Keep |

---

## Recommended handling summary

### Change in Phase 3
- `README.md`
- `python/server.py` startup messaging
- `desktop/README.md`
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
