# MC-312 — Own data vs filler-data investigation

## Objective
Explain why PARSE currently shows data that is not Lucas's own fieldwork data, identify the exact code/data sources responsible, and distinguish true workspace content from placeholder or bundled sample content.

## Scope
- Canonical repo: `/home/lucas/gh/ardeleanlucas/parse`
- Investigation only unless a fix is explicitly requested afterward
- Focus on React/Vite ParseUI data-loading paths and any persisted local/browser state that can surface non-user data

## Plan
1. Verify the active repo/worktree and inspect current data files (`annotations/`, `source_index.json`, `project.json`, `parse-enrichments.json`, `concepts.csv`).
2. Search the frontend for mock/demo/fallback/default data paths that could populate the UI.
3. Trace the stores and config-loading path to see how speakers/concepts are discovered and selected.
4. If helpful, inspect the running browser UI and console to match code paths to the visible filler data.
5. Report the root cause clearly, with exact files/functions and whether the issue is workspace data, seeded sample data, or browser-persisted state.

## Completion criteria
- Root cause identified with evidence from the current codebase
- Clear explanation of whether the non-user data comes from checked-in repo fixtures, generated workspace files, or frontend fallbacks
- No fix proposed until the cause is understood

---

## Closed 2026-04-20

**Resolution:** No filler/mock/demo/fixture data is wired into PARSE. Any non-user data a user previously observed in the UI came from their own running backend serving a project directory (`os.cwd()`-derived root), not from repo-checked-in or frontend-seeded content.

### Evidence

**Repo state at close:** `main` @ `3c023aa` (post-PR #58). Legacy vanilla-JS surface is removed. Repo root contains no `project.json`, no `annotations/`, no `audio/`, no `source_index.json`.

**Final audit greps (run from a blank checkout, Stage 5 of 2026-04-20 docs audit):**

```bash
# Frontend: mock/fixture/fake/stub/demo tokens, excluding tests, test dirs, and DSP audio-sample terminology
grep -rEi --include='*.ts' --include='*.tsx' \
  '\b(mock|fixture|fake|stub|demo)\b|\bsamples?\b' src/ \
  | grep -vE '\.test\.|__tests__|/workers/spectrogram'
# → 0 hits

# Backend: string-literal fixture shapes, excluding test files
grep -rE --include='*.py' '"(mock|demo|fake|stub)"' python/ \
  | grep -vE 'test_|_test\.py'
# → 0 hits
```

**Frontend assertion (still present):** [`src/ParseUI.tsx:54`](../../src/ParseUI.tsx#L54):

```ts
// No fallback data — workspace must supply real speakers and concepts via /api/config.
```

### Why the investigation existed

A running PARSE backend loads its project from `os.cwd()` (`python/server.py::_project_root`). If the user launches the server from a directory that already contains `project.json`/`annotations/`, those files populate the UI immediately — with no "open project" prompt. This is an architectural property (single-project, cwd-anchored), not filler data. A separate follow-up (blank-slate startup UX — explicit open/create-project flow) is tracked outside this investigation.

### Scope boundary

MC-312 was about identifying filler data in the product. That answer is: **there is none.** The follow-up about making the product start from a blank state by default is a product/UX question, not a data-integrity question, and belongs in its own ticket.

