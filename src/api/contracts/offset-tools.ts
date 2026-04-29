import type { ComputeJob } from "../types";
import { pollCompute } from "./chat-and-generic-compute";
import { apiFetch, resolveJobId } from "./shared";

export interface OffsetMatch {
  anchor_index: number;
  anchor_text: string;
  anchor_start: number | null;
  segment_index: number;
  segment_text: string;
  segment_start: number | null;
  score: number;
  offset_sec: number;
}

export type OffsetDirection = "earlier" | "later" | "none";

export interface OffsetDetectResult {
  speaker: string;
  offsetSec: number;
  confidence: number;
  nAnchors: number;
  totalAnchors: number;
  totalSegments: number;
  method: string;
  spreadSec?: number;
  direction?: OffsetDirection;
  directionLabel?: string;
  anchorDistribution?: string;
  reliable?: boolean;
  warnings?: string[];
  matches?: OffsetMatch[];
}

export interface OffsetApplyResult {
  speaker: string;
  appliedOffsetSec: number;
  shiftedIntervals: number;
  shiftedConcepts: number;
  protectedIntervals: number;
  protectedLexemes: number;
}

export async function detectTimestampOffset(
  speaker: string,
  options?: {
    sttJobId?: string;
    sttSegments?: unknown[];
    anchorDistribution?: "quantile" | "earliest";
    nAnchors?: number;
  },
): Promise<ComputeJob> {
  const payload = await apiFetch<unknown>("/api/offset/detect", {
    method: "POST",
    body: JSON.stringify({
      speaker,
      sttJobId: options?.sttJobId,
      sttSegments: options?.sttSegments,
      anchorDistribution: options?.anchorDistribution,
      nAnchors: options?.nAnchors,
    }),
  });
  return { job_id: resolveJobId(payload), jobId: resolveJobId(payload) };
}

export interface OffsetPair {
  audioTimeSec: number;
  csvTimeSec?: number;
  conceptId?: string;
}

export async function detectTimestampOffsetFromPair(
  speaker: string,
  audioTimeSec: number,
  options: { csvTimeSec?: number; conceptId?: string },
): Promise<ComputeJob> {
  const payload = await apiFetch<unknown>("/api/offset/detect-from-pair", {
    method: "POST",
    body: JSON.stringify({
      speaker,
      audioTimeSec,
      csvTimeSec: options.csvTimeSec,
      conceptId: options.conceptId,
    }),
  });
  return { job_id: resolveJobId(payload), jobId: resolveJobId(payload) };
}

export async function detectTimestampOffsetFromPairs(
  speaker: string,
  pairs: OffsetPair[],
): Promise<ComputeJob> {
  const payload = await apiFetch<unknown>("/api/offset/detect-from-pair", {
    method: "POST",
    body: JSON.stringify({ speaker, pairs }),
  });
  return { job_id: resolveJobId(payload), jobId: resolveJobId(payload) };
}

export class OffsetJobError extends Error {
  readonly jobId: string;
  readonly traceback?: string;

  constructor(jobId: string, message: string, traceback?: string) {
    super(message);
    this.name = "OffsetJobError";
    this.jobId = jobId;
    if (traceback) this.traceback = traceback;
  }
}

export async function pollOffsetDetectJob(
  jobId: string,
  computeType: "offset_detect" | "offset_detect_from_pair" = "offset_detect",
  {
    intervalMs = 500,
    timeoutMs = 600_000,
    onProgress,
  }: {
    intervalMs?: number;
    timeoutMs?: number;
    onProgress?: (p: { progress: number; message?: string }) => void;
  } = {},
): Promise<OffsetDetectResult> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise<void>((r) => setTimeout(r, intervalMs));
    const status = await pollCompute(computeType, jobId);
    if (onProgress) {
      onProgress({ progress: status.progress, message: status.message });
    }
    if (status.status === "complete") {
      return status.result as OffsetDetectResult;
    }
    if (status.status === "error") {
      const reason = status.error ?? status.message ?? "Offset detection failed";
      throw new OffsetJobError(jobId, reason, status.traceback);
    }
  }
  throw new OffsetJobError(jobId, "Offset detection timed out (client-side deadline)");
}

export async function applyTimestampOffset(
  speaker: string,
  offsetSec: number,
): Promise<OffsetApplyResult> {
  return apiFetch<OffsetApplyResult>("/api/offset/apply", {
    method: "POST",
    body: JSON.stringify({ speaker, offsetSec }),
  });
}
