import type { PipelineRunResult, PipelineStepResultBase } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchSpeakerOutcome {
  speaker: string;
  status: "pending" | "running" | "complete" | "error" | "cancelled";
  error: string | null;
  jobId?: string;
  errorPhase?: "start" | "poll";
  result: PipelineRunResult | null;
}

export const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Normalize",
  stt: "STT",
  ortho: "Ortho",
  ipa: "IPA",
};

const TRUNCATE_LEN = 40;

export function truncate(text: string, max: number = TRUNCATE_LEN): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 1)) + "…";
}

export function okDetail(step: PipelineStepId, cell: PipelineStepResultBase): string {
  switch (step) {
    case "normalize":
      return "done";
    case "stt": {
      const segs = cell["segments"];
      if (typeof segs === "number") return `${segs} segs`;
      return "done";
    }
    case "ortho":
    case "ipa": {
      const ivs = cell["intervals"];
      if (typeof ivs === "number") return `${ivs} ivs`;
      const filled = cell["filled"];
      if (typeof filled === "number") return `${filled} ivs`;
      const total = cell["total"];
      if (typeof total === "number") return `${total} ivs`;
      return "done";
    }
  }
}

export type CellKind = "ok" | "skipped" | "empty" | "error" | "unknown";

export function classifyCell(cell: PipelineStepResultBase): CellKind {
  const explicit = cell["status"];
  if (explicit === "ok" || explicit === "skipped" || explicit === "error") {
    if (explicit === "ok") {
      const filled = cell["filled"];
      const total = cell["total"];
      if (
        typeof filled === "number" &&
        filled === 0 &&
        typeof total === "number" &&
        total > 0
      ) {
        return "empty";
      }
    }
    return explicit;
  }
  if (typeof cell["error"] === "string" && cell["error"].trim()) {
    return "error";
  }
  if (cell["skipped"] === true) {
    return "skipped";
  }
  const numericKeys = ["filled", "segments", "intervals", "total"];
  for (const k of numericKeys) {
    const v = cell[k];
    if (typeof v === "number" && v > 0) return "ok";
  }
  if (cell["done"] === true) return "ok";
  if (cell["filled"] === 0 && (cell["total"] === 0 || cell["total"] === undefined)) {
    return "skipped";
  }
  return "unknown";
}

export function speakerHasFailure(outcome: BatchSpeakerOutcome): boolean {
  if (outcome.status === "error") return true;
  if (outcome.result) {
    for (const step of Object.keys(outcome.result.results) as PipelineStepId[]) {
      const cell = outcome.result.results[step];
      if (!cell) continue;
      const kind = classifyCell(cell);
      if (kind === "error" || kind === "empty") return true;
    }
  }
  return false;
}

export function countTotals(
  outcomes: BatchSpeakerOutcome[],
  stepsRun: PipelineStepId[],
): { ok: number; skipped: number; empty: number; errored: number } {
  let ok = 0;
  let skipped = 0;
  let empty = 0;
  let errored = 0;
  for (const outcome of outcomes) {
    if (outcome.status === "error" && !outcome.result) {
      errored += 1;
      continue;
    }
    if (!outcome.result) continue;
    for (const step of stepsRun) {
      const cell = outcome.result.results[step];
      if (!cell) continue;
      const kind = classifyCell(cell);
      if (kind === "ok") ok += 1;
      else if (kind === "skipped") skipped += 1;
      else if (kind === "empty") empty += 1;
      else if (kind === "error") errored += 1;
    }
  }
  return { ok, skipped, empty, errored };
}
