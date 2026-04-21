# PR: Wire Actions menu job lifecycle — progress, polling, error UI

> **Archived historical plan (2026-04-21):** this PR brief documents a completed slice from the ParseUI integration era. Keep it as implementation history only. For current branch policy, validation policy, and the live contract table, use `AGENTS.md`; for live ParseUI execution priorities, use `docs/plans/parseui-current-state-plan.md`.

**Branch:** `feat/actions-job-lifecycle` → `main`
**Reviewer:** TrueNorth49
**Gate:** Pre-C5/C6 — no destructive changes, no legacy removal
**Depends on:** PR #37 (Tailwind CSS import fix — merged)

---

## Problem

The Actions dropdown in `ParseUI.tsx` currently **fire-and-forget** every processing job:

```tsx
// Current pattern — no progress, no polling, console-only errors
void startNormalize(speaker).catch(err => console.error('[ParseUI] normalize failed:', err));
void startSTT(speaker, `${speaker}.wav`, 'ckb').catch(err => console.error('[ParseUI] STT failed:', err));
void startCompute('ipa_only').catch(err => console.error('[ParseUI] IPA compute failed:', err));
void startCompute('full_pipeline').catch(err => console.error('[ParseUI] Full pipeline failed:', err));
void startCompute('contact-lexemes').catch(err => console.error('[ParseUI] Cross-speaker match failed:', err));
```

**What's wrong:**
1. **No progress UI** — user clicks "Run Audio Normalization" and sees nothing; no spinner, no bar, no status
2. **No polling** — the typed client already has `pollNormalize()`, `pollSTT()`, `pollCompute()` but the Actions menu doesn't use them
3. **Console-only errors** — failures log to `console.error`, invisible to the user
4. **No disable-while-running** — user can re-fire the same action while a job is in-flight
5. **Inconsistent pattern** — the Compute panel at bottom *does* use `useComputeJob` with progress/error UI, but the Actions dropdown doesn't use the same model

