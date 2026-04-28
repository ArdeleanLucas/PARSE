---
agent: parse-front-end
queued_by: parse-coordinator
queued_at: 2026-04-28T00:00:00+02:00
status: done
completed_at: 2026-04-28T22:55:36+02:00
related_prs:
  - 172
  - 179
follow_up_prs:
  - 180
handoff_path_note: legacy — file lives under .hermes/handoffs/parse-builder/ even though the agent is parse-front-end
---

# DONE — parse-front-end lexeme save overlap bundle

Completion note, 2026-04-29: PR #179 (`fix: retime lexeme save by overlap`) merged at `5153669` and closed the queued overlap-retime/BND-refresh scope from this handoff. The active queue should no longer point at this file. Open PR #180 (`fix: create missing IPA lexeme interval on save`) is a follow-up for a newly observed missing-IPA-interval edge case and should not be treated as completed until merged.

---

# parse-front-end — Save Annotation silently drops IPA / ORTH text and never retimes BND

> **Legacy pathway note (2026-04-28).** This file is in `.hermes/handoffs/parse-builder/` rather than a parse-front-end folder because the on-disk directory wasn't migrated when the agent role was renamed. New handoffs continue to land here until/unless a PR explicitly creates `.hermes/handoffs/parse-front-end/`.

## Why this exists

PR #172 (`be40440`, "fix(annotate): bundle lexeme save + scope retime") landed a new lexeme save bundle. In dogfood today on `Fail01` / concept `hair` (timestamps `808.689`–`809.623`), Lucas observed two symptoms:

1. The success message reads **"Saved (1 tier updated)"** even after editing IPA + ORTH + concept + BND timestamps.
2. The BND boundary lane and the IPA/ORTH lane bars do not visually move to the new bounds — they stay at the previous positions.

These are two visible faces of one root cause. Worse: the user-typed IPA and Kurdish ORTH text are **silently dropped**, never persisted to the IPA / ortho tier intervals. Only the concept tier interval gets updated.

## Root cause (verified against `main` on `c0d026f`)

Load and save use **different** matchers for the IPA / ORTH / ortho_words tiers.

`findAnnotationForConcept` (in [src/components/annotate/annotate-views/shared.ts](src/components/annotate/annotate-views/shared.ts)) populates the AnnotationPanel by **overlap**:

```ts
const ipaInterval   = (record.tiers.ipa?.intervals ?? []).find((iv) => overlaps(iv, conceptInterval)) ?? null;
const orthoInterval = pickOrthoIntervalForConcept(record, conceptInterval);   // best overlap
```

But `saveLexemeAnnotation` ([src/stores/annotation/actions.ts:262-285](src/stores/annotation/actions.ts:262)) writes back via **exact-bound match** with `±1ms` tolerance:

```ts
// actions.ts:42-47
const MATCH_TOLERANCE_SEC = 0.001;
function findMatchingIntervalIndex(intervals, start, end) {
  return intervals.findIndex(iv =>
    Math.abs(iv.start - start) < MATCH_TOLERANCE_SEC &&
    Math.abs(iv.end - end)   < MATCH_TOLERANCE_SEC);
}

// actions.ts:271-277 — saveLexemeAnnotation
let moved = 0;
if (updateMatchingInterval(clone, "concept",     oldStart, oldEnd, newStart, newEnd, conceptName)) moved += 1;
if (updateMatchingInterval(clone, "ipa",         oldStart, oldEnd, newStart, newEnd, ipaText))     moved += 1;
if (updateMatchingInterval(clone, "ortho",       oldStart, oldEnd, newStart, newEnd, orthoText))   moved += 1;
if (updateMatchingInterval(clone, "ortho_words", oldStart, oldEnd, newStart, newEnd))              moved += 1;
```

`oldStart`/`oldEnd` come from `conceptInterval.start/end` ([AnnotateView.tsx:422-423](src/components/annotate/annotate-views/AnnotateView.tsx:422)). Real PARSE data: IPA / ortho / ortho_words intervals come from independent forced-alignment / STT passes, almost never within 1ms of the concept tier's bounds. So on every real save:

