# AGENTS.md — PARSE React + Vite Integration (2026)

> **Rebuild repo note (2026-04-25):** this repository is the isolated refactor/rebuild lane. The live/oracle PARSE repo remains `ArdeleanLucas/PARSE` at `/home/lucas/gh/ardeleanlucas/parse`. Do not treat this repo as the currently deployed thesis runtime.

## Repo-target rule (READ BEFORE OPENING ANY PR)

All refactor and rebuild work in this lane lands on **`TarahAssistant/PARSE-rebuild`**, NEVER on `ArdeleanLucas/PARSE`. Three prior refactor PRs landed on the wrong remote and had to be reverted or replayed:

- `ArdeleanLucas/PARSE#225` — reverted in oracle commit `0951287` (`revert: move refactor PRs out of live PARSE (#228)`)
- `ArdeleanLucas/PARSE#226` — reverted in the same commit
- `ArdeleanLucas/PARSE#229` — closed without merging on 2026-04-26; replayed onto rebuild as `TarahAssistant/PARSE-rebuild#68`

Before opening any PR for any task in this lane, verify all three:

1. **Working clone** is the rebuild clone:
   ```
   $ pwd
   /home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
   ```
   NOT `/home/lucas/gh/ArdeleanLucas/PARSE` (oracle clone, capital).
   NOT `/home/lucas/gh/ardeleanlucas/parse` (oracle clone, lowercase duplicate).
   NOT any worktree under `/home/lucas/gh/worktrees/PARSE/...` whose `.git` gitfile resolves to either oracle clone above. Worktrees inherit the parent clone's remote.

2. **Origin remote** points at rebuild, not oracle:
   ```
   $ git remote -v
   origin\tgit@github.com:TarahAssistant/PARSE-rebuild.git (fetch)   # CORRECT
   origin\tgit@github.com:TarahAssistant/PARSE-rebuild.git (push)
   ```
   If the URL says `ArdeleanLucas/PARSE`, **stop**. Switch to `/home/lucas/gh/tarahassistant/PARSE-rebuild` (or create a worktree under `/home/lucas/gh/worktrees/PARSE-rebuild/...`) before doing anything else.

3. **PR-create command** explicitly targets the rebuild repo:
   ```
   $ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...
   ```
   The `--repo` flag is **mandatory**. Without it, `gh` infers the remote from the local clone's origin, and any agent that ends up in an oracle clone or worktree will silently push to oracle. **Do not omit the `--repo` flag.**

If you ever see a PR URL like `https://github.com/ArdeleanLucas/PARSE/pull/...`, **close it immediately** and replay the same commit onto rebuild via `git cherry-pick`. The recovery path is documented in `docs/plans/2026-04-26-parse-back-end-next-chat-tools-decomposition.md` §Recovery path.

Exceptions to this rule (cases where landing on oracle IS correct):

- A live thesis-runtime bug fix that Lucas explicitly requests — open the PR on `ArdeleanLucas/PARSE` with title prefix `fix(live):`
- A controlled sync/revert PR moving a previously-merged change between repos — open on whichever repo is the target, with title prefix `sync(oracle->rebuild):` or `revert(oracle):`

Both exceptions require Lucas's explicit approval per task. Do not assume.

## Screenshot convention (private-repo constraint)

**Use markdown links, NOT inline image embeds, for screenshots in PR descriptions.** This repo is private; inline `<img>` fetches in PR bodies do not carry repo auth, so `raw.githubusercontent.com` and `github.com/.../blob/...?raw=1` URLs 404 silently for everyone — including the PR author.

**Working pattern:**

```markdown
## Screenshot

[Screenshot: AnnotateView post-extraction](docs/pr-assets/foo.png)
```

**Failing patterns to avoid:**

```markdown
![alt](https://raw.githubusercontent.com/TarahAssistant/PARSE-rebuild/<branch>/docs/pr-assets/foo.png)
![alt](https://github.com/TarahAssistant/PARSE-rebuild/blob/<branch>/docs/pr-assets/foo.png?raw=1)
```

Both 404 in browsers. Verified 2026-04-26 — every screenshot embed in PRs #62, #63, #73, #79, #86 was failing silently. The screenshot rule had been doing nothing.

