import React, { useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  Ban,
  CheckCircle2,
  Loader2,
  Mic,
  Pin,
  RotateCcw,
  SkipForward,
  Type,
  Workflow,
} from "lucide-react";
import { Modal } from "./Modal";
import { getPipelineState, type PipelineState } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export type RunScope = "gaps" | "overwrite";

// Default scope for collisions. "gaps" preserves existing data (IPA fills
// empty intervals; ORTH is a no-op when the tier already has content). The
// user must explicitly opt into "overwrite" to clobber finalized work.
const DEFAULT_SCOPE: RunScope = "gaps";

const STEP_ORDER: PipelineStepId[] = ["normalize", "stt", "ortho", "ipa"];

const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Normalize",
  stt: "STT",
  ortho: "ORTH",
  ipa: "IPA",
};

const STEP_ICONS: Record<
  PipelineStepId,
  React.ComponentType<{ className?: string }>
> = {
  normalize: AudioLines,
  stt: Mic,
  ortho: Type,
  ipa: Workflow,
};

type LoadStatus = "loading" | "ready" | "error";

interface SpeakerLoadEntry {
  status: LoadStatus;
  state: PipelineState | null;
  error: string | null;
}

export interface TranscriptionRunConfirm {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  /** Opt-in short-clip Whisper fallback for the ORTH step. Only meaningful
   *  when `steps` includes `"ortho"`; the backend ignores it otherwise. */
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

type CellKind =
  | "ok"
  | "skip"
  | "keep"
  | "overwrite"
  | "blocked"
  | "loading"
  | "unknown";

interface CellInfo {
  kind: CellKind;
  count: number;
  reason: string | null;
}

// Per-step human-readable copy for the "keep existing" scope. ORTH is a pure
// no-op when the tier already has content (razhan's segmentation isn't stable
// across runs), so the tooltip wording differs from IPA.
function keepTooltip(step: PipelineStepId, count: number): string {
  if (step === "ortho") {
    return `Keeping existing ORTH tier (${count} intervals). This step will no-op — switch to Overwrite to redo it.`;
  }
  if (step === "ipa") {
    return `Keeping existing IPA intervals (${count}). Empty intervals will still be filled; finalized text stays put.`;
  }
  return `Keeping existing output (${count}). Switch to Overwrite to redo.`;
}

function stepCount(step: PipelineStepId, state: PipelineState): number {
  switch (step) {
    case "normalize":
      return state.normalize.done ? 1 : 0;
    case "stt":
      return state.stt.segments;
    case "ortho":
      return state.ortho.intervals;
    case "ipa":
      return state.ipa.intervals;
  }
}

function computeCell(
  step: PipelineStepId,
  entry: SpeakerLoadEntry | undefined,
  speakerSelected: boolean,
  scope: RunScope,
): CellInfo {
  if (!entry) return { kind: "unknown", count: 0, reason: null };
  if (entry.status === "loading")
    return { kind: "loading", count: 0, reason: null };
  if (entry.status === "error" || !entry.state)
    return { kind: "unknown", count: 0, reason: entry.error };

  const stepState = entry.state[step];
  const count = stepCount(step, entry.state);

  if (!stepState.can_run) {
    return { kind: "blocked", count, reason: stepState.reason };
  }
  if (stepState.done) {
    if (speakerSelected) {
      return {
        kind: scope === "overwrite" ? "overwrite" : "keep",
        count,
        reason: null,
      };
    }
    return { kind: "skip", count, reason: null };
  }
  return { kind: "ok", count, reason: null };
}

function cellClasses(kind: CellKind): string {
  switch (kind) {
    case "ok":
      return "bg-emerald-50 text-emerald-800 border-emerald-200";
    case "overwrite":
      return "bg-amber-50 text-amber-800 border-amber-300";
    case "keep":
      return "bg-sky-50 text-sky-800 border-sky-200";
    case "skip":
      return "bg-slate-100 text-slate-600 border-slate-200";
    case "blocked":
      return "bg-rose-50 text-rose-800 border-rose-200";
    case "loading":
      return "bg-slate-50 text-slate-400 border-slate-200";
    default:
      return "bg-white text-slate-400 border-slate-200";
  }
}

function cellLabel(kind: CellKind): string {
  switch (kind) {
    case "ok":
      return "ok";
    case "overwrite":
      return "overwrite";
    case "keep":
      return "keep existing";
    case "skip":
      return "will skip";
    case "blocked":
      return "blocked";
    case "loading":
      return "loading";
    default:
      return "—";
  }
}

function CellIcon({ kind }: { kind: CellKind }) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (kind) {
    case "ok":
      return <CheckCircle2 className={cls} aria-hidden="true" />;
    case "overwrite":
      return <RotateCcw className={cls} aria-hidden="true" />;
    case "keep":
      return <Pin className={cls} aria-hidden="true" />;
    case "skip":
      return <SkipForward className={cls} aria-hidden="true" />;
    case "blocked":
      return <Ban className={cls} aria-hidden="true" />;
    case "loading":
      return <Loader2 className={`${cls} animate-spin`} aria-hidden="true" />;
    default:
      return null;
  }
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
  const [stateBySpeaker, setStateBySpeaker] = useState<
    Record<string, SpeakerLoadEntry>
  >({});
  const [selectedSpeakers, setSelectedSpeakers] = useState<Set<string>>(
    () => new Set(),
  );
  const [selectedSteps, setSelectedSteps] = useState<Set<PipelineStepId>>(
    () => new Set(),
  );
  // Off by default — opt-in per run. Adds ~1-2 min to each ORTH run on
  // thesis-scale audio, so surfacing it as unchecked is the safer default.
  const [refineLexemes, setRefineLexemes] = useState(false);
  // Per-step scope — only consulted when a step has `done=true` for at least
  // one selected speaker. "gaps" keeps existing data (safe default); the user
  // must explicitly flip a step to "overwrite" to clobber finalized output.
  const [scopeByStep, setScopeByStep] = useState<
    Record<PipelineStepId, RunScope>
  >(() => ({
    normalize: DEFAULT_SCOPE,
    stt: DEFAULT_SCOPE,
    ortho: DEFAULT_SCOPE,
    ipa: DEFAULT_SCOPE,
  }));

