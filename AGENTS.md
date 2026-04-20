# AGENTS.md — PARSE React + Vite Integration (2026)

## Current State (updated 2026-06-14)

PARSE has crossed the React pivot and the unified UI redesign is **merged to `main`**.

- **UI Redesign landed** (MC-294, merged via multiple PRs through PR #31):
  - `src/ParseUI.tsx` — unified shell (Annotate + Compare + Tags + AI Chat in one layout)
  - `App.tsx` simplified to `<BrowserRouter><ParseUI /></BrowserRouter>`
  - Dependencies: `lucide-react`, `tailwindcss v3`, `postcss`, `autoprefixer`
  - Wired: `useWaveSurfer`, `useChatSession`, `useConfigStore`, `useTagStore`, `usePlaybackStore`, `useUIStore`, `useAnnotationSync`
  - Spectrogram Worker TS port + `useSpectrogram` hook (MC-297, PR #31)
  - Annotate prefill/save/mark/badge, compare real data, import modal, notes, compute basics, decisions basics, tags bulk-selection — all landed
- **Phase C1–C4 complete** on integration branch:
  - Track merge (`feat/annotate-react` + `feat/compare-react`)
  - Cross-mode navigation (Annotate ↔ Compare)
  - Store persistence regression coverage
  - API regression suite + CLEF integration coverage
- **CLEF shipped**:
  - Provider registry in `python/compare/providers/`
  - Compare UI panel in `src/components/compare/ContactLexemePanel.tsx`
  - Server endpoints:
    - `POST /api/compute/contact-lexemes`
    - `GET /api/contact-lexemes/coverage`

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
| ~~`pollAuth()`~~ | `POST /api/auth/poll` | ✅ (server route exists; client helper removed — use `getAuthStatus()`) |
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

## Release Gates (hard)

The following are **manual Lucas gates** and must be respected in order:

- **C5:** LingPy TSV export verification (columns + row counts in browser)
- **C6:** Full browser regression checklist (Annotate waveform/regions/STT + Compare grid/tags/nav)
- **C7:** Cleanup and legacy deletion **blocked until C5 + C6 are explicitly cleared**

Do not start C7 early.

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

## Safe Work Now (pre-C6)

- Add provider test coverage under `python/compare/providers/test_*.py`
- Improve Lexibank/WOLD setup docs and CKB coverage strategy
- Expand provider metadata and scholarly-source coverage plans
- Non-destructive documentation/policy clarification about React (`:5173`) vs legacy (`parse.html`/`compare.html`) entrypoints is allowed when needed to reduce operator confusion

## Do Not Touch

- `src/components/compare/*` (ContactLexemePanel + compare components currently stable)
- `python/server.py` destructive routing/cutover changes before C5+C6 signoff
- `config/sil_contact_languages.json` directly (runtime output file)
- Any C7 cleanup/deletion before C5+C6 signoff

## Test Gates (pre-push)

Run both before pushing integration changes:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

Expected floor: **>=132 passing tests** and clean TypeScript compile.

## Baseline Architecture

- Frontend: React 18 + TypeScript + Vite + Zustand
- Backend: Python server on `127.0.0.1:8766`
- Data: speaker annotations JSON + enrichments + LingPy export pipeline

---

If pivot status changes (new phase completion, gating updates, ownership shifts), update this file immediately to prevent stale coordination instructions.
