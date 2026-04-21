# B8 — useComputeJob

> **Archived Oda Track B task brief (2026-04-21):** this file is historical implementation scaffolding from the Compare-track React pivot. Do **not** execute it as a live task. Current PARSE work branches from `origin/main`, and the landed Compare code lives in `src/components/compare/`, `src/hooks/`, and `AGENTS.md`.

**Model:** gemini-2.5-flash
**Output:** `src/hooks/useComputeJob.ts` + `useComputeJob.test.ts`
**Used by:** EnrichmentsPanel (B5)

---

## What It Is

Manages the full lifecycle of a phonetic compute job for one speaker.
Called by EnrichmentsPanel when the user clicks [Run Compute].

---

## Interface

```typescript
interface ComputeJobState {
  status: 'idle' | 'running' | 'complete' | 'error';
  progress: number;      // 0.0 – 1.0
  error: string | null;
}

export function useComputeJob(speaker: string) {
  const start: () => Promise<void>
  const state: ComputeJobState
  return { start, state }
}
```

---

## Lifecycle

1. `start()` → calls `startCompute(speaker)` from `client.ts` → receives `{ job_id }`
2. Set `status = 'running'`
3. Poll `pollCompute(speaker, jobId)` every 1000ms
4. Each poll → update `progress` from response
5. When response `status === 'complete'` → stop polling, call `enrichmentStore.load()`,
   set `status = 'complete'`
6. When response `status === 'error'` → stop polling, set `status = 'error'`,
   set `error` from response message
7. Cleanup: clear polling interval on component unmount

---

## Rules

- Use `setInterval` + `clearInterval`. Clean up in a `useEffect` return function.
- Never call `pollCompute` after `status` reaches `complete` or `error`.
- `enrichmentStore.load()` is called automatically on complete — EnrichmentsPanel
  does not need to call it separately.

---

## Required Tests

```typescript
describe('useComputeJob', () => {
  it('sets status to running after start() is called', async () => { ... })
  it('sets status to complete when poll returns complete', async () => { ... })
  it('calls enrichmentStore.load() on complete', async () => { ... })
  it('sets status to error when poll returns error', async () => { ... })
  it('clears polling interval on unmount', async () => { ... })
})
```

Run: `npm run test -- useComputeJob`
Expected: 5 passed, 0 failed.