- `concept` → exact-match → updated → `moved = 1`
- `ipa` → no exact match → **skipped silently** (typed IPA text discarded)
- `ortho` → no exact match → **skipped silently** (typed Kurdish ORTH discarded)
- `ortho_words` → no exact match → **skipped silently** → BND lane (derived from `ortho_words` per [TranscriptionLanes.tsx:336](src/components/annotate/TranscriptionLanes.tsx:336)) keeps old boundaries

The PR #172 test [moveInterval.test.ts](src/__tests__/moveInterval.test.ts) seeded all four tiers with identical bounds `(100, 101)` — so it passed; real data doesn't.

`moveIntervalAcrossTiers` (used by the WaveSurfer drag-commit path at [AnnotateView.tsx:166](src/components/annotate/annotate-views/AnnotateView.tsx:166) with `LEXEME_SCOPE_TIERS`) has the same bug.

There is **no `bnd` tier** in the data model — `blankRecord` in [annotationStoreShared.ts:39-50](src/stores/annotationStoreShared.ts:39) defines `ipa_phone, ipa, ortho, ortho_words, stt, concept, sentence, speaker`. The "BND" lane is a *derived* boundary lane built from `ortho_words.intervals`. So `LEXEME_SCOPE_TIERS = ["concept","ipa","ortho","ortho_words"]` is the right scope; the bug is the matcher, not the scope.

## Goal

Make `saveLexemeAnnotation` and the lexeme-scoped path of `moveIntervalAcrossTiers` use the same overlap-based matchers that the load path uses. Concept tier stays exact-match (it defines the lexeme span). IPA / ortho retime by best overlap with the lexeme span. ortho_words rescales every word whose midpoint lies inside the old span, so the BND lane follows the new bounds.

After the fix, a typical save should report `moved >= 3` (concept + IPA + ORTH, and `+1` more if ortho_words has any word inside the span). Lane bars on IPA, ORTH, BND must visibly snap to the new bounds. Reloading the speaker must show the typed IPA / ORTH text persisted in the IPA and ortho tier intervals.

## Working environment

Standard parse-builder rules. AGENTS.md PR #74 + screenshot link convention (PR #89) + refetch before mergeable status (PR #116) + standard validation commands (PR #151).

```text
parse-worktree-new lexeme-save-overlap-bundle
cd /home/lucas/gh/worktrees/lexeme-save-overlap-bundle
git checkout -b fix/lexeme-save-overlap-bundle
```

Verify `git remote -v` shows `ArdeleanLucas/PARSE` before any commit.

## Required validation

- `npx vitest run` — all tests green, including new real-shape tests below
- `./node_modules/.bin/tsc --noEmit` — clean
- `npm run build` — clean
- Browser regression on Lucas's machine (or yours): open `Fail01` annotate view, navigate to concept `hair` (#1 of 521), edit IPA + ORTH text, change start/end to non-trivially different values, click **Save Annotation**. Expected: success message reads `"Saved (3 tiers updated)."` or higher; the BND red `[ [` markers, the IPA lane bar, and the ORTH lane bar all snap to the new bounds. Reload the speaker; typed IPA/ORTH text persists.
- Markdown-link screenshot in `docs/pr-assets/lexeme-save-overlap-bundle-after.png`, linked from PR body.

## Proposed fix (sketch — adapt as you see fit)

### 1. Add overlap + rescale helpers in `src/stores/annotation/actions.ts`

