# MC-439-B canonical-character integrity report

## Objective
Deliver a backend-only canonical-character audit report and collapse design note for MC-439 without changing export or compute behavior.

## Scope
- Add a pure analysis module and CLI under `python/`.
- Add deterministic pytest coverage using in-repo fixtures only.
- Add `docs/canonical-character-collapse-plan.md` documenting the collapse contract and follow-up MC-439-C design.
- Do not read `/home/lucas/parse-workspace`.
- Do not modify `python/ai/tools/export_tools.py`, `python/compare/cognate_compute.py`, or live export/compute paths unless only a non-behavioral shared helper is proven necessary; default is no changes.

## Grounding steps
1. Verify canonical worktree remote is `git@github.com:ArdeleanLucas/PARSE.git` and branch is `feat/mc-439-b-canonical-character-report`.
2. Verify PR #606 state and inspect its `src/lib/speakerForm.ts` keying behavior for the design doc. If #606 is not merged, document the deviation and avoid depending on its code in this backend PR.
3. Inspect export NCHAR construction in `python/ai/tools/export_tools.py`, numeric id grouping in `python/compare/cognate_compute.py`, and canonical gloss helpers in `python/concept_linking.py`.
4. Inspect existing fixture workspaces and add a minimal audit fixture if needed.

## Implementation plan
1. Write RED tests in `python/test_concept_character_audit.py` for:
   - Class 1 byte-identical duplicate concepts classified as `safe_union`.
   - Class 2 same survey/source-item but differing columns classified as `needs_recluster`.
   - Class 3 cross-survey canonical duplicate classified as `needs_recluster`.
   - Current NCHAR math and projected NCHAR after canonical collapse.
   - Current NCHAR parity with the existing NEXUS/export character-count semantics on a shared fixture.
   - CLI JSON output shape.
2. Implement `python/concept_character_audit.py` with:
   - `audit_canonical_characters(concepts_rows, enrichments) -> AuditReport`.
   - Workspace loaders for `concepts.csv` and `parse-enrichments.json`.
   - Exact export-style current character counting over top-level and manual-override `cognate_sets` with manual precedence.
   - Reuse of `normalize_cross_survey_gloss` / `build_canonical_gloss_index` from `concept_linking` for canonical identity.
   - `python -m concept_character_audit <workspace_dir>` CLI with readable summary and JSON.
3. Write `docs/canonical-character-collapse-plan.md` with the canonical contract, per-id group-letter warning, safe-union vs recluster design, FE key-contract impact, manual override compatibility, and MC-439-C follow-up.
4. Run targeted tests, backend sweep, and ruff.
5. Commit, push, open PR to `ArdeleanLucas/PARSE` with `--base main --label MC-439 --label chore`, then verify base/labels/status.

## Completion criteria
- No export/compute output changes.
- In-repo fixture audit headline numbers are included in the PR body.
- Backend validation and ruff pass.
- One PR is open; Lucas merges, not this agent.
