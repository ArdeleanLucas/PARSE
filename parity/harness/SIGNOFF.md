# PARSE Option 1 sign-off prep — BND-wave draft (2026-04-27)

> **DRAFT ONLY — not a final coordinator sign-off.**
> This file is pre-staged for the final BND-wave closeout. PR #149 (frontend) and PR #152 (backend) are both merged; remaining coordinator work is a harness refresh/rerun plus final real-workspace dogfood evidence.

## Audit snapshot

- **Oracle repo / SHA:** `ArdeleanLucas/PARSE` @ `b34578b45f2b972f7a04d44939069ad5684e461c`
- **Rebuild repo / SHA:** `TarahAssistant/PARSE-rebuild` @ `6a55178da264794a60d1f2de32fc9daab9baef94`
- **Harness fixture:** `saha-2speaker`
- **Merged BND frontend port:** PR #149 — https://github.com/TarahAssistant/PARSE-rebuild/pull/149
- **Merged BND backend/MCP port:** PR #152 — https://github.com/TarahAssistant/PARSE-rebuild/pull/152
- **PR #149 investigation verdict:** `A` — real frontend port, not a false claim (`docs/reports/2026-04-27-pr149-scope-investigation.md`)

## Current pre-final numbers

### Standard full harness (`all` sections)
- **Harness raw diff count:** `42`
- **Harness allowlist count:** `0`
- **Harness unallowed count:** `42`
- **Section mix:** `mcp_tools=40`, `server_boot_smoke=2`
- **Interpretation:** this is not the BND-wave blocker number; it is the current report-only full harness state on this machine and still needs a clean final rerun before cutover sign-off.

### BND feature-contract slice
- **Feature-contract raw diff count:** `4`
- **Feature-contract allowlist count:** `0`
- **Feature-contract unallowed count:** `4`
- **Interpretation:** the old `16`-diff BND gap has narrowed to `4` after PR #149 + PR #152 merged. The remaining four diffs are stale exact-string source-audit mismatches (`Phonetic Tools` heading literal and double-quoted `ortho_source = "ortho_words"`), not missing frontend/backend BND code.

## Validation evidence on current main
- `PYTHONPATH=. python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults' python` → `777 passed, 2 deselected`
- `npx vitest run` → `431 passed`
- `./node_modules/.bin/tsc --noEmit` → clean
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --output-dir /tmp/parse-bnd-final-signoff-full-harness` → `raw 42`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --diff-category feature_contracts --output-dir /tmp/parse-bnd-feature-contracts-current-main` → `raw 4`

## Post-refresh placeholders
- **Final full-harness raw diff count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final full-harness allowlist count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final full-harness unallowed count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final BND feature-contract diff count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final real-workspace dogfood verdict:** `<!-- TBD post parse-front-end dogfood rerun -->`
- **Final cutover readiness verdict:** `<!-- TBD after both items above are complete -->`

## Coordinator reading of the BND wave
- **Frontend BND/UI port:** landed via PR #149.
- **Backend/MCP BND port:** landed via PR #152.
- **Remaining coordinator blocker for BND parity:** refresh `feature_contracts.source_audit` so rebuild-equivalent evidence passes instead of being judged by overly literal oracle strings.
- **Separate cutover blocker outside the BND port itself:** fresh real-workspace browser dogfood still needs to land and pass.

## Coordinator sign-off
- **Lucas:** ______________________________
- **Date:** ______________________________
- **Decision:** `<!-- TBD post coordinator rerun -->`