```ts
// IPA / ortho intervals come from independent passes (forced alignment, STT)
// and rarely share exact bounds with the concept span. Locate them by best
// overlap — the same rule findAnnotationForConcept uses for the panel — so
// save and load agree on which interval belongs to the lexeme.
function findBestOverlapIntervalIndex(
  intervals: AnnotationInterval[],
  start: number,
  end: number,
): number {
  let bestIdx = -1;
  let bestOverlap = 0;
  for (let i = 0; i < intervals.length; i += 1) {
    const iv = intervals[i];
    if (iv.end <= start || iv.start >= end) continue;
    const ov = Math.min(iv.end, end) - Math.max(iv.start, start);
    if (ov > bestOverlap) {
      bestOverlap = ov;
      bestIdx = i;
    }
  }
  return bestIdx;
}

function retimeOverlappingInterval(
  record: AnnotationRecord,
  tierKey: string,
  oldStart: number,
  oldEnd: number,
  newStart: number,
  newEnd: number,
  text?: string,
): boolean {
  const tier = record.tiers[tierKey];
  if (!tier) return false;
  const idx = findBestOverlapIntervalIndex(tier.intervals, oldStart, oldEnd);
  if (idx < 0) return false;
  tier.intervals[idx] = {
    ...tier.intervals[idx],
    start: newStart,
    end: newEnd,
    manuallyAdjusted: true,
    ...(text !== undefined ? { text } : {}),
  };
  tier.intervals.sort((a, b) => a.start - b.start);
  return true;
}

// ortho_words can hold several word boundaries inside one lexeme span; rescale
// every word whose midpoint falls inside the old span so the BND lane follows
// the new bounds.
function rescaleAssociatedIntervals(
  record: AnnotationRecord,
  tierKey: string,
  oldStart: number,
  oldEnd: number,
  newStart: number,
  newEnd: number,
): number {
  const tier = record.tiers[tierKey];
  if (!tier) return 0;
  const oldDur = oldEnd - oldStart;
  if (oldDur <= 0) return 0;
  const newDur = newEnd - newStart;
  let count = 0;
  for (let i = 0; i < tier.intervals.length; i += 1) {
    const iv = tier.intervals[i];
    const mid = (iv.start + iv.end) / 2;
    if (mid < oldStart - MATCH_TOLERANCE_SEC) continue;
    if (mid > oldEnd + MATCH_TOLERANCE_SEC) continue;
    const fStart = Math.max(0, Math.min(1, (iv.start - oldStart) / oldDur));
    const fEnd   = Math.max(0, Math.min(1, (iv.end   - oldStart) / oldDur));
    tier.intervals[i] = {
      ...iv,
      start: newStart + fStart * newDur,
      end:   newStart + fEnd   * newDur,
      manuallyAdjusted: true,
    };
    count += 1;
  }
  if (count > 0) tier.intervals.sort((a, b) => a.start - b.start);
  return count;
}

function isLexemeScope(scope: readonly string[] | undefined): boolean {
  if (!scope) return false;
  if (scope.length !== LEXEME_SCOPE_TIERS.length) return false;
  return LEXEME_SCOPE_TIERS.every((t) => scope.includes(t));
}

function applyLexemeRetime(
  record: AnnotationRecord,
  oldStart: number,
  oldEnd: number,
  newStart: number,
  newEnd: number,
  texts?: { conceptName?: string; ipaText?: string; orthoText?: string },
): number {
  let moved = 0;
  if (updateMatchingInterval(record, "concept", oldStart, oldEnd, newStart, newEnd, texts?.conceptName)) moved += 1;
  if (retimeOverlappingInterval(record, "ipa",   oldStart, oldEnd, newStart, newEnd, texts?.ipaText))    moved += 1;
  if (retimeOverlappingInterval(record, "ortho", oldStart, oldEnd, newStart, newEnd, texts?.orthoText))  moved += 1;
  if (rescaleAssociatedIntervals(record, "ortho_words", oldStart, oldEnd, newStart, newEnd) > 0)         moved += 1;
  return moved;
}
```

### 2. Rewrite the two action methods to use `applyLexemeRetime`

```ts
moveIntervalAcrossTiers: (speaker, oldStart, oldEnd, newStart, newEnd, tierScope) => {
  if (!Number.isFinite(newStart) || !Number.isFinite(newEnd)) return 0;
  if (newEnd < newStart) return 0;

  const pre = selectSpeakerRecord(get(), speaker);
  if (!pre) return 0;

  const clone = deepClone(pre);
  let moved = 0;

  if (isLexemeScope(tierScope)) {
    moved = applyLexemeRetime(clone, oldStart, oldEnd, newStart, newEnd);
  } else {
    // Preserve generic full-tier-walk behavior for non-lexeme scopes / no scope.
    const allowedTiers = tierScope ? new Set(tierScope) : null;
    for (const [tierKey, tier] of Object.entries(clone.tiers)) {
      if (allowedTiers && !allowedTiers.has(tierKey)) continue;
      const idx = findMatchingIntervalIndex(tier.intervals, oldStart, oldEnd);
      if (idx < 0) continue;
      tier.intervals[idx] = {
        ...tier.intervals[idx],
        start: newStart,
        end: newEnd,
        manuallyAdjusted: true,
      };
      tier.intervals.sort((a, b) => a.start - b.start);
      moved += 1;
    }
  }

  if (moved === 0) return 0;
  clone.modified_at = nowIsoUtc();
  commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "retime lexeme");
  return moved;
},

saveLexemeAnnotation: ({ speaker, oldStart, oldEnd, newStart, newEnd, ipaText, orthoText, conceptName }) => {
  if (!Number.isFinite(newStart) || !Number.isFinite(newEnd) || newEnd <= newStart) {
    return { ok: false, error: "End must be greater than start." };
  }

  const pre = selectSpeakerRecord(get(), speaker);
  if (!pre) return { ok: false, error: "Speaker record not loaded." };

  const clone = deepClone(pre);
  const moved = applyLexemeRetime(clone, oldStart, oldEnd, newStart, newEnd, {
    conceptName, ipaText, orthoText,
  });

  if (moved === 0) {
    return { ok: false, error: "No matching lexeme intervals found." };
  }

  clone.modified_at = nowIsoUtc();
  commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "save lexeme annotation");
  return { ok: true, moved };
},
```

