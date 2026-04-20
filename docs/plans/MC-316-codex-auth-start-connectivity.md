# MC-316 — Codex auth start connectivity and proxy verification

## Objective
Determine why PARSE showed `Could not reach the PARSE API for POST /api/auth/start...` during Codex login, verify the real root cause on the canonical repo/runtime, and implement the smallest durable fix if the failure is code-related rather than just a dead dev server.

## Scope
1. Verify the canonical repo/runtime state and current branch/PR context.
2. Inspect the backend auth-start route, frontend auth flow wiring, and Vite proxy configuration.
3. Check live backend/frontend availability on `127.0.0.1:8766` and `127.0.0.1:5173`.
4. Reproduce `POST /api/auth/start` both direct-to-backend and through the Vite proxy/browser path.
5. If a real code bug exists, add failing regression coverage first, then patch minimally.
6. Re-run targeted and full validation; ship on a fresh branch/PR if code changes are required.

## Files likely in scope
- `python/server.py`
- `src/api/client.ts`
- `src/ParseUI.tsx`
- `src/components/annotate/ChatPanel.tsx`
- `vite.config.ts`
- auth-related tests/docs as needed

## Constraints
- Canonical repo only: `/home/lucas/gh/ardeleanlucas/parse`
- Current open PR #64 is for Grok reasoning-effort only; do not mix unrelated auth changes into it.
- PR #62 is already merged; do not push further work to its merged branch.
- Preserve working xAI auth/key flow while checking Codex/OpenAI auth.

## Completion criteria
- Real cause of the `/api/auth/start` reachability error is tool-grounded.
- If code changes are needed, failing tests are written first and pass after the fix.
- `npm run test -- --run` passes.
- `./node_modules/.bin/tsc --noEmit` passes.
- A fresh PR exists if code changes are required.
