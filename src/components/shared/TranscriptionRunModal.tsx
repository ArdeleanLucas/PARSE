import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Workflow, X as XIcon, ChevronDown } from "lucide-react";
import { Modal } from "./Modal";
import { TranscriptionRunGrid } from "./TranscriptionRunGrid";
import {
  getAnnotation,
  getConceptsByTag,
  getPipelineState,
} from "../../api/client";
import type { ConceptsByTagResponse, TagMatchMode } from "../../api/contracts/concepts";
import { LEXEME_RERUN_PAD_VALUES, type AnnotationInterval, type LexemeRerunPad } from "../../api/types";
import { useTagStore } from "../../stores/tagStore";
import {
  DEFAULT_SCOPE,
  STEP_ICONS,
  STEP_LABELS,
  STEP_ORDER,
  computeCell,
  type PipelineStepId,
  type RunScope,
  type SpeakerLoadEntry,
  type TranscriptionRunMode,
} from "./transcriptionRunShared";

export type { PipelineStepId, RunScope } from "./transcriptionRunShared";

export interface TranscriptionRunConfirm {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  refineLexemes?: boolean;
  runMode: TranscriptionRunMode;
  pad?: LexemeRerunPad;
  tagLabels?: string[];
  tagMatch?: TagMatchMode;
}

interface EditedConceptPreviewRow {
  conceptId: string;
  conceptName: string;
  start: number;
  end: number;
}

function conceptIntervalId(interval: AnnotationInterval, index: number): string {
  const raw = (interval as AnnotationInterval & { id?: unknown; concept_id?: unknown; conceptId?: unknown }).id
    ?? (interval as AnnotationInterval & { concept_id?: unknown }).concept_id
    ?? (interval as AnnotationInterval & { conceptId?: unknown }).conceptId;
  const text = raw == null ? "" : String(raw).trim();
  return text || String(index + 1);
}

function formatEditedConceptPreviewRow(row: EditedConceptPreviewRow): string {
  return `#${row.conceptId} "${row.conceptName}"  ${row.start.toFixed(3)}–${row.end.toFixed(3)}s`;
}

const DEFAULT_ACTION_MENU_PAD: LexemeRerunPad = 0.2;
const ACTION_MENU_PAD_OPTIONS: LexemeRerunPad[] = [...LEXEME_RERUN_PAD_VALUES];
const PAD_APPLICABLE_STEPS = new Set<PipelineStepId>(["stt", "ortho", "ipa"]);

