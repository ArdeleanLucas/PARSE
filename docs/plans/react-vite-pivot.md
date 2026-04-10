# PARSE React + Vite Pivot — Dual-Agent Implementation Plan

> **Owners:** ParseBuilder (ParseBuilder + Codex) owns Track A — Annotate Mode.
> Oda (Gemini + Flash/Pro) owns Track B — Compare Mode.
> Both tracks share a pre-agreed contract (Phase 0) before any parallel work begins.
> Integration happens in Phase C after both tracks pass their own gate tests.
>
> **Historical note (post-merge):** the React/Vite pivot has already landed on `main`. Branch references in this document such as `feat/parse-react-vite` are historical only. Do not branch from or recreate them; start new work from `origin/main`.

**Goal:** Replace the vanilla-JS monolith (36,951 lines across parse.html, compare.html, 25 JS modules)
with a React + Vite frontend, keeping the Python backend (port 8766) completely unchanged.

**Python backend status: FROZEN with one surgical exception.** `python/server.py` had two new GET routes added in commit aa2728e: `/api/export/lingpy` (streams TSV via existing `export_wordlist_tsv()`) and `/api/export/nexus` (returns 501 — not yet implemented). No existing handler was modified. All other Python files remain untouched.

**Thesis deadline:** End of May 2026. This pivot must ship inside 10 days of start.

**No emoji in the PARSE UI.** Timestamps are the bible in annotation data.

---

## Status

| Phase / Step | Branch | Status | Gate |
|---|---|---|---|
| Phase 0 | feat/annotate-react | DONE e9cf22f | tsc clean, proxy ok |
| A1 useWaveSurfer | feat/annotate-react | DONE c4643cb | 5 tests |
| A2 annotationStore + useAnnotationSync | feat/annotate-react | DONE 7098c21 | 4 tests |
| A3 RegionManager | feat/annotate-react | DONE 366b39f | 5 tests |
| A4 AnnotationPanel | feat/annotate-react | DONE 841cea2 | 6 tests |
| A5 TranscriptPanel | feat/annotate-react | DONE e6dfb53 | 5 tests |
| A6 SuggestionsPanel + useSuggestions | feat/annotate-react | DONE 9d83dc4 | 6 tests |
| A7 OnboardingFlow | feat/annotate-react | DONE fd630f8 | 3 tests |
| A8 useImportExport | feat/annotate-react | DONE fd630f8 | 4 tests |
| A9 ChatPanel + useChatSession | feat/annotate-react | DONE fd630f8 | 4 tests |
| A10 AnnotateMode root | feat/annotate-react | DONE ce5d6b1 | 5 tests |
| A11 Browser integration | — | PENDING Lucas | manual |
| B1 ConceptTable | feat/compare-react | DONE 44ee8de | 6 tests |
| B2 CognateControls | feat/compare-react | DONE 44ee8de | 5 tests |
| B3 BorrowingPanel | feat/compare-react | DONE 44ee8de | 6 tests |
| B4 TagManager | feat/compare-react | DONE 44ee8de | 5 tests |
| B5 EnrichmentsPanel | feat/compare-react | DONE 44ee8de | 5 tests |
| B6 SpeakerImport | feat/compare-react | DONE 44ee8de | 5 tests |
| B7 useExport + useComputeJob | feat/compare-react | DONE aa2728e | 9 tests (4+5) |
| B8 CompareMode root | feat/compare-react | DONE aa2728e | 6 tests |
| B9 Browser integration | — | PENDING Lucas | manual |
| agent-gpt EnrichmentsPanel rebase | feat/compare-react | PENDING agent-gpt | rebase onto ad09bcf |
| Phase C merge | feat/parse-react-vite | BLOCKED — wait for agent-gpt rebase | — |
| **UI Redesign — ParseUI unified shell** | **historical `feat/annotate-ui-redesign` lane** | **DONE fd955cc** | **tsc clean** |

---

## Codebase Snapshot (pre-pivot)

| File | Lines | Owner | Disposition |
|---|---|---|---|
| `parse.html` | 3,202 | ParseBuilder | Replaced by Vite entry |
| `compare.html` | 1,591 | Oda | Replaced by Vite entry |
| `js/annotate/parse.js` | 1,871 | ParseBuilder | Decompose → React |
| `js/annotate/waveform-controller.js` | 734 | ParseBuilder | → `useWaveSurfer` hook |
| `js/annotate/region-manager.js` | 933 | ParseBuilder | → `RegionManager` component |
| `js/annotate/annotation-panel.js` | 1,037 | ParseBuilder | → `AnnotationPanel` |
| `js/annotate/transcript-panel.js` | 765 | ParseBuilder | → `TranscriptPanel` |
| `js/annotate/suggestions-panel.js` | 885 | ParseBuilder | → `SuggestionsPanel` |
| `js/annotate/import-export.js` | 807 | ParseBuilder | → `useImportExport` hook |
| `js/annotate/onboarding.js` | 663 | ParseBuilder | → `OnboardingFlow` |
| `js/annotate/fullscreen-mode.js` | 620 | ParseBuilder | → `FullscreenMode` |
| `js/annotate/video-sync-panel.js` | 1,376 | ParseBuilder | → `VideoSyncPanel` |
| `js/compare/compare.js` | 4,654 | Oda | Decompose → React |
| `js/compare/concept-table.js` | 873 | Oda | → `ConceptTable` |
| `js/compare/cognate-controls.js` | 854 | Oda | → `CognateControls` |
| `js/compare/borrowing-panel.js` | 1,678 | Oda | → `BorrowingPanel` |
| `js/compare/enrichments.js` | 1,557 | Oda | → `EnrichmentsPanel` |
| `js/compare/speaker-import.js` | 2,147 | Oda | → `SpeakerImport` |
| `js/shared/annotation-store.js` | 2,587 | ParseBuilder | → Zustand `annotationStore` |
| `js/shared/tags.js` | 845 | Oda | → Zustand `tagStore` + `TagManager` |
| `js/shared/ai-client.js` | 909 | ParseBuilder | → `src/api/client.ts` |
| `js/shared/project-config.js` | 371 | ParseBuilder | → Zustand `configStore` |
| `js/shared/audio-player.js` | 269 | ParseBuilder | → absorbed into `useWaveSurfer` |
| `js/shared/chat-client.js` | 1,430 | ParseBuilder | → `ChatPanel` + `useChatSession` |
| `js/shared/chat-panel.js` | 885 | ParseBuilder | → `ChatPanel` component |
| `js/shared/chat-tool-adapters.js` | 639 | ParseBuilder | → `useChatSession` hook |
| `js/shared/spectrogram-worker.js` | 273 | ParseBuilder | → `spectrogramWorker.ts` |

