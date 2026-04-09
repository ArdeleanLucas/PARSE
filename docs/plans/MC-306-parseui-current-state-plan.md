# MC-306 — Replace stale ParseUI wiring plan with a current-state execution plan

## Objective
Retire `docs/plans/parseui-wiring-todo.md` as a live execution guide and replace it with one current-state ParseUI plan grounded in `origin/main`, the implemented UI, and the live client/server contract.

## Scope
1. Audit the current `main` code and tests for what is already done in ParseUI.
2. Mark `parseui-wiring-todo.md` as historical/stale rather than deleting it.
3. Create a new plan with only the genuinely open work.
4. Point `parsebuilder-todo.md` at the new plan.
5. Submit a docs-only PR and request review from `TrueNorth49`.

## Working assumptions
- Branch policy comes from `AGENTS.md`: new work starts from `origin/main`; old pivot branches are historical.
- `parseui-wiring-todo.md` is useful as an archive, but no longer safe to execute literally.
- The next open work is not the old annotate/compare wiring list; it is contract reconciliation and verification around actions, compute, decisions, and C5/C6 evidence.

## Completion criteria
- `parseui-wiring-todo.md` clearly labeled historical.
- New `parseui-current-state-plan.md` added.
- `parsebuilder-todo.md` updated to reference the new plan.
- Docs branch committed, pushed, and in PR.
