# parse-builder next task — original UI parity audit and correction pass

## Goal

Audit the React PARSE frontend against the original workstation and correct any visual, structural, or interaction drift so the React UI stays **identical to the original**, not a re-imagined redesign.

## Hard product rule

- **No UI re-imagining.**
- The original UI is the spec.
- Match the original layout, labels, ordering, panel structure, control grouping, and interaction flow unless a deviation is strictly required for a proven technical reason.
- If you believe a deviation is necessary, keep it minimal, justify it in the PR body, and prefer behavior-preserving implementation under the hood over visible change.

## Source of truth

Use the original PARSE implementation at:
- `/home/lucas/gh/ardeleanlucas/parse`

Check at minimum:
- `parse.html`
- `compare.html`
- `js/annotate/*`
- `js/compare/*`
- relevant shared CSS / structural markup / control labels

## Why this is the right task now

- Lucas explicitly clarified that the React PARSE UI should be identical to the original and that any UI reinvention is unacceptable.
- Current rebuild `origin/main` is `0d78bb8` (`test(compare): harden compute semantics regressions (#28)`).
- There are already narrow implementation PRs open for non-visual cleanup:
  - PR `#27` — `fix(compare): use typed CLEF client in BorrowingPanel`
  - PR `#29` — `fix(config): wire configStore update to typed client`
- Those lanes should stay narrow. The parity audit / correction pass should be a separate Builder implementation PR if any actual drift is found.

## Specific task

Perform a parity audit of the React shell and correct only real drift from the original.

### Required audit surfaces
1. `src/ParseUI.tsx`
2. annotate-mode layout/components
3. compare-mode layout/components
4. shared shell chrome, panel ordering, labels, and control affordances
5. any recently touched UI surfaces that may have drifted from the original workstation

### Required implementation behavior
1. Compare current React UI against the original workstation files listed above.
2. Identify any visible or interaction-level drift.
3. Revert or correct that drift.
4. Keep non-visual refactors and typed-client cleanup separate from this parity pass.
5. Do **not** add new chrome, restyle panels, rename controls, reshape workflows, or otherwise modernize the UI.

## In scope

- `src/ParseUI.tsx`
- relevant `src/components/annotate/*`
- relevant `src/components/compare/*`
- relevant shared UI components if needed for strict parity
- parity-focused tests / snapshots / browser verification notes

## Out of scope

- backend route changes unless required for a proven parity bug and separately justified
- `python/server.py` backend refactors
- expanding PR `#27` or `#29` into UI redesign work
- product redesign, visual refresh, or speculative UX improvement

## Validation requirements

Run and report at least:
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

Also include in the implementation PR:
- a concise original-vs-React parity checklist
- confirmation that the UI stayed aligned with the original
- explicit note of any unavoidable deviation and why

## Academic / fieldwork considerations

- PARSE is a fieldwork workstation; interface stability matters for annotation speed, reviewer trust, and cross-session reproducibility.
- Linguistic users depend on consistent panel structure and control placement while working through timestamped speech data and cognate adjudication.
- A visual redesign creates unnecessary cognitive cost without improving the data pipeline.

## Reporting requirements

Open a fresh Builder implementation PR from current `origin/main` if drift is found.

In the PR body, include:
- which original files were used as the parity reference
- exact UI drift corrected
- confirmation that no UI re-imagining was introduced
- exact tests run