---

## Python API Contract (read-only reference — both agents must know this)

All endpoints are at `localhost:8766`. Vite proxy forwards `/api/*` → `http://localhost:8766`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/annotations/{speaker}` | Load speaker annotation record |
| POST | `/api/annotations/{speaker}` | Save speaker annotation record |
| GET | `/api/enrichments` | Load compare enrichments |
| POST | `/api/enrichments` | Save compare enrichments |
| GET | `/api/config` | Load project config |
| POST `/PUT` | `/api/config` | Update project config |
| GET | `/api/auth/status` | AI provider auth status |
| POST | `/api/auth/start` | Begin device auth flow |
| POST | `/api/auth/poll` | Poll device auth |
| POST | `/api/auth/logout` | Logout provider |
| POST | `/api/stt` | Start STT job → returns `{job_id}` |
| POST | `/api/stt/status` | Poll STT job → `{status, progress, segments}` |
| POST | `/api/ipa` | IPA transcription for text |
| POST | `/api/suggest` | AI annotation suggestions |
| POST | `/api/chat/session` | Create/get chat session |
| GET | `/api/chat/session/{id}` | Get chat session state |
| POST | `/api/chat/run` | Start chat AI job |
| POST | `/api/chat/status` | Poll chat job |
| POST | `/api/compute/{speaker}` | Start compute/enrichment job |
| POST | `/api/compute/{speaker}/status` | Poll compute job |
| GET | `/api/export/lingpy` | Stream LingPy-compatible wordlist TSV (Content-Disposition: attachment) |
| GET | `/api/export/nexus` | NEXUS export — 501 Not Implemented until backend adds it |
| GET | Static files | All non-`/api/` paths served from project root |

---

## Phase 0 — Shared Contract (BOTH AGENTS BLOCK ON THIS)

**Owner:** ParseBuilder writes; Oda reviews and approves before Phase A/B begin.
**Model:** ParseBuilder → Codex for scaffold; Oda uses gemini-2.5-flash for review.
**Time estimate:** 0.5 days.
**Gate:** Oda must explicitly sign off on store shapes before any Track A or B work starts.

### 0.1 — Vite Project Scaffold

**Files to create:**

```
src/
  main.tsx               # React entry, mounts <App />
  App.tsx                # React Router: / = AnnotateMode, /compare = CompareMode
  vite-env.d.ts          # Vite type declarations
  api/
    client.ts            # Typed fetch wrapper for all Python API endpoints
    types.ts             # Shared TypeScript types for API payloads
  stores/
    annotationStore.ts   # Zustand — annotation data per speaker
    playbackStore.ts     # Zustand — WaveSurfer playback state
    configStore.ts       # Zustand — project.json config
    tagStore.ts          # Zustand — global tags (replaces localStorage parse-tags-v1)
    enrichmentStore.ts   # Zustand — compare enrichments
    uiStore.ts           # Zustand — active speaker, active concept, panel visibility
  components/
    annotate/            # Track A (ParseBuilder)
    compare/             # Track B (Oda)
    shared/              # Shared UI primitives
index.html               # Vite entry HTML
vite.config.ts           # Vite config with /api/* proxy
package.json
tsconfig.json
```

**`vite.config.ts` (exact content):**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8766',
        changeOrigin: true,
      },
      // Also proxy static data files served by Python
      '/project.json': { target: 'http://localhost:8766', changeOrigin: true },
      '/source_index.json': { target: 'http://localhost:8766', changeOrigin: true },
      '/annotations': { target: 'http://localhost:8766', changeOrigin: true },
      '/audio': { target: 'http://localhost:8766', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
```

**`package.json` dependencies (exact):**

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.0",
    "zustand": "^4.5.2",
    "wavesurfer.js": "^7.8.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.4.5",
    "vite": "^5.2.12",
    "vitest": "^1.6.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "jsdom": "^24.1.0"
  },
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:ui": "vitest --ui"
  }
}
```

### 0.2 — Zustand Store Shapes (SHARED CONTRACT)

These exact shapes must be agreed before Track A or B writes any store code.
**No agent may deviate from these without a written amendment approved by Lucas.**

```typescript
// src/stores/annotationStore.ts
// One record per speaker. Mirrors /api/annotations/{speaker} exactly.
interface AnnotationInterval {
  start: number;       // seconds — IMMUTABLE once written
  end: number;         // seconds — IMMUTABLE once written
  text: string;
}

interface AnnotationTier {
  name: string;
  display_order: number;
  intervals: AnnotationInterval[];
}

interface AnnotationRecord {
  speaker: string;
  tiers: Record<string, AnnotationTier>;  // keys: ipa, ortho, concept, speaker
  created_at: string;
  modified_at: string;
  source_wav: string;
}

interface AnnotationStore {
  records: Record<string, AnnotationRecord>;  // keyed by speaker id
  dirty: Record<string, boolean>;             // true = unsaved changes
  loading: Record<string, boolean>;

  loadSpeaker: (speaker: string) => Promise<void>;
  saveSpeaker: (speaker: string) => Promise<void>;
  updateInterval: (speaker: string, tier: string, index: number, text: string) => void;
  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  removeInterval: (speaker: string, tier: string, index: number) => void;
}

