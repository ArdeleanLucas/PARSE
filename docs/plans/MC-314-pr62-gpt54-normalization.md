# MC-314 — PR #62 GPT 5.4 normalization hardening

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


## Objective
Finish the final pre-merge pass for PR #62 by eliminating remaining legacy `gpt54` placeholder paths and making the canonical OpenAI default model `gpt-5.4` across active PARSE chat/provider configuration surfaces.

## Scope
1. Inspect the current PR branch and targeted failing tests.
2. Normalize legacy `gpt54` placeholders to `gpt-5.4` in the backend config/runtime path without regressing xAI provider remapping.
3. Update active example config defaults if they still advertise stale OpenAI defaults.
4. Re-run targeted Python tests plus full PARSE frontend gates.
5. Confirm PR #62 state and record merge-readiness evidence.

## Files
- `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`)
- `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
- `python/test_server_chat_policy.py`
- `config/ai_config.example.json`
- PR #62 metadata if visible behavior changes

## Constraints
- Use the canonical repo: `/home/lucas/gh/ardeleanlucas/parse`
- Keep the fix minimal and targeted.
- Preserve explicit OpenAI model selections such as `o3`.
- Preserve xAI direct-key override behavior and xAI default model routing.
- Do not touch C7 cleanup or protected Compare surfaces.

## Completion criteria
- `pytest python/test_server_chat_policy.py -q` passes.
- `npm run test -- --run` passes.
- `./node_modules/.bin/tsc --noEmit` passes.
- No active OpenAI default/model placeholders remain as `gpt54` in runtime config paths for this PR scope.
- PR #62 has a clean follow-up commit (if code changed) and a precise merge-readiness summary.