### 3. Test-first: add real-shape tests in `src/__tests__/moveInterval.test.ts`

The existing tests use synthetic identical-bounds data and will continue to pass with the new logic. Add a real-shape test where the IPA / ortho / ortho_words intervals have **different** bounds from the concept span — that is the case the current code silently fails on:

```ts
function seedFail02RealShape() {
  // Real-world: ipa/ortho/ortho_words have their own boundaries from
  // independent STT/forced-alignment passes that don't coincide with the
  // concept span. This is what real PARSE annotation files look like.
  useAnnotationStore.setState({
    records: {
      Fail02: {
        speaker: "Fail02",
        tiers: {
          ipa: {
            name: "ipa", display_order: 1,
            intervals: [
              { start: 99.50, end: 99.95, text: "prev" },
              { start: 99.95, end: 101.10, text: "hɪr" },
              { start: 101.20, end: 101.50, text: "next" },
            ],
          },
          ortho: {
            name: "ortho", display_order: 2,
            intervals: [{ start: 99.90, end: 101.05, text: "هەر" }],
          },
          ortho_words: {
            name: "ortho_words", display_order: 3,
            intervals: [
              { start: 99.90, end: 100.50, text: "" },
              { start: 100.50, end: 101.05, text: "" },
              { start: 101.20, end: 101.50, text: "" },   // outside lexeme span
            ],
          },
          concept: {
            name: "concept", display_order: 4,
            intervals: [{ start: 100.000, end: 101.000, text: "hair" }],
          },
          speaker: {
            name: "speaker", display_order: 5,
            intervals: [{ start: 0, end: 200, text: "Fail02" }],
          },
        },
        created_at: "2026-01-01T00:00:00Z",
        modified_at: "2026-01-01T00:00:00Z",
        source_wav: "x.wav",
      },
    },
    dirty: {}, loading: {}, histories: {},
  });
}

describe("annotationStore.saveLexemeAnnotation (real-shape data)", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {}, histories: {} });
  });

  it("retimes IPA/ORTH by overlap and scales ortho_words by midpoint when bounds differ from concept", () => {
    seedFail02RealShape();
    const result = useAnnotationStore.getState().saveLexemeAnnotation({
      speaker: "Fail02",
      oldStart: 100, oldEnd: 101,
      newStart: 200, newEnd: 202,
      ipaText: "ndʒə",
      orthoText: "نوێ",
      conceptName: "hair",
    });
    expect(result).toEqual({ ok: true, moved: 4 });

    const rec = useAnnotationStore.getState().records["Fail02"];

    // concept: exact-match retimed.
    expect(rec.tiers.concept.intervals[0]).toMatchObject({
      start: 200, end: 202, text: "hair", manuallyAdjusted: true,
    });

    // ipa: only the overlapping interval is moved + retexted; siblings untouched.
    const movedIpa = rec.tiers.ipa.intervals.find((iv) => iv.text === "ndʒə");
    expect(movedIpa).toMatchObject({ start: 200, end: 202, manuallyAdjusted: true });
    expect(rec.tiers.ipa.intervals.find((iv) => iv.text === "prev")).toMatchObject({ start: 99.50, end: 99.95 });
    expect(rec.tiers.ipa.intervals.find((iv) => iv.text === "next")).toMatchObject({ start: 101.20, end: 101.50 });

    // ortho: best-overlap interval retimed and text replaced.
    expect(rec.tiers.ortho.intervals[0]).toMatchObject({
      start: 200, end: 202, text: "نوێ", manuallyAdjusted: true,
    });

    // ortho_words: two intervals inside the lexeme span scaled proportionally;
    // outside-the-span interval untouched.
    const words = [...rec.tiers.ortho_words.intervals].sort((a, b) => a.start - b.start);
    expect(words).toHaveLength(3);
    // outside (101.20, 101.50) — untouched, sorts first after rescaling moves the others to 200+
    expect(words[0]).toMatchObject({ start: 101.20, end: 101.50 });
    expect(words[0].manuallyAdjusted).toBeFalsy();
    // (99.90, 100.50) — mid 100.20, fStart=clamp(-0.10)=0, fEnd=0.50 → (200, 201)
    expect(words[1].start).toBeCloseTo(200);
    expect(words[1].end).toBeCloseTo(201);
    expect(words[1].manuallyAdjusted).toBe(true);
    // (100.50, 101.05) — mid 100.775, fStart=0.50, fEnd=clamp(1.05)=1 → (201, 202)
    expect(words[2].start).toBeCloseTo(201);
    expect(words[2].end).toBeCloseTo(202);
    expect(words[2].manuallyAdjusted).toBe(true);
  });

  it("returns moved=0 with a clean error when no concept interval matches", () => {
    seedFail02RealShape();
    const result = useAnnotationStore.getState().saveLexemeAnnotation({
      speaker: "Fail02",
      oldStart: 500, oldEnd: 501,
      newStart: 600, newEnd: 601,
      ipaText: "x", orthoText: "y", conceptName: "z",
    });
    expect(result).toEqual({ ok: false, error: "No matching lexeme intervals found." });
  });
});
```

