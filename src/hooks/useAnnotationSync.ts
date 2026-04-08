import { useEffect } from "react";
import { useUIStore } from "../stores/uiStore";
import { useAnnotationStore } from "../stores/annotationStore";

export function useAnnotationSync() {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const loadSpeaker = useAnnotationStore((s) => s.loadSpeaker);

  useEffect(() => {
    if (!activeSpeaker) return;
    loadSpeaker(activeSpeaker).catch((err) => {
      console.error("[useAnnotationSync] loadSpeaker failed:", err);
    });
  }, [activeSpeaker, loadSpeaker]);

  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );
  const dirty = useAnnotationStore((s) =>
    activeSpeaker ? (s.dirty[activeSpeaker] ?? false) : false,
  );
  const loading = useAnnotationStore((s) =>
    activeSpeaker ? (s.loading[activeSpeaker] ?? false) : false,
  );

  return { record, dirty, loading, activeSpeaker };
}