// src/stores/playbackStore.ts
interface PlaybackStore {
  activeSpeaker: string | null;
  isPlaying: boolean;
  currentTime: number;        // seconds
  duration: number;           // seconds
  zoom: number;               // wavesurfer zoom level (pixels per second)
  playbackRate: number;       // 1.0 default
  selectedRegion: { start: number; end: number } | null;
  loopEnabled: boolean;

  setActiveSpeaker: (speaker: string) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  setZoom: (z: number) => void;
  setPlaybackRate: (r: number) => void;
  setSelectedRegion: (r: { start: number; end: number } | null) => void;
  toggleLoop: () => void;
  togglePlay: () => void;
}

// src/stores/configStore.ts
interface ProjectConfig {
  project_name: string;
  language_code: string;
  speakers: string[];
  audio_dir: string;
  annotations_dir: string;
  [key: string]: unknown;
}

interface ConfigStore {
  config: ProjectConfig | null;
  loading: boolean;
  load: () => Promise<void>;
  update: (patch: Partial<ProjectConfig>) => Promise<void>;
}

// src/stores/tagStore.ts  — replaces localStorage 'parse-tags-v1'
interface Tag {
  id: string;         // uuid
  label: string;
  color: string;      // hex
  concepts: string[]; // concept ids that carry this tag
}

interface TagStore {
  tags: Tag[];
  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Tag>) => void;
  tagConcept: (tagId: string, conceptId: string) => void;
  untagConcept: (tagId: string, conceptId: string) => void;
  getTagsForConcept: (conceptId: string) => Tag[];
  persist: () => void;      // write to localStorage
  hydrate: () => void;      // read from localStorage on boot
}

// src/stores/enrichmentStore.ts
interface EnrichmentStore {
  data: Record<string, unknown>;   // mirrors parse-enrichments.json shape exactly
  loading: boolean;
  load: () => Promise<void>;
  save: (patch: Record<string, unknown>) => Promise<void>;
}

// src/stores/uiStore.ts
interface UIStore {
  activeSpeaker: string | null;
  activeConcept: string | null;
  annotatePanel: 'annotation' | 'transcript' | 'suggestions' | 'chat';
  comparePanel: 'table' | 'borrowing' | 'enrichments' | 'tags';
  sidebarOpen: boolean;
  onboardingComplete: boolean;

  setActiveSpeaker: (s: string | null) => void;
  setActiveConcept: (c: string | null) => void;
  setAnnotatePanel: (p: UIStore['annotatePanel']) => void;
  setComparePanel: (p: UIStore['comparePanel']) => void;
  toggleSidebar: () => void;
  setOnboardingComplete: (v: boolean) => void;
}
```

### 0.3 — API Client Contract

```typescript
// src/api/client.ts — ALL fetch calls go through these typed functions.
// No component may call fetch() directly. Always use this module.

export async function getAnnotation(speaker: string): Promise<AnnotationRecord>
export async function saveAnnotation(speaker: string, record: AnnotationRecord): Promise<void>
export async function getEnrichments(): Promise<Record<string, unknown>>
export async function saveEnrichments(data: Record<string, unknown>): Promise<void>
export async function getConfig(): Promise<ProjectConfig>
export async function updateConfig(patch: Partial<ProjectConfig>): Promise<void>
export async function getAuthStatus(): Promise<{ authenticated: boolean; provider: string }>
export async function startSTT(speaker: string, sourceWav: string, language?: string): Promise<{ job_id: string }>
export async function pollSTT(jobId: string): Promise<{ status: string; progress: number; segments: unknown[] }>
export async function requestIPA(text: string, language?: string): Promise<{ ipa: string }>
export async function requestSuggestions(speaker: string, conceptIds: string[]): Promise<unknown[]>
export async function startChatSession(sessionId?: string): Promise<{ session_id: string }>
export async function getChatSession(sessionId: string): Promise<unknown>
export async function runChat(sessionId: string, message: string): Promise<{ job_id: string }>
export async function pollChat(jobId: string): Promise<{ status: string; result?: string }>
export async function startCompute(speaker: string): Promise<{ job_id: string }>
export async function pollCompute(speaker: string, jobId: string): Promise<{ status: string; progress: number }>
```

### 0.4 — Shared Component Primitives (no business logic)

```
src/components/shared/
  Button.tsx         # Primary, secondary, danger variants
  IconButton.tsx     # Icon-only button
  Panel.tsx          # Bordered panel with header
  Modal.tsx          # Dialog overlay
  ProgressBar.tsx    # Progress indicator for jobs
  Spinner.tsx        # Loading state
  Badge.tsx          # Tag/label chip
  Input.tsx          # Text input
  Textarea.tsx       # Multiline input
  Select.tsx         # Dropdown
  Toast.tsx          # Notification (no emoji — text only)
```

### 0.5 — Phase 0 Gate Test

```bash
cd parse  # project root
npm install
npm run dev
# Expected: Vite server starts on :5173
# http://localhost:5173/     → Annotate mode placeholder renders
# http://localhost:5173/compare → Compare mode placeholder renders
# No TypeScript errors in terminal
npm run test
# Expected: 0 tests, 0 failures (test suite is empty — that's fine at this stage)
```

**Gate criteria (Oda must confirm before Track B starts):**
- [ ] Store shape types compile without error
- [ ] API client types compile without error
- [ ] Vite proxy to :8766 works (verify with: `curl http://localhost:5173/api/config`)
- [ ] React Router routes render without error

---

## Track A — Annotate Mode (ParseBuilder + Codex)

**Branch:** `feat/annotate-react`
**Parallel to:** Track B. Track A NEVER touches `src/components/compare/`.

---

### A1 — `useWaveSurfer` Hook

**Model:** Codex (with ParseBuilder reviewing output carefully)
**Complexity:** HIGH — React strict mode double-mount leaks audio context.
**Source file:** `js/annotate/waveform-controller.js` (734 lines)
**Output:** `src/hooks/useWaveSurfer.ts`

