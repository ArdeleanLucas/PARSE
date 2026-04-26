import { describe, expect, it } from "vitest";
import type { AnnotationRecord } from "../api/types";
import {
  emptyHistory,
  HISTORY_CAP,
  popRedoDelta,
  popUndoDelta,
  pushHistoryDelta,
} from "./annotationStoreHistory";
import type { SpeakerHistory } from "./annotationStoreHistory";

function record(text: string): AnnotationRecord {
  return {
    speaker: "S1",
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 1,
        intervals: [{ start: 0, end: 1, text }],
      },
    },
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    source_wav: "x.wav",
  };
}

describe("annotationStoreHistory", () => {
  it("pushHistoryDelta caps undo at HISTORY_CAP and clears redo", () => {
    let histories: Record<string, SpeakerHistory> = {
      S1: { undo: [], redo: [{ snapshot: record("redo"), label: "redo" }] },
    };
    for (let i = 0; i < HISTORY_CAP + 3; i += 1) {
      histories = pushHistoryDelta(histories, "S1", record(`t${i}`), `label-${i}`);
    }
    expect(histories.S1.redo).toEqual([]);
    expect(histories.S1.undo).toHaveLength(HISTORY_CAP);
    expect(histories.S1.undo[0]?.label).toBe("label-3");
    expect(histories.S1.undo[histories.S1.undo.length - 1]?.label).toBe(`label-${HISTORY_CAP + 2}`);
  });

  it("popUndoDelta restores the prior snapshot and queues redo", () => {
    const current = record("current");
    const previous = record("previous");
    const histories: Record<string, SpeakerHistory> = {
      S1: {
        undo: [{ snapshot: previous, label: "text edit (IPA)" }],
        redo: emptyHistory().redo,
      },
    };

    const delta = popUndoDelta(histories, { S1: current }, "S1");
    expect(delta).not.toBeNull();
    expect(delta?.label).toBe("text edit (IPA)");
    expect(delta?.record.tiers.ipa.intervals[0].text).toBe("previous");
    expect(delta?.histories.S1.undo).toEqual([]);
    expect(delta?.histories.S1.redo).toHaveLength(1);
    expect(delta?.histories.S1.redo[0]?.snapshot.tiers.ipa.intervals[0].text).toBe("current");
  });

  it("popRedoDelta reapplies the redone snapshot and pushes current back to undo", () => {
    const current = record("current");
    const redone = record("redone");
    const histories: Record<string, SpeakerHistory> = {
      S1: {
        undo: [{ snapshot: record("older"), label: "older" }],
        redo: [{ snapshot: redone, label: "retime IPA segment" }],
      },
    };

    const delta = popRedoDelta(histories, { S1: current }, "S1");
    expect(delta).not.toBeNull();
    expect(delta?.label).toBe("retime IPA segment");
    expect(delta?.record.tiers.ipa.intervals[0].text).toBe("redone");
    expect(delta?.histories.S1.redo).toEqual([]);
    expect(delta?.histories.S1.undo).toHaveLength(2);
    expect(delta?.histories.S1.undo[delta!.histories.S1.undo.length - 1]?.snapshot.tiers.ipa.intervals[0].text).toBe("current");
  });
});
