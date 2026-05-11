import { useEffect, useMemo, useState } from "react";

import { useAnnotationStore } from "../../../stores/annotationStore";
import type { DragToCreateSelection, WaveSurferRegionsControls } from "../../../hooks/wave-surfer/types";

type CreateLexemePanelProps = {
  speaker: string;
  conceptKey: string;
  enableDragToCreate: WaveSurferRegionsControls["enableDragToCreate"];
  disableDragToCreate: WaveSurferRegionsControls["disableDragToCreate"];
  onCreated?: () => void;
};

function formatSelectionValue(value: number | null): string {
  return value === null ? "—" : value.toFixed(3);
}

function regionIsValid(region: DragToCreateSelection | null): region is DragToCreateSelection {
  return Boolean(region && Number.isFinite(region.start) && Number.isFinite(region.end) && region.end > region.start);
}

export function CreateLexemePanel({
  speaker,
  conceptKey,
  enableDragToCreate,
  disableDragToCreate,
  onCreated,
}: CreateLexemePanelProps) {
  const [inFlightRegion, setInFlightRegion] = useState<DragToCreateSelection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const createConceptInterval = useAnnotationStore((store) => store.createConceptInterval);

  useEffect(() => {
    setInFlightRegion(null);
    setError(null);
    const cleanup = enableDragToCreate({
      onRegionCreated: (selection) => {
        setError(null);
        setInFlightRegion(selection);
      },
      onRegionUpdated: (selection) => {
        setError(null);
        setInFlightRegion(selection);
      },
    });
    return () => {
      if (cleanup === disableDragToCreate) {
        cleanup();
      } else {
        cleanup();
        disableDragToCreate();
      }
    };
  }, [conceptKey, disableDragToCreate, enableDragToCreate, speaker]);

  const canCreate = regionIsValid(inFlightRegion) && !saving;
  const intervalLabel = useMemo(() => {
    if (!inFlightRegion) return "No waveform selection yet.";
    return `Selected ${(inFlightRegion.end - inFlightRegion.start).toFixed(3)}s`;
  }, [inFlightRegion]);

  return (
    <div className="rounded-xl border border-dashed border-emerald-300 bg-emerald-50/60 px-4 py-3 text-[12px] text-slate-700">
      <p className="mb-2 font-semibold text-slate-800">No lexeme interval yet for this variant.</p>
      <p className="mb-3 text-slate-600">Drag on the waveform above to mark the audio span for this lexeme.</p>
      <div className="flex flex-wrap items-center gap-3">
        <div data-testid="create-lexeme-start" className="font-mono text-[11px] text-slate-700">
          Start: {formatSelectionValue(inFlightRegion?.start ?? null)}
        </div>
        <div data-testid="create-lexeme-end" className="font-mono text-[11px] text-slate-700">
          End: {formatSelectionValue(inFlightRegion?.end ?? null)}
        </div>
        <div className="text-[11px] text-slate-500">{intervalLabel}</div>
        <button
          type="button"
          data-testid="create-lexeme-interval"
          disabled={!canCreate}
          onClick={async () => {
            if (!regionIsValid(inFlightRegion)) return;
            setSaving(true);
            setError(null);
            try {
              await createConceptInterval(speaker, conceptKey, inFlightRegion.start, inFlightRegion.end);
              setInFlightRegion(null);
              onCreated?.();
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err || "Create lexeme failed."));
            } finally {
              setSaving(false);
            }
          }}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:opacity-70"
        >
          {saving ? "Creating…" : "Create lexeme"}
        </button>
      </div>
      {error && <p className="mt-2 text-rose-600">{error}</p>}
    </div>
  );
}
