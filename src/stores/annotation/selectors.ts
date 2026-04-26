import type { AnnotationInterval, AnnotationRecord } from "../../api/types";
import type { SpeakerHistory } from "../annotationStoreHistory";
import type { AnnotationStoreState } from "./types";

export function selectSpeakerRecord(
  state: Pick<AnnotationStoreState, "records">,
  speaker: string,
): AnnotationRecord | null {
  return state.records[speaker] ?? null;
}

export function selectSpeakerDirty(
  state: Pick<AnnotationStoreState, "dirty">,
  speaker: string,
): boolean {
  return state.dirty[speaker] ?? false;
}

export function selectSpeakerLoading(
  state: Pick<AnnotationStoreState, "loading">,
  speaker: string,
): boolean {
  return state.loading[speaker] ?? false;
}

export function selectSpeakerHistory(
  state: Pick<AnnotationStoreState, "histories">,
  speaker: string,
): SpeakerHistory | null {
  return state.histories[speaker] ?? null;
}

export function selectConceptIntervals(
  state: Pick<AnnotationStoreState, "records">,
  speaker: string,
): AnnotationInterval[] {
  return selectSpeakerRecord(state, speaker)?.tiers?.concept?.intervals ?? [];
}

export function countProtectedConceptLexemes(
  state: Pick<AnnotationStoreState, "records">,
  speaker: string | null | undefined,
): number {
  if (!speaker) return 0;
  let count = 0;
  for (const interval of selectConceptIntervals(state, speaker)) {
    if (interval.manuallyAdjusted) count += 1;
  }
  return count;
}
