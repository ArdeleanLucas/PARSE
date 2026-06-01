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

  it("triggers autosave scheduling through the normal record mutation path", () => {
    const { actions, getState, scheduleAutosave } = makeHarness(makeRecord());

    actions.createConceptInterval("S1", "623", 1.25, 2.5);

    expect(scheduleAutosave).toHaveBeenCalledTimes(1);
    expect(scheduleAutosave).toHaveBeenCalledWith("S1");
    const undo = getState().histories.S1.undo;
    expect(undo[undo.length - 1]?.label).toBe("create concept interval");
  });

  it("allows multiple elicitation intervals for the same concept_id", () => {
    const { actions, getState } = makeHarness(makeRecord([
      { start: 1, end: 2, text: "head", concept_id: "527" },
    ]));

    actions.createConceptInterval("S1", "527", 2.5, 3.5);

    expect(getState().records.S1.tiers.concept.intervals).toEqual([
      { start: 1, end: 2, text: "head", concept_id: "527" },
      { start: 2.5, end: 3.5, text: "", concept_id: "527" },
    ]);
  });

});

describe("reassignRealization", () => {
  it("moves the targeted realization's concept_id, keeping text and timing", () => {
    const { actions, getState } = makeHarness(makeRecord([
      { start: 0.5, end: 1.0, text: "big", concept_id: "53" },
      { start: 2.0, end: 2.6, text: "thin (man)", concept_id: "53" },
    ]));

    const ok = actions.reassignRealization("S1", "53", 1, "62");

    expect(ok).toBe(true);
    expect(getState().records.S1.tiers.concept.intervals).toEqual([
      { start: 0.5, end: 1.0, text: "big", concept_id: "53" },
      { start: 2.0, end: 2.6, text: "thin (man)", concept_id: "62" },
    ]);
    expect(getState().dirty.S1).toBe(true);
    expect(getState().records.S1.modified_at).not.toBe("2026-05-11T00:00:00.000Z");
  });

  it("indexes realizations by start time, not file order", () => {
    const { actions, getState } = makeHarness(makeRecord([
      { start: 5.0, end: 5.5, text: "later", concept_id: "42" },
      { start: 1.0, end: 1.5, text: "earlier", concept_id: "42" },
    ]));

    // index 0 must be the earliest-by-start interval (start=1.0), matching the sidebar pill order
    actions.reassignRealization("S1", "42", 0, "49");

    const byStart = [...getState().records.S1.tiers.concept.intervals].sort((a, b) => a.start - b.start);
    expect(byStart[0]).toEqual({ start: 1.0, end: 1.5, text: "earlier", concept_id: "49" });
    expect(byStart[1]).toEqual({ start: 5.0, end: 5.5, text: "later", concept_id: "42" });
  });

  it("schedules autosave and records an undo entry", () => {
    const { actions, getState, scheduleAutosave } = makeHarness(makeRecord([
      { start: 0.5, end: 1.0, text: "rain", concept_id: "42" },
    ]));

    actions.reassignRealization("S1", "42", 0, "49");

    expect(scheduleAutosave).toHaveBeenCalledTimes(1);
    expect(scheduleAutosave).toHaveBeenCalledWith("S1");
    const undo = getState().histories.S1.undo;
    expect(undo[undo.length - 1]?.label).toBe("reassign realization");
  });

  it("returns false and mutates nothing for a missing interval, a no-op, or bad input", () => {
    const { actions, getState, scheduleAutosave } = makeHarness(makeRecord([
      { start: 0.5, end: 1.0, text: "big", concept_id: "53" },
    ]));

    expect(actions.reassignRealization("S1", "53", 5, "62")).toBe(false); // index out of range
    expect(actions.reassignRealization("S1", "53", 0, "53")).toBe(false); // same source/target
    expect(actions.reassignRealization("S1", "53", -1, "62")).toBe(false); // negative index
    expect(actions.reassignRealization("S1", "999", 0, "62")).toBe(false); // unknown source concept

    expect(getState().records.S1.tiers.concept.intervals).toEqual([
      { start: 0.5, end: 1.0, text: "big", concept_id: "53" },
    ]);
    expect(getState().dirty.S1 ?? false).toBe(false);
    expect(scheduleAutosave).not.toHaveBeenCalled();
  });
});
