> **Historical (post-cutover 2026-04-27).** The rebuild→canonical cutover is complete and the CI parity step is now a no-op gate; these harness docs remain only as historical reference plus regression-test context.

# PARSE Option 1 sign-off — BND-wave coordinator closeout (2026-04-27)

This file supersedes the earlier draft snapshot for the BND/MCP port wave.

## Audit snapshot

- **Oracle repo / SHA:** `ArdeleanLucas/PARSE` @ `b34578b45f2b972f7a04d44939069ad5684e461c`
- **Rebuild repo / SHA:** `TarahAssistant/PARSE-rebuild` @ `fdd9af7625d349e8c40f47513155f7f135f222bf`
- **Harness fixture:** `saha-2speaker`
- **Merged BND frontend port:** PR #149 — https://github.com/TarahAssistant/PARSE-rebuild/pull/149
- **Merged BND backend/MCP port:** PR #152 — https://github.com/TarahAssistant/PARSE-rebuild/pull/152
- **Dogfood verdict source:** PR #159 / `docs/reports/2026-04-27-rebuild-dogfood-post-fix-verification.md`

## Final harness numbers

### Standard full harness (`all` sections)
- **Harness raw diff count:** `9`
- **Harness allowlist count:** `9`
- **Harness unallowlisted count:** `0`
- **Section mix:** `mcp_tools=8`, `server_boot_smoke=1`
- **Interpretation:** rebuild closes every coordinator-owned parity gap. The remaining raw entries are fully explained by explicit allowlist rules: 8 metadata-only MCP descriptor-copy diffs and 1 accepted oracle-only boot quirk.

### BND feature-contract slice
- **Feature-contract raw diff count:** `0`
- **Feature-contract allowlist count:** `0`
- **Feature-contract unallowlisted count:** `0`
- **Interpretation:** the stale exact-string audit drift is resolved. Rebuild BND/UI + BND/MCP presence now passes against current oracle main.

### MCP-tool triage closeout
- **Real rebuild gaps filed:** `0`
- **Harness artifact diffs closed by fresh MCP fixture isolation:** `32`
- **Metadata-only MCP diffs allowlisted:** `8`
- **Allowlist rules:** `mcp-compute-boundaries-copy-drift`, `mcp-retranscribe-with-boundaries-copy-drift`
- **Interpretation:** rebuild exposes the same BND tools and dry-run contract as oracle; only descriptive copy differs in `python/ai/tools/acoustic_starter_tools.py`.

### Server boot smoke closeout
- **Rebuild script-mode boot:** `PASS`
- **Oracle script-mode boot:** `FAIL` on isolated ports, allowlisted as `oracle-script-boot-bounded-thread-init`
- **Interpretation:** boot-smoke now isolates away local port collisions. The remaining failure is oracle-only (`_BoundedThreadHTTPServer` initializes `_pool` after `super().__init__`, so `server_close()` can run before `_pool` exists). Rebuild is not blocked by it.

## Validation evidence on current branch
- `PYTHONPATH=. python3 -m pytest parity/harness/tests -q` → `21 passed`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --diff-category feature_contracts --output-dir /tmp/parse-bnd-fc-refreshed` → `raw 0`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --diff-category mcp_tools --output-dir /tmp/parse-bnd-mcp-allowlisted` → `raw 8 / allowlisted 8 / unallowlisted 0`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --emit-signoff --output-dir /tmp/parse-bnd-full-final-v3` → `raw 9 / allowlisted 9 / unallowlisted 0`
- `npx vitest run` → `431 passed`
- `./node_modules/.bin/tsc --noEmit` → clean
- `PYTHONPATH=. python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults' python` → `777 passed, 2 deselected`

## Monolith state snapshot

| File | Oracle LoC | Rebuild LoC | Delta | Delta % |
|---|---:|---:|---:|---:|
| `python/server.py` | 9,294 | 1,999 | -7,295 | -78.5% |
| `python/ai/chat_tools.py` | 6,692 | 1,342 | -5,350 | -80.0% |
| `src/ParseUI.tsx` | 5,533 | 2,180 | -3,353 | -60.6% |
| `python/adapters/mcp_adapter.py` | 2,151 | 218 | -1,933 | -89.9% |
| `python/ai/provider.py` | 2,049 | 325 | -1,724 | -84.1% |

## P0 / P1 coverage snapshot

| Surface | Priority | Final status | Notes |
|---|---|---|---|
| Shell / navigation | P0 | `blocked-by-dogfood` | Coordinator parity is clean, but PR #159 still reports real-workspace failures in live thesis use. |
| Annotate core | P0 | `blocked-by-dogfood` | PR #159 reports save → reload regression still failing on real workspace (#143). |
| Compare core | P0 | `blocked-by-dogfood` | Final browser verdict still rides on the same real-workspace dogfood lane. |
| Annotate BND / phonetic-tools UI | P0 | `pass-via-harness` | PR #149 landed the real frontend BND port; refreshed source-audit rules now verify the actual rebuild literals. |
| BND UI gate surfaces (`tiers.ortho_words`, STT word timestamps) | P0 | `pass-via-harness` | Gate checks now match rebuild selectors (`sttHasWordTimestamps`, `bndIntervalCount`) instead of brittle oracle headings. |
| BND / MCP tool surface | P1 | `pass-via-harness` | PR #152 landed the backend foundation; only metadata-copy differences remain and are explicitly allowlisted. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | Historical browser evidence remains authoritative; no BND-wave regression surfaced here. |
| Import / onboarding | P1 | `pass-via-harness` | Shared harness coverage remains green. |
| Compute and report modals | P1 | `blocked-by-dogfood` | Browser-side persistence/UX still depends on the real-workspace dogfood lane. |
| Contact lexeme / CLEF compare extensions | P1 | `pass-via-harness` | Harness covers config/catalog/providers/report plus job lifecycle surfaces. |
| Job diagnostics | P1 | `pass-via-harness` | Harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs`. |
| ~~AI/chat shell~~ | P1 | `dropped` | Out of scope. |

## Coordinator sign-off verdict

- **Harness parity verdict:** `PASS` — coordinator-owned parity baseline is now clean on current rebuild main (`0` unallowlisted diffs).
- **Cutover readiness verdict:** `needs-fixes` — do **not** cut over yet because PR #159 still shows real-workspace dogfood failures (#143 save/reload regression and #154 note-persistence regression). The parity harness is no longer the blocker.
- **Coordinator recommendation:** merge this PR as the final parity/signoff record, then hold cutover until the dogfood blockers in PR #159 are cleared or superseded by a passing real-workspace verification artifact.
