---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #82 sequence (PR A done as #86, PR B in flight, PR C next) should land first to clear the orchestrator pass
  - This handoff is the next pass after ParseUI.tsx hits ≤1800 (or its floor)
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — TranscriptionLanes.tsx decomposition

**Why this exists:** With PR #82's three-PR orchestrator pass shipping (PR A landed as #86, PR B in flight, PR C queued), ParseUI.tsx will be at or near the ≤1800 LoC target. The next-largest frontend monolith is `src/components/annotate/TranscriptionLanes.tsx` at 943 LoC. Same pattern parse-builder has been using: extract sibling components, lift pure helpers, pair with tests, move ParseUI.tsx-style discipline to the next file.

## Working environment

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo mandatory
```

Per AGENTS.md (PR #74). **Screenshot convention update**: use markdown link `[Screenshot: foo](docs/pr-assets/foo.png)` not inline image embed — see the AGENTS.md screenshot section.

## Goal

Reduce `src/components/annotate/TranscriptionLanes.tsx` from 943 LoC to ≤500 LoC by extracting 3-4 sibling components and any standalone helpers. Behavior must stay byte-equivalent against the live oracle.

## Probable cuts (verify against actual file structure before starting)

Read the file end-to-end first; the names below are plausible based on the symbol structure but the agent should re-derive from the actual file:

- **Lane row component** — the per-lane render block (suspect ~200-250 LoC)
- **Lane header / toolbar** — visibility toggle, color picker integration, label editing (suspect ~120 LoC)
- **Boundary edit affordance** — drag/click handlers for editing boundaries inside a lane (suspect ~150 LoC)
- **STT inline editor** — the in-lane editing UI for STT-suggested intervals (suspect ~100 LoC)
- Standalone helpers (lane sorting, lane-kind dispatch tables) co-located in their own helper file if they're shared with `TranscriptionLanesControls`

Final target file tree under `src/components/annotate/`:

```
TranscriptionLanes.tsx          (orchestrator, ≤500 LoC)
TranscriptionLaneRow.tsx
TranscriptionLaneHeader.tsx
TranscriptionLaneEdit.tsx       (or BoundaryEdit / STTInlineEdit if cleaner split)
laneHelpers.ts                  (if shared standalone helpers exist)
```

Each new file gets a paired `.test.tsx` (or `.test.ts` for helpers).

## Sequence

One PR per extraction. 3-4 PRs total depending on how the file actually splits. Do NOT bundle into one mega-PR — same discipline as the ParseUI.tsx passes.

For each PR, follow the same procedure as the AIChat extraction in PR #61 / Compare helpers in PR #79:

1. Cut the component + its types/constants verbatim into the new file
2. Re-import from `TranscriptionLanes.tsx`
3. Verify no orphaned imports left behind on either side
4. Add a paired test file with one `it()` per scenario (do not collapse multiple scenarios into one test)
5. Run gates: `npm run typecheck`, `npm run test`, `npm run build`, existing `TranscriptionLanes.test.tsx` still green
6. Browser regression: open Annotate, exercise the affected lane behavior; **markdown-link screenshot in PR body** showing the lane in its primary state (not inline embed — see AGENTS.md)

## Scope guardrails

- Do not change `useTranscriptionLanesStore` shape or `LaneKind` union
- Do not change keyboard-routing behavior or hotkey priorities
- Do not change waveform integration (`useWaveSurfer`) or spectrogram overlay (`useSpectrogram`)
- Do not refactor `TranscriptionLanes.test.tsx` itself — let the existing assertions act as a regression net
- Do not touch `LaneColorPicker.tsx` (already separate)
- Do not touch `TranscriptionLanesControls` (already extracted in PR #73)

## Acceptance (cumulative across all 3-4 PRs)

- `wc -l src/components/annotate/TranscriptionLanes.tsx` ≤ 500
- 3-4 new sibling files under `src/components/annotate/`, each ≤350 LoC
- Each new file has a paired test file ≥60 LoC
- All existing tests pass without modification
- Browser regression markdown-link screenshot in each PR body
- Coordinator (parse-gpt) reviews and merges; do not self-merge

## After this lands

The next likely target is `src/components/shared/BatchReportModal.tsx` (843 LoC) using the same pattern. Coordinator will queue it via the next handoff once this lands. Don't plan that here.

## Conventions

- One commit per logical operation
- PR title format: `refactor(annotate): extract <ComponentName> from TranscriptionLanes.tsx`
- Co-author line: `Co-Authored-By: parse-builder <noreply@anthropic.com>`
- Do not merge your own PRs

## Out-of-band notes

- **Refetch before each PR** — main is moving fast; verify `git fetch origin && git rev-parse origin/main` is recent.
- **Screenshot must be a link, not an inline embed** — `[Screenshot: TranscriptionLanes after extract](docs/pr-assets/foo.png)`. Inline `![](url)` 404s in this private repo. AGENTS.md screenshot section has the full convention.
- **Sanity-check your screenshot tool** — recent screenshots have been byte-identical across PRs (same SHA-1), which suggests the tool is capturing a blank/error state. Verify your screenshot actually shows the lane behavior the PR is supposed to be evidencing.
- If you discover `TranscriptionLanes.tsx` contains dead code, flag it in the PR body but do not delete in this task — separate cleanup PR after the extractions land.
