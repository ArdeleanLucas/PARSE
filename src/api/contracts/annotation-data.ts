import type { AnnotationRecord, IpaCandidatesPayload, IpaReviewState, IpaReviewUpdate, SttSegmentsPayload } from "../types";
import { apiFetch } from "./shared";

type SaveAnnotationResponse = AnnotationRecord | { annotation?: AnnotationRecord };

function unwrapSavedAnnotation(payload: SaveAnnotationResponse): AnnotationRecord {
  if (payload && typeof payload === "object" && "annotation" in payload && payload.annotation) {
    return payload.annotation;
  }
  return payload as AnnotationRecord;
}

export async function getAnnotation(speaker: string): Promise<AnnotationRecord> {
  return apiFetch<AnnotationRecord>(`/api/annotations/${encodeURIComponent(speaker)}`);
}

export async function saveAnnotation(speaker: string, record: AnnotationRecord): Promise<AnnotationRecord> {
  const payload = await apiFetch<SaveAnnotationResponse>(`/api/annotations/${encodeURIComponent(speaker)}`, {
    method: "POST",
    body: JSON.stringify(record),
  });
  return unwrapSavedAnnotation(payload);
}

export async function getSttSegments(speaker: string): Promise<SttSegmentsPayload> {
  return apiFetch<SttSegmentsPayload>(`/api/stt-segments/${encodeURIComponent(speaker)}`);
}

export async function getIpaCandidates(speaker: string): Promise<IpaCandidatesPayload> {
  return apiFetch<IpaCandidatesPayload>(`/api/annotations/${encodeURIComponent(speaker)}/ipa-candidates`);
}

export async function putIpaReview(
  speaker: string,
  key: string,
  state: IpaReviewUpdate,
): Promise<IpaReviewState> {
  const payload = await apiFetch<{ review: IpaReviewState }>(
    `/api/annotations/${encodeURIComponent(speaker)}/ipa-review/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: JSON.stringify(state),
    },
  );
  return payload.review;
}
