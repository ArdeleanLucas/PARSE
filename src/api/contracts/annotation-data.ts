import type { AnnotationRecord, SttSegmentsPayload } from "../types";
import { apiFetch } from "./shared";

export async function getAnnotation(speaker: string): Promise<AnnotationRecord> {
  return apiFetch<AnnotationRecord>(`/api/annotations/${encodeURIComponent(speaker)}`);
}

export async function saveAnnotation(speaker: string, record: AnnotationRecord): Promise<void> {
  await apiFetch<void>(`/api/annotations/${encodeURIComponent(speaker)}`, {
    method: "POST",
    body: JSON.stringify(record),
  });
}

export async function getSttSegments(speaker: string): Promise<SttSegmentsPayload> {
  return apiFetch<SttSegmentsPayload>(`/api/stt-segments/${encodeURIComponent(speaker)}`);
}
