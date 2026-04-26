import { useAnnotationStore } from "../../../stores/annotationStore";
import { useConfigStore } from "../../../stores/configStore";
import { useUIStore } from "../../../stores/uiStore";

export function useAnnotateSelection() {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConceptId = useUIStore((s) => s.activeConcept);
  const concepts = useConfigStore((s) => s.config?.concepts ?? []);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );

  return {
    activeConceptId,
    activeSpeaker,
    concepts,
    record,
  };
}
