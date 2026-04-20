# MC-315 — Grok reasoning-effort compatibility fix

## Objective
Fix PARSE AI chat so Grok/xAI requests do not send a `reasoningEffort` / `reasoning_effort` parameter to models that reject it, while preserving OpenAI reasoning-effort behavior where supported.

## Scope
1. Inspect the current canonical PARSE repo and locate every active chat/runtime path that injects `reasoning_effort`.
2. Reproduce the incompatibility with a failing regression test before changing production code.
3. Implement the smallest backend fix that suppresses unsupported reasoning-effort parameters for xAI/Grok chat models.
4. Re-run targeted Python tests plus full PARSE frontend gates.
5. Deliver the fix on a fresh post-merge branch, update PR metadata if needed, and log the outcome.

## Files likely in scope
- `python/ai/provider.py`
- `python/server.py`
- `python/test_server_chat_policy.py`
- `config/ai_config.example.json` only if policy defaults need clarification

## Constraints
- Canonical repo only: `/home/lucas/gh/ardeleanlucas/parse`
- PR #62 is already merged; do not push further work to its merged branch
- Keep the fix minimal and targeted
- Preserve explicit OpenAI model selections and any supported OpenAI reasoning-effort behavior
- Preserve xAI provider routing and model normalization already fixed in PR #62

## Completion criteria
- A regression test fails first for the unsupported Grok/xAI reasoning-effort path
- Targeted Python regressions pass after the fix
- `npm run test -- --run` passes
- `./node_modules/.bin/tsc --noEmit` passes
- New branch/PR exists if code changes are required
