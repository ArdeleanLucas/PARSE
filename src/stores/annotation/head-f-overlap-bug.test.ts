// Regression guard for the persistent-IPA bug on Kalh01 "head (F)".
//
// Reproduces the exact tier state from the workspace JSON
// (annotations/Kalh01.parse.json on the PC) for concept_id "652":
//   - concept tier: [1339.212, 1339.897] text "head (F)"
//   - ipa tier interval A: [1338.775, 1339.495] text "ændeɪdʒ"   (CTC, manuallyAdjusted:false)
//   - ipa tier interval B: [1339.212, 1339.897] text ""          (manuallyAdjusted:true, from a prior save)
//
// Pre-fix: display used `.find()` (first overlap) and returned the CTC chunk,
// while the save path used findBestOverlapIntervalIndex (largest overlap) and
// targeted the empty interval. They disagreed, so user "clear + save" left the
// visible ændeɪdʒ in place. Fix: pickIpaIntervalForConcept aligns display
// with the save target (contained > biggest overlap).

import { describe, expect, it, vi } from "vitest";

import type { AnnotationRecord } from "../../api/types";
import { findAnnotationForConcept } from "../../components/annotate/annotate-views/shared";
import type { Concept } from "../../components/annotate/annotate-views/types";
import { emptyHistory } from "../annotationStoreHistory";
import { createAnnotationActionsSlice } from "./actions";
import type { AnnotationStore, AnnotationStoreSet } from "./types";

const HEAD_F_START = 1339.212;
const HEAD_F_END = 1339.897;
const CTC_IPA_START = 1338.7749999999999;
const CTC_IPA_END = 1339.4950000000001;
const BAD_IPA_TEXT = "ændeɪdʒ";

const HEAD_F_CONCEPT: Concept = { id: 652, key: "652", name: "head (F)" };

function makeKalh01Record(): AnnotationRecord {
  return {
    speaker: "Kalh01",
    source_wav: "Kalh_M_1981.wav",
    created_at: "2026-05-04T00:00:00.000Z",
    modified_at: "2026-05-19T16:42:00.000Z",
    tiers: {
      concept: {
        name: "concept",
        display_order: 6,
        intervals: [
          {
            start: HEAD_F_START,
            end: HEAD_F_END,
            text: "head (F)",
            concept_id: "652",
            manuallyAdjusted: true,
          },
        ],
      },
      ipa: {
        name: "ipa",
        display_order: 1,
        intervals: [
          // CTC-decoded chunk, partial overlap, never manually touched.
          {
            start: CTC_IPA_START,
            end: CTC_IPA_END,
            text: BAD_IPA_TEXT,
            manuallyAdjusted: false,
          },
          // Concept-aligned empty interval from a previous "clear + save" attempt.
          {
            start: HEAD_F_START,
            end: HEAD_F_END,
            text: "",
            manuallyAdjusted: true,
          },
        ],
      },
      ortho: { name: "ortho", display_order: 3, intervals: [] },
    },
  } as AnnotationRecord;
}

function makeHarness(record: AnnotationRecord) {
  let state: AnnotationStore = {
    records: { Kalh01: record },
    dirty: {},
    loading: {},
    histories: { Kalh01: emptyHistory() },
  } as unknown as AnnotationStore;
  const scheduleAutosave = vi.fn();
  const set: AnnotationStoreSet = (partial) => {
    const next = typeof partial === "function" ? partial(state) : partial;
    state = { ...state, ...next } as AnnotationStore;
  };
  const get = () => state;
  const actions = createAnnotationActionsSlice(set, get, scheduleAutosave);
  state = { ...state, ...actions };
  return { actions, getState: () => state };
}

describe("Kalh01 head (F) — persistent CTC IPA bug", () => {
  it("display path: findAnnotationForConcept returns the concept-aligned interval, not the stray CTC chunk", () => {
    const record = makeKalh01Record();
    const lookup = findAnnotationForConcept(record, HEAD_F_CONCEPT);

    expect(lookup.conceptInterval).toMatchObject({ concept_id: "652" });
    // Fully-contained / largest-overlap pick: the empty manually-adjusted
    // interval at [1339.212, 1339.897] wins over the partial-overlap CTC chunk.
    expect(lookup.ipaInterval?.start).toBeCloseTo(HEAD_F_START, 6);
    expect(lookup.ipaInterval?.end).toBeCloseTo(HEAD_F_END, 6);
    expect(lookup.ipaInterval?.text).toBe("");
    expect(lookup.ipaInterval?.manuallyAdjusted).toBe(true);
  });

  it("save path: saveLexemeAnnotation with empty ipaText updates the empty interval, NOT the CTC chunk", () => {
    const { actions, getState } = makeHarness(makeKalh01Record());

    const result = actions.saveLexemeAnnotation({
      speaker: "Kalh01",
      oldStart: HEAD_F_START,
      oldEnd: HEAD_F_END,
      newStart: HEAD_F_START,
      newEnd: HEAD_F_END,
      ipaText: "",
      orthoText: undefined,
      orthoEdited: false,
      conceptName: "head (F)",
    });

    expect(result.ok).toBe(true);

    const ipa = getState().records.Kalh01.tiers.ipa.intervals;
    // Smoking gun: the CTC ændeɪdʒ chunk survived the "save with empty IPA".
    const ctcChunk = ipa.find((iv) => Math.abs(iv.start - CTC_IPA_START) < 1e-6);
    const conceptAligned = ipa.find((iv) => Math.abs(iv.start - HEAD_F_START) < 1e-6);

    expect(ctcChunk?.text).toBe(BAD_IPA_TEXT);
    expect(conceptAligned?.text).toBe("");
  });

  it("user-visible: clearing the IPA field and saving removes ændeɪdʒ from the head (F) display", () => {
    const { actions, getState } = makeHarness(makeKalh01Record());

    // The exact action sequence the user runs: edit IPA field to "" and Mark Done.
    actions.saveLexemeAnnotation({
      speaker: "Kalh01",
      oldStart: HEAD_F_START,
      oldEnd: HEAD_F_END,
      newStart: HEAD_F_START,
      newEnd: HEAD_F_END,
      ipaText: "",
      orthoText: undefined,
      orthoEdited: false,
      conceptName: "head (F)",
    });

    const afterSave = getState().records.Kalh01;
    const lookup = findAnnotationForConcept(afterSave, HEAD_F_CONCEPT);

    expect(lookup.ipaInterval?.text ?? "").toBe("");
  });
});