  // Reset state when the modal opens.
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

    // Seed per-speaker load entries as "loading".
    const initial: Record<string, SpeakerLoadEntry> = {};
    for (const s of speakers) {
      initial[s] = { status: "loading", state: null, error: null };
    }
    setStateBySpeaker(initial);

    // Pre-check the default speaker (if any).
    setSelectedSpeakers(
      new Set(
        defaultSelectedSpeaker && speakers.includes(defaultSelectedSpeaker)
          ? [defaultSelectedSpeaker]
          : [],
      ),
    );

    // Pre-check steps. If fixedSteps is set, lock to exactly those. Otherwise
    // default to everything (we'll refine once the default speaker's state
    // loads).
    if (fixedSteps && fixedSteps.length > 0) {
      setSelectedSteps(new Set(fixedSteps));
    } else {
      setSelectedSteps(new Set(STEP_ORDER));
    }

    // Fire all speaker-state fetches independently.
    for (const speaker of speakers) {
      getPipelineState(speaker)
        .then((state) => {
          if (cancelled) return;
          setStateBySpeaker((prev) => ({
            ...prev,
            [speaker]: { status: "ready", state, error: null },
          }));
          // When the default speaker's state arrives, refine step defaults
          // (only if fixedSteps wasn't provided).
          if (
            !fixedSteps &&
            defaultSelectedSpeaker &&
            speaker === defaultSelectedSpeaker
          ) {
            const next = new Set<PipelineStepId>();
            for (const step of STEP_ORDER) {
              if (!state[step].done) next.add(step);
            }
            // If literally nothing is undone, leave the "all" default so the
            // user sees overwrite cues rather than an empty selection.
            if (next.size > 0) setSelectedSteps(next);
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const message =
            err instanceof Error
              ? err.message
              : String(err ?? "Failed to load pipeline state");
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
    const active =
      fixedSteps && fixedSteps.length > 0 ? fixedSteps : STEP_ORDER;
    return STEP_ORDER.filter((s) => active.includes(s)).filter((s) =>
      selectedSteps.has(s),
    );
  }, [fixedSteps, selectedSteps]);

  // For the grid we want to always render every column that the user could
  // tick (so toggling a step shows its column), not only the currently-ticked
  // ones. The badge inside each cell still reacts to (selected speaker, step,
  // state).
  const gridStepColumns: PipelineStepId[] = useMemo(() => {
    if (fixedSteps && fixedSteps.length > 0) {
      return STEP_ORDER.filter((s) => fixedSteps.includes(s));
    }
    return STEP_ORDER.filter((s) => selectedSteps.has(s));
  }, [fixedSteps, selectedSteps]);

  const toggleSpeaker = (speaker: string) => {
    setSelectedSpeakers((prev) => {
      const next = new Set(prev);
      if (next.has(speaker)) next.delete(speaker);
      else next.add(speaker);
      return next;
    });
  };

  const toggleStep = (step: PipelineStepId) => {
    if (fixedSteps && fixedSteps.length > 0) return;
    setSelectedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  };

  const setAllSpeakers = (mode: "all" | "none" | "runnable") => {
    if (mode === "none") {
      setSelectedSpeakers(new Set());
      return;
    }
    if (mode === "all") {
      setSelectedSpeakers(
        new Set(
          speakers.filter((s) => stateBySpeaker[s]?.status !== "error"),
        ),
      );
      return;
    }
    // "runnable" — speakers with at least one can_run=true in the currently
    // selected step columns.
    const relevantSteps = gridStepColumns;
    const next = new Set<string>();
    for (const speaker of speakers) {
      const entry = stateBySpeaker[speaker];
      if (!entry || entry.status !== "ready" || !entry.state) continue;
      const anyRunnable = relevantSteps.some(
        (step) => entry.state![step].can_run,
      );
      if (anyRunnable) next.add(speaker);
    }
    setSelectedSpeakers(next);
  };

  // Steps where at least one selected speaker has done=true — i.e. steps that
  // need a scope choice. Used to drive the collisions toolbar.
  const collisionSteps: PipelineStepId[] = useMemo(() => {
    const out: PipelineStepId[] = [];
    for (const step of stepsToRender) {
      let hit = false;
      for (const speaker of selectedSpeakers) {
        const entry = stateBySpeaker[speaker];
        if (
          entry?.status === "ready" &&
          entry.state &&
          entry.state[step].done
        ) {
          hit = true;
          break;
        }
      }
      if (hit) out.push(step);
    }
    return out;
  }, [stepsToRender, selectedSpeakers, stateBySpeaker]);

  // Summary stats over the visible grid.
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

  const setStepScope = (step: PipelineStepId, scope: RunScope) => {
    setScopeByStep((prev) => ({ ...prev, [step]: scope }));
  };

  const handleConfirm = () => {
    const speakersArr = speakers.filter((s) => selectedSpeakers.has(s));
    const stepsArr = STEP_ORDER.filter((s) => stepsToRender.includes(s));

    const overwrites: Partial<Record<PipelineStepId, boolean>> = {};
    for (const step of stepsArr) {
      if (scopeByStep[step] !== "overwrite") continue;
      for (const speaker of speakersArr) {
        const entry = stateBySpeaker[speaker];
        if (
          entry?.status === "ready" &&
          entry.state &&
          entry.state[step].done
        ) {
          overwrites[step] = true;
          break;
        }
      }
    }

    // refine_lexemes only matters when ORTH is actually scheduled; drop it
    // otherwise so the backend falls back to its ai_config default.
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
          Pick speakers and steps. The grid below previews what will run — green
          cells run fresh, sky cells keep existing data, amber cells overwrite
          it, grey cells are skipped, and red cells are blocked by the backend.
        </p>

        {/* Step checkboxes — hidden when fixedSteps is set. */}
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

        {/* ORTH options — only relevant when ortho is scheduled. */}
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

        {/* Collisions toolbar — per-step scope when the selected speakers
            already have finalized output for a step. Hidden when there are no
            collisions so the default view stays clean. */}
        {collisionSteps.length > 0 && (
          <div
            className="flex flex-wrap items-center gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2"
            data-testid="transcription-run-scope-bar"
          >
            <span
              className="text-xs font-semibold text-amber-900"
              title="Some selected speakers already have finalized output for these steps. Choose Keep to preserve existing data, or Overwrite to clobber it."
            >
              Existing data
            </span>
            {collisionSteps.map((step) => {
              const Icon = STEP_ICONS[step];
              const scope = scopeByStep[step];
              return (
                <div
                  key={step}
                  className="flex items-center gap-1.5 text-xs text-slate-700"
                  data-testid={`transcription-run-scope-${step}`}
                  data-step-scope={scope}
                >
                  <Icon className="h-3.5 w-3.5 text-slate-500" />
                  <span className="font-medium">{STEP_LABELS[step]}</span>
                  <div
                    role="radiogroup"
                    aria-label={`${STEP_LABELS[step]} scope`}
                    className="ml-0.5 inline-flex overflow-hidden rounded border border-slate-300"
                  >
                    <button
                      type="button"
                      role="radio"
                      aria-checked={scope === "gaps"}
                      onClick={() => setStepScope(step, "gaps")}
                      data-testid={`transcription-run-scope-${step}-keep`}
                      className={`px-2 py-0.5 text-[11px] font-medium transition ${
                        scope === "gaps"
                          ? "bg-sky-600 text-white"
                          : "bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      Keep
                    </button>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={scope === "overwrite"}
                      onClick={() => setStepScope(step, "overwrite")}
                      data-testid={`transcription-run-scope-${step}-overwrite`}
                      className={`border-l border-slate-300 px-2 py-0.5 text-[11px] font-medium transition ${
                        scope === "overwrite"
                          ? "bg-amber-600 text-white"
                          : "bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      Overwrite
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Speaker selection toolbar */}
        <div className="flex items-center gap-2 text-[11px] text-slate-600">
          <span className="font-semibold">Speakers:</span>
          <button
            type="button"
            onClick={() => setAllSpeakers("all")}
            className="rounded px-2 py-0.5 hover:bg-slate-100"
            data-testid="transcription-run-select-all"
          >
            Select all
          </button>
          <span className="text-slate-300">·</span>
          <button
            type="button"
            onClick={() => setAllSpeakers("runnable")}
            className="rounded px-2 py-0.5 hover:bg-slate-100"
            data-testid="transcription-run-select-runnable"
          >
            Select visible-runnable
          </button>
          <span className="text-slate-300">·</span>
          <button
            type="button"
            onClick={() => setAllSpeakers("none")}
            className="rounded px-2 py-0.5 hover:bg-slate-100"
            data-testid="transcription-run-select-none"
          >
            None
          </button>
        </div>

        {/* Grid */}
        <div
          className="max-h-[50vh] overflow-auto rounded-md border border-slate-200"
          data-testid="transcription-run-grid"
        >
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-slate-100 text-slate-700">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Speaker</th>
                {gridStepColumns.map((step) => {
                  const Icon = STEP_ICONS[step];
                  return (
                    <th
                      key={step}
                      className="px-3 py-2 text-left font-semibold"
                      data-testid={`transcription-run-col-${step}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        <Icon className="h-3.5 w-3.5" />
                        {STEP_LABELS[step]}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {speakers.map((speaker) => {
                const entry = stateBySpeaker[speaker];
                const speakerSelected = selectedSpeakers.has(speaker);
                const loadFailed = entry?.status === "error";
                return (
                  <tr
                    key={speaker}
                    className="border-t border-slate-200"
                    data-testid={`transcription-run-row-${speaker}`}
                  >
                    <td className="px-3 py-2">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          data-testid={`transcription-run-speaker-${speaker}`}
                          checked={speakerSelected}
                          disabled={loadFailed}
                          onChange={() => toggleSpeaker(speaker)}
                          className="h-3.5 w-3.5 rounded border-slate-300"
                        />
                        <span
                          className={`font-medium ${
                            loadFailed ? "text-slate-400" : "text-slate-800"
                          }`}
                        >
                          {speaker}
                        </span>
                        {loadFailed && (
                          <span className="text-[11px] text-slate-400">
                            (failed to load state)
                          </span>
                        )}
                      </label>
                    </td>
                    {gridStepColumns.map((step) => {
                      const info = computeCell(
                        step,
                        entry,
                        speakerSelected,
                        scopeByStep[step],
                      );
                      const tooltip = (() => {
                        if (info.kind === "blocked")
                          return info.reason ?? "Blocked by backend";
                        if (info.kind === "skip")
                          return `Already done (${info.count} items). Tick this row's speaker to choose a scope.`;
                        if (info.kind === "keep")
                          return keepTooltip(step, info.count);
                        if (info.kind === "overwrite")
                          return `Will overwrite ${info.count} existing items.`;
                        if (info.kind === "unknown")
                          return info.reason ?? "State unavailable";
                        return undefined;
                      })();
                      return (
                        <td
                          key={step}
                          className="px-3 py-2"
                          data-testid={`transcription-run-cell-${speaker}-${step}`}
                          data-cell-kind={info.kind}
                          title={tooltip}
                        >
                          <span
                            className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium ${cellClasses(
                              info.kind,
                            )}`}
                          >
                            <CellIcon kind={info.kind} />
                            <span>{cellLabel(info.kind)}</span>
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Summary footer */}
        <div
          className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600"
          data-testid="transcription-run-summary"
        >
          <span>
            Running {selectedSpeakers.size} speaker
            {selectedSpeakers.size === 1 ? "" : "s"} × {stepsToRender.length}{" "}
            step{stepsToRender.length === 1 ? "" : "s"}.{" "}
            <span className="text-emerald-700 font-medium">
              {summary.ok} ok
            </span>
            ,{" "}
            <span className="text-sky-700 font-medium">
              {summary.keep} keep existing
            </span>
            ,{" "}
            <span className="text-amber-700 font-medium">
              {summary.overwrite} will overwrite
            </span>
            ,{" "}
            <span className="text-rose-700 font-medium">
              {summary.blocked} blocked
            </span>{" "}
            (will be skipped at runtime).
          </span>
        </div>

        {/* Buttons */}
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
              willOverwrite
                ? "bg-amber-600 hover:bg-amber-700"
                : "bg-indigo-600 hover:bg-indigo-700"
            }`}
          >
            <Workflow className="h-3.5 w-3.5" />
            Run {selectedSpeakers.size} speaker
            {selectedSpeakers.size === 1 ? "" : "s"}
            {willOverwrite ? " (with overwrites)" : ""}
          </button>
        </div>
      </div>
    </Modal>
  );
}
