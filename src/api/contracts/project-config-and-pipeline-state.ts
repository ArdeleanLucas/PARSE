import type { ProjectConfig } from "../types";
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

export type PipelineStepStatus = "ok" | "skipped" | "error";

export interface PipelineStepResultBase {
  status?: PipelineStepStatus;
  reason?: string;
  error?: string;
  traceback?: string;
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
}