Why the link works: clicking the markdown link navigates to GitHub's blob view, which respects the viewer's auth session. Reviewers see the image one click away. Agents can do this trivially with no API changes.

**File location convention** unchanged: commit screenshots as binary files under `docs/pr-assets/<pr-number-or-slug>-<descriptor>.png`.

**Sanity-check your screenshot is real**: capture distinct browser states for each PR. If your screenshot tool keeps producing byte-identical PNGs across different PRs (compare blob SHAs), the tool is capturing a blank/error state, not real UI. Investigate before adding more screenshot evidence.

## Current State (updated 2026-04-25)

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
- **Streaming responses shipped**:
  - Additive WebSocket sidecar in `python/external_api/streaming.py`
  - Dedicated port via `PARSE_WS_PORT` (default `8767`)
  - Per-job subscription endpoint: `ws://<host>:<ws_port>/ws/jobs/{jobId}`
  - Typed events: `job.snapshot`, `job.progress`, `job.log`, `stt.segment`, `job.complete`, `job.error`
  - Existing HTTP polling and callback flows remain fully supported

## MCP adapter note

- `python/adapters/mcp_adapter.py` now supports `config/mcp_config.json` with `{ "expose_all_tools": true }`.
- Default MCP surface is **36 tools**: the legacy 29 `ParseChatTools` wrappers, 3 high-level `WorkflowTools` macros from `python/ai/workflow_tools.py`, the 3 generic observability tools (`jobs_list`, `job_status`, `job_logs`), plus read-only `mcp_get_exposure_mode` for self-inspection.
- Enabling `expose_all_tools` expands the MCP surface to **54 tools**: all 50 `ParseChatTools`, the 3 `WorkflowTools` macros, plus `mcp_get_exposure_mode`.
- The workflow macros are:
  - `run_full_annotation_pipeline`
  - `prepare_compare_mode`
  - `export_complete_lingpy_dataset`
- For backward compatibility, root-level `mcp_config.json` is also accepted when `config/mcp_config.json` is absent.
- `ChatToolSpec` is the MCP metadata source of truth. MCP tools should forward the strict schema from `spec.parameters`, standard MCP annotations from `spec.mcp_annotations_payload()`, and PARSE-specific safety metadata from `meta["x-parse"] = spec.mcp_meta_payload()`.
- Task 5 adds a parallel **HTTP MCP bridge** in `python/server.py`:
  - `GET /api/mcp/exposure`
  - `GET /api/mcp/tools`
  - `GET /api/mcp/tools/{toolName}`
  - `POST /api/mcp/tools/{toolName}`
- Task 5 also adds OpenAPI docs served directly by `python/server.py`:
  - `GET /openapi.json`
  - `GET /docs`
  - `GET /redoc`
- Additive WebSocket job streaming now runs beside the HTTP server:
  - `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}`
  - event envelope fields: `event`, `jobId`, `type`, `ts`, `payload`
  - current v1 events: `job.snapshot`, `job.progress`, `job.log`, `stt.segment`, `job.complete`, `job.error`
- Official external wrappers now live in `python/packages/parse_mcp/`.
- Mutability meanings:
  - `read_only` — inspection only; no writes or background jobs
  - `stateful_job` — starts or manages a background job that can later mutate project artifacts
  - `mutating` — can write files or otherwise change project state directly
- Agent-facing safety reasoning should read `meta["x-parse"]["preconditions"]` / `postconditions` instead of guessing from prose.

### Safety Metadata Reference

Example `meta["x-parse"]` payload exposed through MCP:

```json
{
  "mutability": "mutating",
  "supports_dry_run": true,
  "dry_run_parameter": "dryRun",
  "preconditions": [
    {
      "id": "project_loaded",
      "description": "The PARSE project root must be available and readable.",
      "severity": "required",
      "kind": "project_state"
    },
    {
      "id": "speaker_annotation_exists",
      "description": "The requested speaker must already have an annotation file to export.",
      "severity": "required",
      "kind": "file_presence"
    }
  ],
  "postconditions": [
    {
      "id": "export_file_written",
      "description": "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
      "severity": "required",
      "kind": "filesystem_write"
    }
  ]
}
```

Agent-side example:

```python
x_parse = tool.meta["x-parse"]
if any(cond["id"] == "project_loaded" for cond in x_parse["preconditions"]):
    # Load / verify project context before calling the tool.
    ...
if x_parse["supports_dry_run"]:
    # Prefer a preview call before a mutating call.
    ...
```

