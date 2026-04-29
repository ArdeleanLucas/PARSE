import type {
  AnnotationInterval,
  AnnotationRecord,
  ConfirmedAnchor,
  SttSegment,
} from "../../api/types";
import {
  applyAddInterval,
  applyMergeIntervals,
  applyRemoveInterval,
  applySetInterval,
  applySplitInterval,
  applyUpdateInterval,
  applyUpdateIntervalTimes,
} from "../annotationStoreIntervals";
import { popRedoDelta, popUndoDelta, pushHistoryDelta } from "../annotationStoreHistory";
import {
  blankRecord,
  CANONICAL_TIER_ORDER,
  deepClone,
  nowIsoUtc,
  tierLabel,
} from "../annotationStoreShared";
import { selectSpeakerRecord } from "./selectors";
import type {
  AnnotationStoreActionsSlice,
  AnnotationStoreGet,
  AnnotationStoreSet,
  ScheduleAnnotationAutosave,
} from "./types";

/**
 * Tiers updated by a lexeme-scoped retime.
 *
 * Lexeme retiming moves only intervals that semantically belong to the
 * lexeme: its concept label, IPA transcription, orthographic transcription,
 * and Tier-2 word boundaries. Sub-lexical (`ipa_phone`) and supra-lexical
 * (`stt`, `sentence`, `speaker`) tiers are intentionally excluded.
 */
export const LEXEME_SCOPE_TIERS = ["concept", "ipa", "ortho", "ortho_words"] as const;

const MATCH_TOLERANCE_SEC = 0.001;

function findMatchingIntervalIndex(intervals: AnnotationInterval[], start: number, end: number): number {
  return intervals.findIndex(
    (interval) => Math.abs(interval.start - start) < MATCH_TOLERANCE_SEC && Math.abs(interval.end - end) < MATCH_TOLERANCE_SEC,
  );
}

function updateMatchingInterval(
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
  const idx = findMatchingIntervalIndex(tier.intervals, oldStart, oldEnd);
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

function findBestOverlapIntervalIndex(intervals: AnnotationInterval[], start: number, end: number): number {
  let bestIdx = -1;
  let bestOverlap = 0;
  for (let i = 0; i < intervals.length; i += 1) {
    const interval = intervals[i];
    if (interval.end <= start || interval.start >= end) continue;
    const overlap = Math.min(interval.end, end) - Math.max(interval.start, start);
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestIdx = i;
    }
  }
  return bestIdx;
}

function ensureAnnotationTier(record: AnnotationRecord, tierKey: string) {
  if (!record.tiers[tierKey]) {
    const fallbackOrder = Math.max(0, ...Object.values(record.tiers).map((tier) => tier.display_order)) + 1;
    record.tiers[tierKey] = {
      name: tierKey,
      display_order: CANONICAL_TIER_ORDER[tierKey as keyof typeof CANONICAL_TIER_ORDER] ?? fallbackOrder,
      intervals: [],
    };
  }
  return record.tiers[tierKey];
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
  const idx = tier ? findBestOverlapIntervalIndex(tier.intervals, oldStart, oldEnd) : -1;
  if (tier && idx >= 0) {
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

  if (text === undefined || text.trim() === "") return false;
  const writableTier = ensureAnnotationTier(record, tierKey);
  writableTier.intervals.push({
    start: newStart,
    end: newEnd,
    text,
    manuallyAdjusted: true,
  });
  writableTier.intervals.sort((a, b) => a.start - b.start);
  return true;
}

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
    const interval = tier.intervals[i];
    const midpoint = (interval.start + interval.end) / 2;
    if (midpoint < oldStart - MATCH_TOLERANCE_SEC) continue;
    if (midpoint > oldEnd + MATCH_TOLERANCE_SEC) continue;
    const startFraction = Math.max(0, Math.min(1, (interval.start - oldStart) / oldDur));
    const endFraction = Math.max(0, Math.min(1, (interval.end - oldStart) / oldDur));
    tier.intervals[i] = {
      ...interval,
      start: newStart + startFraction * newDur,
      end: newStart + endFraction * newDur,
      manuallyAdjusted: true,
    };
    count += 1;
  }
  if (count > 0) tier.intervals.sort((a, b) => a.start - b.start);
  return count;
}

