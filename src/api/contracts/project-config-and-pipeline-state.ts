import type { ProjectConfig, SurveyOverlapPatch, SurveyOverlapState } from "../types";
import { apiFetch, unwrapConfig } from "./shared";

export async function getConfig(): Promise<ProjectConfig> {
  const payload = await apiFetch<unknown>("/api/config");
  return unwrapConfig(payload);
}

export async function updateConfig(patch: Partial<ProjectConfig>): Promise<void> {
  await apiFetch<void>("/api/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function getSurveyOverlap(): Promise<SurveyOverlapState> {
  return apiFetch<SurveyOverlapState>("/api/survey-overlap");
}

export async function updateSurveyOverlap(patch: SurveyOverlapPatch): Promise<SurveyOverlapState> {
  return apiFetch<SurveyOverlapState>("/api/survey-overlap", {
    method: "POST",
    body: JSON.stringify(patch),
  });
}

export interface PipelineStepState {
  done: boolean;
  can_run: boolean;
  reason: string | null;
  coverage_start_sec?: number | null;
  coverage_end_sec?: number | null;
  coverage_fraction?: number | null;
  full_coverage?: boolean | null;
}

export interface PipelineNormalizeState extends PipelineStepState {
  path: string | null;
}

export interface PipelineSttState extends PipelineStepState {
  segments: number;
}

export interface PipelineTierState extends PipelineStepState {
  intervals: number;
}

export interface PipelineState {
  speaker: string;
  duration_sec?: number | null;
  normalize: PipelineNormalizeState;
  stt: PipelineSttState;
  ortho: PipelineTierState;
  ipa: PipelineTierState;
}

export async function getPipelineState(speaker: string): Promise<PipelineState> {
  return apiFetch<PipelineState>(`/api/pipeline/state/${encodeURIComponent(speaker)}`);
}

// MC-384 Milestone A result-envelope shape. Canonical spec:
// /mnt/c/Users/Lucas/Desktop/parse/compute-architecture-differentiation-spec.md
// Decisions #10-12. These types mirror python/workers/audio_chunking.py.
export type KnownErrorCode = "oom_suspect" | "chunk_failed" | "provider_error" | "timeout";

export interface ChunkSpan {
  idx: number;
  start: number;
  end: number;
}

export interface ChunkResult {
  idx: number;
  span: ChunkSpan;
  status: "ok" | "error" | "skipped" | "cancelled";
  error_code?: KnownErrorCode | string;
  error?: string;
}

// Deferred to Milestone B (MC-385+):
//   - Chunk-level progress UI (chunk N/M overlay during long jobs)
//   - Per-chunk retry affordance (click failed chunk -> re-run scoped to its span)
//   - Batch report partial-result coloring (yellow for "some chunks failed", not just red/green)
export type PipelineStepStatus = "ok" | "skipped" | "error" | "cancelled" | "partial_cancelled";

export interface PipelineStepResultBase {
  status?: PipelineStepStatus;
  error_code?: KnownErrorCode | string;
  reason?: string;
  error?: string;
  traceback?: string;
  chunks?: ChunkResult[];
  skip_breakdown?: {
    empty_ortho?: number;
    existing_ipa_no_overwrite?: number;
    zero_range?: number;
    exception?: number;
    empty_ipa_from_model?: number;
  };
  exception_samples?: string[];
  [key: string]: unknown;
}

export interface PipelineRunResult {
  speaker: string;
  steps_run: string[];
  results: Partial<Record<"normalize" | "stt" | "ortho" | "ipa", PipelineStepResultBase>>;
  summary: { ok: number; skipped: number; error: number };
  run_mode?: "full" | "concept-windows" | "edited-only";
  runMode?: "full" | "concept-windows" | "edited-only";
  affected_concepts?: Array<{ concept_id?: string; conceptId?: string; id?: string; start?: number; end?: number; [key: string]: unknown }>;
  affectedConcepts?: Array<{ concept_id?: string; conceptId?: string; id?: string; start?: number; end?: number; [key: string]: unknown }>;
}