**Reference implementation pattern:**

```typescript
// src/hooks/useWaveSurfer.ts
import { useEffect, useRef, useCallback } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.js'
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.js'
import { usePlaybackStore } from '../stores/playbackStore'

interface UseWaveSurferOptions {
  containerRef: React.RefObject<HTMLDivElement>
  audioUrl: string
  onRegionUpdate?: (start: number, end: number) => void
  onTimeUpdate?: (time: number) => void
  onReady?: (duration: number) => void
}

export function useWaveSurfer(options: UseWaveSurferOptions) {
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null)

  useEffect(() => {
    if (!options.containerRef.current) return

    // Regions + Timeline plugins
    const regions = RegionsPlugin.create()
    const timeline = TimelinePlugin.create({ height: 20 })
    regionsRef.current = regions

    const ws = WaveSurfer.create({
      container: options.containerRef.current,
      waveColor: '#6b7280',
      progressColor: '#3b82f6',
      height: 80,
      normalize: true,
      plugins: [regions, timeline],
    })

    wsRef.current = ws

    ws.load(options.audioUrl)
    ws.on('ready', () => options.onReady?.(ws.getDuration()))
    ws.on('timeupdate', (t) => options.onTimeUpdate?.(t))
    regions.on('region-updated', (r) => options.onRegionUpdate?.(r.start, r.end))

    return () => {
      // CRITICAL: destroy prevents audio context leak in React strict mode
      ws.destroy()
      wsRef.current = null
      regionsRef.current = null
    }
  }, [options.audioUrl]) // re-init only when URL changes

  const play = useCallback(() => wsRef.current?.play(), [])
  const pause = useCallback(() => wsRef.current?.pause(), [])
  const seek = useCallback((t: number) => wsRef.current?.seekTo(t / (wsRef.current?.getDuration() || 1)), [])
  const setZoom = useCallback((z: number) => wsRef.current?.zoom(z), [])
  const setRate = useCallback((r: number) => { if (wsRef.current) wsRef.current.setPlaybackRate(r) }, [])
  const addRegion = useCallback((start: number, end: number, id?: string) => {
    regionsRef.current?.addRegion({ start, end, id: id ?? `r-${start}`, drag: true, resize: true })
  }, [])
  const clearRegions = useCallback(() => regionsRef.current?.clearRegions(), [])

  return { play, pause, seek, setZoom, setRate, addRegion, clearRegions, wsRef, regionsRef }
}
```

**Test (Vitest + jsdom):**

```typescript
// src/hooks/__tests__/useWaveSurfer.test.ts
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock WaveSurfer — we can't run audio in jsdom
vi.mock('wavesurfer.js', () => ({
  default: {
    create: vi.fn(() => ({
      load: vi.fn(),
      destroy: vi.fn(),
      play: vi.fn(),
      pause: vi.fn(),
      seekTo: vi.fn(),
      zoom: vi.fn(),
      setPlaybackRate: vi.fn(),
      getDuration: vi.fn(() => 10.0),
      on: vi.fn(),
    })),
  },
}))

vi.mock('wavesurfer.js/dist/plugins/regions.js', () => ({
  default: { create: vi.fn(() => ({ addRegion: vi.fn(), clearRegions: vi.fn(), on: vi.fn() })) },
}))

vi.mock('wavesurfer.js/dist/plugins/timeline.js', () => ({
  default: { create: vi.fn(() => ({})) },
}))

import { useWaveSurfer } from '../useWaveSurfer'
import WaveSurfer from 'wavesurfer.js'

describe('useWaveSurfer', () => {
  it('destroys wavesurfer instance on cleanup', () => {
    const containerRef = { current: document.createElement('div') }
    const { unmount } = renderHook(() =>
      useWaveSurfer({ containerRef, audioUrl: '/audio/test.wav' })
    )
    const mockWs = (WaveSurfer.create as ReturnType<typeof vi.fn>).mock.results[0].value
    unmount()
    expect(mockWs.destroy).toHaveBeenCalledOnce()
  })

  it('reinitializes when audioUrl changes', () => {
    const containerRef = { current: document.createElement('div') }
    const { rerender } = renderHook(
      ({ url }) => useWaveSurfer({ containerRef, audioUrl: url }),
      { initialProps: { url: '/audio/a.wav' } }
    )
    rerender({ url: '/audio/b.wav' })
    expect(WaveSurfer.create).toHaveBeenCalledTimes(2)
  })
})
```

**Run:** `npm run test -- --reporter=verbose src/hooks/__tests__/useWaveSurfer.test.ts`
**Expected:** 2 passed.

---

### A2 — `useAnnotationSync` Hook + `annotationStore`

**Model:** Codex
**Source:** `js/shared/annotation-store.js` (2,587 lines)
**Output:** `src/stores/annotationStore.ts` + `src/hooks/useAnnotationSync.ts`

Key behaviors to preserve from `annotation-store.js`:
- Debounced server save (500ms) after any mutation
- Immediate localStorage mirror on every mutation
- `speaker` tier is auto-synced from interval timestamps (do not break this)
- `modified_at` timestamp updated on every save

**Test:**

```typescript
// src/stores/__tests__/annotationStore.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAnnotationStore } from '../annotationStore'

// Mock API client
vi.mock('../../api/client', () => ({
  getAnnotation: vi.fn(() => Promise.resolve({
    speaker: 'Test01',
    tiers: { ipa: { name: 'ipa', display_order: 0, intervals: [] } },
    created_at: '2024-01-01T00:00:00Z',
    modified_at: '2024-01-01T00:00:00Z',
    source_wav: 'test.wav',
  })),
  saveAnnotation: vi.fn(() => Promise.resolve()),
}))

describe('annotationStore', () => {
  beforeEach(() => {
    // Reset store between tests
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} })
  })

  it('loads a speaker record', async () => {
    await useAnnotationStore.getState().loadSpeaker('Test01')
    expect(useAnnotationStore.getState().records['Test01']).toBeDefined()
  })

  it('marks record dirty after updateInterval', async () => {
    await useAnnotationStore.getState().loadSpeaker('Test01')
    useAnnotationStore.getState().addInterval('Test01', 'ipa', { start: 0, end: 1, text: 'test' })
    expect(useAnnotationStore.getState().dirty['Test01']).toBe(true)
  })
})
```