### Generic job observability tools

Use the generic tools when an agent needs transport-independent job inspection instead of guessing by job type.

- `jobs_list(statuses=[...], types=[...], speaker="Fail01", limit=20)`
  - lists active + recent jobs from the shared registry
- `job_status(jobId="...")`
  - returns the full generic snapshot: `type`, `status`, `progress`, `message`, `error`, `errorCode`, timestamps, `meta`, `logCount`
- `job_logs(jobId="...", offset=0, limit=50)`
  - returns structured log lines (`ts`, `level`, `event`, `message`, optional `progress`, optional `data`)

Recommended agent pattern:
1. Start a heavy job (`pipeline_run`, `stt_start`, `audio_normalize_start`, etc.)
2. Poll `job_status` for transport-neutral state
3. Inspect `locks` when coordinating speaker-scoped mutating work between humans and agents
4. Read `job_logs` when the human asks "what is it doing?" or when progress stalls
5. For HTTP-started jobs that need push completion, pass `callbackUrl` (absolute `http(s)` URL) on the job-start request so PARSE POSTs the final generic job payload on `complete` / `error`
6. For realtime progress, connect to `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}` and consume the typed event stream
7. Fall back to old per-type status tools only when a workflow needs type-specific payload shaping

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
- **Active execution repo in this rebuild lane:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- **Live/oracle PARSE repo:** `/home/lucas/gh/ardeleanlucas/parse`
  - Treat this oracle repo and `github.com/ArdeleanLucas/PARSE` as the behavior source of truth until parity is explicitly signed off.
  - Refactor implementation should happen here in the rebuild repo, not on the live/oracle repo.
- **Archive/divergent clone:** `/home/lucas/gh/ArdeleanLucas/PARSE`
  - This uppercase clone currently follows archival/worktree history and may not match `origin/main`.
  - Do not use it as branch truth without an explicit fetch/prune check.

### Historical worktrees (traceability only)
- Oracle integration root: `/home/lucas/gh/ardeleanlucas/parse`
- Historical pivot worktrees under `/home/lucas/gh/worktrees/PARSE/` remain useful for archaeology only.
- These worktrees describe migration history; they are not the current rebuild repo source of truth.

### Active development rule
- **New refactor/rebuild work should branch from `origin/main` in `/home/lucas/gh/tarahassistant/PARSE-rebuild`.**
- Keep `ArdeleanLucas/PARSE` stable unless Lucas explicitly requests a live-repo bugfix or a controlled sync/revert PR.
- `feat/annotate-react`, `feat/compare-react`, `feat/parse-react-vite` (merged/deleted), and `feat/annotate-ui-redesign` are historical pivot lanes, not default bases for new rebuild work.
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


## Coordinator handoff convention (2026-04-26)

New queued work for `parse-builder`, `parse-back-end`, and `parse-gpt` is now tracked under repo-local handoff files instead of merge-to-main queue-prompt PRs.

### Canonical queue location

```text
.hermes/handoffs/<agent>/<YYYY-MM-DD>-<slug>.md
```

### Rules

- New coordinator task queueing should go into `.hermes/handoffs/`, not `docs: queue <agent> next task` PRs.
- Handoff front matter must record at minimum: `agent`, `queued_by`, `queued_at`, `status`, and optional `related_prs`.
- Lifecycle is file-based: `queued` → `in-progress` → `done` (move completed items into `.hermes/handoffs/<agent>/done/`).
- Historical queue-prompt PRs remain part of the audit trail, but they are no longer the preferred mechanism for staging the next task.
- Current open queue PRs that predate this convention can finish their immediate lifecycle, but future queue churn should not go through main-branch docs PRs.

## Safe Work Now (current priority)

- Freeze the rebuild-repo contract: oracle SHA, parity fixtures, and Phase 0 shared-contract checklist
- Continue behavior-preserving refactor work here instead of landing refactor slices on the live PARSE repo
- Port live refactor PRs here first when needed, then use narrow revert/sync PRs to keep `ArdeleanLucas/PARSE` stable
- Maintain parity artifacts under `parity/` and keep deviations explicit when rebuild behavior temporarily differs from the oracle

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
