import { useActionJob } from "./useActionJob";
import type { ActionJobState } from "./useActionJob";
import { startCompute, pollCompute } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

export type ComputeJobState = ActionJobState;

interface UseComputeJobOptions {
  body?: Record<string, unknown> | (() => Record<string, unknown> | undefined);
  label?: string;
}

function resolveComputeJobBody(
  body: UseComputeJobOptions["body"],
): Record<string, unknown> | undefined {
  if (typeof body === "function") {
    return body();
  }
  return body;
}

export function useComputeJob(computeType: string, options: UseComputeJobOptions = {}) {
  const loadEnrichments = useEnrichmentStore((store) => store.load);
  const { state, run, reset } = useActionJob({
    start: () => startCompute(computeType, resolveComputeJobBody(options.body)),
    poll: (jobId) => pollCompute(computeType, jobId),
    label: options.label ?? `Computing ${computeType}…`,
    onComplete: loadEnrichments,
    autoDismissMs: 0, // compute panel manages its own display
  });
  return { start: run, state, reset };
}