function isLexemeScope(scope: readonly string[] | undefined): boolean {
  if (!scope || scope.length !== LEXEME_SCOPE_TIERS.length) return false;
  return LEXEME_SCOPE_TIERS.every((tier) => scope.includes(tier));
}

function applyLexemeRetime(
  record: AnnotationRecord,
  oldStart: number,
  oldEnd: number,
  newStart: number,
  newEnd: number,
  texts?: { conceptName?: string; ipaText?: string; orthoText?: string },
): number {
  if (!updateMatchingInterval(record, "concept", oldStart, oldEnd, newStart, newEnd, texts?.conceptName)) return 0;
  let moved = 1;
  if (retimeOverlappingInterval(record, "ipa", oldStart, oldEnd, newStart, newEnd, texts?.ipaText)) moved += 1;
  if (retimeOverlappingInterval(record, "ortho", oldStart, oldEnd, newStart, newEnd, texts?.orthoText)) moved += 1;
  if (rescaleAssociatedIntervals(record, "ortho_words", oldStart, oldEnd, newStart, newEnd) > 0) moved += 1;
  return moved;
}

function commitRecordMutation(
  set: AnnotationStoreSet,
  scheduleAutosave: ScheduleAnnotationAutosave,
  speaker: string,
  pre: AnnotationRecord,
  next: AnnotationRecord,
  label: string,
) {
  set((state) => ({
    histories: pushHistoryDelta(state.histories, speaker, pre, label),
    records: { ...state.records, [speaker]: next },
    dirty: { ...state.dirty, [speaker]: true },
  }));
  scheduleAutosave(speaker);
}

