# AGENTS.md — PARSE React + Vite Integration (2026)

## Current State (updated 2026-04-21)

PARSE has crossed the React pivot and the unified UI redesign is **merged to `main`**.

- **UI Redesign landed** (MC-294, merged via multiple PRs through PR #31):
  - `src/ParseUI.tsx` — unified shell (Annotate + Compare + Tags + AI Chat in one layout)
  - `App.tsx` simplified to `<BrowserRouter><ParseUI /></BrowserRouter>`
  - Dependencies: `lucide-react`, `tailwindcss v3`, `postcss`, `autoprefixer`
  - Wired: `useWaveSurfer`, `useChatSession`, `useConfigStore`, `useTagStore`, `usePlaybackStore`, `useUIStore`, `useAnnotationSync`
  - Spectrogram Worker TS port + `useSpectrogram` hook (MC-297, PR #31)
  - Annotate prefill/save/mark/badge, compare real data, import modal, notes, compute basics, decisions basics, tags bulk-selection — all landed
- **Cross-mode integration landed on current `main`**:
  - Track merge (`feat/annotate-react` + `feat/compare-react`) completed
  - Cross-mode navigation (Annotate ↔ Compare)
  - Store persistence regression coverage
  - API regression suite + CLEF integration coverage
- **CLEF shipped**:
  - Provider registry in `python/compare/providers/`
  - Compare UI panel in `src/components/compare/ContactLexemePanel.tsx`
  - Server endpoints:
    - `POST /api/compute/contact-lexemes`
    - `GET /api/contact-lexemes/coverage`

## MCP adapter note

- `python/adapters/mcp_adapter.py` now supports `config/mcp_config.json` with `{ "expose_all_tools": true }`.
- Default MCP surface is **30 tools**: the legacy 29 `ParseChatTools` wrappers plus read-only `mcp_get_exposure_mode` for self-inspection.
- Enabling `expose_all_tools` expands the MCP surface to **48 tools**: all 47 `ParseChatTools` plus `mcp_get_exposure_mode`.
- For backward compatibility, root-level `mcp_config.json` is also accepted when `config/mcp_config.json` is absent.
- `ChatToolSpec` is the MCP metadata source of truth. MCP tools should forward the strict schema from `spec.parameters`, standard MCP annotations from `spec.mcp_annotations_payload()`, and PARSE-specific safety metadata from `meta["x-parse"] = spec.mcp_meta_payload()`.
- Mutability meanings:
  - `read_only` — inspection only; no writes or background jobs
  - `stateful_job` — starts or manages a background job that can later mutate project artifacts
  - `mutating` — can write files or otherwise change project state directly
- Agent-facing safety reasoning should read `meta["x-parse"]["preconditions"]` / `postconditions` instead of guessing from prose. Example:

```python
x_parse = tool.meta["x-parse"]
if any(cond["id"] == "project_loaded" for cond in x_parse["preconditions"]):
    # Load / verify project context before calling the tool.
    ...
if x_parse["supports_dry_run"]:
    # Prefer a preview call before a mutating call.
    ...
```

## Client/Server Contract Surface

All `src/api/client.ts` helpers have matching routes in `python/server.py`:

| Client helper | Endpoint | Server status |
|---|---|---|
| `getAnnotation()` | `GET /api/annotations/{speaker}` | ✅ |
| `saveAnnotation()` | `POST /api/annotations/{speaker}` | ✅ |
| `getEnrichments()` | `GET /api/enrichments` | ✅ |
| `saveEnrichments()` | `POST /api/enrichments` | ✅ |
| `getConfig()` | `GET /api/config` | ✅ |
| `updateConfig()` | `PUT /api/config` | ✅ |
| `getAuthStatus()` | `GET /api/auth/status` | ✅ |
| `startAuthFlow()` | `POST /api/auth/start` | ✅ |
| `pollAuth()` | `POST /api/auth/poll` | ✅ (required to drive Codex device-token exchange; `getAuthStatus` only reads cached state) |
| `saveApiKey()` | `POST /api/auth/key` | ✅ |
| `logoutAuth()` | `POST /api/auth/logout` | ✅ |
| `startSTT()` | `POST /api/stt` | ✅ |
| `pollSTT()` | `POST /api/stt/status` | ✅ |
| `requestIPA()` | `POST /api/ipa` | ✅ |
| `requestSuggestions()` | `POST /api/suggest` | ✅ |
| `startChatSession()` | `POST /api/chat/session` | ✅ |
| `getChatSession()` | `GET /api/chat/session/{id}` | ✅ |
| `runChat()` | `POST /api/chat/run` | ✅ |
| `pollChat()` | `POST /api/chat/run/status` | ✅ |
| `startCompute()` | `POST /api/compute/{type}` | ✅ Dynamic dispatch |
| `pollCompute()` | `POST /api/compute/{type}/status` | ✅ |
| `getLingPyExport()` | `GET /api/export/lingpy` | ✅ |
| `getNEXUSExport()` | `GET /api/export/nexus` | ⏳ Placeholder |
| `getContactLexemeCoverage()` | `GET /api/contact-lexemes/coverage` | ✅ |
| `startContactLexemeFetch()` | `POST /api/compute/contact-lexemes` | ✅ |
| `startNormalize()` | `POST /api/normalize` | ✅ ffmpeg loudnorm pipeline |
| `pollNormalize()` | `POST /api/normalize/status` | ✅ |
| `onboardSpeaker()` | `POST /api/onboard/speaker` | ✅ Multipart upload, background job |
| `pollOnboardSpeaker()` | `POST /api/onboard/speaker/status` | ✅ |
| `getTags()` | `GET /api/tags` | ✅ |
| `mergeTags()` | `POST /api/tags/merge` | ✅ |

**Rule:** Keep this table current. Every new client helper must have a matching server route before merge.

## Deferred Validation Backlog

The following validation items remain important, but they are **not hard blockers for current implementation work**:

- **C5:** LingPy TSV export verification (columns + row counts in browser)
- **C6:** Full browser regression checklist (Annotate waveform/regions/STT + Compare grid/tags/nav)
- **Current policy:** if Lucas asks for work on other PR stages, do that work. Keep C5/C6 on a deferred to-test list and run them in the order of actual testing once onboarding/import and end-to-end flows are ready.
- **C7 / legacy cleanup:** destructive cleanup is no longer mechanically blocked on C5/C6 signoff, but it still requires a scoped PR, rollback discipline, and Lucas review/merge.

## Branch + Worktree Policy

### Canonical repository path
- **Active execution repo:** `/home/lucas/gh/ardeleanlucas/parse`
- **Archive/divergent clone:** `/home/lucas/gh/ArdeleanLucas/PARSE`
  - This uppercase clone currently follows archival/worktree history and may not match `origin/main`.
  - Do not use it as branch truth without an explicit fetch/prune check.

### Historical worktrees (traceability only)
- Integration root: `/home/lucas/gh/ArdeleanLucas/PARSE` → historical `feat/parse-react-vite` lane (merged/deleted)
- Annotate lane: `/home/lucas/gh/worktrees/PARSE/annotate-react` → `feat/annotate-react`
- Compare lane: `/home/lucas/gh/worktrees/PARSE/compare-react` → `feat/compare-react`
- These worktrees describe migration history; they are not the current runtime source of truth.

### Active development rule
- **New work should branch from `origin/main` in `/home/lucas/gh/ardeleanlucas/parse` unless Lucas explicitly changes repo policy.**
- `feat/annotate-react`, `feat/compare-react`, `feat/parse-react-vite` (merged/deleted), and `feat/annotate-ui-redesign` are historical pivot lanes, not default bases for new work.
- Do not assume stale track branches or archival clones reflect current `main`.

## Ownership + Coordination

Historical split remains useful for boundaries:

- ParseBuilder domain: Annotate + shared platform
- Oda domain: Compare mode components/stores/hooks

However, on current `main`, coordinate shared-surface edits carefully.

### Shared surfaces requiring coordination before commit
- `src/api/client.ts`
- `src/api/types.ts`
- `python/server.py`

## Safe Work Now (current priority)

- Add provider test coverage under `python/compare/providers/test_*.py`
- Improve Lexibank/WOLD setup docs and CKB coverage strategy
- Expand provider metadata and scholarly-source coverage plans
- Work other PR stages directly when Lucas asks; do not use C5/C6 as a reason to defer implementation work

## Do Not Touch

- Avoid broad incidental churn in `src/components/compare/*`; edit compare components when required by the active stage and keep changes scoped/test-backed
- `config/sil_contact_languages.json` directly (runtime output file)
- Broad destructive cleanup without a scoped PR, rollback plan, and Lucas review/merge

## Frontend Rules (hard constraints)

These apply to every `src/` file. Violation = stop and fix before merge.

**API & state**
1. **No bare `fetch()` calls.** Every API call goes through `src/api/client.ts`.
2. **No `window.PARSE` references.** The old global namespace is dead in React.
3. **No `localStorage` reads/writes** except inside `tagStore.persist()` and `tagStore.hydrate()`.
4. **Zustand is the only state for data.** `useState` is allowed only for pure UI state (modal open/close, which tab is active).
5. **`enrichmentStore.save()` is the only write path for enrichment data.** No direct `POST /api/enrichments` from components.
6. **`tagStore.persist()` after every mutation.** A tag that is not persisted is lost on page reload.

**Data invariants**
7. **Timestamps are immutable.** `start` and `end` on `AnnotationInterval` are set once and never changed.
8. **Concept IDs are stable identifiers.** Never normalize, trim, lowercase, or transform. The entire pipeline (annotations, enrichments, LingPy, BEAST2) breaks silently if IDs drift.

**Code quality**
9. **TypeScript strict mode.** Every file must compile with `npx tsc --noEmit`.
10. **No `any` types** unless unavoidable. If you use `any`, add an inline comment explaining exactly why.
11. **Prefer classes / Tailwind / CSS modules over inline styles.** Inline `style={{…}}` is allowed for values that are genuinely dynamic (computed widths, progress bars) — don't use it as a shortcut for static layout. Existing files with heavy inline styles (e.g. `ParseUI.tsx`, shared primitives) should migrate as they're touched, not via broad churn.
12. **No emoji in the UI.** Text labels only — this is a fieldwork research tool.
13. **Every feature component and hook has a co-located test file.** "Feature" = anything under `src/components/annotate/`, `src/components/compare/`, `src/hooks/`. Shared primitives under `src/components/shared/` are exempt. The floor in Test Gates below (≥157 passing) is the enforced check; this rule is the target for new features.

## Test Gates (pre-push)

Run both before pushing PARSE changes:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

Expected floor: **>=157 passing tests** and clean TypeScript compile.

## Baseline Architecture

- Frontend: React 18 + TypeScript + Vite + Zustand
- Backend: Python server on `127.0.0.1:8766`
- Data: speaker annotations JSON + enrichments + LingPy export pipeline

---

If pivot status changes (new milestone completion, gating updates, ownership shifts), update this file immediately to prevent stale coordination instructions.
