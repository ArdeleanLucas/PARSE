# PR #38 — Dispatch Specs for parse-gpt

All specs for the 4 `opencode_task` dispatches. Opus-authored, parse-gpt executes.

---

## Spec 1A: `useActionJob` Hook Interface

### File: `src/hooks/useActionJob.ts`

```typescript
import { useState, useRef, useCallback, useEffect } from "react";

// ── Public types ──────────────────────────────────────────────

/** Normalized poll response — the hook expects this shape from the `poll` function. */
export interface PollResult {
  status: string;          // "running" | "complete" | "done" | "error" | "failed"
  progress?: number;       // 0–1 or 0–100 (hook normalizes)
  message?: string;        // human-readable status message
  error?: string;          // error detail (used when status is error/failed)
}

export interface ActionJobState {
  status: "idle" | "running" | "complete" | "error";
  progress: number;        // always 0.0–1.0
  error: string | null;
  label: string | null;    // display label while running, e.g. "Normalizing audio…"
}

export interface ActionJobConfig {
  /** Kick off the job. Must return an object containing job_id. */
  start: () => Promise<{ job_id: string }>;

  /** Poll job status by id. Return shape is normalized by the hook. */
  poll: (jobId: string) => Promise<PollResult>;

  /** Human-readable label shown in the UI while running. */
  label: string;

  /** Called once when job completes successfully. May be async. */
  onComplete?: () => void | Promise<void>;

  /** Polling interval in ms. Default 1000. */
  pollIntervalMs?: number;
}

export interface ActionJobHandle {
  state: ActionJobState;
  run: () => Promise<void>;
  reset: () => void;
}
```

### State machine

```
  idle ──run()──▸ running ──poll complete──▸ complete
                     │
                     └──poll error / network fail──▸ error
                     
  error ──reset()──▸ idle
  complete ──reset()──▸ idle
```

### Behavioral rules

1. **`run()`** — If already `running`, no-op (return immediately). Otherwise:
   - Call `stopPolling()` to clean up any previous cycle
   - Set state to `{ status: "running", progress: 0, error: null, label: config.label }`
   - Call `config.start()`. On failure → set error state, return.
   - Extract `job_id` from response. If empty → error state.
   - Start interval polling at `config.pollIntervalMs ?? 1000`.

2. **Polling loop** — On each tick:
   - Guard: if a poll is already in-flight (`inFlightRef`), skip this tick.
   - Call `config.poll(jobId)`.
   - Normalize progress: if `> 1`, divide by 100; clamp to `[0, 1]`.
   - If status is `"complete"` or `"done"` (case-insensitive):
     - Stop polling.
     - Call `config.onComplete?.()` (await if it returns a promise).
     - Set state `{ status: "complete", progress: 1, error: null, label: config.label }`.
   - If status is `"error"` or `"failed"` (case-insensitive):
     - Stop polling.
     - Set state `{ status: "error", progress, error: message ?? error ?? "Job failed", label: config.label }`.
   - Otherwise:
     - Update progress only (keep status `"running"`).
   - On network/fetch error:
     - Stop polling.
     - Set error state with the caught message.

3. **`reset()`** — Stop polling, set state to `{ status: "idle", progress: 0, error: null, label: null }`.

4. **Unmount cleanup** — `useEffect` teardown calls `stopPolling()`.

5. **`stopPolling()`** — Internal helper: `clearInterval`, null out jobId ref and inFlight ref. Identical pattern to existing `useComputeJob`.

### Helper: `normalizeProgress`

Reuse the exact logic from `useComputeJob.ts`:
```typescript
function normalizeProgress(progress: number): number {
  if (!Number.isFinite(progress) || progress < 0) return 0;
  if (progress > 1) return Math.min(1, progress / 100);
  return Math.min(1, progress);
}
```

### Helper: `toErrorMessage`

Reuse from `useComputeJob.ts`:
```typescript
function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}
```

---

## Spec 1B: `useActionJob` Test Cases

### File: `src/hooks/__tests__/useActionJob.test.ts`

Environment: `@vitest-environment jsdom`
Use `renderHook` + `act` from `@testing-library/react`, `vi.useFakeTimers()`.

Mock nothing from `../../api/client` — instead pass mock `start` and `poll` functions directly into the config.

**8 test cases:**

