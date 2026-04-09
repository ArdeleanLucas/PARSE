# ParseBuilder — Personal TODO

> **Owner:** ParseBuilder (@parse-builder)
> **Domain:** Annotate mode + shared platform (waveform, spectrogram, phonetic tools)
> **Updated:** 2026-04-10

---

## 🔒 Blocked

### MC-299 — C6 Browser Regression Checklist
> Waiting on Lucas / C5 clearance. See `docs/plans/phase4-c5-c6-signoff-checklist.md` (PR #7).

When Lucas signals C5 cleared:
- [ ] Annotate: real audio loads, waveform renders
- [ ] Annotate: IPA/ortho pre-populate from store on concept/speaker change
- [ ] Annotate: region draw → Save Annotation round-trip persists to disk
- [ ] Annotate: STT from Actions menu populates IPA field
- [ ] Annotate: Mark Done → concept dot turns green
- [ ] Compare: speaker forms table shows real IPA (not mock data) ✓ wired
- [ ] Compare: Accept/Flag concept writes to tagStore ✓ wired
- [ ] Compare: Export LingPy TSV downloads correctly (also C5 gate)
- [ ] Chat: send message → real xAI response

---

## ✅ Done

- [x] **MC-299 prep** — ParseUI integration tests, 111/111 passing · PR #12 (2026-04-10)
- [x] **Compare notes** — localStorage persistence per concept · PR #12 (2026-04-10)
- [x] **Compare real data** — MOCK_FORMS → `buildSpeakerForm` from `annotationRecords` · PR #12 (2026-04-10)
- [x] **MC-297** — `spectrogram-worker.ts` (TS port) + `useSpectrogram` hook + AnnotateView canvas · PR #11 (2026-04-10)
- [x] **MC-298** — `server.py` startup messaging — React `:5173` + legacy fallback labels · main `b930b1b`
- [x] **MC-296** — ParseUI stale reference cleanup · PR #9
- [x] **MC-295** — Annotate wiring: IPA/ortho pre-populate, Save (setInterval × 3 tiers + saveSpeaker), Mark Done (tagConcept), Annotated/Missing badge · PR #9 + #11
- [x] **MC-294** — ParseUI unified shell (1482-line React UI, Tailwind, lucide-react, all stores/hooks wired) · PR #9

---

## Test baseline (main, 2026-04-10)

```
npm run test -- --run   →  111 / 111 passing
tsc --noEmit            →  0 errors
```

## Status

All ParseBuilder tasks complete. **MC-299 activates on Lucas's C5 signal.**
