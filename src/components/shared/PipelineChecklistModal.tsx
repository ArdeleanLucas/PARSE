import React, { useEffect, useMemo, useState } from "react";
import { AlertCircle, AudioLines, Loader2, Mic, Type, Workflow } from "lucide-react";
import { Modal } from "./Modal";
import { getPipelineState, type PipelineState } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

const STEP_ORDER: PipelineStepId[] = ["normalize", "stt", "ortho", "ipa"];

const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Audio normalization",
  stt: "Speech-to-text",
  ortho: "Orthographic transcription (razhan)",
  ipa: "IPA transcription",
};

const STEP_ICONS: Record<PipelineStepId, React.ComponentType<{ className?: string }>> = {
  normalize: AudioLines,
  stt: Mic,
  ortho: Type,
  ipa: Type,
};

export interface PipelineChecklistResult {
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
}

interface PipelineChecklistModalProps {
  open: boolean;
  speaker: string;
  onClose: () => void;
  onConfirm: (result: PipelineChecklistResult) => void;
}

function describeState(step: PipelineStepId, state: PipelineState | null): string {
  if (!state) return "Checking…";
  switch (step) {
    case "normalize":
      return state.normalize.done
        ? "Already done (normalized WAV present)"
        : "Not yet run";
    case "stt":
      return state.stt.done
        ? `Already done (${state.stt.segments} segments cached)`
        : "Not yet run";
    case "ortho":
      return state.ortho.done
        ? `Already done (${state.ortho.intervals} intervals)`
        : "Not yet run";
    case "ipa":
      return state.ipa.done
        ? `Already done (${state.ipa.intervals} intervals)`
        : "Not yet run";
  }
}

function isStepDone(step: PipelineStepId, state: PipelineState | null): boolean {
  if (!state) return false;
  return state[step].done;
}

export function PipelineChecklistModal({
  open,
  speaker,
  onClose,
  onConfirm,
}: PipelineChecklistModalProps) {
  const [state, setState] = useState<PipelineState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Checked steps start as "everything that hasn't been done yet." The user
  // can opt IN to re-running completed steps by ticking the checkbox — that
  // tick implicitly grants the overwrite permission the backend needs.
  const [selected, setSelected] = useState<Record<PipelineStepId, boolean>>({
    normalize: false,
    stt: false,
    ortho: false,
    ipa: false,
  });

  useEffect(() => {
    if (!open || !speaker) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setState(null);
    getPipelineState(speaker)
      .then((result) => {
        if (cancelled) return;
        setState(result);
        // Default selection: run everything not yet done.
        setSelected({
          normalize: !result.normalize.done,
          stt: !result.stt.done,
          ortho: !result.ortho.done,
          ipa: !result.ipa.done,
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err ?? "Failed to load pipeline state");
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, speaker]);

  const toggle = (step: PipelineStepId) => {
    setSelected((prev) => ({ ...prev, [step]: !prev[step] }));
  };

  const willOverwriteAny = useMemo(
    () =>
      STEP_ORDER.some(
        (step) => selected[step] && isStepDone(step, state),
      ),
    [selected, state],
  );

  const hasAnySelected = useMemo(
    () => STEP_ORDER.some((s) => selected[s]),
    [selected],
  );

  const handleConfirm = () => {
    const steps = STEP_ORDER.filter((s) => selected[s]);
    const overwrites: Partial<Record<PipelineStepId, boolean>> = {};
    for (const step of steps) {
      if (isStepDone(step, state)) overwrites[step] = true;
    }
    onConfirm({ steps, overwrites });
  };

  return (
    <Modal open={open} onClose={onClose} title={`Run Full Pipeline — ${speaker || "no speaker"}`}>
      <div className="flex flex-col gap-3" data-testid="pipeline-checklist-modal">
        <p className="text-xs text-slate-600">
          Choose which steps to run. Steps already done are shown; re-ticking one
          will overwrite its existing data. Unchecked steps are skipped.
        </p>

        {loading && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading pipeline state…
          </div>
        )}
        {error && (
          <div className="flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && (
          <ul className="flex flex-col gap-1.5">
            {STEP_ORDER.map((step) => {
              const Icon = STEP_ICONS[step];
              const done = isStepDone(step, state);
              const willOverwrite = done && selected[step];
              return (
                <li
                  key={step}
                  className={`flex items-start gap-2 rounded-md border px-2.5 py-2 ${
                    willOverwrite
                      ? "border-amber-300 bg-amber-50"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <input
                    id={`pipeline-step-${step}`}
                    data-testid={`pipeline-step-${step}`}
                    type="checkbox"
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-slate-300"
                    checked={selected[step]}
                    onChange={() => toggle(step)}
                  />
                  <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                  <label
                    htmlFor={`pipeline-step-${step}`}
                    className="flex min-w-0 flex-1 flex-col cursor-pointer"
                  >
                    <span className="text-xs font-medium text-slate-700">
                      {STEP_LABELS[step]}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {describeState(step, state)}
                    </span>
                    {willOverwrite && (
                      <span className="mt-0.5 text-[11px] font-medium text-amber-700">
                        Will overwrite existing {step === "normalize" ? "WAV" : "data"}.
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-1 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            data-testid="pipeline-checklist-run"
            disabled={loading || Boolean(error) || !hasAnySelected}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 ${
              willOverwriteAny ? "bg-amber-600 hover:bg-amber-700" : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            <Workflow className="h-3.5 w-3.5" />
            {willOverwriteAny ? "Run (with overwrites)" : "Run selected steps"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
