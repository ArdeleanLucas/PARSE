# ParseBuilder — Personal TODO

> **Owner:** ParseBuilder (@parse-builder)
> **Domain:** Annotate mode + shared platform (waveform, spectrogram, phonetic tools)
> **Branch:** `feat/annotate-ui-redesign`
> **Updated:** 2026-05-14

---

## 🔴 Active — In Progress

### MC-295 — ParseUI: Annotate wiring (IPA/ortho + Save + Mark Done + Missing badge)
**Priority: thesis-critical**

- [ ] Load IPA/ortho from `annotationStore.records[speaker]` on concept/speaker change — pre-populate fields
- [ ] Wire Save Annotation button → create intervals in `tiers.ipa`, `tiers.ortho`, `tiers.concept` → call `saveSpeaker()`
- [ ] Wire Mark Done button → `tagStore.tagConcept('confirmed', concept.id.toString())`
- [ ] Make Missing badge reactive — check `annotationStore` for existing interval vs concept name

**Files:** `src/ParseUI.tsx` (AnnotateView component, lines ~498–780)
**Hooks/stores:** `useAnnotationStore`, `useTagStore`, `usePlaybackStore` (for `selectedRegion`)

---

### MC-296 — ParseUI: Stale reference cleanup
**Priority: quick win — do first**

- [ ] Line 863: `CONCEPTS.find(...)` → `concepts.find(...)`
- [ ] Line 865: `CONCEPTS.length` → `concepts.length`
- [ ] Line 1300: `SPEAKERS.length` → `speakers.length`
- [ ] Lines 451–468: delete stale JSDoc block about mock waveform
- [ ] Lines 592–595: delete stale `TODO: Replace mock` comment
- [ ] Line 127 (AIChat useEffect): `[messages, minimized]` → `[chatSession.messages, minimized]`

**Files:** `src/ParseUI.tsx`
**Time estimate:** 15 min

---

### MC-297 — Spectrogram Worker — TypeScript port + `useSpectrogram` hook
**Priority: post-thesis unless Lucas needs it for C6**

- [ ] Create `src/workers/spectrogram-worker.ts` — port from `js/shared/spectrogram-worker.js` (273 lines, STFT/FFT Cooley-Tukey)
  - Add TypeScript types for message protocol: `{ type: 'compute', audioData: Float32Array, sampleRate, windowSize, startSec, endSec }`
  - Output: `{ type: 'result', imageData: Uint8ClampedArray, width, height, startSec, endSec }`
- [ ] Create `src/hooks/useSpectrogram.ts`
  - Manages Worker lifecycle (create on mount, terminate on unmount)
  - Accepts `wsRef` (from useWaveSurfer) to get decoded audio buffer
  - Posts PCM window to worker when `spectroOn` is true
  - Returns `{ canvasRef, ready }` — caller mounts canvas as overlay
- [ ] Wire into `AnnotateView` — replace CSS gradient placeholder with real canvas overlay
- [ ] Run `npm run check` — clean compile required

**Files:** `src/workers/spectrogram-worker.ts` (new), `src/hooks/useSpectrogram.ts` (new), `src/ParseUI.tsx`
**Reference:** `parse/js/shared/spectrogram-worker.js` — copy the FFT logic, type it up

---

## 🟡 Pending — Waiting on Lucas or other gates

### MC-298 — `server.py` startup messaging cleanup (Phase 3.2 of cleanup plan)
**Blocked by:** Phase 3 non-destructive PR not yet merged
**Gate:** Non-destructive, can open PR anytime

- [ ] Update `python/server.py` startup output — label `/parse.html` + `/compare.html` as legacy fallback
- [ ] Add React dev guidance in startup: `http://localhost:5173/` and `http://localhost:5173/compare`
- [ ] Explicitly separate: legacy serving vs React dev vs (future) built dist serving

**Files:** `python/server.py`
**PR:** Open to `main` — Lucas merges

---

### MC-299 — C6 Browser Regression Checklist Prep
**Blocked by:** Lucas ready to do C6 signoff
**Gate:** C5 must be cleared first

When Lucas is ready, I prepare and walk through:

- [ ] Annotate: waveform loads real audio for a real speaker
- [ ] Annotate: regions can be drawn, IPA/ortho can be typed and saved
- [ ] Annotate: STT runs from Actions menu, results populate fields
- [ ] Annotate: Mark Done tags concept as confirmed
- [ ] Annotate: concept list updates dot color after tagging
- [ ] Compare: speaker forms table shows real IPA (not mock data)
- [ ] Compare: Accept/Flag concept writes to tagStore
- [ ] Compare: Export LingPy TSV downloads correctly (this is C5 too)
- [ ] Chat: send a message, get a real response from xAI

**Files:** `docs/plans/repo-state-cleanup-and-architecture-unification.md` (Task 4.2)

---

## ✅ Done

- [x] **MC-294** — ParseUI unified shell — 1482-line React UI, Tailwind + lucide-react installed, initial store/hook wiring, `feat/annotate-ui-redesign` branch, tsc clean (2026-05-14)
- [x] All Phase C1–C4 pivot integration work (see `react-vite-pivot.md`)
- [x] `useWaveSurfer` hook — full implementation with RegionsPlugin + TimelinePlugin
- [x] All Annotate mode hooks: `useAnnotationSync`, `useChatSession`, `useImportExport`, `useSuggestions`
- [x] `annotationStore`, `configStore`, `playbackStore`, `uiStore`, `tagStore`

---

## Order of attack

1. **MC-296** — stale cleanup (15 min, unblocks everything else compiling cleanly)
2. **MC-295** — annotate wiring (core thesis workflow)
3. **MC-298** — server.py messaging (quick, non-destructive, open PR to main)
4. **MC-297** — spectrogram (when annotate wiring is stable)
5. **MC-299** — when Lucas signals C5 cleared