---

### A3 — `RegionManager` Component

**Model:** Codex
**Source:** `js/annotate/region-manager.js` (933 lines)
**Output:** `src/components/annotate/RegionManager.tsx`

Responsibilities:
- Renders draggable WaveSurfer regions mapped 1:1 to annotation intervals
- Bidirectional sync: annotation store changes → update regions; region drag → update store
- Keyboard shortcuts: Space = play/pause, Left/Right arrow = seek ±0.1s
- No playback logic here — delegates to `useWaveSurfer`

**Props interface:**

```typescript
interface RegionManagerProps {
  speaker: string
  containerRef: React.RefObject<HTMLDivElement>
  wavesurfer: ReturnType<typeof useWaveSurfer>
}
```

**Test:**

```typescript
// Check that region count matches interval count in store
it('renders one region per ipa interval', () => {
  // seed store with 3 intervals, verify wavesurfer.addRegion called 3 times
})
```

---

### A4 — `AnnotationPanel` Component

**Model:** Codex
**Source:** `js/annotate/annotation-panel.js` (1,037 lines)
**Output:** `src/components/annotate/AnnotationPanel.tsx`

Four tiers: IPA, orthography, concept, speaker. Each tier row shows intervals as editable cells.
Tier cells sync bidirectionally with `annotationStore`.

**Constraint:** The tier labeled "speaker" is read-only (auto-synced). IPA, ortho, concept are editable.

---

### A5 — `TranscriptPanel` Component

**Model:** Codex
**Source:** `js/annotate/transcript-panel.js` (765 lines)
**Output:** `src/components/annotate/TranscriptPanel.tsx`

Displays the full linear transcript with concept labels. Click on a line → seek waveform.
Inline edit triggers `annotationStore.updateInterval`.

---

### A6 — `SuggestionsPanel` + `useSuggestions` Hook

**Model:** Codex
**Source:** `js/annotate/suggestions-panel.js` (885 lines)
**Output:** `src/components/annotate/SuggestionsPanel.tsx` + `src/hooks/useSuggestions.ts`

Calls `POST /api/suggest`, polls `POST /api/stt/status`, applies suggestions to annotationStore.
AI calls go via `src/api/client.ts` — never direct fetch.

---

### A7 — `OnboardingFlow` Component

**Model:** Codex
**Source:** `js/annotate/onboarding.js` (663 lines)
**Output:** `src/components/annotate/OnboardingFlow.tsx`

Multi-step wizard: select speaker → select audio file → configure tiers → confirm.
State machine: `idle → select_speaker → select_audio → configure → complete`.
Uses `uiStore.setOnboardingComplete()` on finish.

**Test (state machine):**

```typescript
it('transitions from idle to select_speaker on start', () => { ... })
it('transitions to complete when all fields filled', () => { ... })
it('does not advance if speaker is empty', () => { ... })
```

---

### A8 — `useImportExport` Hook

**Model:** Codex
**Source:** `js/annotate/import-export.js` (807 lines)
**Output:** `src/hooks/useImportExport.ts`

Functions:
- `exportTextGrid(speaker)` → downloads .TextGrid file
- `exportELAN(speaker)` → downloads .eaf file
- `exportCSV(speaker)` → downloads .csv
- `importTextGrid(file, speaker)` → parses and loads into annotationStore

**Test:**

```typescript
it('exportCSV produces correct column headers', () => {
  // seed store with known data, call exportCSV, inspect Blob content
})
it('importTextGrid populates annotationStore intervals', () => {
  // supply a minimal TextGrid fixture, verify intervals loaded
})
```

---

### A9 — `ChatPanel` + `useChatSession` Hook

**Model:** Codex
**Source:** `js/shared/chat-client.js` (1,430 lines) + `js/shared/chat-panel.js` (885 lines)
**Output:** `src/components/shared/ChatPanel.tsx` + `src/hooks/useChatSession.ts`

Manages chat session lifecycle: create → send message → poll for response → display.
Chat tool adapters (`chat-tool-adapters.js`) → inline in `useChatSession`.

---

### A10 — `AnnotateMode` Root Component

**Model:** Codex
**Output:** `src/components/annotate/AnnotateMode.tsx`

Assembles all Track A components into the Annotate Mode layout.
Reads `configStore` for speaker list, renders `OnboardingFlow` if `uiStore.onboardingComplete = false`.

```typescript
// Layout:
// <TopBar />
// <main>
//   <aside><SpeakerList /></aside>
//   <section>
//     <WaveformContainer> (ref for WaveSurfer)
//       <RegionManager />
//     </WaveformContainer>
//     <PanelSwitcher>
//       <AnnotationPanel /> | <TranscriptPanel /> | <SuggestionsPanel /> | <ChatPanel />
//     </PanelSwitcher>
//   </section>
// </main>
```

### A11 — Track A Integration Test

**Run in browser (not jsdom) — Lucas tests these himself:**

1. `npm run dev` → navigate to `http://localhost:5173/`
2. Onboarding wizard appears if no config → complete it → `onboardingComplete = true`
3. Select a speaker (e.g. `Fail01`) → waveform loads from `/audio/Fail01/...`
4. Play audio → timeline cursor moves
5. Drag a region → annotation interval updates in panel
6. Edit an IPA cell → `dirty['Fail01'] = true` → save debounces and clears dirty
7. Run STT → job polling works → segments appear in SuggestionsPanel
8. Export CSV → file downloads with correct headers
9. Hard refresh → annotation persists from localStorage and/or server

**Automated checks (`npm run test`):**
- All unit tests in `src/hooks/__tests__/` and `src/stores/__tests__/` pass
- No TypeScript errors: `npx tsc --noEmit`
- No console errors in browser dev tools

