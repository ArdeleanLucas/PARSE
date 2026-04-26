import { useAnnotationStore } from "../../../stores/annotationStore";
import { useConfigStore } from "../../../stores/configStore";
import { useEnrichmentStore } from "../../../stores/enrichmentStore";
import { useUIStore } from "../../../stores/uiStore";

export function useCompareSelection() {
  const config = useConfigStore((s) => s.config);
  const records = useAnnotationStore((s) => s.records);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedSpeakers = useUIStore((s) => s.selectedSpeakers);
  const setActiveConcept = useUIStore((s) => s.setActiveConcept);
  const enrichmentData = useEnrichmentStore((s) => s.data) as Record<string, unknown>;

  const speakers = selectedSpeakers.length > 0 ? selectedSpeakers : config?.speakers ?? [];

  return {
    activeConcept,
    config,
    enrichmentData,
    records,
    selectedSpeakers,
    setActiveConcept,
    speakers,
  };
}
