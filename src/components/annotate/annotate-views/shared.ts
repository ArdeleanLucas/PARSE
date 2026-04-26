import type { AnnotationRecord } from "../../../api/types";
import {
  conceptMatchesIntervalText,
  overlaps,
  pickOrthoIntervalForConcept,
} from "../../../lib/parseUIUtils";

import type { AnnotationLookup, Concept } from "./types";

export { overlaps, pickOrthoIntervalForConcept };

export function formatPlaybackTime(t: number): string {
  if (!Number.isFinite(t) || t < 0) return "00:00.00";
  const m = Math.floor(t / 60).toString().padStart(2, "0");
  const s = Math.floor(t % 60).toString().padStart(2, "0");
  const ms = Math.floor((t * 100) % 100).toString().padStart(2, "0");
  return `${m}:${s}.${ms}`;
}

export function findAnnotationForConcept(
  record: AnnotationRecord | null | undefined,
  concept: Concept,
): AnnotationLookup {
  if (!record) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const conceptIntervals = record.tiers.concept?.intervals ?? [];
  const conceptInterval = conceptIntervals.find((interval) => conceptMatchesIntervalText(concept, interval.text)) ?? null;

  if (!conceptInterval) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const ipaInterval = (record.tiers.ipa?.intervals ?? []).find((interval) => overlaps(interval, conceptInterval)) ?? null;
  const orthoInterval = pickOrthoIntervalForConcept(record, conceptInterval);

  return { conceptInterval, ipaInterval, orthoInterval };
}

export function formatPlayhead(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00.000";
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

export function formatSearchTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

export function buildLexemeSearchStatus(resp: {
  candidates: unknown[];
  signals_available: { phonemizer: boolean; cross_speaker_anchors: number };
}): string {
  const n = resp.candidates.length;
  if (n === 0) {
    return "No candidates above confidence threshold. Try adding variants or fuzzier spellings.";
  }
  const bits: string[] = [`${n} candidate${n === 1 ? "" : "s"}.`];
  if (!resp.signals_available.phonemizer) {
    bits.push("Phonemizer unavailable — scoring on orthographic similarity only.");
  }
  if (resp.signals_available.cross_speaker_anchors > 0) {
    bits.push(`${resp.signals_available.cross_speaker_anchors} cross-speaker anchor(s) in scoring.`);
  }
  return bits.join(" ");
}

export function tierChipBg(tier: string): string {
  switch (tier) {
    case "ortho_words":
      return "#059669";
    case "ortho":
      return "#2563eb";
    case "stt":
      return "#6366f1";
    case "ipa":
      return "#8b5cf6";
    default:
      return "#64748b";
  }
}
