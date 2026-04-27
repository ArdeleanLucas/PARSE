# PR #149 scope investigation — 2026-04-27

## Question
Did `TarahAssistant/PARSE-rebuild#149` actually deliver the frontend BND/UI port, or did it repeat the earlier "claimed already present" pattern?

## PR snapshot
- **PR:** `#149` — `port: oracle BND UI bundle (frontend half)`
- **URL:** https://github.com/TarahAssistant/PARSE-rebuild/pull/149
- **State:** `MERGED`
- **Merged at:** `2026-04-27T12:39:10Z`
- **Branch:** `port/oracle-bnd-ui-bundle`
- **Base SHA at review:** `1cfc318be20ce43d27c0478543d637828e9dc0f2`
- **Head SHA:** `28987b621421b0bd06cafa5e0b89280669a80b22`

## Changed files
- `docs/pr-assets/oracle-bnd-port.png`
- `src/ParseUI.test.tsx`
- `src/ParseUI.tsx`
- `src/api/types.ts`
- `src/components/annotate/TranscriptionLaneRow.tsx`
- `src/components/annotate/TranscriptionLanes.tsx`
- `src/stores/transcriptionLanesStore.ts`

## Oracle mapping claimed by PR #149
From the merged PR body:
- oracle `#239` — standalone boundaries refresh UI
- oracle `#241` — BND-STT UI gate on `tiers.ortho_words`
- oracle `#242` — `compute_boundaries` UI gate on STT word timestamps
- dependent oracle `#240` UI surface — `Re-run STT with Boundaries`

## Distinguishing-string evidence

### Direct diff hits from PR #149
`gh pr diff 149 --repo TarahAssistant/PARSE-rebuild | grep -nE 'Phonetic Tools|compute_boundaries_standalone|phonetic-refine-boundaries|phonetic-retranscribe-with-boundaries|bnd_stt|tiers\.ortho_words|compute_boundaries'`

Observed hits:
- `phonetic-refine-boundaries` — present in diff (`src/ParseUI.tsx`, `src/ParseUI.test.tsx`)
- `phonetic-retranscribe-with-boundaries` — present in diff (`src/ParseUI.tsx`, `src/ParseUI.test.tsx`)
- `Phonetic Tools` — **not** copied literally
- `compute_boundaries_standalone` — **not** copied literally
- `bnd_stt` — **not** copied literally in frontend files

### Current main code evidence after merge
Current rebuild main (`6a55178da264794a60d1f2de32fc9daab9baef94`) contains:
- `src/ParseUI.tsx`
  - `data-testid="phonetic-refine-boundaries"`
  - `data-testid="phonetic-retranscribe-with-boundaries"`
  - `sttHasWordTimestamps` gate for standalone BND refresh
  - `bndIntervalCount` gate for BND-constrained STT
  - rendered labels:
    - `Refine Boundaries (BND)`
    - `Re-run STT with Boundaries`
- `src/ParseUI.test.tsx`
  - disabled/enabled coverage for STT word-timestamp gate
  - disabled/enabled coverage for `tiers.ortho_words` existence gate
- `src/components/annotate/TranscriptionLanes.tsx`
  - persisted BND lane already targets `tiers.ortho_words`

### Harness follow-up evidence
Current current-main BND feature-contract rerun:
```bash
PYTHONPATH=. python3 -m parity.harness.runner \
  --oracle /home/lucas/gh/ardeleanlucas/parse \
  --rebuild . \
  --fixture saha-2speaker \
  --diff-category feature_contracts \
  --output-dir /tmp/parse-bnd-feature-contracts-current-main
```

Result:
- **feature-contract diff count:** `4`

The remaining four diffs are **not missing frontend port code**. They are stale exact-string audits:
- oracle has literal `Phonetic Tools`; rebuild renders the two BND buttons without copying that section-heading string verbatim
- oracle has exact `ortho_source = "ortho_words"`; rebuild current-main uses the equivalent single-quoted implementation in `python/server_routes/annotate.py`

## Verdict
**A — PR #149 *is* the frontend BND port and it really ports the features.**

It changed the exact `src/` surfaces expected for the BND UI wave, added both buttons (`phonetic-refine-boundaries`, `phonetic-retranscribe-with-boundaries`), and added the real gate behavior tied to STT word timestamps and `tiers.ortho_words` presence. The remaining harness diffs are now a coordinator/harness issue, not a missing frontend-port issue: the current `feature_contracts` audit still relies on overly literal oracle string matching instead of rebuild-equivalent modular/UI evidence.

## Coordinator implication
Do **not** queue parse-front-end on a fresh BND/UI port task. The correct next coordinator task is to refresh the harness source-audit rules so the BND wave can sign off cleanly against the already-merged PR #149 + PR #152 state.
