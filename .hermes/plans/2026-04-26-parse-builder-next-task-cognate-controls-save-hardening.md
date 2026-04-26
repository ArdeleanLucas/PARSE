# parse-builder next prompt — original UI parity audit of current React work

## Goal

Audit the current React PARSE frontend against the original workstation and correct any visible, structural, or interaction drift. The React UI must remain **identical to the original PARSE UI**.

## Hard rule

- **No UI re-imagining.**
- The original UI is the spec.
- Do not redesign layout, rename controls, modernize chrome, restyle panels, or reshape workflows.
- If a visible deviation already exists, correct it back toward the original.

## Source of truth

Use the original implementation at:
- `/home/lucas/gh/ardeleanlucas/parse`

Audit against at least:
- `parse.html`
- `compare.html`
- `js/annotate/*`
- `js/compare/*`
- any shared structure/labels/control ordering those files define

## What to audit now

Start with the currently visible frontend lanes and touched surfaces:
- PR #27 — `fix(compare): use typed CLEF client in BorrowingPanel`
- PR #29 — `fix(config): wire configStore update to typed client`
- `src/ParseUI.tsx`
- relevant annotate/compare/shared components affected by the React shell

## Required task

1. Compare the current React UI against the original workstation.
2. Determine whether PR #27 or PR #29 introduce any visible/layout/interaction drift.
3. Determine whether current main already contains any drift that needs correction.
4. If drift is found, open a fresh Builder implementation PR from current `origin/main` that corrects the drift.
5. If no drift is found in PR #27 / #29, explicitly report that they are under-the-hood only and safe with respect to UI parity.

## In scope

- React frontend parity audit
- minimal parity corrections if needed
- parity-focused tests / notes / screenshots if helpful

## Out of scope

- backend refactors
- product redesign
- speculative UX improvement
- widening PR #27 or #29 into unrelated UI work unless a true parity bug is found

## Validation requirements

Run and report at least:
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Reporting requirements

In your implementation PR or report, include:
- which original files you used as the parity reference
- whether PR #27 is UI-parity-safe
- whether PR #29 is UI-parity-safe
- exact drift found, if any
- confirmation that no UI re-imagining was introduced
- exact tests run