export function createAnnotationActionsSlice(
  set: AnnotationStoreSet,
  get: AnnotationStoreGet,
  scheduleAutosave: ScheduleAnnotationAutosave,
): AnnotationStoreActionsSlice {
  return {
    setInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
      const pre = selectSpeakerRecord(get(), speaker) ?? blankRecord(speaker);
      const next = applySetInterval(pre, tier, interval);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `save ${tierLabel(tier)} segment`);
    },

    updateInterval: (speaker: string, tier: string, index: number, text: string) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applyUpdateInterval(pre, tier, index, text);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `text edit (${tierLabel(tier)})`);
    },

    addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applyAddInterval(pre, tier, interval);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `add ${tierLabel(tier)} segment`);
    },

    removeInterval: (speaker: string, tier: string, index: number) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applyRemoveInterval(pre, tier, index);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `delete ${tierLabel(tier)} segment`);
    },

    updateIntervalTimes: (speaker, tier, index, start, end) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applyUpdateIntervalTimes(pre, tier, index, start, end);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `retime ${tierLabel(tier)} segment`);
    },

    mergeIntervals: (speaker, tier, index) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applyMergeIntervals(pre, tier, index);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `merge with next (${tierLabel(tier)})`);
    },

    splitInterval: (speaker, tier, index, splitTime) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      const next = applySplitInterval(pre, tier, index, splitTime);
      if (!next) return;
      commitRecordMutation(set, scheduleAutosave, speaker, pre, next, `split (${tierLabel(tier)})`);
    },

    ensureSttTier: (speaker: string, segments: SttSegment[]) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      if ((pre.tiers.stt?.intervals.length ?? 0) > 0) return;
      if (!Array.isArray(segments) || segments.length === 0) return;

      const clone = deepClone(pre);
      if (!clone.tiers.stt) {
        clone.tiers.stt = {
          name: "stt",
          display_order: CANONICAL_TIER_ORDER.stt,
          intervals: [],
        };
      }
      clone.tiers.stt.intervals = segments.map((segment) => ({
        start: segment.start,
        end: segment.end,
        text: segment.text,
      }));
      clone.modified_at = nowIsoUtc();

      commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "enable STT editing");
    },

    ensureSttWordsTier: (speaker: string, segments: SttSegment[]) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;
      if ((pre.tiers.stt_words?.intervals.length ?? 0) > 0) return;
      if (!Array.isArray(segments) || segments.length === 0) return;

      const flat: AnnotationInterval[] = [];
      for (const segment of segments) {
        const words = segment.words ?? [];
        for (const word of words) {
          if (typeof word.start !== "number" || typeof word.end !== "number") continue;
          if (word.start === 0 && word.end === 0) continue;
          flat.push({ start: word.start, end: word.end, text: "" });
        }
      }
      if (flat.length === 0) return;

      const clone = deepClone(pre);
      if (!clone.tiers.stt_words) {
        const maxOrder = Math.max(0, ...Object.values(clone.tiers).map((tierState) => tierState.display_order));
        clone.tiers.stt_words = {
          name: "stt_words",
          display_order: maxOrder + 1,
          intervals: [],
        };
      }
      clone.tiers.stt_words.intervals = flat;
      clone.modified_at = nowIsoUtc();

      commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "enable Words editing");
    },

    setConfirmedAnchor: (speaker: string, conceptId: string, anchor: ConfirmedAnchor | null) => {
      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return;

      const clone = deepClone(pre);
      const existing = { ...(clone.confirmed_anchors ?? {}) };
      const key = String(conceptId);
      if (anchor === null) {
        delete existing[key];
      } else {
        existing[key] = { ...anchor };
      }
      clone.confirmed_anchors = existing;
      clone.modified_at = nowIsoUtc();

      commitRecordMutation(
        set,
        scheduleAutosave,
        speaker,
        pre,
        clone,
        anchor === null ? "clear concept anchor" : "confirm concept anchor",
      );
    },

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
      const moved = applyLexemeRetime(clone, oldStart, oldEnd, newStart, newEnd, { conceptName, ipaText, orthoText });

      if (moved === 0) {
        return { ok: false, error: "No matching lexeme intervals found." };
      }

      clone.modified_at = nowIsoUtc();
      commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "save lexeme annotation");
      return { ok: true, moved };
    },

    markLexemeManuallyAdjusted: (speaker, start, end) => {
      if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;

      const pre = selectSpeakerRecord(get(), speaker);
      if (!pre) return 0;

      const clone = deepClone(pre);
      const tol = 0.001;
      let flagged = 0;
      for (const tier of Object.values(clone.tiers)) {
        for (let index = 0; index < tier.intervals.length; index += 1) {
          const interval = tier.intervals[index];
          if (Math.abs(interval.start - start) < tol && Math.abs(interval.end - end) < tol) {
            if (!interval.manuallyAdjusted) {
              tier.intervals[index] = { ...interval, manuallyAdjusted: true };
            }
            flagged += 1;
          }
        }
      }
      if (flagged === 0) return 0;
      clone.modified_at = nowIsoUtc();

      commitRecordMutation(set, scheduleAutosave, speaker, pre, clone, "mark lexeme manually adjusted");
      return flagged;
    },

    undo: (speaker: string) => {
      const state = get();
      const delta = popUndoDelta(state.histories, state.records, speaker);
      if (!delta) return null;

      set((current) => ({
        records: { ...current.records, [speaker]: delta.record },
        dirty: { ...current.dirty, [speaker]: true },
        histories: delta.histories,
      }));
      scheduleAutosave(speaker);
      return delta.label;
    },

    redo: (speaker: string) => {
      const state = get();
      const delta = popRedoDelta(state.histories, state.records, speaker);
      if (!delta) return null;

      set((current) => ({
        records: { ...current.records, [speaker]: delta.record },
        dirty: { ...current.dirty, [speaker]: true },
        histories: delta.histories,
      }));
      scheduleAutosave(speaker);
      return delta.label;
    },
  };
}
