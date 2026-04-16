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
