> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# PARSE Option-1 Rebuild — Parity Inventory and Evidence Matrix

**Status:** Proposed planning doc for the separate rebuild repo  
**Date:** 2026-04-25  
**Depends on:**
- `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md`
- `docs/plans/option1-two-agent-parallel-rebuild-plan.md`
- `docs/desktop_product_architecture.md`
- current oracle files under `src/`, `python/`, and project data layout

**Primary goal:** define exactly what the separate rebuild repo must match before the Option-1 rebuild can be treated as functionally equivalent to the current PARSE workstation.

---

## 1. Purpose and rules

This document is the **parity scope and evidence contract** for the separate rebuild repo.

It exists to prevent three common failure modes:
1. silent behavior drift during rebuild work
2. backend contract drift that the frontend "works around" locally
3. declaring parity from intuition instead of evidence

### Core rules

- The current PARSE repo remains the **behavior oracle**, **API oracle**, **data-format oracle**, **export oracle**, and **fallback runtime**.
- Option 1 means **domain-preserving modularization**, not feature redesign.
- No parity claim is valid without a linked artifact: test output, screenshot, snapshot, export sample, or written checklist evidence.
- Any non-parity outcome must be logged as a **deviation** with owner, rationale, risk, and closure plan.
- Coordinator-owned shared contracts remain authoritative; implementation lanes do not redefine them ad hoc.

---

## 2. Oracle definition and freeze

### 2.1 Canonical oracle surfaces

The rebuild must be compared against the current PARSE repo, especially these surfaces:

