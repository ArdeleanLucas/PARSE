import { pollCompute, type PipelineRunResult } from "../../api/client";

import { delay, isCompleteStatus, isErrorStatus, normalizeProgress, toErrorMessage } from "./useBatchJobErrors";
import type { BatchPollOutcome } from "./types";
import { POLL_INTERVAL_MS } from "./types";

export async function pollBatchSpeakerJob(
  jobId: string,
  isActive: () => boolean,
  onProgress: (progress: number, message: string | null) => void,
  isCancelled: () => boolean,
): Promise<BatchPollOutcome> {
  let pollErrored = false;
  let pollResult: PipelineRunResult | null = null;
  let pollErrorMessage: string | null = null;
  let pollCancelled = false;

  const markCancelled = () => {
    pollCancelled = true;
  };

  while (isActive()) {
    if (isCancelled()) {
      markCancelled();
      break;
    }

    let poll;
    try {
      poll = await pollCompute("full_pipeline", jobId);
    } catch (error) {
      if (!isActive()) break;
      if (isCancelled()) {
        markCancelled();
        break;
      }
      pollErrored = true;
      pollErrorMessage = toErrorMessage(error, "Pipeline poll failed");
      break;
    }
    if (!isActive()) break;
    if (isCancelled()) {
      markCancelled();
      break;
    }

    const progress = normalizeProgress(Number(poll.progress ?? 0));
    const status = String(poll.status || "running").toLowerCase();
    const message = typeof poll.message === "string" && poll.message ? poll.message : null;
    onProgress(progress, message);

    const raw = poll as unknown as { result?: PipelineRunResult };
    if (isCompleteStatus(status)) {
      pollResult = raw.result ?? null;
      break;
    }
    if (isErrorStatus(status)) {
      pollErrored = true;
      pollErrorMessage = poll.error ?? poll.message ?? "Pipeline failed";
      pollResult = raw.result ?? null;
      break;
    }

    await delay(POLL_INTERVAL_MS);
  }

  return { pollErrored, pollResult, pollErrorMessage, pollCancelled };
}