**Gate criteria before Track A merges to integration branch:**
- [ ] All automated tests pass
- [ ] Lucas has verified browser items 1–9 above
- [ ] No `window.PARSE` references remain in Track A code
- [ ] No direct `fetch()` calls — only `src/api/client.ts` functions used

---

## Track B — Compare Mode (Oda + Gemini Flash/Pro)

**Branch:** `feat/compare-react`
**Parallel to:** Track A. Track B NEVER touches `src/components/annotate/`.
**Model assignments below are suggestions for Oda's subagent routing.**

---

### B1 — `ConceptTable` Component

**Model:** gemini-2.5-pro (complex grid render logic)
**Source:** `js/compare/concept-table.js` (873 lines) + `js/compare/compare.js` (4,654 lines — extract table section)
**Output:** `src/components/compare/ConceptTable.tsx`

Grid layout: rows = concept IDs, columns = speakers. Cell = IPA form + accept/reject badge.
Data source: `enrichmentStore.data.table` — if null, fetch from `/api/enrichments`.
Cell interaction: click → open `CognateControls` for that (concept, speaker) pair.

**Critical data shape (from parse-enrichments.json):**

```typescript
interface ConceptTableData {
  concepts: string[]            // ordered concept IDs
  speakers: string[]            // ordered speaker IDs
  cells: Record<string, Record<string, {
    ipa: string
    ortho: string
    cognate_set: string | null
    status: 'accepted' | 'rejected' | 'pending' | 'borrowed'
  }>>  // cells[concept][speaker]
}
```

**Test:**

```typescript
it('renders N rows for N concepts', () => { ... })
it('renders M columns for M speakers', () => { ... })
it('shows "pending" badge when cell status = pending', () => { ... })
it('clicking a cell opens CognateControls with correct concept+speaker', () => { ... })
```

---

### B2 — `CognateControls` Component

**Model:** gemini-2.5-flash
**Source:** `js/compare/cognate-controls.js` (854 lines)
**Output:** `src/components/compare/CognateControls.tsx`

Controls: Accept / Split / Merge / Cycle cognate set / Mark borrowed.
Writes to `enrichmentStore` via `saveEnrichments`.
No local state — fully driven by `enrichmentStore`.

---

### B3 — `BorrowingPanel` Component

**Model:** gemini-2.5-flash
**Source:** `js/compare/borrowing-panel.js` (1,678 lines)
**Output:** `src/components/compare/BorrowingPanel.tsx`

Shows borrowing adjudication table. Reads/writes `enrichmentStore`.
Displays donor language, source form, confidence score.

---

### B4 — `TagManager` Component (Two-Panel Design)

**Model:** gemini-2.5-pro (non-trivial master-detail UI)
**Source:** `js/shared/tags.js` (845 lines) + `js/compare/compare.js` (extract tag section)
**Output:** `src/components/compare/TagManager.tsx`

