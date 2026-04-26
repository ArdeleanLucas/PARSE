import type { PipelineRunResult } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchRunRequest {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  language?: string;
  stepsBySpeaker?: Partial<Record<string, PipelineStepId[]>>;
  refineLexemes?: boolean;
}

export interface BatchSpeakerOutcome {
  speaker: string;
  status: "pending" | "running" | "complete" | "error" | "cancelled";
  error: string | null;
  jobId?: string;
  errorPhase?: "start" | "poll";
  result: PipelineRunResult | null;
}

export interface BatchState {
  status: "idle" | "running" | "cancelling" | "complete";
  cancelled: boolean;
  totalSpeakers: number;
  completedSpeakers: number;
  currentSpeakerIndex: number | null;
  currentSpeaker: string | null;
  currentSubJobId: string | null;
  currentProgress: number;
  currentMessage: string | null;
  outcomes: BatchSpeakerOutcome[];
}

export interface UseBatchPipelineJobResult {
  state: BatchState;
  run: (request: BatchRunRequest) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

export interface BatchPollOutcome {
  pollErrored: boolean;
  pollResult: PipelineRunResult | null;
  pollErrorMessage: string | null;
}

export const IDLE_STATE: BatchState = {
  status: "idle",
  cancelled: false,
  totalSpeakers: 0,
  completedSpeakers: 0,
  currentSpeakerIndex: null,
  currentSpeaker: null,
  currentSubJobId: null,
  currentProgress: 0,
  currentMessage: null,
  outcomes: [],
};

export const POLL_INTERVAL_MS = 1500;
