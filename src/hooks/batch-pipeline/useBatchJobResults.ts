import type { BatchRunRequest, BatchSpeakerOutcome, BatchState } from "./types";

export function createInitialOutcomes(speakers: string[]): BatchSpeakerOutcome[] {
  return speakers.map((speaker) => ({ speaker, status: "pending", error: null, result: null }));
}

export function createRunningState(speakers: string[]): BatchState {
  return {
    status: "running",
    cancelled: false,
    totalSpeakers: speakers.length,
    completedSpeakers: 0,
    currentSpeakerIndex: null,
    currentSpeaker: null,
    currentSubJobId: null,
    currentProgress: 0,
    currentMessage: null,
    outcomes: createInitialOutcomes(speakers),
  };
}

export function markPendingSpeakersCancelled(outcomes: BatchSpeakerOutcome[], startIndex: number): BatchSpeakerOutcome[] {
  return outcomes.map((outcome, index) => (
    index >= startIndex && outcome.status === "pending" ? { ...outcome, status: "cancelled" } : outcome
  ));
}

export function resolveStepsForSpeaker(request: BatchRunRequest, speaker: string) {
  return request.stepsBySpeaker?.[speaker] ?? request.steps;
}
