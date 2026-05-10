import type { AnnotationRecord, IpaCandidatesPayload, IpaReviewState, IpaReviewUpdate, LexemeRerunIpaResponse, LexemeRerunOrthoResponse, LexemeRerunRequest, SttSegmentsPayload } from "../types";
import { apiFetch } from "./shared";
import { pollCompute, startCompute } from "./chat-and-generic-compute";

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


const LEXEME_RERUN_POLL_INTERVAL_MS = 500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function rerunLexemeViaCompute<T extends LexemeRerunIpaResponse | LexemeRerunOrthoResponse>(
  computeType: "lexeme_rerun_ipa" | "lexeme_rerun_ortho",
  request: LexemeRerunRequest,
): Promise<T> {
  const job = await startCompute(computeType, { ...request });
  const jobId = job.jobId ?? job.job_id;
  if (!jobId) {
    throw new Error("Lexeme rerun did not return a jobId");
  }

  while (true) {
    const status = await pollCompute(computeType, jobId);
    if (status.status === "complete") {
      return status.result as T;
    }
    if (status.status === "error") {
      throw new Error(status.error || status.message || "Lexeme rerun failed");
    }
    await sleep(LEXEME_RERUN_POLL_INTERVAL_MS);
  }
}

export async function rerunLexemeIpa(request: LexemeRerunRequest): Promise<LexemeRerunIpaResponse> {
  return rerunLexemeViaCompute<LexemeRerunIpaResponse>("lexeme_rerun_ipa", request);
}

export async function rerunLexemeOrtho(request: LexemeRerunRequest): Promise<LexemeRerunOrthoResponse> {
  return rerunLexemeViaCompute<LexemeRerunOrthoResponse>("lexeme_rerun_ortho", request);
}
