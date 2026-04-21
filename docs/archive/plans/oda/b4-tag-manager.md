# B4 — TagManager

> **Archived Oda Track B task brief (2026-04-21):** this file is historical implementation scaffolding from the Compare-track React pivot. Do **not** execute it as a live task. Current PARSE work branches from `origin/main`, and the landed Compare code lives in `src/components/compare/`, `src/hooks/`, and `AGENTS.md`.

**Model:** gemini-2.5-pro (non-trivial master-detail UI + multi-store state)
**Read first:** `js/shared/tags.js` (845 lines), `js/compare/compare.js` (search 'tag')
**Output:** `src/components/compare/TagManager.tsx` + `TagManager.test.tsx`
**Requires:** `tagStore` fully implemented + `enrichmentStore.data.concepts` available.

---

## What It Is

Two-panel master-detail UI. Left = tag list. Right = concept browser filtered by active tag.

---

## Exact Layout (do not deviate)

```
+---------------------+----------------------------------+
| LEFT (Tag Master)   | RIGHT (Concept Browser)          |
+---------------------+----------------------------------+
| [+ New Tag]         | Filter: [___ omnibox search ___] |
|                     |                                  |
| [___ search ___]    | [water] [fire *] [stone *] ...   |
|                     |  chips — * = in active tag       |
| Tag A       (12)    |                                  |
| Tag B  (3)  <active |  [Select All]  [Clear Selection] |
| Tag C        (7)    |                                  |
| (hover: edit | del) |                                  |
+---------------------+----------------------------------+
```

---

## Left Panel Behavior

- `[+ New Tag]` → inline form: label text input + hex color picker + Save button
- Search input → filters tag list by label substring (case-insensitive)
- Each row: `{label}  ({concept count})`
- Clicking a row → makes that tag "active"; right panel filters to its concepts
- One active tag at a time. Clicking active tag again deactivates it (right panel shows all)
- Hover → edit icon (pencil) + delete icon (trash) appear inline
- Edit → inline form pre-filled with current label + color
- Delete → calls `tagStore.removeTag(id)` which also untags all concepts automatically

---

## Right Panel Behavior

- Concept list from `enrichmentStore.data.concepts` (array of `ConceptRow`)
- Omnibox search → filters chips by `concept_label` (case-insensitive)
- Each chip: `concept_label` + checkmark overlay if concept is in active tag
- Click chip (active tag set) → toggle: `tagStore.tagConcept` or `tagStore.untagConcept`
- Click chip (no active tag) → no-op (chips non-interactive without active tag)
- `[Select All]` → tags all currently visible (filtered) chips to active tag
- `[Clear Selection]` → untags all chips in active tag (not filtered — all of them)
- `tagStore.persist()` called after every tag or concept mutation

---

## State Rules

- All tag data lives in `tagStore`. No local component state for tag data.
- No local state for active tag selection — use component `useState` only for
  the active tag ID (UI state, not data state).
- Concept list is read-only from `enrichmentStore` — TagManager never writes enrichments.

---

## Required Tests

```typescript
describe('TagManager', () => {
  it('left panel shows all tags from tagStore with correct counts', () => { ... })
  it('clicking a tag activates it and right panel shows its concepts checked', () => { ... })
  it('clicking an active tag deactivates it', () => { ... })
  it('clicking an unchecked chip calls tagStore.tagConcept', () => { ... })
  it('clicking a checked chip calls tagStore.untagConcept', () => { ... })
  it('omnibox filters concept chips by label substring', () => { ... })
  it('Select All tags all filtered concepts to active tag', () => { ... })
  it('Clear Selection untags all concepts from active tag', () => { ... })
  it('delete tag calls tagStore.removeTag and tag disappears from list', () => { ... })
  it('chips are not clickable when no tag is active', () => { ... })
})
```

Run: `npm run test -- TagManager`
Expected: 10 passed, 0 failed.