**Exact UI spec (Lucas's design — do not deviate):**

```
┌─────────────────────┬──────────────────────────────────┐
│ LEFT PANEL          │ RIGHT PANEL                      │
│ (Tag Master)        │ (Concept Browser)                │
├─────────────────────┤                                  │
│ [+ New Tag]         │ Filter: [__omnibox search____]   │
│                     │                                  │
│ [search tags...]    │ Concept chips:                   │
│                     │   [water ✓] [fire] [stone ✓] ... │
│ • Tag A    (12)     │                                  │
│ • Tag B    (3)  ←── │ ── selected tag filters list ──  │
│                     │                                  │
│ (hover: edit/del)   │ [Select All] [Clear]             │
└─────────────────────┴──────────────────────────────────┘
```

- Left panel: list of tags with concept count. Hover → edit icon + delete icon.
  Click a tag → right panel filters to concepts tagged with it.
- Right panel: all concepts as chips. Selected concepts (in the active tag) show checkmark.
  Click a concept chip → toggles it in/out of active tag.
- Search box in right panel: filters concept chips by label text.
- `tagStore` is the single source of truth. Tags persist via `tagStore.persist()` to localStorage.
- Migration from old `parse-tags-v1` key: `tagStore.hydrate()` reads both old and new keys.

**Test:**

```typescript
it('left panel shows tag count matching tagStore', () => { ... })
it('clicking a tag filters right panel to its concepts', () => { ... })
it('toggling a concept chip updates tagStore', () => { ... })
it('search in right panel filters concept chips', () => { ... })
it('hydrate() migrates data from parse-tags-v1 localStorage key', () => { ... })
```

---

### B5 — `EnrichmentsPanel` Component

**Model:** gemini-2.5-flash
**Source:** `js/compare/enrichments.js` (1,557 lines)
**Output:** `src/components/compare/EnrichmentsPanel.tsx`

Displays computed phonetic enrichments (edit distance, PMI, IPA alignment).
Reads `enrichmentStore.data.enrichments`. Triggers compute job via `startCompute` / `pollCompute`.

---

### B6 — `SpeakerImport` Component

**Model:** gemini-2.5-flash
**Source:** `js/compare/speaker-import.js` (2,147 lines)
**Output:** `src/components/compare/SpeakerImport.tsx`

Wizard for importing a new speaker into Compare Mode.
Steps: upload annotation JSON → preview detected concepts → confirm merge into enrichments.

---

### B7 — Export Pipeline Wiring

**Model:** gemini-2.5-flash
**Output:** `src/hooks/useExport.ts`

Connects the five export formats to their Python-side logic:

| Export | Method | Notes |
|---|---|---|
| LingPy TSV | `GET /api/export/lingpy` (new endpoint — coordinate with ParseBuilder if needed) | Primary thesis output |
| CSV | Client-side from annotationStore | Already in Track A `useImportExport` |
| NEXUS | `GET /api/export/nexus` (new if not exists) | Phylogenetic format |
| ELAN | Client-side from annotationStore | Already in Track A |
| TextGrid | Client-side from annotationStore | Already in Track A |

**Note:** If LingPy TSV and NEXUS export endpoints do not exist in `python/server.py`, Oda must flag this to ParseBuilder. Do NOT add Python code without Lucas's approval — the Python backend is frozen.

---

### B8 — `CompareMode` Root Component

**Model:** gemini-2.5-flash
**Output:** `src/components/compare/CompareMode.tsx`

Assembles all Track B components.

```typescript
// Layout:
// <TopBar />
// <main>
//   <ConceptTable />  (main grid)
//   <aside>
//     <CognateControls /> | <BorrowingPanel /> | <EnrichmentsPanel /> | <TagManager />
//   </aside>
// </main>
```

### B9 — Track B Integration Test

**Run in browser — Lucas tests these himself:**

1. Navigate to `http://localhost:5173/compare`
2. ConceptTable renders with correct concept × speaker grid
3. Click a cell → CognateControls opens for that pair
4. Accept a cognate → cell badge updates
5. Split a cognate set → set ID changes
6. Mark a form as borrowed → BorrowingPanel shows it
7. Open TagManager → create a tag → assign 3 concepts → right panel reflects them
8. Search in TagManager right panel → filters correctly
9. EnrichmentsPanel → trigger compute job → progress bar → results load
10. Export LingPy TSV → file downloads (verify not empty, correct headers)

**Automated checks:**
- All unit tests in `src/components/compare/__tests__/` pass
- No TypeScript errors: `npx tsc --noEmit`

**Gate criteria before Track B merges to integration branch:**
- [ ] All automated tests pass
- [ ] Lucas has verified browser items 1–10 above
- [ ] No `window.PARSE` references remain in Track B code
- [ ] `tagStore.hydrate()` handles missing/malformed localStorage gracefully

---

## Phase C — Integration, Wiring, and Regression

**Branch:** `feat/parse-react-vite` (merge target for both A and B)
**Owner:** ParseBuilder leads merge; Oda reviews Compare side conflicts.

---

### C1 — Merge Tracks

```bash
git checkout -b feat/parse-react-vite
git merge feat/annotate-react
git merge feat/compare-react
```

Expected conflicts:
- `src/App.tsx` — both tracks touch React Router
- `package.json` — if dependencies diverged
- `vite.config.ts` — if proxy rules diverged

Resolve all conflicts, then:

```bash
npm run test
npx tsc --noEmit
```

Both must pass before proceeding.

---

### C2 — Cross-Mode Navigation

Implement React Router properly:

```typescript
// src/App.tsx
import { Routes, Route, Navigate } from 'react-router-dom'
import { AnnotateMode } from './components/annotate/AnnotateMode'
import { CompareMode } from './components/compare/CompareMode'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<AnnotateMode />} />
      <Route path="/compare" element={<CompareMode />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  )
}
```

Top bar (`src/components/shared/TopBar.tsx`) must show navigation links:
- "Annotate" → `/`
- "Compare" → `/compare`

State isolation test: navigate Annotate → Compare → back to Annotate.
Verify `playbackStore` retains `activeSpeaker`. Verify `enrichmentStore` does not reset.

---

### C3 — Store Persistence Regression

```typescript
// src/__tests__/storePersistence.test.ts
describe('Cross-session persistence', () => {
  it('annotationStore dirty intervals survive component remount', () => { ... })
  it('tagStore tags survive navigation to compare and back', () => { ... })
  it('configStore does not re-fetch if already loaded', () => { ... })
  it('playbackStore resets currentTime to 0 when activeSpeaker changes', () => { ... })
})
```

---

### C4 — Python API Regression Suite

These are automated HTTP tests against the live Python server.
Run with Python backend running on :8766.

```typescript
// src/__tests__/apiRegression.test.ts
// Uses vitest with global fetch — must run against live :8766
describe('Python API regression', () => {
  it('GET /api/config returns project_name', async () => {
    const r = await fetch('http://localhost:8766/api/config')
    const d = await r.json()
    expect(d.project_name).toBeTruthy()
  })

  it('GET /api/annotations/Fail01 returns valid annotation record', async () => {
    const r = await fetch('http://localhost:8766/api/annotations/Fail01')
    const d = await r.json()
    expect(d.speaker).toBe('Fail01')
    expect(d.tiers).toBeDefined()
  })

  it('POST /api/annotations/Fail01 round-trips data', async () => {
    const r1 = await fetch('http://localhost:8766/api/annotations/Fail01')
    const original = await r1.json()
    const r2 = await fetch('http://localhost:8766/api/annotations/Fail01', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(original),
    })
    expect(r2.status).toBe(200)
  })

  it('GET /api/enrichments returns data', async () => {
    const r = await fetch('http://localhost:8766/api/enrichments')
    const d = await r.json()
    expect(d).toBeDefined()
  })
})
```

Run: `npm run test -- src/__tests__/apiRegression.test.ts`
**Expected:** 4 passed. If any fail, the Python API is not running — check `:8766`.

---

### C5 — LingPy TSV Export Verification

This is the primary thesis output. Must be verified manually by Lucas.

```bash
# With both Vite dev server and Python server running:
# 1. Navigate to /compare
# 2. Click Export → LingPy TSV
# 3. Open downloaded file in spreadsheet
# Verify columns: ID, DOCULECT, CONCEPT, IPA, COGID, TOKENS, NOTE
# Verify row count matches expected concept × speaker count
# Verify IPA values match annotations for known speakers (e.g. Fail01)
```

---

### C6 — Full Regression Checklist (Lucas runs personally)

**Annotate Mode:**
- [ ] Waveform loads for each of: Fail01, Fail02, Kalh01, Mand01, Qasr01, Saha01
- [ ] Play/pause works without audio glitch
- [ ] Drag region → annotation tier updates
- [ ] Edit IPA cell → auto-save within 1s
- [ ] STT pipeline runs to completion (≥1 concept)
- [ ] Import TextGrid → tiers populate
- [ ] Export CSV → valid file
- [ ] Hard refresh → all annotations preserved
- [ ] Onboarding wizard completes for a new test speaker

**Compare Mode:**
- [ ] ConceptTable renders for all T1 speakers
- [ ] Accept/Reject/Split/Merge all save to enrichments
- [ ] TagManager creates/edits/deletes tag
- [ ] TagManager concept assignment persists after page reload
- [ ] EnrichmentsPanel shows computed values
- [ ] Export LingPy TSV → valid file (correct headers, non-empty)

**Cross-mode:**
- [ ] Navigate Annotate → Compare → Annotate — no state loss
- [ ] Python server port 8766 stays connected throughout

---

### C7 — Final Cleanup

1. Delete old HTML/JS files (ONLY after C6 checklist is 100% green):
   ```bash
   git rm parse.html compare.html
   git rm -r js/
   ```
2. Update `python/server.py` to serve `dist/index.html` as the fallback (Vite build output):
   ```python
   # In static file handler, return dist/index.html for non-/api/ paths
   # Lucas approves this change before merge
   ```
3. Update `start_parse.sh` to run `npm run build` before starting server (production mode).
4. Update `README.md` with new dev workflow:
   - `npm install` (once)
   - Terminal 1: `python python/server.py --project-root /path/to/data`
   - Terminal 2: `npm run dev`
   - Open `http://localhost:5173`
5. Commit:
   ```bash
   git add -A
   git commit -m "feat: React + Vite pivot complete — Annotate + Compare modes"
   git tag v2.0.0-react
   ```

---

## Parallel Execution Summary

```
Day 0.5:  Phase 0 — ParseBuilder writes contract; Oda reviews; Lucas approves store shapes
          ┌──────────────────────────────────────────────────────────────┐
Days 1–4: │ Track A (ParseBuilder+Codex) │ Track B (Oda+Gemini Flash/Pro) │
          │  A1 useWaveSurfer            │  B1 ConceptTable (Pro)         │
          │  A2 annotationStore          │  B2 CognateControls            │
          │  A3 RegionManager            │  B3 BorrowingPanel             │
          │  A4 AnnotationPanel          │  B4 TagManager (Pro)           │
          │  A5 TranscriptPanel          │  B5 EnrichmentsPanel           │
          │  A6 SuggestionsPanel         │  B6 SpeakerImport              │
          │  A7 OnboardingFlow           │  B7 Export wiring              │
          │  A8 useImportExport          │  B8 CompareMode root           │
          │  A9 ChatPanel                │  B9 Track B integration test   │
          │  A10 AnnotateMode root       │                                │
          │  A11 Track A integration     │                                │
          └──────────────────────────────────────────────────────────────┘
Days 5–6:  Phase C — Merge, wire, regression suite
Day 7:     C6 — Lucas full regression checklist
Day 8–9:  Buffer / fix failures from C6
Day 10:    C7 — Final cleanup, tag v2.0.0-react
```

---

## Failure Modes and Mitigation

| Risk | Probability | Mitigation |
|---|---|---|
| WaveSurfer React strict mode double-mount | High | `useEffect` cleanup destroys instance; see A1 pattern |
| Store shapes diverge between tracks | Medium | Phase 0 gate — Oda must sign off before any coding starts |
| API proxy not forwarding audio correctly | Medium | Test early: `curl http://localhost:5173/audio/Fail01/...` |
| `tagStore` breaks localStorage migration | Medium | `hydrate()` wraps read in try/catch; migrates old key |
| LingPy TSV export endpoint not in Python server | Low | Check server.py export routes; if missing, flag before Track B B7 |
| Track merge conflicts in shared stores | Low | Stores are in `src/stores/` — only ParseBuilder touches them |
| TypeScript strict mode incompatibility | Low | `tsconfig.json` strict: true from day 0; fix at creation not after |

---

## What Lucas Must Test Himself (Not Automatable)

1. **Waveform audio playback** — browsers vary; jsdom cannot test this
2. **Region dragging** — requires mouse interaction
3. **STT job end-to-end** — requires GPU + live model
4. **LingPy TSV correctness** — requires domain knowledge to verify IPA/COGID values
5. **Annotation round-trip for each T1 speaker** — requires actual annotation files
6. **Store shape approval** — Phase 0 gate, Lucas must sign off in writing

---

## Agent Assignment Summary

| Phase | Agent | Model | Task |
|---|---|---|---|
| 0.1–0.5 | ParseBuilder + Codex | codex | Scaffold, store types, API client, shared components |
| A1 | ParseBuilder + Codex | codex | `useWaveSurfer` hook |
| A2 | ParseBuilder + Codex | codex | `annotationStore` + `useAnnotationSync` |
| A3 | ParseBuilder + Codex | codex | `RegionManager` |
| A4–A5 | ParseBuilder + Codex | codex | `AnnotationPanel`, `TranscriptPanel` |
| A6 | ParseBuilder + Codex | codex | `SuggestionsPanel` |
| A7 | ParseBuilder + Codex | codex | `OnboardingFlow` |
| A8 | ParseBuilder + Codex | codex | `useImportExport` |
| A9 | ParseBuilder + Codex | codex | `ChatPanel` + `useChatSession` |
| A10–A11 | ParseBuilder + Codex | codex | `AnnotateMode` root + integration |
| B1 | Oda + Gemini | gemini-2.5-pro | `ConceptTable` |
| B2–B3 | Oda + Gemini | gemini-2.5-flash | `CognateControls`, `BorrowingPanel` |
| B4 | Oda + Gemini | gemini-2.5-pro | `TagManager` |
| B5–B6 | Oda + Gemini | gemini-2.5-flash | `EnrichmentsPanel`, `SpeakerImport` |
| B7–B8 | Oda + Gemini | gemini-2.5-flash | Export wiring, `CompareMode` root |
| B9 | Oda + Gemini | gemini-2.5-flash | Track B integration test |
| C1–C7 | ParseBuilder (leads) | codex | Merge, regression, cleanup |
