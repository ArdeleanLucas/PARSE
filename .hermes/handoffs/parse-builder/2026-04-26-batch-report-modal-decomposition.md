---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - TranscriptionLanes sequence from handoff #90 should complete first (PR A #97 shipped, PRs B/C/D in flight)
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — BatchReportModal.tsx decomposition

**Why this exists:** TranscriptionLanes is in flight via handoff #90. Next-largest frontend monolith is `src/components/shared/BatchReportModal.tsx` at 843 LoC. Same per-component-extraction discipline parse-builder has been using since PR #61.

## Working environment

Same rule. AGENTS.md PR #74 + screenshot link convention from PR #89 + screenshot SHA256 verification (your discipline on PR #97 is the standard now).

## Goal

Reduce `src/components/shared/BatchReportModal.tsx` from 843 LoC to ≤450 LoC by extracting 2-3 sibling components and any standalone helpers. Behavior must stay byte-equivalent against the live oracle.

## Probable cuts (verify against actual file before starting)

Read the file end-to-end first. Names below are best-guess from typical batch-report patterns:

- **Per-step row component** — the expandable row for each pipeline step (suspect ~150-200 LoC)
- **Traceback expansion panel** — the error/traceback display when a step fails (suspect ~100 LoC)
- **Summary header / status pill** — the top-of-modal aggregate state (suspect ~80 LoC)
- Standalone helpers (status formatting, duration formatting) — `src/lib/batchReportHelpers.ts` if needed

Final target tree under `src/components/shared/`:

```
BatchReportModal.tsx              (orchestrator, ≤450 LoC)
BatchReportRow.tsx                (per-step row + paired test)
BatchReportTraceback.tsx          (or BatchReportError.tsx — verify naming)
BatchReportSummary.tsx            (or co-locate in BatchReportModal if small)
batchReportHelpers.ts             (lib, if shared with other batch consumers)
```

## Sequence

2-3 PRs total depending on actual file structure. Same procedure as PR #97:

1. Re-derive line numbers via grep (do NOT trust this prompt's line numbers)
2. Cut verbatim, add `export`
3. Update `BatchReportModal.tsx` imports
4. Add paired test file with one `it()` per scenario; hoisted-mock pattern from `parse-vitest-hoisted-store-mocks` skill
5. Run gates: typecheck, test, build, existing `BatchReportModal.test.tsx` still green
6. Browser regression: trigger a batch run, open the report modal, expand a row, screenshot in markdown-link form per AGENTS.md
7. Verify screenshot SHA256 differs from prior PR's screenshot (your PR #97 verification pattern is now the standard)

## Scope guardrails

- Do not change `useBatchPipelineJob` shape or hook contract
- Do not change the modal's prop signature (callers in ParseUI.tsx and elsewhere depend on it)
- Do not refactor `BatchReportModal.test.tsx` itself — let existing assertions act as regression net
- Out of scope: `TranscriptionRunModal.tsx` (792 LoC, separate handoff later)

## Acceptance (cumulative across all 2-3 PRs)

- `wc -l src/components/shared/BatchReportModal.tsx` ≤ 450
- 2-3 new sibling files under `src/components/shared/`, each ≤300 LoC, each with paired test ≥50 LoC
- Browser screenshot per PR (markdown link, SHA256 verified distinct from prior PRs)
- All existing tests pass without modification

## After this lands

Coordinator will queue next monolith — likely `TranscriptionRunModal.tsx` (792) or `annotationStore.ts` (753). Don't plan that here.
