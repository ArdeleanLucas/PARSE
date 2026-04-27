# Phase 0 — Scaffold Gate, Store Shapes, API Contract

> **Archived Oda Track B phase note (2026-04-21):** this file records the original scaffold gate for the Compare-track pivot. Do **not** execute it as a live prerequisite checklist. Current PARSE work starts from `origin/main` and uses the landed React runtime.
>
> Load this file at the start of Track B. Block until the gate passes.
> After Phase 0 is confirmed, you only need the specific Bx file for each task.

---

## Gate — You Block Here

Before writing any component code, ParseBuilder must have committed:

- `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) — typed fetch wrapper
- `src/api/types.ts` — shared TypeScript interfaces
- All six Zustand store files (types stubbed, no implementation needed)
- `vite.config.ts` with `/api/*` proxy to `:8766`
- `package.json` with all dependencies
- `index.html` + `src/main.tsx` + `src/App.tsx`

**Run these three checks. All must pass before you begin:**

```bash
npm install
npm run dev
# Expected: Vite server starts on :5173

curl http://localhost:5173/api/config
# Expected: JSON response from Python — proves proxy to :8766 works

npx tsc --noEmit
# Expected: zero errors
```

If any fail, stop and tell ParseBuilder what failed. Do not begin Track B.

---

## tagStore — You Implement

```typescript
// src/stores/tagStore.ts

interface Tag {
  id: string;           // uuid — generated with crypto.randomUUID()
  label: string;
  color: string;        // hex string e.g. '#3b82f6'
  concepts: string[];   // concept IDs carrying this tag
}

interface TagStore {
  tags: Tag[];

  // Mutations
  addTag: (label: string, color: string) => Tag;
  removeTag: (id: string) => void;
  updateTag: (id: string, patch: Partial<Pick<Tag, 'label' | 'color'>>) => void;
  tagConcept: (tagId: string, conceptId: string) => void;
  untagConcept: (tagId: string, conceptId: string) => void;

  // Queries
  getTagsForConcept: (conceptId: string) => Tag[];
  getConceptsForTag: (tagId: string) => string[];

  // Persistence
  persist: () => void;   // write to localStorage key 'parse-tags-v2'
  hydrate: () => void;   // read from localStorage; migrate 'parse-tags-v1' if present
}
```

**Implementation rules:**
- `persist()` called after every mutation — use Zustand middleware or explicit call.
- `hydrate()` called once on app boot:
  - `parse-tags-v2` exists → use it
  - `parse-tags-v2` missing, `parse-tags-v1` exists → migrate to v2 format, write v2 key
  - Both missing → initialize `tags: []`
  - Malformed JSON → swallow error, initialize empty
- `addTag` → generate fresh UUID via `crypto.randomUUID()`
- `removeTag` → also removes tag ID from all `concepts` arrays
- `updateTag` → never changes `id` or `concepts`

---

## enrichmentStore — You Implement

```typescript
// src/stores/enrichmentStore.ts

import type { EnrichmentsPayload } from '../api/types'  // ParseBuilder defines this shape

interface EnrichmentStore {
  data: EnrichmentsPayload | null;
  loading: boolean;
  error: string | null;

  load: () => Promise<void>;                             // GET /api/enrichments via client.ts
  save: (patch: Partial<EnrichmentsPayload>) => Promise<void>;  // POST /api/enrichments
  reset: () => void;
}
```

Do not define `EnrichmentsPayload` yourself. Import it from `src/api/types.ts`.

---

## Stores You Consume (Read-Only)

```typescript
// src/stores/uiStore.ts (ParseBuilder's — read only)
uiStore.activeConcept          // string | null — currently selected concept ID
uiStore.setActiveConcept(id)   // call when user clicks a concept cell
uiStore.comparePanel           // 'table' | 'borrowing' | 'enrichments' | 'tags'
uiStore.setComparePanel(p)     // call when user switches sidebar panel

// src/stores/configStore.ts (ParseBuilder's — read only)
configStore.config.speakers    // string[] — ordered speaker ID list
configStore.config.language_code

// src/stores/annotationStore.ts (ParseBuilder's — read only, SpeakerImport only)
annotationStore.records        // preview new speaker's annotations before import
```

---

## Python API Contract

Port 8766. Vite proxies `/api/*`. Never call `fetch()` directly.
Always use functions from `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`).

**Functions you use:**

```typescript
import {
  getEnrichments,     // GET  /api/enrichments
  saveEnrichments,    // POST /api/enrichments
  getConfig,          // GET  /api/config
  startCompute,       // POST /api/compute/{speaker}  → { job_id }
  pollCompute,        // POST /api/compute/{speaker}/status → { status, progress }
  getAuthStatus,      // GET  /api/auth/status
  saveAnnotation,     // POST /api/annotations/{speaker}  (SpeakerImport only)
} from '../api/client'
```

If a function is missing from `client.ts`, tell ParseBuilder what to add.
Do not add fetch calls yourself.

**Full API surface (reference):**

| Method | Path | Used by |
|---|---|---|
| GET | `/api/enrichments` | enrichmentStore.load |
| POST | `/api/enrichments` | enrichmentStore.save |
| GET | `/api/config` | configStore (ParseBuilder) |
| POST | `/api/compute/{speaker}` | useComputeJob |
| POST | `/api/compute/{speaker}/status` | useComputeJob |
| GET | `/api/auth/status` | CompareMode mount |
| POST | `/api/annotations/{speaker}` | SpeakerImport |
| GET | `/api/export/lingpy` | useExport — verify exists before implementing |
| GET | `/api/export/nexus` | useExport — verify exists before implementing |