```
describe("useActionJob", () => {

  1. "starts in idle state"
     → renderHook with a config. Check state is { status: "idle", progress: 0, error: null, label: null }.

  2. "transitions to running on run()"
     → mock start resolves { job_id: "j1" }, poll resolves { status: "running", progress: 0.3 }.
     → call run(). Check status is "running", progress is 0, label is the config label.

  3. "transitions to complete when poll returns done"
     → mock start resolves { job_id: "j2" }, poll resolves { status: "complete", progress: 100 }.
     → call run(), advance timers 1000ms.
     → Check status "complete", progress 1.

  4. "transitions to error when poll returns failed"
     → mock start resolves { job_id: "j3" }, poll resolves { status: "error", progress: 0.4, message: "Out of memory" }.
     → call run(), advance timers 1000ms.
     → Check status "error", error "Out of memory".

  5. "calls onComplete callback on success"
     → mock onComplete = vi.fn().
     → start resolves, poll resolves complete.
     → advance timers. Check onComplete called once.

  6. "normalizes progress > 1 as percentage"
     → poll resolves { status: "running", progress: 68 }.
     → advance timers. Check progress is 0.68.

  7. "cleans up polling interval on unmount"
     → start resolves, poll resolves running.
     → call run(). spy on clearInterval. unmount(). Check clearInterval was called.

  8. "reset() returns to idle and clears error"
     → drive to error state first.
     → call reset(). Check state is idle with no error and label null.

  9. "run() is a no-op when already running"
     → start resolves, poll resolves running.
     → call run(). call run() again. Check start was called only once.
})
```

---

## Spec 1C: Per-Action Wiring Table

These are the 5 `useActionJob` instances to create in the `TopBar` component of `ParseUI.tsx`.

The `speaker` variable used below is `selectedSpeakers[0]` — already available in TopBar scope.

### Import changes needed at top of ParseUI.tsx

Add to the existing client import:
```typescript
import { 
  getLingPyExport, saveApiKey, startSTT, startCompute, startNormalize,
  pollSTT, pollNormalize, pollCompute   // ← ADD these three
} from './api/client';
```

Add the hook import:
```typescript
import { useActionJob } from './hooks/useActionJob';
import type { PollResult } from './hooks/useActionJob';
```

### Adapter note — STTStatus → PollResult

`pollSTT` and `pollNormalize` return `STTStatus` which is `{ status, progress, segments }` — no `message` or `error` fields. The hook expects `PollResult`. Two options:

**Option A (preferred — inline adapter):**
```typescript
const normalizeJob = useActionJob({
  start: () => startNormalize(speaker),
  poll: (id) => pollNormalize(id) as Promise<PollResult>,
  label: 'Normalizing audio…',
  onComplete: () => annotationStore.loadSpeaker(speaker),
});
```
This works because `PollResult` only requires `status: string` — `progress` and `message` are optional. `STTStatus` has `status` and `progress`, so the cast is safe.

**Option B (explicit wrapper):**
```typescript
poll: async (id) => {
  const r = await pollNormalize(id);
  return { status: r.status, progress: r.progress };
},
```

Use Option A unless TypeScript complains due to the extra `segments` field (it shouldn't, since `PollResult` doesn't forbid extra props, but if `strict` excess-property checks trigger on the return, use Option B).

### Wiring table

| # | Hook instance name | `start` | `poll` | `label` | `onComplete` |
|---|---|---|---|---|---|
| 1 | `normalizeJob` | `() => startNormalize(speaker)` | `(id) => pollNormalize(id)` | `"Normalizing audio…"` | `() => annotationStore.loadSpeaker(speaker)` |
| 2 | `sttJob` | `() => startSTT(speaker, \`${speaker}.wav\`, 'ckb')` | `(id) => pollSTT(id)` | `"Running STT…"` | `() => annotationStore.loadSpeaker(speaker)` |
| 3 | `ipaJob` | `() => startCompute('ipa_only')` | `(id) => pollCompute('ipa_only', id)` | `"Transcribing IPA…"` | `() => enrichmentStore.load()` |
| 4 | `pipelineJob` | `() => startCompute('full_pipeline')` | `(id) => pollCompute('full_pipeline', id)` | `"Running full pipeline…"` | `() => enrichmentStore.load()` |
| 5 | `crossSpeakerJob` | `() => startCompute('contact-lexemes')` | `(id) => pollCompute('contact-lexemes', id)` | `"Matching cross-speaker…"` | `() => enrichmentStore.load()` |

### Where to place the hooks

Inside the `TopBar` component function body, near the existing `useComputeJob` call (~line 1236). The hooks need access to `selectedSpeakers[0]` for speaker-scoped jobs.