The typed client surface and server endpoints are **already complete** (PR #33 closed all contract gaps). The infrastructure is there — the Actions menu just doesn't use it.

---

## Solution

### 1. Extract a generic `useActionJob` hook

Generalize the existing `useComputeJob` pattern into a reusable `useActionJob` hook that works for **any** async job with polling:

**New file:** `src/hooks/useActionJob.ts`

```ts
export interface ActionJobState {
  status: 'idle' | 'running' | 'complete' | 'error';
  progress: number;  // 0.0–1.0
  error: string | null;
  label: string | null;  // e.g. "Normalizing audio…", "Running STT…"
}

export function useActionJob(config: {
  start: () => Promise<{ job_id: string }>;
  poll: (jobId: string) => Promise<{ status: string; progress?: number; error?: string; message?: string }>;
  label: string;
  onComplete?: () => void | Promise<void>;
  pollIntervalMs?: number;  // default 1000
}): {
  state: ActionJobState;
  run: () => Promise<void>;
  reset: () => void;
}
```

**Design rules:**
- Same polling loop / interval / cleanup logic as the proven `useComputeJob`
- `onComplete` callback for side-effects (e.g. reload enrichments, reload annotations)
- Exposed `reset()` to clear error state
- Cleanup on unmount via `useEffect` teardown (same as `useComputeJob` already does)
- Normalize `progress` values > 1 to 0–1 range (same helper already in `useComputeJob`)

### 2. Refactor `useComputeJob` to use `useActionJob` internally

`useComputeJob` becomes a thin wrapper:

```ts
export function useComputeJob(computeType: string) {
  const loadEnrichments = useEnrichmentStore((s) => s.load);
  return useActionJob({
    start: () => startCompute(computeType),
    poll: (jobId) => pollCompute(computeType, jobId),
    label: `Computing ${computeType}…`,
    onComplete: loadEnrichments,
  });
}
```

Existing Compute panel behavior and tests are preserved — just backed by the new hook.

### 3. Wire each Actions menu item through `useActionJob`

Each processing action gets its own `useActionJob` instance in the `TopBar` component:

| Action | start | poll | onComplete |
|---|---|---|---|
| **Audio Normalization** | `startNormalize(speaker)` | `pollNormalize(jobId)` | reload annotation |
| **Orthographic STT** | `startSTT(speaker, wav, lang)` | `pollSTT(jobId)` | reload annotation |
| **IPA Transcription** | `startCompute('ipa_only')` | `pollCompute('ipa_only', jobId)` | reload enrichments |
| **Full Pipeline** | `startCompute('full_pipeline')` | `pollCompute('full_pipeline', jobId)` | reload enrichments |
| **Cross-Speaker Match** | `startCompute('contact-lexemes')` | `pollCompute('contact-lexemes', jobId)` | reload enrichments |

### 4. Add a topbar action status indicator

Replace the silent fire-and-forget with a visible inline status bar in the topbar, below or beside the Actions dropdown:

```
┌──────────────────────────────────────────────────────────────┐
│  ▸ Actions ▾                                                 │
│  ┌─ Running Audio Normalization… ████████░░░░ 68% ─────────┐ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**States:**
- **idle** — nothing shown
- **running** — label + progress bar + percentage
- **complete** — brief "✓ Done" flash (auto-dismiss after 3s)
- **error** — red error message + "Retry" / "Dismiss" buttons

**Multiple concurrent jobs:** If more than one action is running, stack them vertically or show a summary count with expandable detail.

### 5. Disable buttons while their job is in-flight

Each Actions menu button checks its corresponding `useActionJob` state:

```tsx
<button
  onClick={normalizeJob.run}
  disabled={normalizeJob.state.status === 'running'}
  className={...}
>
  <AudioLines className="h-3.5 w-3.5 text-slate-400"/>
  {normalizeJob.state.status === 'running' ? 'Normalizing…' : 'Run Audio Normalization'}
</button>
```

### 6. Reset Project confirmation tightening

The current Reset Project handler directly calls `setState` on multiple stores inline. This PR:
- Wraps it in a dedicated `resetProject()` function
- Clears any in-flight action job state on reset
- Keeps the existing `window.confirm` guard

---

## Files changed

| File | Change |
|---|---|
| `src/hooks/useActionJob.ts` | **New** — generic async job hook with polling |
| `src/hooks/useActionJob.test.ts` | **New** — unit tests for the hook |
| `src/hooks/useComputeJob.ts` | Refactor to thin wrapper over `useActionJob` |
| `src/hooks/useComputeJob.test.ts` | Verify existing tests still pass unchanged |
| `src/ParseUI.tsx` | Replace fire-and-forget Actions handlers with `useActionJob` instances; add status indicator |
| `src/ParseUI.test.tsx` | Add regression tests for action status + disable-while-running |
| `src/api/types.ts` | No changes expected — existing types cover all job shapes |
| `src/api/client.ts` | No changes expected — all poll/start functions already exist |

---

## What this PR does NOT do

- **No new server endpoints** — all start/poll routes already exist and are verified
- **No changes to `python/server.py`** — server contract is complete (PR #33)
- **No changes to Compare components** — per AGENTS.md "Do Not Touch" list
- **No decisions persistence changes** — that's a separate follow-up (Priority 3)
- **No C7 cleanup / legacy deletion** — blocked until C5+C6 signoff
- **No new dependencies** — pure React hooks + existing Tailwind classes

---

## Test plan

### Automated
```bash
npm run test -- --run        # must stay >= 119 passing (expect ~125+ with new tests)
npm run check                # tsc --noEmit clean
```

### New test coverage

1. **`useActionJob` unit tests:**
   - idle → running → complete lifecycle
   - idle → running → error lifecycle
   - progress normalization (0–1 and 0–100 inputs)
   - cleanup on unmount cancels polling
   - `onComplete` callback fires on success
   - `reset()` returns to idle
   - concurrent start calls don't stack (guard against double-click)

2. **`useComputeJob` regression:**
   - Existing test file passes without modification (refactor is internal)

3. **`ParseUI` regression:**
   - Actions menu renders all action buttons
   - Clicking "Run Audio Normalization" shows running state in topbar
   - Button is disabled while job is running
   - Error state shows retry option
   - Reset Project clears action job states

### Manual browser verification
- Start normalize on a speaker → confirm progress bar appears and updates
- Trigger STT → confirm progress, then verify annotation reloads on complete
- Fire two actions simultaneously → confirm both show progress independently
- Kill the Python server mid-job → confirm error surfaces in the UI, not just console
- Reset Project while a job is running → confirm clean state

---

## Execution order

1. Write `useActionJob` hook + tests (RED/GREEN)
2. Refactor `useComputeJob` → wrapper; verify existing tests pass
3. Wire Actions menu handlers one-by-one (normalize → STT → IPA → pipeline → cross-speaker)
4. Add topbar status indicator component
5. Add disable-while-running to each button
6. Tighten Reset Project
7. Full test suite + typecheck
8. Push, open PR, request TrueNorth49

---

## Acceptance criteria

- [ ] No Actions menu item uses `console.error` as the only failure path
- [ ] Every processing action shows visible progress in the UI
- [ ] Every processing action shows visible errors in the UI (not just console)
- [ ] Buttons are disabled while their corresponding job is in-flight
- [ ] `useComputeJob` existing behavior and tests are preserved
- [ ] `npm run test -- --run` >= 119 passing, `npm run check` clean
- [ ] No changes to `python/server.py`, `src/api/client.ts`, or compare components

---

## Relation to roadmap

This is **Priority 2** from the post-PR #37 cleanup assessment, and **§3 of the current-state execution plan** (`docs/plans/parseui-current-state-plan.md`).

After this merges, the next steps are:
- **Priority 3:** Decisions persistence unification (§4 of current-state plan)
- **Priority 4:** C5/C6 evidence collection (§6 of current-state plan)
