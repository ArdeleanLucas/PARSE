# MC-418-G — Migration verification, idempotence, MCP wrapper, and Fail01 regression

## Objective
Extend the concept suffix pollution migration so it is safe to validate and invoke before the live PARSE workspace migration: verification invariants, idempotence/no-op detection, cross-survey link validation, text-vs-concept_en consistency audit, MCP/chat wrapper, and a full Fail01 8-pattern regression fixture.

## Scope

### In
- `python/migration/concept_suffix_pollution.py`
- `python/scripts/migrate_concept_suffix_pollution.py`
- `python/ai/tools/migration_tools.py`
- MCP/chat tool registry files discovered from current implementation
- `python/ai/tools/test_migration_tools.py`
- `tests/migration/test_idempotence.py`
- `tests/migration/test_verification.py`
- `tests/migration/test_fail01_regression.py`
- `tests/migration/fixtures/issue_529_full/`

### Out
- No live `/home/lucas/parse-workspace` mutation.
- No allocator/route/production concept helper changes outside the additive migration/MCP surface.
- No browser, screenshots, or `parse-run`.

## Implementation plan
1. Inspect the MC-418-F migration module, CLI, and AI tool registration pattern on current `origin/main`.
2. Add RED tests first:
   - already-canonical migration no-op with no backups/writes;
   - verification violations for suffix/prefix/orphan/tag references;
   - cross-survey wrong-target validation;
   - text-vs-concept_en inconsistency audit;
   - full Fail01 synthetic fixture with 8 polluted IDs merged to canonical IDs;
   - MCP wrapper happy path and bad-workspace path.
3. Implement additive migration APIs:
   - `MigrationResult.already_canonical` marker;
   - `is_already_canonical(workspace)`;
   - `verify_post_migration(workspace)`;
   - `validate_cross_survey_links(workspace)`;
   - `audit_text_vs_concept_en(workspace)`;
   - post-migration result verification fields and idempotence no-op path.
4. Extend CLI with `--verify-only` and distinct already-canonical output.
5. Add `python/ai/tools/migration_tools.py` using the existing `ChatToolSpec` + `TOOL_FUNCTIONS` pattern and register it in the current tool registry.
6. Validate with targeted pytest, isolated MCP HTTP smoke on port 18766, selected ruff, and full backend sweep.
7. Commit, push, open PR `[MC-418-G] feat: migration verification + idempotence + MCP wrapper + Fail01 regression` with labels `MC-418`, `feat`, `backend`, `scripts`, base `main`, and do not merge.

## Completion criteria
- All new tests pass.
- `pytest tests/migration/ -x` passes.
- `pytest python/ai/tools/test_migration_tools.py -x` passes.
- Isolated MCP tool list/call smoke proves `migrate_concept_suffix_pollution` is exposed.
- `uvx ruff check python/ --select E9,F63,F7,F82` passes.
- `PYTHONPATH=python python3 -m pytest python/ -q` passes before push.
- PR is open against `ArdeleanLucas/PARSE:main`, labeled correctly, and not merged.