**Important:** `speaker` may be `undefined` if no speakers are selected. The `start` functions must guard:
```typescript
start: () => {
  if (!speaker) return Promise.reject(new Error("No speaker selected"));
  return startNormalize(speaker);
},
```

### Annotation store access

The TopBar doesn't currently call `useAnnotationStore` directly. Add:
```typescript
const loadSpeaker = useAnnotationStore((s) => s.loadSpeaker);
```

Then `onComplete` for normalize/STT is `() => { if (speaker) loadSpeaker(speaker); }`.

### Enrichment store access

Already available — `useEnrichmentStore` is imported. But TopBar may need its own selector. Check if `loadEnrichments` or equivalent is already in scope. If not:
```typescript
const loadEnrichments = useEnrichmentStore((s) => s.load);
```

### Collect all jobs for the status indicator

Create a convenience array for rendering:
```typescript
const allJobs = [normalizeJob, sttJob, ipaJob, pipelineJob, crossSpeakerJob];
const activeJobs = allJobs.filter(j => j.state.status !== 'idle');
```

---

## Spec 1D: Status Indicator UI

### Component: inline in TopBar (not a separate file)

Position: immediately after the Actions dropdown `</div>`, still inside the topbar flex container.

### Render logic

```tsx
{/* Action job status indicators */}
{activeJobs.length > 0 && (
  <div className="flex flex-col gap-1 ml-2">
    {activeJobs.map((job, i) => (
      <div key={i} className="flex items-center gap-2 text-[11px]">
        {job.state.status === 'running' && (
          <>
            <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
            <span className="text-slate-600">{job.state.label}</span>
            <div className="h-1.5 w-20 rounded-full bg-slate-200 overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${Math.round(job.state.progress * 100)}%` }}
              />
            </div>
            <span className="text-slate-400 tabular-nums">{Math.round(job.state.progress * 100)}%</span>
          </>
        )}
        {job.state.status === 'complete' && (
          <>
            <Check className="h-3 w-3 text-emerald-500" />
            <span className="text-emerald-600">{job.state.label?.replace('…', '')} done</span>
          </>
        )}
        {job.state.status === 'error' && (
          <>
            <XCircle className="h-3 w-3 text-rose-500" />
            <span className="text-rose-600 truncate max-w-[200px]">{job.state.error}</span>
            <button
              onClick={job.reset}
              className="text-[10px] text-slate-500 underline hover:text-slate-700"
            >
              Dismiss
            </button>
          </>
        )}
      </div>
    ))}
  </div>
)}
```

### Lucide icons needed

Add to the existing lucide-react import:
- `Check` (for complete state)
- `XCircle` (for error state)

`Loader2` is already imported (line 7).

### Auto-dismiss complete state

After `onComplete` fires and state becomes `"complete"`, auto-reset to `"idle"` after 3 seconds. This can be done inside `useActionJob` itself:

```typescript
// Inside the hook, after setting complete state:
if (config.autoDismissMs !== 0) {
  setTimeout(() => {
    setState(IDLE_STATE);
  }, config.autoDismissMs ?? 3000);
}
```

Add `autoDismissMs?: number` to `ActionJobConfig`. Default `3000`. Set to `0` to disable.

### Button label changes while running

Each action button in the dropdown should show its running label:

```tsx
<button
  onClick={() => { setActionsMenuOpen(false); void normalizeJob.run(); }}
  disabled={normalizeJob.state.status === 'running'}
  className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
>
  <AudioLines className="h-3.5 w-3.5 text-slate-400"/>
  {normalizeJob.state.status === 'running' ? 'Normalizing…' : 'Run Audio Normalization'}
</button>
```

Pattern repeats for all 5 buttons.

### Reset Project addition

In the Reset Project `onClick` handler, after the existing store clears, add:
```typescript
allJobs.forEach(j => j.reset());
```

---

## Dispatch sequence

1. **Dispatch 1** → `useActionJob.ts` + `useActionJob.test.ts` (new files only)
2. **Dispatch 2** → `useComputeJob.ts` refactor (single file, existing tests must pass)
3. **Dispatch 3** → `ParseUI.tsx` wiring (single file, import changes + handler rewrites + status bar)
4. **Dispatch 4** → `ParseUI.test.tsx` regression additions (single file)

Each dispatch is independent enough that parse-gpt can succeed with the file context + this spec. Opus reviews between each dispatch.
