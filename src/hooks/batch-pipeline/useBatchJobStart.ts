import { startCompute } from "../../api/client";

import type { BatchRunRequest, PipelineStepId } from "./types";

export async function startBatchSpeakerJob(
  request: BatchRunRequest,
  speaker: string,
  stepsForSpeaker: PipelineStepId[],
): Promise<string> {
  const body: Record<string, unknown> = {
    speaker,
    steps: stepsForSpeaker,
    overwrites: request.overwrites,
  };
  if (request.language) body.language = request.language;
  if (request.runMode) body.run_mode = request.runMode;
  if (request.refineLexemes) body.refine_lexemes = true;
  const job = await startCompute("full_pipeline", body);
  const jobId = String(job.job_id || "").trim();
  if (!jobId) throw new Error("Missing pipeline job id");
  return jobId;
}
