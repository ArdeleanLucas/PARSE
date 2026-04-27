# 2026-04-27 — BND/MCP port-wave coordinator audit handoff

## Goal
Coordinate the rebuild-side audit/signoff wave for oracle BND/MCP PRs #238-#242 (plus prior relevant oracle PRs #214, #216, #219) under the AGENTS.md PR #148 rule: **grep the actual feature strings on the port PR branch before signoff**.

## Current coordinator PR
- Harness extension PR: https://github.com/TarahAssistant/PARSE-rebuild/pull/150
- Branch: `coordinator/bnd-mcp-port-audit-and-harness`
- Purpose: make the parity harness catch the BND/MCP drift that previously false-greened.

## Current harness evidence
Against fresh oracle current main (`b34578b`, includes oracle PR #242), the new feature-contract harness slice reports:
- `feature_contracts` diff count: **18**
- command:
  ```bash
  PYTHONPATH=. python3 -m parity.harness.runner \
    --oracle /tmp/parse-oracle-current-main \
    --rebuild /home/lucas/gh/worktrees/coordinator-bnd-mcp-audit \
    --diff-category feature_contracts \
    --output-dir /tmp/parse-bnd-feature-contracts-latest
  ```

Interpretation: current rebuild main is still missing the BND/MCP wave, and the harness now exposes that explicitly.

## Port PRs to audit once opened
Expected rebuild lanes:
- parse-back-end: `port/oracle-bnd-mcp-bundle`
- parse-front-end: `port/oracle-bnd-ui-bundle`

As of this note, those PRs were **not open yet**.

## Oracle PR → distinguishing-string audit map

### PR #238 — IPA prefers BND tier
Oracle: https://github.com/ArdeleanLucas/PARSE/pull/238
Use grep strings:
- `ortho_source = "ortho_words"`
- optional corroboration: `tiers.ortho_words`

Primary rebuild search area:
- `python/**/*.py`

### PR #239 — standalone boundaries refresh + Phonetic Tools button
Oracle: https://github.com/ArdeleanLucas/PARSE/pull/239
Use grep strings:
- `def _compute_speaker_boundaries(`
- `Writing tiers.ortho_words`
- `Phonetic Tools`
- `phonetic-refine-boundaries`

Primary rebuild search area:
- backend: `python/**/*.py`
- frontend: `src/**/*.ts*`

### PR #240 — boundary-constrained STT
Oracle: https://github.com/ArdeleanLucas/PARSE/pull/240
Use grep strings:
- `def _compute_speaker_retranscribe_with_boundaries(`
- `"bnd_stt"`
- `phonetic-retranscribe-with-boundaries`

Primary rebuild search area:
- backend: `python/**/*.py`
- frontend: `src/**/*.ts*`

### PR #241 — MCP exposure + UI gate on ortho_words
Oracle: https://github.com/ArdeleanLucas/PARSE/pull/241
Use grep strings:
- `retranscribe_with_boundaries_start`
- `boundary_constrained_stt_job_started`
- `No BND intervals yet for this speaker`
- `tiers.ortho_words`

Primary rebuild search area:
- backend: `python/**/*.py`
- frontend: `src/**/*.ts*`

### PR #242 — standalone boundaries MCP + STT-word-timestamp gate
Oracle: https://github.com/ArdeleanLucas/PARSE/pull/242
Use grep strings:
- `compute_boundaries_start`
- `compute_boundaries_status`
- `boundaries_job_started`
- `phonetic-refine-boundaries`
- `Run STT first`

Primary rebuild search area:
- backend: `python/**/*.py`
- frontend: `src/**/*.ts*`

### Additional prior oracle PRs called out by Lucas
- #214: IPA thread-config stability (not BND-specific, but part of the requested wave context)
- #216: CLEF exact-match doculect IDs
- #219: batch poll disconnect job-id preservation

These should be audited from the oracle diff when the concrete rebuild port PR says it ports them.

## Review command pattern
Run on the **port PR branch worktree**, not on rebuild `main`:

```bash
cd /home/lucas/gh/worktrees/<port-pr-worktree>
grep -rE "<distinguishing-string>" src/ python/
```

## Suggested review-comment structure
```md
PR #148 grep audit for oracle port wave:

- Oracle PR #238: FOUND / MISSING
  - grep: `ortho_source = "ortho_words"`
  - hits: `python/...:<line>`
- Oracle PR #239: FOUND / MISSING
  - grep: `def _compute_speaker_boundaries(`
  - grep: `Phonetic Tools`
  - hits: ...
- Oracle PR #240: FOUND / MISSING
  - grep: `def _compute_speaker_retranscribe_with_boundaries(`
  - grep: `"bnd_stt"`
  - hits: ...
- Oracle PR #241: FOUND / MISSING
  - grep: `retranscribe_with_boundaries_start`
  - grep: `boundary_constrained_stt_job_started`
  - hits: ...
- Oracle PR #242: FOUND / MISSING
  - grep: `compute_boundaries_start`
  - grep: `boundaries_job_started`
  - hits: ...

Signoff: APPROVE only if the distinguishing strings are actually present on this branch.
```

## Post-merge work still queued
After both port PRs merge:
1. rerun
   ```bash
   python -m parity.harness.runner --emit-signoff
   ```
2. update `parity/harness/SIGNOFF.md`
3. update `docs/plans/option1-parity-inventory.md` §12
4. ship superseding scorecard:
   - `docs/reports/2026-04-27-rebuild-progress-scorecard-after-bnd-port.md`

## Local validation already completed for PR #150
- `PYTHONPATH=. python3 -m pytest parity/harness/tests -q`
- `PYTHONPATH=. python3 -m compileall parity/harness`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
