import type { PipelineState } from "../../api/client";
import {
  AudioLines,
  Ban,
  CheckCircle2,
  Loader2,
  Mic,
  Pin,
  RotateCcw,
  SkipForward,
  Type,
  Workflow,
} from "lucide-react";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";
export type TranscriptionRunMode = "full" | "concept-windows" | "edited-only";
export type RunScope = "gaps" | "overwrite";
export const DEFAULT_SCOPE: RunScope = "gaps";
export const STEP_ORDER: PipelineStepId[] = ["normalize", "stt", "ortho", "ipa"];
export const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Normalize",
  stt: "STT",
  ortho: "ORTH",
  ipa: "IPA",
};
export const STEP_ICONS: Record<
  PipelineStepId,
  React.ComponentType<{ className?: string }>
> = {
  normalize: AudioLines,
  stt: Mic,
  ortho: Type,
  ipa: Workflow,
};

export type LoadStatus = "loading" | "ready" | "error";
export interface SpeakerLoadEntry {
  status: LoadStatus;
  state: PipelineState | null;
  error: string | null;
}

export type CellKind =
  | "ok"
  | "skip"
  | "keep"
  | "overwrite"
  | "blocked"
  | "loading"
  | "unknown";

export interface CellInfo {
  kind: CellKind;
  count: number;
  reason: string | null;
}

export function keepTooltip(step: PipelineStepId, count: number): string {
  if (step === "ortho") {
    return `Keeping existing ORTH tier (${count} intervals). This step will no-op — switch to Overwrite to redo it.`;
  }
  if (step === "ipa") {
    return `Keeping existing IPA intervals (${count}). Empty intervals will still be filled; finalized text stays put.`;
  }
  return `Keeping existing output (${count}). Switch to Overwrite to redo.`;
}

export function stepCount(step: PipelineStepId, state: PipelineState): number {
  switch (step) {
    case "normalize":
      return state.normalize.done ? 1 : 0;
    case "stt":
      return state.stt.segments;
    case "ortho":
      return state.ortho.intervals;
    case "ipa":
      return state.ipa.intervals;
  }
}

export function computeCell(
  step: PipelineStepId,
  entry: SpeakerLoadEntry | undefined,
  speakerSelected: boolean,
  scope: RunScope,
): CellInfo {
  if (!entry) return { kind: "unknown", count: 0, reason: null };
  if (entry.status === "loading") return { kind: "loading", count: 0, reason: null };
  if (entry.status === "error" || !entry.state) {
    return { kind: "unknown", count: 0, reason: entry.error };
  }

  const stepState = entry.state[step];
  const count = stepCount(step, entry.state);

  if (!stepState.can_run) return { kind: "blocked", count, reason: stepState.reason };
  if (stepState.done) {
    if (speakerSelected) {
      return {
        kind: scope === "overwrite" ? "overwrite" : "keep",
        count,
        reason: null,
      };
    }
    return { kind: "skip", count, reason: null };
  }
  return { kind: "ok", count, reason: null };
}

export function cellClasses(kind: CellKind): string {
  switch (kind) {
    case "ok":
      return "bg-emerald-50 text-emerald-800 border-emerald-200";
    case "overwrite":
      return "bg-amber-50 text-amber-800 border-amber-300";
    case "keep":
      return "bg-sky-50 text-sky-800 border-sky-200";
    case "skip":
      return "bg-slate-100 text-slate-600 border-slate-200";
    case "blocked":
      return "bg-rose-50 text-rose-800 border-rose-200";
    case "loading":
      return "bg-slate-50 text-slate-400 border-slate-200";
    default:
      return "bg-white text-slate-400 border-slate-200";
  }
}

export function cellLabel(kind: CellKind): string {
  switch (kind) {
    case "ok":
      return "ok";
    case "overwrite":
      return "overwrite";
    case "keep":
      return "keep existing";
    case "skip":
      return "will skip";
    case "blocked":
      return "blocked";
    case "loading":
      return "loading";
    default:
      return "—";
  }
}

export function CellIcon({ kind }: { kind: CellKind }) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (kind) {
    case "ok":
      return <CheckCircle2 className={cls} aria-hidden="true" />;
    case "overwrite":
      return <RotateCcw className={cls} aria-hidden="true" />;
    case "keep":
      return <Pin className={cls} aria-hidden="true" />;
    case "skip":
      return <SkipForward className={cls} aria-hidden="true" />;
    case "blocked":
      return <Ban className={cls} aria-hidden="true" />;
    case "loading":
      return <Loader2 className={`${cls} animate-spin`} aria-hidden="true" />;
    default:
      return null;
  }
}
