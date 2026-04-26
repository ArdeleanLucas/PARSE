import { useEnrichmentStore } from "../../../stores/enrichmentStore";

export function useEnrichmentsBinding() {
  const enrichmentData = useEnrichmentStore((s) => s.data) as Record<string, unknown>;
  const saveEnrichments = useEnrichmentStore((s) => s.save);
  return { enrichmentData, saveEnrichments };
}
