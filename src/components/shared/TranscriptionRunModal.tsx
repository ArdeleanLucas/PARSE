import { useEffect, useMemo, useState } from "react";
import { Workflow } from "lucide-react";
import { Modal } from "./Modal";
import { TranscriptionRunGrid } from "./TranscriptionRunGrid";
import { getPipelineState } from "../../api/client";
import {
  DEFAULT_SCOPE,
  STEP_ICONS,
  STEP_LABELS,
  STEP_ORDER,
  computeCell,
  type PipelineStepId,
  type RunScope,
  type SpeakerLoadEntry,
} from "./transcriptionRunShared";

export type { PipelineStepId, RunScope } from "./transcriptionRunShared";

export interface TranscriptionRunConfirm {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  refineLexemes?: boolean;
}

export interface TranscriptionRunModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (confirm: TranscriptionRunConfirm) => void;
  speakers: string[];
  defaultSelectedSpeaker: string | null;
  fixedSteps?: PipelineStepId[];
  title: string;
}

export function TranscriptionRunModal({
  open,
  onClose,
  onConfirm,
  speakers,
  defaultSelectedSpeaker,
  fixedSteps,
  title,
}: TranscriptionRunModalProps): JSX.Element | null {
  const [stateBySpeaker, setStateBySpeaker] = useState<Record<string, SpeakerLoadEntry>>({});
  const [selectedSpeakers, setSelectedSpeakers] = useState<Set<string>>(() => new Set());
  const [selectedSteps, setSelectedSteps] = useState<Set<PipelineStepId>>(() => new Set());
  const [refineLexemes, setRefineLexemes] = useState(false);
  const [scopeByStep, setScopeByStep] = useState<Record<PipelineStepId, RunScope>>(() => ({
    normalize: DEFAULT_SCOPE,
    stt: DEFAULT_SCOPE,
    ortho: DEFAULT_SCOPE,
    ipa: DEFAULT_SCOPE,
  }));

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setRefineLexemes(false);
    setScopeByStep({
      normalize: DEFAULT_SCOPE,
      stt: DEFAULT_SCOPE,
      ortho: DEFAULT_SCOPE,
      ipa: DEFAULT_SCOPE,
    });

    const initial: Record<string, SpeakerLoadEntry> = {};
    for (const s of speakers) initial[s] = { status: "loading", state: null, error: null };
    setStateBySpeaker(initial);

    setSelectedSpeakers(
      new Set(
        defaultSelectedSpeaker && speakers.includes(defaultSelectedSpeaker)
          ? [defaultSelectedSpeaker]
          : [],
      ),
    );

    if (fixedSteps && fixedSteps.length > 0) setSelectedSteps(new Set(fixedSteps));
    else setSelectedSteps(new Set(STEP_ORDER));

    for (const speaker of speakers) {
      getPipelineState(speaker)
        .then((state) => {
          if (cancelled) return;
          setStateBySpeaker((prev) => ({
            ...prev,
            [speaker]: { status: "ready", state, error: null },
          }));
          if (!fixedSteps && defaultSelectedSpeaker && speaker === defaultSelectedSpeaker) {
            const next = new Set<PipelineStepId>();
            for (const step of STEP_ORDER) if (!state[step].done) next.add(step);
            if (next.size > 0) setSelectedSteps(next);
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const message = err instanceof Error ? err.message : String(err ?? "Failed to load pipeline state");
          setStateBySpeaker((prev) => ({
            ...prev,
            [speaker]: { status: "error", state: null, error: message },
          }));
        });
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const stepsToRender: PipelineStepId[] = useMemo(() => {
    const active = fixedSteps && fixedSteps.length > 0 ? fixedSteps : STEP_ORDER;
    return STEP_ORDER.filter((s) => active.includes(s)).filter((s) => selectedSteps.has(s));
  }, [fixedSteps, selectedSteps]);

  const gridStepColumns: PipelineStepId[] = useMemo(() => {
    if (fixedSteps && fixedSteps.length > 0) {
      return STEP_ORDER.filter((s) => fixedSteps.includes(s));
    }
    return STEP_ORDER.filter((s) => selectedSteps.has(s));
  }, [fixedSteps, selectedSteps]);

  const toggleStep = (step: PipelineStepId) => {
    if (fixedSteps && fixedSteps.length > 0) return;
    setSelectedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  };

  const summary = useMemo(() => {
    let ok = 0;
    let keep = 0;
    let overwrite = 0;
    let blocked = 0;
    for (const speaker of selectedSpeakers) {
      const entry = stateBySpeaker[speaker];
      for (const step of stepsToRender) {
        const info = computeCell(step, entry, true, scopeByStep[step]);
        if (info.kind === "ok") ok++;
        else if (info.kind === "keep") keep++;
        else if (info.kind === "overwrite") overwrite++;
        else if (info.kind === "blocked") blocked++;
      }
    }
    return { ok, keep, overwrite, blocked };
  }, [selectedSpeakers, stepsToRender, stateBySpeaker, scopeByStep]);

  const hasAnySpeaker = selectedSpeakers.size > 0;
  const hasAnyStep = stepsToRender.length > 0;
  const willOverwrite = summary.overwrite > 0;

  const handleConfirm = () => {
    const speakersArr = speakers.filter((s) => selectedSpeakers.has(s));
    const stepsArr = STEP_ORDER.filter((s) => stepsToRender.includes(s));
    const overwrites: Partial<Record<PipelineStepId, boolean>> = {};
    for (const step of stepsArr) {
      if (scopeByStep[step] !== "overwrite") continue;
      for (const speaker of speakersArr) {
        const entry = stateBySpeaker[speaker];
        if (entry?.status === "ready" && entry.state && entry.state[step].done) {
          overwrites[step] = true;
          break;
        }
      }
    }
    const includesOrtho = stepsArr.includes("ortho");
    onConfirm({
      speakers: speakersArr,
      steps: stepsArr,
      overwrites,
      refineLexemes: includesOrtho && refineLexemes ? true : undefined,
    });
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div
        className="flex flex-col gap-3"
        data-testid="transcription-run-modal"
        style={{ minWidth: "36rem", maxWidth: "80vw" }}
      >
        <p className="text-xs text-slate-600">
          Pick speakers and steps. The grid below previews what will run — green cells run fresh, sky cells keep existing data, amber cells overwrite it, grey cells are skipped, and red cells are blocked by the backend.
        </p>

        {!fixedSteps && (
          <div
            className="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
            data-testid="transcription-run-step-checkboxes"
          >
            <span className="text-xs font-semibold text-slate-700">Steps</span>
            {STEP_ORDER.map((step) => {
              const Icon = STEP_ICONS[step];
              const checked = selectedSteps.has(step);
              return (
                <label
                  key={step}
                  className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    data-testid={`transcription-run-step-${step}`}
                    className="h-3.5 w-3.5 rounded border-slate-300"
                    checked={checked}
                    onChange={() => toggleStep(step)}
                  />
                  <Icon className="h-3.5 w-3.5 text-slate-500" />
                  <span>{STEP_LABELS[step]}</span>
                </label>
              );
            })}
          </div>
        )}

        {stepsToRender.includes("ortho") && (
          <div
            className="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-white px-3 py-2"
            data-testid="transcription-run-ortho-options"
          >
            <span className="text-xs font-semibold text-slate-700">ORTH</span>
            <label
              className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
              title="Re-transcribes each concept whose forced-alignment confidence is below 0.5 using a ±0.8 s audio clip. Adds ~1–2 min on thesis-scale recordings — leave off unless forced-alignment quality is poor."
            >
              <input
                type="checkbox"
                data-testid="transcription-run-refine-lexemes"
                className="h-3.5 w-3.5 rounded border-slate-300"
                checked={refineLexemes}
                onChange={(e) => setRefineLexemes(e.target.checked)}
              />
              <span>Refine lexemes (short-clip fallback)</span>
            </label>
          </div>
        )}

        <TranscriptionRunGrid
          speakers={speakers}
          gridStepColumns={gridStepColumns}
          selectedSpeakers={selectedSpeakers}
          stateBySpeaker={stateBySpeaker}
          scopeByStep={scopeByStep}
          onToggleSpeaker={(speaker) => {
            setSelectedSpeakers((prev) => {
              const next = new Set(prev);
              if (next.has(speaker)) next.delete(speaker);
              else next.add(speaker);
              return next;
            });
          }}
          onSetAllSpeakers={setSelectedSpeakers}
          onSetStepScope={(step, scope) => {
            setScopeByStep((prev) => ({ ...prev, [step]: scope }));
          }}
        />

        <div
          className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600"
          data-testid="transcription-run-summary"
        >
          <span>
            Running {selectedSpeakers.size} speaker{selectedSpeakers.size === 1 ? "" : "s"} × {stepsToRender.length} step{stepsToRender.length === 1 ? "" : "s"}. <span className="text-emerald-700 font-medium">{summary.ok} ok</span>, <span className="text-sky-700 font-medium">{summary.keep} keep existing</span>, <span className="text-amber-700 font-medium">{summary.overwrite} will overwrite</span>, <span className="text-rose-700 font-medium">{summary.blocked} blocked</span> (will be skipped at runtime).
          </span>
        </div>

        <div className="mt-1 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
            data-testid="transcription-run-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!hasAnySpeaker || !hasAnyStep}
            data-testid="transcription-run-confirm"
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 ${
              willOverwrite ? "bg-amber-600 hover:bg-amber-700" : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            <Workflow className="h-3.5 w-3.5" />
            Run {selectedSpeakers.size} speaker{selectedSpeakers.size === 1 ? "" : "s"}
            {willOverwrite ? " (with overwrites)" : ""}
          </button>
        </div>
      </div>
    </Modal>
  );
}
