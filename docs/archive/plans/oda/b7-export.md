# B7 — useExport

**Model:** gemini-2.5-flash
**Output:** `src/hooks/useExport.ts` + `useExport.test.ts`

---

## What It Is

Handles all export formats available from Compare Mode.
LingPy TSV is P0 — implement and verify it first before writing any other export.

---

## Pre-implementation Check (mandatory)

Before writing any code:

```bash
curl http://localhost:8766/api/export/lingpy
```

- Returns 200 → proceed.
- Returns 404 → **STOP. Report to ParseBuilder and Lucas immediately.**
  Do not stub, mock, or defer. Track B does not ship without a working LingPy TSV export.

Same check for NEXUS:

```bash
curl http://localhost:8766/api/export/nexus
```

---

## Interface

```typescript
export function useExport() {
  // LingPy TSV — P0 — calls client.ts getLingPyExport()
  // GET /api/export/lingpy → triggers file download
  const exportLingPyTSV: () => Promise<void>

  // NEXUS — calls client.ts getNEXUSExport()
  // GET /api/export/nexus → triggers file download
  const exportNEXUS: () => Promise<void>

  // CSV — client-side only
  // Reads enrichmentStore.data, builds CSV blob, triggers download
  // Columns: ID, DOCULECT, CONCEPT, IPA, COGID, TOKENS, NOTE
  const exportCSV: () => void

  return { exportLingPyTSV, exportNEXUS, exportCSV }
}
```

---

## Download Trigger Pattern

```typescript
function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
```

---

## Required Tests

```typescript
describe('useExport', () => {
  it('exportCSV triggers a browser download', () => { ... })
  it('exportCSV blob contains correct column headers: ID DOCULECT CONCEPT IPA COGID TOKENS NOTE', () => { ... })
  it('exportLingPyTSV calls client.ts getLingPyExport', () => { ... })
  it('exportNEXUS calls client.ts getNEXUSExport', () => { ... })
})
```

Run: `npm run test -- useExport`
Expected: 4 passed, 0 failed.
