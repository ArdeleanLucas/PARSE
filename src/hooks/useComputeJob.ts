import { useActionJob } from "./useActionJob";
import type { ActionJobState } from "./useActionJob";
import { startCompute, pollCompute } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

export type ComputeJobState = ActionJobState;

export function useComputeJob(computeType: string) {
  const loadEnrichments = useEnrichmentStore((store) => store.load);
  const { state, run, reset } = useActionJob({
    start: () => startCompute(computeType),
    poll: (jobId) => pollCompute(computeType, jobId),
    label: `Computing ${computeType}…`,
    onComplete: loadEnrichments,
    autoDismissMs: 0, // compute panel manages its own display
  });
  return { start: run, state, reset };
}