- `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) — live frontend HTTP contract and helper surface
- `package.json` — frontend scripts and baseline validation commands
- `docs/desktop_product_architecture.md` — desktop launch, loopback, and path rules
- `src/components/annotate/**` — Annotate workstation behavior
- `src/components/compare/**` — Compare workstation behavior
- `src/components/compute/**` and shared modals — compute/config/reporting flows
- `src/stores/*.ts` — state persistence and UI orchestration invariants
- `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) and backend tests — route semantics, jobs, errors, static/runtime safety
- on-disk project artifacts — annotations, enrichments, project metadata, exports, audio/transcript layout

### 2.1a Current rebuild mapping for those oracle surfaces

Use these rebuild-lane destinations when translating oracle surfaces into the current post-decomposition layout:

- frontend HTTP helpers → `src/api/contracts/*.ts` re-exported through `src/api/client.ts`
- annotation-store logic → `src/stores/annotation/*.ts` re-exported through `src/stores/annotationStore.ts`
- route/domain backend logic → `python/server_routes/*.py` wired through `python/server.py`
- chat-tool implementations → `python/ai/tools/*.py` plus existing grouped bundles under `python/ai/chat_tools/`, aggregated by `python/ai/chat_tools.py`
- MCP adapter internals → `python/adapters/mcp/*.py`, entered through `python/adapters/mcp_adapter.py`
- provider implementations → `python/ai/providers/*.py`, routed through `python/ai/provider.py`
- canonical quick reference → `docs/architecture/post-decomp-file-map.md`

### 2.2 Oracle baseline record

Before rebuild implementation starts, the coordinator records:

- [ ] oracle repo path
- [ ] oracle branch
- [ ] oracle commit SHA
- [ ] date frozen
- [ ] frontend gate result on the oracle
- [ ] backend/API gate result on the oracle
- [ ] selected fixture dataset/version

Only the coordinator updates the oracle baseline.

---

## 3. Priority tiers

| Tier | Meaning | Examples |
|---|---|---|
| **P0** | Must pass before the Option-1 rebuild can be called functionally ready | Annotate, Compare, Tags persistence, annotation/enrichment/config APIs, core jobs, LingPy export, desktop local-runtime rules |
| **P1** | Must pass before advanced rebuild phases are considered complete | auth flows, AI chat, normalize/onboard, offset tools, CLEF/contact lexeme flows, job logs, comments/tag/concept import |
| **P2** | Useful parity coverage that can trail the core rebuild if explicitly tracked | extra diagnostics, future-page placeholders, non-critical ergonomics, later package extraction readiness |

No P0 item may be silently downgraded.

---

## 4. Surface inventory summary

| Surface | Primary oracle sources | Primary rebuild paths now | Primary owner in rebuild | Required parity outcome |
|---|---|---|---|---|
| App shell + navigation | `src/ParseUI.tsx`, `src/components/shared/TopBar.tsx`, `src/stores/uiStore.ts` | `src/ParseUI.tsx`, shared shell modules, `src/components/parse/right-panel/` | Agent A | Same workbench entrypoints, shell state transitions, global feedback surfaces, and no missing thesis-critical controls |
| Annotate workstation | `src/components/annotate/*.tsx`, `src/stores/annotationStore.ts` (barrel; concrete slices/helpers live under `src/stores/annotation/`), `src/stores/playbackStore.ts` | `src/components/annotate/annotate-views/**`, annotate siblings, `src/stores/annotation/**` | Agent A + Agent B contract support | Same speaker load/edit/save workflow, waveform review, region/lane actions, STT-assisted review, and playback behavior |
| Compare workstation | `src/components/compare/*.tsx`, `src/stores/enrichmentStore.ts`, `src/stores/tagStore.ts` | `src/components/compare/compare-panels/**`, compare siblings, `src/stores/enrichmentStore.ts`, `src/stores/tagStore.ts` | Agent A + Agent B contract support | Same concept × speaker review flow, cognate decisions, borrowing adjudication, enrichments, notes, and tag workflows |
| Import / management flows | `OnboardingFlow.tsx`, `SpeakerImport.tsx`, `CommentsImport.tsx`, CSV import helpers | annotate-view / compare-panel descendants plus import helpers under `src/api/contracts/` and backend route domains | Agent A + Agent B contract support | Same upload/import entrypoints, state transitions, and persisted results |
| HTTP API surface | `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`), backend route tests | `src/api/contracts/**`, `python/server_routes/**`, thin `python/server.py` wiring | Agent B | Same method/path contracts, payload shapes, error semantics, and async job orchestration |
| Async jobs + observability | job helpers in `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`), backend job tests | `src/api/contracts/job-observability.ts`, `python/server_routes/jobs.py`, shared job registry/log plumbing | Agent B | Same start/poll/log/result semantics and same visible progress/failure handling |
| Export behavior | export helpers in `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`), backend export tests | `src/api/contracts/export-and-media.ts`, `python/server_routes/exports.py` | Agent B | LingPy parity, preserved NEXUS semantics, deterministic failures |
| Desktop/runtime constraints | `docs/desktop_product_architecture.md` | archived historical reference only; active rebuild lane instead documents runtime constraints in `README.md`, `docs/getting-started.md`, and `docs/architecture/post-decomp-file-map.md` | Coordinator + Agent A + Agent B | Same local-first launch model, path safety, loopback-only backend boundary, and no hidden cwd/path assumptions |
| Data/storage invariants | project artifact layout + stores + backend persistence paths | project artifacts plus current store/backend split documented in `docs/architecture.md` and `docs/architecture/post-decomp-file-map.md` | Coordinator + Agent B | Same files, same compatibility assumptions, same invariants for concept IDs, timestamps, tags, and enrichments |

---

## 5. UI / workbench parity matrix

### 5.1 P0 workbenches and shell surfaces

| Surface | Current oracle files | Critical behaviors that must match | Priority |
|---|---|---|---|
| Shell / navigation | `src/ParseUI.tsx`, `src/components/shared/TopBar.tsx`, `src/stores/uiStore.ts` | boot into a usable shell, switch major workbenches/modes, preserve global feedback and blocking/error states, preserve keyboard-accessible top-level actions | P0 |
| Annotate | `src/components/annotate/AnnotateMode.tsx` (barrel; implementation lives under `src/components/annotate/annotate-views/`), `AnnotationPanel.tsx`, `TranscriptPanel.tsx`, `RegionManager.tsx`, `SuggestionsPanel.tsx`, `TranscriptionLanes.tsx` | load speaker, display waveform/transcript context, manage intervals/lanes, invoke STT/suggestions, preserve save/reload behavior, support fast playback/review loop | P0 |
| Compare | `src/components/compare/CompareMode.tsx`, `ConceptTable.tsx`, `CognateControls.tsx`, `BorrowingPanel.tsx`, `EnrichmentsPanel.tsx`, `LexemeDetail.tsx` | concept × speaker table rendering, cognate accept/split/merge/cycle, borrowing marking, notes/enrichment persistence, navigation between items | P0 |
| Tags / enrichments management | `src/components/compare/TagManager.tsx`, `src/stores/tagStore.ts`, `src/stores/enrichmentStore.ts` | create/edit/merge tags, bulk state changes, persistence after mutation, reload survival | P0 |

### 5.2 P1 operational and auxiliary surfaces

| Surface | Current oracle files | Critical behaviors that must match | Priority |
|---|---|---|---|
| ~~AI/chat shell~~ — **DROPPED from rebuild parity scope 2026-04-26** | `src/components/annotate/ChatPanel.tsx`, `src/components/shared/ChatMarkdown.tsx` | start session, run/poll chat, show status/result/error cleanly, preserve session semantics expected by UI | P1 |
| Import / onboarding | `src/components/annotate/OnboardingFlow.tsx`, `src/components/compare/SpeakerImport.tsx`, `src/components/compare/CommentsImport.tsx` | upload/start/poll flows, completion and failure states, no phantom success, persisted outputs appear where current PARSE expects them | P1 |
| Compute and report modals | `src/components/compute/ClefConfigModal.tsx` (barrel; implementation lives under `src/components/compute/clef/`), `ClefSourcesReportModal.tsx`, `ClefPopulateSummaryBanner.tsx`, `src/components/shared/BatchReportModal.tsx`, `TranscriptionRunModal.tsx` | same launch affordances, status/progress handling, and report visibility for users reviewing compute outputs | P1 |
| Contact lexeme / CLEF compare extensions | `ContactLexemePanel.tsx` and CLEF helpers | same coverage/config/fetch flow and same decision-support affordances in Compare mode | P1 |
| Job diagnostics | shell modals + `getJobLogs()` support | users can inspect job status/logs and distinguish running, failed, and finished states | P1 |

### 5.3 ~~Reserved Phase-3 shell extensibility~~ — CANCELLED 2026-04-26

> **Cancelled per Lucas decision 2026-04-26**: Option 3 desktop platform pivot is dropped. The reserved Phase-3 placeholders (training, phonetics, broader CL workbenches) are not parity targets. Original §5.3 content preserved below for historical context only.

### 5.3 Reserved Phase-3 shell extensibility

Future shell placeholders for `training`, `phonetics`, and broader computational-linguistics workbenches may be scaffolded in Phase 3, but they are **not parity targets** for the current oracle unless and until the coordinator explicitly adds them.

---

## 6. HTTP API parity inventory

The rebuild must preserve the frontend helper surface presently exposed by `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`).

| Contract group | Current client helpers | Expected parity requirement |
|---|---|---|
| Annotation data | `getAnnotation`, `saveAnnotation`, `getSttSegments` | same per-speaker load/save semantics and same response compatibility for annotation review surfaces |
| Project config and pipeline state | `getConfig`, `updateConfig`, `getPipelineState` | same config mutation semantics, same pipeline-state visibility, same error behavior |
| Enrichments, tags, notes, imports | `getEnrichments`, `saveEnrichments`, `getTags`, `mergeTags`, `saveLexemeNote`, `importConceptsCsv`, `importTagCsv`, `importCommentsCsv` | same request requirements, same mutation persistence, same success/error semantics for import/admin flows |
| Auth | `getAuthStatus`, `startAuthFlow`, `pollAuth`, `saveApiKey`, `logoutAuth` | same auth lifecycle and same compatibility quirks expected by current UI/provider flows |
| STT / normalize / onboard | `startSTT`, `pollSTT`, `startNormalize`, `pollNormalize`, `onboardSpeaker`, `pollOnboardSpeaker` | same start/poll/result semantics, same failure signaling, same artifact side effects |
| Offset tools | `detectTimestampOffset`, `detectTimestampOffsetFromPair`, `detectTimestampOffsetFromPairs`, `pollOffsetDetectJob`, `applyTimestampOffset` | same request/response semantics, same protected-apply behavior, same job/result handling |
| Suggestions / lexeme search | `requestSuggestions`, `searchLexeme` | same payload expectations, same result shapes, same user-visible failure handling |
| Chat and generic compute | `startChatSession`, `getChatSession`, `runChat`, `pollChat`, `startCompute`, `pollCompute` | same session/job lifecycle, same completion statuses, same result envelope expectations |
| Job observability | `listActiveJobs`, `getJobLogs` | same active-job visibility and same log-fetch semantics |
| Export and media | `getLingPyExport`, `getNEXUSExport`, `spectrogramUrl` | same export endpoints/content behavior and same spectrogram URL contract |
| CLEF / contact lexeme | `getContactLexemeCoverage`, `startContactLexemeFetch`, `getClefConfig`, `saveClefConfig`, `getClefCatalog`, `getClefProviders`, `getClefSourcesReport`, `saveClefFormSelections` | same config/catalog/reporting/fetch flows and same compare-mode support contracts |

### 6.1 API-level acceptance criteria

For every contract group above, parity means:

- method + path compatibility are preserved
- required request fields are preserved
- response field names and nullable/optional behavior are preserved
- error status class and structured error behavior are preserved
- async start/poll patterns remain consistent with the current UI
- compatibility aliases already expected by the UI remain supported where required

No frontend lane may "solve" a contract mismatch by inventing a new local convention without coordinator approval.

---

## 7. Async job and export parity requirements

### 7.1 Async jobs that require explicit parity evidence

| Job family | Core endpoints/helpers | Minimum parity evidence |
|---|---|---|
| STT | `startSTT`, `pollSTT` | start artifact, poll artifact, completion artifact, failure artifact |
| Normalize | `startNormalize`, `pollNormalize` | same start/poll semantics and same resulting workspace side effects |
| Generic compute | `startCompute`, `pollCompute` | per-compute-type fixture or snapshot proving status/result parity |
| Chat | `runChat`, `pollChat` | same session-to-job wiring, same completion semantics, same result rendering compatibility |
| Onboard speaker | `onboardSpeaker`, `pollOnboardSpeaker` | same long-running import behavior, same completion/failure semantics, same persisted outputs |
| Offset detection | `detectTimestampOffset*`, `pollOffsetDetectJob`, `applyTimestampOffset` | same detection/apply flow and same safety checks |
| Active jobs / logs | `listActiveJobs`, `getJobLogs` | at least one running-job snapshot and one completed/failed-job log artifact |

### 7.2 Export parity requirements

| Export surface | Required parity outcome | Priority |
|---|---|---|
| LingPy | same endpoint availability, download behavior, and structurally compatible output for downstream use | P0 |
| NEXUS | preserve the current behavior exactly until the coordinator explicitly changes the product decision | P1 |
| Failure cases | deterministic and understandable failures for missing/invalid export prerequisites | P0 |

---

## 8. Data and storage invariants

The rebuild may reorganize code, but it must not casually break the project model.

### 8.1 Persisted artifact invariants

The rebuild must preserve compatibility expectations around:

- `annotations/<Speaker>.parse.json` as the active per-speaker annotation format
- legacy speaker annotation JSON readability where current PARSE still supports it
- `parse-enrichments.json` as the shared comparative overlay store
- project metadata files such as `project.json` and `source_index.json`
- project subdirectories used in desktop planning: `annotations/`, `transcripts/`, `peaks/`, `exports/`, `audio/original/`, `audio/working/`, `sync/`

### 8.2 Semantic invariants

These invariants are not optional without an explicit migration plan:

- concept IDs remain stable identifiers; no silent normalization drift
- annotation interval `start`/`end` semantics remain compatible with current review/save assumptions
- tag and enrichment persistence stays durable across reloads
- per-speaker annotations + shared enrichments remain the core storage model
- project-relative path behavior remains the default desktop target
- no rebuild-only hidden fallback data or scaffold content is introduced

---

## 9. Desktop, runtime, and safety parity

The rebuild must preserve the local-first desktop/runtime model already documented for PARSE Desktop.

### Required constraints

- backend boundary remains loopback HTTP, not a remote-first redesign
- desktop shell starts the backend and waits for readiness before presenting the main workstation
- backend launch contract remains explicit about host, port, project root, auth token, and user-data root
- path normalization and traversal prevention remain mandatory
- no hardcoded machine-specific paths appear in shipped defaults
- no dependence on current working directory as the implicit project selector
- cloud AI remains optional and explicitly configured

### Minimum evidence

- one successful desktop/local-runtime launch trace
- one failure-mode trace showing clear startup or readiness error handling
- one path-safety or static-serving check linked to the rebuild evidence set

---

## 10. Evidence model and reporting rules

### 10.1 Required evidence fields per parity row

Every parity row or checklist item must record:

- status
- priority tier
- oracle reference
- rebuild reference
- owner
- evidence path or artifact link
- reviewer / approver
- deviation link, if applicable

### 10.2 Status vocabulary

Use only these status values:

- `not-started`
- `in-progress`
- `pass`
- `blocked`
- `deviation-approved`

### 10.3 Recommended artifact layout in the rebuild repo

Coordinator-owned shared parity surfaces should remain under `parity/contracts/`, `parity/harness/`, `parity/fixtures/`, and `parity/deviations.md`; lane-owned evidence lives under the UI/API/jobs/export subtrees only when the harness cannot cover the surface directly.

The harness root now also carries its own support artifacts:
- `canonicalization.md` — volatility normalization rules
- `allowlist.yaml` — explicit accepted-diff rules with reasons
- `SIGNOFF.md` — coordinator sign-off template

```text
parity/
  contracts/
    oracle-baseline.md
    route-inventory.md
  harness/
    README.md
    canonicalization.md
    allowlist.yaml
    SIGNOFF.md
    fixtures/
    tests/
    output/        # ignored runtime reports / uploaded CI artifacts
  ui/
    checklists/
    screenshots/
  api/
    snapshots/
    contract-tests/
  jobs/
    traces/
    logs/
  export/
    goldens/
    comparisons/
  fixtures/
  deviations.md
```

### 10.4 Reporting rule

No agent may report a parity surface as complete without linking the underlying artifact.

"It behaves the same" is not evidence.

---

## 11. Option-1 parity exit criteria

The Option-1 rebuild is ready for sign-off only if:

1. all P0 rows are `pass` or explicitly `deviation-approved`
2. no hidden contract drift remains between frontend and backend
3. LingPy export parity is proven on real fixtures
4. current PARSE can still serve as the fallback runtime until cutover is approved
5. the coordinator signs off that the rebuild is stable enough to promote toward Option 3 later without another ground-up rewrite

---

## 12. Immediate next use of this document

1. Freeze the oracle SHA and fixture set.
2. Convert this inventory into actual parity rows inside the rebuild repo.
3. Use `docs/plans/option1-phase0-shared-contract-checklist.md` to block Agent A / Agent B divergence until shared contracts are frozen.
4. Require each phase checkpoint in `docs/plans/option1-two-agent-parallel-rebuild-plan.md` to reference this inventory when claiming parity progress.

---

## 11. Accepted oracle deviations (added 2026-04-26 evening)

The plan was originally written assuming oracle-as-immutable-spec. Dogfooding the rebuild revealed oracle has its own bugs that parity evidence has been recording as deviations rather than rebuild failures. This section is the durable list of those deviations so future parity passes can reference it.

| Deviation | Oracle issue | Status | Affects parity evidence |
|---|---|---|---|
| TranscriptionLanes hook-order crash on Annotate entry (Saha01 fixture) | [ArdeleanLucas/PARSE#230](https://github.com/ArdeleanLucas/PARSE/issues/230) | **RESOLVED via oracle sync** in [ArdeleanLucas/PARSE#234](https://github.com/ArdeleanLucas/PARSE/pull/234) (merged 2026-04-26) | PR #66 (Annotate parity) remains the historical evidence for the old oracle crash; future Annotate parity passes should treat this as closed unless the regression reappears |
| `_display_readable_path` leaks Windows path separators into `source_index.json` and `annotation.source_audio` | [ArdeleanLucas/PARSE#231](https://github.com/ArdeleanLucas/PARSE/issues/231), [ArdeleanLucas/PARSE#232](https://github.com/ArdeleanLucas/PARSE/issues/232) | **RESOLVED via oracle sync** in [ArdeleanLucas/PARSE#233](https://github.com/ArdeleanLucas/PARSE/pull/233) (merged 2026-04-26) | Historical caveat for the backend gate evidence in PR #64 only; future import/onboarding parity should assume the oracle now preserves POSIX project-relative paths unless new evidence contradicts that |
| Regular `/api/onboard/speaker` import still writes Windows path separators into `source_index.json` and the job result payload | [ArdeleanLucas/PARSE#236](https://github.com/ArdeleanLucas/PARSE/issues/236) | Open on oracle; reproduced in rebuild during import parity pass | The import/onboarding parity evidence report records this as a **shared deviation**: both oracle and rebuild still emit backslashes on the regular onboard route even though processed-speaker imports are fixed |
| 10 oracle backend tests failing in unclassified state | none yet | Deferred audit | Parity claims for backend surfaces have caveats until classified |

### Rules going forward

- Every parity harness report — and any remaining ad-hoc evidence doc that the harness cannot yet replace — MUST reference this deviation list at the top.
- A flow that fails ONLY because oracle is broken is recorded as DEVIATION, not as rebuild parity failure.
- Adding a new deviation requires a one-line entry above + a linked oracle issue (file one if missing).
- Mark a deviation **RESOLVED** once the oracle fix is merged on `main` with a linked upstream PR; the next parity pass on that surface should still note the historical deviation and confirm the regression stays closed.

## 12. Current parity closure matrix (updated 2026-04-27 final sign-off audit)

The shared harness is now the default evidence vehicle for contract-level parity. Surfaces that still depend on browser-only affordances remain explicitly marked below instead of being hand-waved as complete.

| Surface | Priority | Current status | Evidence route | Notes |
|---|---|---|---|---|
| Shell / navigation | P0 | `blocked` | none yet | Current harness proves backend/data/export parity, but no final post-merge shell-navigation browser audit has been rerun on current `origin/main`. |
| Annotate | P0 | `blocked` | historical evidence doc | `docs/reports/2026-04-26-annotate-parity-evidence.md` captured the old oracle-side `TranscriptionLanes` crash. Oracle issue `#230` was fixed upstream in `#234`, so Annotate needs a fresh rerun rather than treating the historical FAIL as final. |
| Compare | P0 | `blocked` | historical evidence doc | `docs/reports/2026-04-26-compare-parity-evidence.md` still shows decision-row `Accept / Split / Merge` divergence on rebuild current-main. |
| Annotate BND / phonetic-tools UI | P0 | `pass-via-harness` | `parity/harness/SIGNOFF.md` | PR #149 is the real frontend BND port. The refreshed coordinator source-audit now verifies rebuild’s actual action-button literals (`Refine Boundaries (BND)`, `Re-run STT with Boundaries`) instead of the stale oracle-only `Phonetic Tools` heading. |
| BND UI gate surfaces (`tiers.ortho_words`, STT word timestamps) | P0 | `pass-via-harness` | `parity/harness/SIGNOFF.md` | Gate logic is present on main via `bndIntervalCount` and `sttHasWordTimestamps`; the feature-contract slice now reruns at `0` raw diffs after the coordinator refreshed the brittle exact-string audit rules. |
| BND / MCP tool surface | P1 | `pass-via-harness` | `parity/harness/SIGNOFF.md` | PR #152 landed the backend foundation (`boundaries`, `retranscribe_with_boundaries`, chat/MCP exposure). Full harness now closes with `0` unallowlisted diffs; the only remaining raw MCP entries are explicitly allowlisted metadata-copy differences for the two BND starter tools. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | `docs/reports/2026-04-26-tags-parity-evidence.md` | Tags parity passed `7/7` browser flows; the shared harness also covers the underlying enrichments/tags contracts, but the browser evidence remains the authoritative closure artifact for this surface. |
| ~~AI/chat shell~~ | P1 | `dropped` | scope decision | Dropped from rebuild parity scope on 2026-04-26; AI chat UI is maintenance-mode-only. |
| Import / onboarding | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers concept import, tag import, onboard start/poll, persistence, and required error envelopes on shared oracle/rebuild fixtures. |
| Compute and report modals | P1 | `blocked` | partial harness coverage only | Harness now covers the underlying compute/report contracts (`full_pipeline`, CLEF config/report/fetch, export/report payloads), but the modal/browser affordances themselves have not been rerun as a final browser parity pass. |
| Contact lexeme / CLEF compare extensions | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers CLEF config/catalog/providers/report plus contact-lexeme coverage and fetch job lifecycles. |
| Job diagnostics | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs` with active + terminal job evidence. |

### Coordinator rule going forward

- If a surface is covered by the shared harness, mark it **pass-via-harness** and link the harness artifact instead of spawning a new standalone evidence memo.
- If a surface still depends on browser-only controls or workflows, keep it in `blocked` or `pass-via-evidence-doc` until a real browser artifact exists.
- Do not collapse `blocked` browser-workbench gaps into harness success; backend parity and browser parity are related but not interchangeable.
