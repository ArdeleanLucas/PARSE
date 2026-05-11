import { describe, expect, it, vi } from "vitest";

import type { AnnotationRecord } from "../../api/types";
import { emptyHistory } from "../annotationStoreHistory";
import { createAnnotationActionsSlice } from "./actions";
import type { AnnotationStore, AnnotationStoreSet } from "./types";

function makeRecord(intervals: AnnotationRecord["tiers"]["concept"]["intervals"] = []): AnnotationRecord {
  return {
    speaker: "S1",
    source_wav: "S1.wav",
    created_at: "2026-05-11T00:00:00.000Z",
    modified_at: "2026-05-11T00:00:00.000Z",
    tiers: {
      concept: {
        name: "concept",
        display_order: 6,
        intervals,
      },
    },
  } as AnnotationRecord;
}

function makeHarness(record: AnnotationRecord) {
  let state: AnnotationStore = {
    records: { S1: record },
    dirty: {},
    loading: {},
    histories: { S1: emptyHistory() },
  } as unknown as AnnotationStore;
  const scheduleAutosave = vi.fn();
  const set: AnnotationStoreSet = (partial) => {
    const next = typeof partial === "function" ? partial(state) : partial;
    state = { ...state, ...next } as AnnotationStore;
  };
  const get = () => state;
  const actions = createAnnotationActionsSlice(set, get, scheduleAutosave);
  state = { ...state, ...actions };
  return { actions, scheduleAutosave, getState: () => state };
}

describe("createConceptInterval", () => {
  it("appends a concept interval for the requested concept_id", () => {
    const { actions, getState } = makeHarness(makeRecord([
      { start: 0.5, end: 1.0, text: "head", concept_id: "527" },
    ]));

    actions.createConceptInterval("S1", "623", 1.25, 2.5);

    expect(getState().records.S1.tiers.concept.intervals).toEqual([
      { start: 0.5, end: 1.0, text: "head", concept_id: "527" },
      { start: 1.25, end: 2.5, text: "", concept_id: "623" },
    ]);
    expect(getState().records.S1.modified_at).not.toBe("2026-05-11T00:00:00.000Z");
    expect(getState().dirty.S1).toBe(true);
  });

  it("is a no-op when the concept_id already has an interval", () => {
    const { actions, getState, scheduleAutosave } = makeHarness(makeRecord([
      { start: 0.5, end: 1.0, text: "head", concept_id: "623" },
    ]));

    actions.createConceptInterval("S1", "623", 1.25, 2.5);

    expect(getState().records.S1.tiers.concept.intervals).toEqual([
      { start: 0.5, end: 1.0, text: "head", concept_id: "623" },
    ]);
    expect(getState().dirty.S1).toBeUndefined();
    expect(scheduleAutosave).not.toHaveBeenCalled();
  });

  it("triggers autosave scheduling through the normal record mutation path", () => {
    const { actions, getState, scheduleAutosave } = makeHarness(makeRecord());

    actions.createConceptInterval("S1", "623", 1.25, 2.5);

    expect(scheduleAutosave).toHaveBeenCalledTimes(1);
    expect(scheduleAutosave).toHaveBeenCalledWith("S1");
    const undo = getState().histories.S1.undo;
    expect(undo[undo.length - 1]?.label).toBe("create concept interval");
  });
});
