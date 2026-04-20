# ParseBuilder — Personal TODO

> **Owner:** ParseBuilder (@parse-builder)
> **Domain:** Annotate mode + shared platform (waveform, spectrogram, phonetic tools)
> **Updated:** 2026-06-14

---

## Current execution plan

- Live execution guide: `docs/plans/parseui-current-state-plan.md`
- Historical archive only: `docs/plans/parseui-wiring-todo.md`
- Short version: most early ParseUI wiring tasks are already done; the remaining work is contract reconciliation around Actions / compute / decisions, followed by C5/C6 evidence.

---

## 🔒 Blocked

### MC-299 — C6 Browser Regression Checklist
> Waiting on Lucas / C5 clearance. See `docs/plans/phase4-c5-c6-signoff-checklist.md`.

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

- [x] **AI login wired** — xAI key form, real `saveApiKey()` → `POST /api/auth/key`, `chatSession.messages` display, key persisted to server config · PR #22 (2026-04-10)
- [x] **AI connect panel** — xAI/OpenAI provider selection, connection state machine, welcome greeting · PR #20 → fixed base in PR #21 (2026-04-10)
- [x] **`/api/onboard/speaker`** — multipart POST, background job, saves audio + CSV, scaffolds annotation, registers in `source_index.json` · main (2026-04-10)
- [x] **`src/main.tsx` CSS import** — `import './index.css'` missing, Tailwind not loading · main (2026-04-10)
- [x] **MC-301** — Actions menu Import Speaker Data → modal with `SpeakerImport` · PR #18 (2026-04-10)
- [x] **MC-299 prep** — ParseUI integration tests, 111/111 passing · PR #12 (2026-04-10)
- [x] **Compare notes** — localStorage persistence per concept · PR #12 (2026-04-10)
- [x] **Compare real data** — MOCK_FORMS → `buildSpeakerForm` from `annotationRecords` · PR #12 (2026-04-10)
- [x] **MC-297** — `spectrogram-worker.ts` (TS port) + `useSpectrogram` hook + AnnotateView canvas · PR #11 (2026-04-10), UI wiring PR #31 (2026-06-14)
- [x] **MC-298** — `server.py` startup messaging — React `:5173` + legacy fallback labels · main `b930b1b`
- [x] **MC-296** — ParseUI stale reference cleanup · PR #9
- [x] **MC-295** — Annotate wiring: IPA/ortho pre-populate, Save (setInterval × 3 tiers + saveSpeaker), Mark Done (tagConcept), Annotated/Missing badge · PR #9 + #11
- [x] **MC-294** — ParseUI unified shell (1482-line React UI, Tailwind, lucide-react, all stores/hooks wired) · PR #9

---

## Test baseline (main, 2026-04-10)

```
npm run test -- --run   →  119 / 119 passing (23 files)
tsc --noEmit            →  0 errors
```

## PR workflow

- Branch → push → `gh pr create --base main --reviewer TrueNorth49` under TarahAssistant
- Never push directly to main
- Deploy: `bash parse-deploy.sh` after merge (pulls `parse_v2` from `origin/main`)

## Status

AI login wired and deployed. MC-297 spectrogram UI wired (PR #31). **MC-299 activates on Lucas's C5 signal.**
