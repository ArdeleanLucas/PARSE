# MC-347 — ORTH rerun pad selector

## Objective
Add a three-option pad selector to the existing lexeme rerun confirmation dialog and type the frontend request contract for `pad?: 0.0 | 0.2 | 0.5`.

## Contract
- Backend default: `0.2` when `pad` is absent.
- Allowed values: exactly `{0.0, 0.2, 0.5}`.
- Frontend API contract must pass provided values through unchanged.
- UI default selection is `0.2`, but the default is omitted from the request body so the backend default remains the single source on the wire; non-default selections are included.
- Both ORTH and IPA rerun endpoints accept the same field.

## Scope
- `src/api/contracts/annotation-data.ts`
- `src/api/client.test.ts`
- `src/components/annotate/annotate-views/AnnotateView.tsx`
- `src/components/annotate/AnnotateView.test.tsx`

## Test-first plan
1. Add API contract tests for ORTH provided pad, ORTH omitted pad, and IPA provided pad.
2. Add AnnotateView dialog tests for three pills/default state, dispatching selected non-default pad, and reset after close/reopen.
3. Run those tests against `origin/main` to capture RED.
4. Implement minimal typed contract and UI state/selector.
5. Run focused GREEN, then full validation gates.

## Validation gates
- `npx vitest run src/api/client.test.ts src/components/annotate/AnnotateView.test.tsx`
- `npx vitest run`
- `./node_modules/.bin/tsc --noEmit`
- `npm run build`
- `git diff --check`
- `PYTHONPATH=python python3 -m pytest -q` (paranoid no-op backend gate)