function formatActionMenuPad(value: LexemeRerunPad): string {
  return value.toFixed(1);
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
  const [runMode, setRunMode] = useState<TranscriptionRunMode>("full");
  const [editedConcepts, setEditedConcepts] = useState<EditedConceptPreviewRow[]>([]);
  const [padSec, setPadSec] = useState<LexemeRerunPad>(DEFAULT_ACTION_MENU_PAD);
  const padRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [editedConceptsStatus, setEditedConceptsStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [editedConceptsError, setEditedConceptsError] = useState<string | null>(null);
  const [refineLexemes, setRefineLexemes] = useState(false);
  const [scopeByStep, setScopeByStep] = useState<Record<PipelineStepId, RunScope>>(() => ({
    normalize: DEFAULT_SCOPE,
    stt: DEFAULT_SCOPE,
    ortho: DEFAULT_SCOPE,
    ipa: DEFAULT_SCOPE,
  }));

  // Tagged-only mode state
  const tagVocabulary = useTagStore((s) => s.tags);
  const [selectedTagLabels, setSelectedTagLabels] = useState<string[]>([]);
  const [tagMatch, setTagMatch] = useState<TagMatchMode>("any");
  const [tagPickerOpen, setTagPickerOpen] = useState(false);
  const [taggedPreview, setTaggedPreview] = useState<ConceptsByTagResponse | null>(null);
  const [taggedPreviewStatus, setTaggedPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [taggedPreviewError, setTaggedPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPadSec(DEFAULT_ACTION_MENU_PAD);
      return;
    }
    let cancelled = false;
    setRefineLexemes(false);
    setRunMode("full");
    setEditedConcepts([]);
    setPadSec(DEFAULT_ACTION_MENU_PAD);
    setEditedConceptsStatus("idle");
    setEditedConceptsError(null);
    setSelectedTagLabels([]);
    setTagMatch("any");
    setTagPickerOpen(false);
    setTaggedPreview(null);
    setTaggedPreviewStatus("idle");
    setTaggedPreviewError(null);
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

  const previewSpeaker = useMemo(() => {
    if (defaultSelectedSpeaker && selectedSpeakers.has(defaultSelectedSpeaker)) return defaultSelectedSpeaker;
    return speakers.find((speaker) => selectedSpeakers.has(speaker)) ?? null;
  }, [defaultSelectedSpeaker, selectedSpeakers, speakers]);

  useEffect(() => {
    if (!open || runMode !== "edited-only" || !previewSpeaker) {
      setEditedConcepts([]);
      setEditedConceptsStatus("idle");
      setEditedConceptsError(null);
      return;
    }

    let cancelled = false;
    setEditedConceptsStatus("loading");
    setEditedConceptsError(null);
    getAnnotation(previewSpeaker)
      .then((record) => {
        if (cancelled) return;
        const rows = (record.tiers.concept?.intervals ?? [])
          .map((interval, index) => ({ interval, index }))
          .filter(({ interval }) => interval.manuallyAdjusted === true)
          .map(({ interval, index }) => ({
            conceptId: conceptIntervalId(interval, index),
            conceptName: interval.text || "(untitled)",
            start: interval.start,
            end: interval.end,
          }))
          .sort((a, b) => a.start - b.start);
        setEditedConcepts(rows);
        setEditedConceptsStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setEditedConcepts([]);
        setEditedConceptsStatus("error");
        setEditedConceptsError(err instanceof Error ? err.message : String(err ?? "Failed to load concepts"));
      });
    return () => {
      cancelled = true;
    };
  }, [open, previewSpeaker, runMode]);

  // Tagged-only preview: re-fire whenever speakers/tags/match change.
  const selectedSpeakersKey = useMemo(
    () => JSON.stringify(speakers.filter((s) => selectedSpeakers.has(s))),
    [speakers, selectedSpeakers],
  );
  const selectedTagsKey = useMemo(
    () => JSON.stringify(selectedTagLabels),
    [selectedTagLabels],
  );

  useEffect(() => {
    if (!open || runMode !== "tagged-only") {
      setTaggedPreview(null);
      setTaggedPreviewStatus("idle");
      setTaggedPreviewError(null);
      return;
    }
    const speakerList = speakers.filter((s) => selectedSpeakers.has(s));
    if (speakerList.length === 0 || selectedTagLabels.length === 0) {
      setTaggedPreview(null);
      setTaggedPreviewStatus("idle");
      setTaggedPreviewError(null);
      return;
    }

    let cancelled = false;
    setTaggedPreviewStatus("loading");
    setTaggedPreviewError(null);
    getConceptsByTag({
      speakers: speakerList,
      tagLabels: selectedTagLabels,
      match: tagMatch,
    })
      .then((resp) => {
        if (cancelled) return;
        setTaggedPreview(resp);
        setTaggedPreviewStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTaggedPreview(null);
        setTaggedPreviewStatus("error");
        setTaggedPreviewError(err instanceof Error ? err.message : String(err ?? "Failed to load tagged concepts"));
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, runMode, selectedSpeakersKey, selectedTagsKey, tagMatch]);

  const selectableStepOrder: PipelineStepId[] = useMemo(() => (
    runMode === "full" ? STEP_ORDER : STEP_ORDER.filter((step) => step !== "normalize")
  ), [runMode]);

  const stepsToRender: PipelineStepId[] = useMemo(() => {
    const active = fixedSteps && fixedSteps.length > 0 ? fixedSteps : selectableStepOrder;
    return selectableStepOrder.filter((s) => active.includes(s)).filter((s) => selectedSteps.has(s));
  }, [fixedSteps, selectedSteps, selectableStepOrder]);

  const gridStepColumns: PipelineStepId[] = useMemo(() => {
    if (fixedSteps && fixedSteps.length > 0) {
      return selectableStepOrder.filter((s) => fixedSteps.includes(s));
    }
    return selectableStepOrder.filter((s) => selectedSteps.has(s));
  }, [fixedSteps, selectedSteps, selectableStepOrder]);

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
        const info = computeCell(step, entry, true, scopeByStep[step], runMode);
        if (info.kind === "ok") ok++;
        else if (info.kind === "keep") keep++;
        else if (info.kind === "overwrite") overwrite++;
        else if (info.kind === "blocked") blocked++;
      }
    }
    return { ok, keep, overwrite, blocked };
  }, [selectedSpeakers, stepsToRender, stateBySpeaker, scopeByStep, runMode]);

  const hasAnySpeaker = selectedSpeakers.size > 0;
  const hasAnyStep = stepsToRender.length > 0;
  const editedOnlyEmpty = runMode === "edited-only" && editedConceptsStatus === "ready" && editedConcepts.length === 0;
  const editedOnlyLoading = runMode === "edited-only" && editedConceptsStatus === "loading";
  const editedOnlyError = runMode === "edited-only" && editedConceptsStatus === "error";
  const taggedOnlyEmpty = runMode === "tagged-only"
    && taggedPreviewStatus === "ready"
    && (taggedPreview?.totalConcepts ?? 0) === 0;
  const taggedOnlyLoading = runMode === "tagged-only" && taggedPreviewStatus === "loading";
  const taggedOnlyError = runMode === "tagged-only" && taggedPreviewStatus === "error";
  const taggedOnlyMissingInputs = runMode === "tagged-only"
    && (selectedTagLabels.length === 0 || !hasAnySpeaker);
  // Mirror Lane A's upcoming 409-on-ambiguous boundary: if the user picked
  // match=ALL and the preview reports any ambiguous label, the request
  // would be rejected server-side. Disable confirm pre-emptively.
  const taggedOnlyAllAmbiguous = runMode === "tagged-only"
    && tagMatch === "all"
    && taggedPreviewStatus === "ready"
    && taggedPreview != null
    && Object.keys(taggedPreview.ambiguousTags).length > 0;
  const willOverwrite = summary.overwrite > 0;
  const includesPadApplicableStep = stepsToRender.some((step) => PAD_APPLICABLE_STEPS.has(step));
  const showPadSelector = runMode !== "full" && includesPadApplicableStep;

  const handlePadKeyDown = (value: LexemeRerunPad, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowDown" && event.key !== "ArrowLeft" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const currentIndex = ACTION_MENU_PAD_OPTIONS.indexOf(value);
    if (currentIndex < 0) return;
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + delta + ACTION_MENU_PAD_OPTIONS.length) % ACTION_MENU_PAD_OPTIONS.length;
    const next = ACTION_MENU_PAD_OPTIONS[nextIndex];
    setPadSec(next);
    padRefs.current[nextIndex]?.focus();
  };

  const toggleTagLabel = (label: string) => {
    setSelectedTagLabels((prev) => (
      prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label]
    ));
  };

  const removeTagLabel = (label: string) => {
    setSelectedTagLabels((prev) => prev.filter((x) => x !== label));
  };

  const tagColorByLabel = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of tagVocabulary) map.set(t.label, t.color);
    return map;
  }, [tagVocabulary]);

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
    const includesPadApplicableStepInPayload = stepsArr.some((step) => PAD_APPLICABLE_STEPS.has(step));
    onConfirm({
      speakers: speakersArr,
      steps: stepsArr,
      overwrites,
      runMode,
      pad: runMode !== "full" && includesPadApplicableStepInPayload ? padSec : undefined,
      refineLexemes: runMode === "full" && includesOrtho && refineLexemes ? true : undefined,
      tagLabels: runMode === "tagged-only" ? selectedTagLabels.slice() : undefined,
      tagMatch: runMode === "tagged-only" ? tagMatch : undefined,
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

        <fieldset
          className="rounded-md border border-slate-200 bg-white px-3 py-2"
          data-testid="transcription-run-mode"
        >
          <legend className="mb-1 text-xs font-semibold text-slate-700">Run mode</legend>
          <div className="flex flex-wrap gap-3">
            {([
              ["full", "Full audio", "Whole-file pipeline run."],
              ["concept-windows", "All concept windows", "Run selected steps on each concept window."],
              ["edited-only", "Edited concepts only", "Run selected steps on manually edited concepts."],
              ["tagged-only", "Tagged concepts only", "Run selected steps on concepts carrying chosen tags."],
            ] as const).map(([mode, label, help]) => (
              <label key={mode} className="flex items-start gap-1.5 text-xs text-slate-700 cursor-pointer">
                <input
                  type="radio"
                  name="transcription-run-mode"
                  value={mode}
                  data-testid={`transcription-run-mode-${mode}`}
                  checked={runMode === mode}
                  onChange={() => {
                    setRunMode(mode);
                    if (mode !== "full") setRefineLexemes(false);
                  }}
                  className="mt-0.5 h-3.5 w-3.5 border-slate-300"
                />
                <span>
                  <span className="font-medium text-slate-800">{label}</span>
                  <span className="ml-1 text-slate-500">{help}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {runMode === "tagged-only" && (
          <fieldset
            className="rounded-md border border-slate-200 bg-white px-3 py-2"
            data-testid="transcription-run-tagged-controls"
          >
            <legend className="mb-1 text-xs font-semibold text-slate-700">Tag filter</legend>

            {/* Selected tag chips */}
            {selectedTagLabels.length > 0 && (
              <div
                className="mb-2 flex flex-wrap gap-1.5"
                data-testid="transcription-run-tagged-chips"
              >
                {selectedTagLabels.map((label) => {
                  const color = tagColorByLabel.get(label) ?? "#6b7280";
                  return (
                    <span
                      key={label}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700"
                      data-testid={`transcription-run-tagged-chip-${label}`}
                    >
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: color }}
                        aria-hidden="true"
                      />
                      <span>{label}</span>
                      <button
                        type="button"
                        onClick={() => removeTagLabel(label)}
                        className="rounded text-slate-400 hover:text-slate-700"
                        aria-label={`Remove tag ${label}`}
                        data-testid={`transcription-run-tagged-chip-remove-${label}`}
                      >
                        <XIcon className="h-3 w-3" />
                      </button>
                    </span>
                  );
                })}
              </div>
            )}

            {/* Tag dropdown trigger */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setTagPickerOpen((v) => !v)}
                aria-expanded={tagPickerOpen}
                aria-haspopup="listbox"
                data-testid="transcription-run-tagged-picker-trigger"
                className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                <span>
                  {selectedTagLabels.length === 0
                    ? "Select tags…"
                    : `${selectedTagLabels.length} tag${selectedTagLabels.length === 1 ? "" : "s"} selected`}
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              </button>
              {tagPickerOpen && (
                <div
                  className="absolute z-10 mt-1 max-h-48 w-72 overflow-y-auto rounded-md border border-slate-200 bg-white p-1 text-xs shadow-md"
                  role="listbox"
                  data-testid="transcription-run-tagged-picker-popover"
                >
                  {tagVocabulary.length === 0 ? (
                    <div
                      className="px-2 py-1.5 text-slate-500"
                      data-testid="transcription-run-tagged-picker-empty"
                    >
                      No tags defined. Add tags from the right panel.
                    </div>
                  ) : (
                    tagVocabulary.map((tag) => {
                      const checked = selectedTagLabels.includes(tag.label);
                      return (
                        <label
                          key={tag.id}
                          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-slate-50"
                          data-testid={`transcription-run-tagged-picker-option-${tag.label}`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleTagLabel(tag.label)}
                            className="h-3.5 w-3.5 rounded border-slate-300"
                          />
                          <span
                            className="inline-block h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: tag.color }}
                            aria-hidden="true"
                          />
                          <span className="text-slate-700">{tag.label}</span>
                        </label>
                      );
                    })
                  )}
                </div>
              )}
            </div>

            {/* Match-mode segmented control */}
            <div
              className="mt-3"
              data-testid="transcription-run-tagged-match"
              role="radiogroup"
              aria-label="Tag match mode"
            >
              <div className="flex flex-wrap gap-3">
                {([
                  ["any", "Match ANY tag (OR — broader)"],
                  ["all", "Match ALL tags (AND — stricter)"],
                ] as const).map(([value, label]) => (
                  <label
                    key={value}
                    className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="transcription-run-tagged-match"
                      value={value}
                      checked={tagMatch === value}
                      onChange={() => setTagMatch(value)}
                      data-testid={`transcription-run-tagged-match-${value}`}
                      className="h-3.5 w-3.5 border-slate-300"
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <div className="mt-1 text-[11px] leading-snug text-slate-500">
                ANY = a concept that carries at least one of the selected tags.
                <br />
                ALL = a concept that carries every selected tag.
              </div>
            </div>
          </fieldset>
        )}

        {runMode === "edited-only" && (
          <div
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
            data-testid="transcription-run-edited-preview"
          >
            <div className="mb-1 font-semibold text-slate-700">Edited concept preview</div>
            {!previewSpeaker ? <div>Select a speaker to preview edited concepts.</div> : null}
            {editedConceptsStatus === "loading" ? <div>Loading edited concepts…</div> : null}
            {editedConceptsStatus === "error" ? (
              <div className="text-rose-700">{editedConceptsError ?? "Failed to load edited concepts."}</div>
            ) : null}
            {editedOnlyEmpty ? <div className="text-rose-700">No manually edited concepts on this speaker.</div> : null}
            {editedConcepts.length > 0 ? (
              <div className="max-h-28 overflow-y-auto rounded border border-slate-200 bg-white p-2 font-mono text-[11px] text-slate-700">
                {editedConcepts.map((row) => (
                  <div key={`${row.conceptId}-${row.start}-${row.end}`}>{formatEditedConceptPreviewRow(row)}</div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {runMode === "tagged-only" && (
          <div
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700"
            data-testid="transcription-run-tagged-preview"
          >
            <div className="mb-1 font-semibold text-slate-700">Tagged concept preview</div>
            {taggedOnlyMissingInputs ? (
              <div>Select at least one speaker and one tag to preview matching concepts.</div>
            ) : null}
            {taggedOnlyLoading ? <div>Loading tagged concepts…</div> : null}
            {taggedOnlyError ? (
              <div className="text-rose-700">
                {taggedPreviewError ?? "Failed to load tagged concepts."}
              </div>
            ) : null}
            {taggedOnlyEmpty ? (
              <div className="text-rose-700">No concepts carry the selected tags.</div>
            ) : null}
            {taggedPreviewStatus === "ready"
              && taggedPreview
              && taggedPreview.totalConcepts > 0 ? (
              <div
                className="max-h-48 overflow-y-auto rounded border border-slate-200 bg-white p-2 font-mono text-[11px] text-slate-700"
                data-testid="transcription-run-tagged-preview-list"
              >
                {Object.entries(taggedPreview.perSpeaker).map(([speaker, entry]) => (
                  <div
                    key={speaker}
                    className="mb-2"
                    data-testid={`transcription-run-tagged-preview-speaker-${speaker}`}
                  >
                    <div className="font-sans text-[11px] font-semibold text-slate-700">
                      {speaker} · {entry.conceptCount} concept{entry.conceptCount === 1 ? "" : "s"}
                    </div>
                    {entry.concepts.map((c) => (
                      <div
                        key={`${speaker}-${c.conceptId}-${c.start}`}
                        className="flex flex-wrap items-center gap-1.5 pl-3"
                        data-testid={`transcription-run-tagged-preview-row-${speaker}-${c.conceptId}`}
                      >
                        <span>
                          {`#${c.conceptId} "${c.name || "(untitled)"}"  ${c.start.toFixed(3)}–${c.end.toFixed(3)}`}
                        </span>
                        {c.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-sans text-slate-700"
                          >
                            <span
                              className="inline-block h-1.5 w-1.5 rounded-full"
                              style={{ backgroundColor: tagColorByLabel.get(tag) ?? "#6b7280" }}
                              aria-hidden="true"
                            />
                            {tag}
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
            {taggedPreviewStatus === "ready"
              && taggedPreview
              && taggedPreview.unknownTags.length > 0 ? (
              <div
                className="mt-1 text-[11px] text-amber-700"
                data-testid="transcription-run-tagged-preview-unknown"
              >
                {tagMatch === "any"
                  ? `Unknown tags ignored: ${taggedPreview.unknownTags.join(", ")}.`
                  : `Unknown tags ignored — note: ALL match expected every tag to resolve. Offending: ${taggedPreview.unknownTags.join(", ")}.`}
              </div>
            ) : null}
            {taggedPreviewStatus === "ready"
              && taggedPreview
              && Object.keys(taggedPreview.ambiguousTags).length > 0 ? (
              <div
                className="mt-1 text-[11px] font-medium text-rose-700"
                data-testid="transcription-run-tagged-preview-ambiguous"
              >
                Ambiguous tags (multiple matches found, ignored):{" "}
                {Object.entries(taggedPreview.ambiguousTags).map(([label, ids], idx, arr) => (
                  <span
                    key={label}
                    data-testid={`transcription-run-tagged-preview-ambiguous-${label}`}
                  >
                    {label} → [{ids.join(", ")}]{idx < arr.length - 1 ? "; " : ""}
                  </span>
                ))}
                . Pick one tag id to disambiguate.
              </div>
            ) : null}
          </div>
        )}

        {!fixedSteps && (
          <div
            className="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
            data-testid="transcription-run-step-checkboxes"
          >
            <span className="text-xs font-semibold text-slate-700">Steps</span>
            {selectableStepOrder.map((step) => {
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

        {runMode === "full" && stepsToRender.includes("ortho") && (
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

        {showPadSelector && (
          <div
            className="rounded-md border border-slate-200 bg-white px-3 py-2"
            data-testid="action-menu-pad-selector"
          >
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">Audio context pad</div>
            <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Audio context pad">
              {ACTION_MENU_PAD_OPTIONS.map((value, index) => {
                const selected = padSec === value;
                const label = value === DEFAULT_ACTION_MENU_PAD ? `${formatActionMenuPad(value)} s · default` : `${formatActionMenuPad(value)} s`;
                return (
                  <button
                    key={value}
                    type="button"
                    ref={(node) => { padRefs.current[index] = node; }}
                    data-testid={`action-menu-pad-${formatActionMenuPad(value)}`}
                    aria-pressed={selected}
                    onClick={() => setPadSec(value)}
                    onKeyDown={(event) => handlePadKeyDown(value, event)}
                    className={
                      "rounded-full border px-3 py-1 text-xs font-semibold transition-colors " +
                      (selected
                        ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")
                    }
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <TranscriptionRunGrid
          speakers={speakers}
          gridStepColumns={gridStepColumns}
          selectedSpeakers={selectedSpeakers}
          stateBySpeaker={stateBySpeaker}
          scopeByStep={scopeByStep}
          runMode={runMode}
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
            {runMode === "edited-only" ? (
              <>Run on {editedConcepts.length} edited concepts × {stepsToRender.length} steps ({stepsToRender.map((step) => STEP_LABELS[step]).join(", ") || "none"}){showPadSelector ? ` · pad ${formatActionMenuPad(padSec)} s` : ""}.</>
            ) : runMode === "tagged-only" ? (
              <>Run on {taggedPreview?.totalConcepts ?? 0} tagged concepts × {stepsToRender.length} steps ({stepsToRender.map((step) => STEP_LABELS[step]).join(", ") || "none"}){showPadSelector ? ` · pad ${formatActionMenuPad(padSec)} s` : ""}.</>
            ) : (
              <>Running {selectedSpeakers.size} speaker{selectedSpeakers.size === 1 ? "" : "s"} × {stepsToRender.length} step{stepsToRender.length === 1 ? "" : "s"}{showPadSelector ? ` · pad ${formatActionMenuPad(padSec)} s` : ""}. <span className="text-emerald-700 font-medium">{summary.ok} ok</span>, <span className="text-sky-700 font-medium">{summary.keep} keep existing</span>, <span className="text-amber-700 font-medium">{summary.overwrite} will overwrite</span>, <span className="text-rose-700 font-medium">{summary.blocked} blocked</span> (will be skipped at runtime).</>
            )}
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
            disabled={
              !hasAnySpeaker
                || !hasAnyStep
                || editedOnlyLoading
                || editedOnlyEmpty
                || editedOnlyError
                || taggedOnlyLoading
                || taggedOnlyEmpty
                || taggedOnlyError
                || taggedOnlyMissingInputs
                || taggedOnlyAllAmbiguous
            }
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