Run **just this test first** (`npx vitest run src/__tests__/moveInterval.test.ts`) and confirm it fails on `main` against the current implementation, then make it pass with the new logic. Existing tests (synthetic identical-bounds) should keep passing throughout.

## Browser repro

After the unit tests pass, prove the fix end-to-end:

1. Start dev server (use Lucas's `parse-run`).
2. Open Annotate for `Fail01`.
3. Navigate to concept #1 (`hair`) — `Fail01.wav`, originally around 13:28.68.
4. Edit IPA → some new value; edit Kurdish ORTH → some new value; change start/end inputs by ≥0.05s.
5. Click **Save Annotation**. Expected: success badge reads `"Saved (3 tiers updated)."` or `"Saved (4 tiers updated)."` (depending on whether `ortho_words` has a word in this lexeme).
6. **Visually confirm**: the BND red `[ [` markers, the IPA lane bar, and the ORTH lane bar all snap to the new bounds. The orange/beige spectrogram region also lines up.
7. Reload the speaker (or close + reopen). Confirm typed IPA + ORTH text persists in their respective tiers, not just the concept tier.
8. Markdown-link screenshot to `docs/pr-assets/lexeme-save-overlap-bundle-after.png`.

## Scope guardrails

- Do **not** change the public `SaveLexemeAnnotationPayload` shape — keep `oldStart`/`oldEnd` as concept bounds (caller already passes that).
- Do **not** alter the `LEXEME_SCOPE_TIERS` constant.
- Do **not** rename `moveIntervalAcrossTiers` or its return type — preserve API.
- Do **not** touch `pickOrthoIntervalForConcept` / `findAnnotationForConcept` — load logic is correct; this fix aligns save with load.
- Do **not** widen the change to other annotation actions (`updateInterval`, `setInterval`, etc.) — they are correct.

## What comes after this lands

- Optional polish: change the success message wording to match the new accuracy ("Saved (3 tiers retimed: concept + IPA + ORTH)") — flag in PR body, not required.
- Re-audit `markLexemeManuallyAdjusted` for the same overlap-vs-exact issue — separate PR if needed.

## Origin

Diagnosed by opus-coordinator on 2026-04-28 from a screenshot Lucas posted of `Fail01` / `hair` showing `"Saved (1 tier updated)"` after multi-field edit. Full diagnosis with file:line evidence is in the linked PR body when this handoff is opened.
