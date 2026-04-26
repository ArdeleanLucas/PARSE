import type { AnnotationInterval, AnnotationRecord } from "../api/types";
import {
  CANONICAL_TIER_ORDER,
  deepClone,
  nowIsoUtc,
} from "./annotationStoreShared";

function ensureTier(record: AnnotationRecord, tier: string) {
  if (record.tiers[tier]) return;
  const maxOrder = Math.max(0, ...Object.values(record.tiers).map((t) => t.display_order));
  record.tiers[tier] = {
    name: tier,
    display_order: CANONICAL_TIER_ORDER[tier] ?? maxOrder + 1,
    intervals: [],
  };
}

export function applySetInterval(
  pre: AnnotationRecord,
  tier: string,
  interval: AnnotationInterval,
): AnnotationRecord | null {
  if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end)) return null;
  if (interval.end < interval.start) return null;

  const clone = deepClone(pre);
  ensureTier(clone, tier);
  clone.tiers[tier].intervals = clone.tiers[tier].intervals.filter(
    (candidate) =>
      !(Math.abs(candidate.start - interval.start) < 0.001 && Math.abs(candidate.end - interval.end) < 0.001),
  );
  clone.tiers[tier].intervals.push(interval);
  clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applyUpdateInterval(
  pre: AnnotationRecord,
  tier: string,
  index: number,
  text: string,
): AnnotationRecord | null {
  if (!pre.tiers[tier]) return null;
  if (index < 0 || index >= pre.tiers[tier].intervals.length) return null;

  const clone = deepClone(pre);
  const target = clone.tiers[tier].intervals[index];
  clone.tiers[tier].intervals[index] = {
    ...target,
    text,
    manuallyAdjusted: true,
  };
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applyAddInterval(
  pre: AnnotationRecord,
  tier: string,
  interval: AnnotationInterval,
): AnnotationRecord | null {
  if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end)) return null;
  if (interval.end < interval.start) return null;

  const clone = deepClone(pre);
  ensureTier(clone, tier);
  clone.tiers[tier].intervals.push(interval);
  clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applyRemoveInterval(
  pre: AnnotationRecord,
  tier: string,
  index: number,
): AnnotationRecord | null {
  if (!pre.tiers[tier]) return null;
  if (index < 0 || index >= pre.tiers[tier].intervals.length) return null;

  const clone = deepClone(pre);
  clone.tiers[tier].intervals.splice(index, 1);
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applyUpdateIntervalTimes(
  pre: AnnotationRecord,
  tier: string,
  index: number,
  start: number,
  end: number,
): AnnotationRecord | null {
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  if (end < start) return null;
  if (!pre.tiers[tier]) return null;
  if (index < 0 || index >= pre.tiers[tier].intervals.length) return null;

  const clone = deepClone(pre);
  const target = clone.tiers[tier].intervals[index];
  clone.tiers[tier].intervals[index] = {
    ...target,
    start,
    end,
    manuallyAdjusted: true,
  };
  clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applyMergeIntervals(
  pre: AnnotationRecord,
  tier: string,
  index: number,
): AnnotationRecord | null {
  if (!pre.tiers[tier]) return null;
  const intervals = pre.tiers[tier].intervals;
  if (index < 0 || index >= intervals.length - 1) return null;

  const left = intervals[index];
  const right = intervals[index + 1];
  const mergedText = [left.text, right.text]
    .map((t) => (t ?? "").trim())
    .filter(Boolean)
    .join(" ");

  const clone = deepClone(pre);
  clone.tiers[tier].intervals.splice(index, 2, {
    start: left.start,
    end: right.end,
    text: mergedText,
    manuallyAdjusted: true,
  });
  clone.modified_at = nowIsoUtc();
  return clone;
}

export function applySplitInterval(
  pre: AnnotationRecord,
  tier: string,
  index: number,
  splitTime: number,
): AnnotationRecord | null {
  if (!Number.isFinite(splitTime)) return null;
  if (!pre.tiers[tier]) return null;
  const intervals = pre.tiers[tier].intervals;
  if (index < 0 || index >= intervals.length) return null;

  const target = intervals[index];
  const tol = 0.001;
  if (splitTime <= target.start + tol || splitTime >= target.end - tol) return null;

  const clone = deepClone(pre);
  clone.tiers[tier].intervals.splice(
    index,
    1,
    {
      start: target.start,
      end: splitTime,
      text: target.text,
      manuallyAdjusted: true,
    },
    {
      start: splitTime,
      end: target.end,
      text: "",
      manuallyAdjusted: true,
    },
  );
  clone.modified_at = nowIsoUtc();
  return clone;
}
