import React, { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Copy,
  Download,
  RotateCw,
  SkipForward,
  XCircle,
} from "lucide-react";
import { Modal } from "./Modal";
import type { PipelineRunResult, PipelineStepResultBase } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchSpeakerOutcome {
  speaker: string;
  /** "cancelled" means the user cancelled the batch before this speaker ran.
   *  The speaker's pipeline never started server-side; its result is null. */
  status: "pending" | "running" | "complete" | "error" | "cancelled";
  /** Whole-speaker error (e.g. network failure before the pipeline job even started,
   *  or a transport disconnect after a job was already queued). */
  error: string | null;
  /** Backend job id when the speaker reached startCompute successfully. */
  jobId?: string;
  /** Which client phase surfaced the top-level error. */
  errorPhase?: "start" | "poll";
  result: PipelineRunResult | null;
}

export interface BatchReportModalProps {
  open: boolean;
  onClose: () => void;
  outcomes: BatchSpeakerOutcome[];
  stepsRun: PipelineStepId[];
  onRerunFailed?: (speakers: string[]) => void;
}

const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Normalize",
  stt: "STT",
  ortho: "Ortho",
  ipa: "IPA",
};

const TRUNCATE_LEN = 40;

function truncate(text: string, max: number = TRUNCATE_LEN): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 1)) + "…";
}

function okDetail(step: PipelineStepId, cell: PipelineStepResultBase): string {
  switch (step) {
    case "normalize":
      return "done";
    case "stt": {
      const segs = cell["segments"];
      if (typeof segs === "number") return `${segs} segs`;
      return "done";
    }
    case "ortho":
    case "ipa": {
      // Both the explicit ``intervals`` key and the ``filled`` counter
      // (which the backend returns from _compute_speaker_ortho and
      // _compute_speaker_ipa) are acceptable sources. Fall back to
      // ``total`` if present, else "done" so the cell is never empty.
      const ivs = cell["intervals"];
      if (typeof ivs === "number") return `${ivs} ivs`;
      const filled = cell["filled"];
      if (typeof filled === "number") return `${filled} ivs`;
      const total = cell["total"];
      if (typeof total === "number") return `${total} ivs`;
      return "done";
    }
  }
}

type CellKind = "ok" | "skipped" | "empty" | "error" | "unknown";

/** Classify a step-result object into one of four visual kinds.
 *
 *  The backend's ``_compute_full_pipeline`` tags every step result with
 *  a ``status`` field ("ok" / "skipped" / "error"), but we also want to
 *  be forgiving of older response shapes (pre-step-resilience main, or
 *  direct calls to the per-step compute endpoints that return their
 *  own shape without a ``status`` tag). The heuristics below recover
 *  the visual intent even when the explicit field is missing.
 *
 *  Returns ``"unknown"`` only when we genuinely can't tell — the cell
 *  then renders with a helpful "unclassified" label instead of a bare
 *  em-dash, so the user knows there's data to inspect (via the raw
 *  JSON download).
 */
function classifyCell(cell: PipelineStepResultBase): CellKind {
  // 1. Explicit status field wins — BUT promote "ok" to "empty" when
  //    the step ran against real work and wrote nothing. This is the
  //    Fail02 Tier-3 case: status=ok, filled=0, total=38 means the
  //    server did not raise, yet no intervals landed. The user needs
  //    to see that immediately — an OK badge on an empty step hides
  //    the failure mode we added diagnostics for.
  const explicit = cell["status"];
  if (explicit === "ok" || explicit === "skipped" || explicit === "error") {
    if (explicit === "ok") {
      const filled = cell["filled"];
      const total = cell["total"];
      if (
        typeof filled === "number" &&
        filled === 0 &&
        typeof total === "number" &&
        total > 0
      ) {
        return "empty";
      }
    }
    return explicit;
  }
  // 2. An error string implies error regardless of other fields.
  if (typeof cell["error"] === "string" && cell["error"].trim()) {
    return "error";
  }
  // 3. Old shape: ``skipped: true`` (pre-status-tag pipelines).
  if (cell["skipped"] === true) {
    return "skipped";
  }
  // 4. Any positive work output implies ok.
  const numericKeys = ["filled", "segments", "intervals", "total"];
  for (const k of numericKeys) {
    const v = cell[k];
    if (typeof v === "number" && v > 0) return "ok";
  }
  // 5. Explicit done flag.
  if (cell["done"] === true) return "ok";
  // 6. ``filled: 0`` with ``total: 0`` and no error = nothing to do — skipped.
  if (cell["filled"] === 0 && (cell["total"] === 0 || cell["total"] === undefined)) {
    return "skipped";
  }
  return "unknown";
}

function speakerHasFailure(outcome: BatchSpeakerOutcome): boolean {
  if (outcome.status === "error") return true;
  if (outcome.result) {
    for (const step of Object.keys(outcome.result.results) as PipelineStepId[]) {
      const cell = outcome.result.results[step];
      if (!cell) continue;
      const kind = classifyCell(cell);
      // "empty" (filled=0 total>0) counts as a failure for re-run
      // purposes: the step ran but produced nothing, so the user
      // almost always wants to rerun-failed with that step included.
      if (kind === "error" || kind === "empty") return true;
    }
  }
  return false;
}

function countTotals(
  outcomes: BatchSpeakerOutcome[],
  stepsRun: PipelineStepId[],
): { ok: number; skipped: number; empty: number; errored: number } {
  let ok = 0;
  let skipped = 0;
  let empty = 0;
  let errored = 0;
  for (const outcome of outcomes) {
    if (outcome.status === "error" && !outcome.result) {
      // Whole-speaker error counts as one errored "cell" so it shows up in totals.
      errored += 1;
      continue;
    }
    if (!outcome.result) continue;
    for (const step of stepsRun) {
      const cell = outcome.result.results[step];
      if (!cell) continue;
      const kind = classifyCell(cell);
      if (kind === "ok") ok += 1;
      else if (kind === "skipped") skipped += 1;
      else if (kind === "empty") empty += 1;
      else if (kind === "error") errored += 1;
    }
  }
  return { ok, skipped, empty, errored };
}

function DetailsBlock({
  speaker,
  step,
  error,
  traceback,
}: {
  speaker: string;
  step: string;
  error: string;
  traceback: string | null;
}) {
  const [copied, setCopied] = useState(false);
  const body = traceback && traceback.trim() ? traceback : error;

  const onCopy = () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        navigator.clipboard.writeText(body).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          },
          () => {
            /* ignore */
          },
        );
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      role="region"
      aria-label={`Traceback for ${speaker} ${step}`}
      className="mt-1 rounded border border-rose-200 bg-rose-50/60 p-2"
    >
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wide text-rose-700">
          Full error {traceback ? "+ traceback" : ""}
        </div>
        <button
          type="button"
          aria-label="Copy traceback to clipboard"
          onClick={onCopy}
          className="inline-flex items-center gap-1 rounded border border-rose-200 bg-white px-1.5 py-0.5 text-[10px] text-rose-700 hover:bg-rose-100"
        >
          <Copy className="h-3 w-3" />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        className="max-h-[200px] overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-[11px] leading-snug text-rose-900"
      >
        {error}
        {traceback && traceback.trim() ? `\n\n${traceback}` : ""}
      </pre>
    </div>
  );
}

function StepCell({
  outcome,
  step,
  stepInBatch,
  isOpen,
  onToggle,
}: {
  outcome: BatchSpeakerOutcome;
  step: PipelineStepId;
  stepInBatch: boolean;
  isOpen: boolean;
  onToggle: () => void;
}) {
  if (!stepInBatch) {
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300"
        title="Step was not selected for this batch"
      >
        —
      </td>
    );
  }
  // Whole-speaker errors (no result) are handled by a banner row — for each
  // individual step cell in that row we show a dim dash pointing at it.
  if (!outcome.result) {
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300"
        title="Speaker-level error — see the highlighted row below for details"
      >
        —
      </td>
    );
  }
  const cell = outcome.result.results[step];
  if (!cell) {
    // The backend didn't return a result entry for this step at all
    // (pipeline finished but the step wasn't in its ``results`` dict).
    // Prefer a labelled marker over a bare em-dash so the user knows
    // there's nothing to inspect rather than silently ignoring it.
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 align-top"
        title={`Backend returned no result entry for "${step}". Inspect via Download report.`}
      >
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
          <SkipForward className="h-3.5 w-3.5" /> No data
        </span>
      </td>
    );
  }

  const kind = classifyCell(cell);

  if (kind === "ok") {
    return (
      <td className="border-b border-slate-100 bg-emerald-50/40 px-2 py-1.5 align-top">
        <div className="flex items-center gap-1.5 text-emerald-700">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span className="text-xs font-semibold">OK</span>
          <span className="text-[11px] text-emerald-900/70 tabular-nums">
            {okDetail(step, cell)}
          </span>
        </div>
      </td>
    );
  }

  if (kind === "skipped") {
    const reason =
      (typeof cell.reason === "string" && cell.reason) ||
      (typeof cell["message"] === "string" ? (cell["message"] as string) : "") ||
      "Nothing to do";
    return (
      <td className="border-b border-slate-100 bg-slate-50 px-2 py-1.5 align-top">
        <div
          className="flex items-center gap-1.5 text-slate-600"
          title={reason}
        >
          <SkipForward className="h-4 w-4 shrink-0" />
          <span className="text-xs font-semibold">Skipped</span>
          {reason && (
            <span className="text-[11px] text-slate-500">
              {truncate(reason)}
            </span>
          )}
        </div>
      </td>
    );
  }

  if (kind === "empty") {
    // Step ran, returned status:ok, but wrote zero intervals. The
    // user needs to see this immediately — a green OK badge on a
    // zero-filled step is the exact trap that hid the Fail02 Tier 3
    // torchcodec crash for a day. Pull the skip_breakdown and
    // first exception sample (populated by the diagnostic commit
    // in server.py) into an expandable details block.
    const filled = typeof cell.filled === "number" ? cell.filled : 0;
    const total = typeof cell.total === "number" ? cell.total : 0;
    const breakdown = cell.skip_breakdown ?? null;
    const samples = Array.isArray(cell.exception_samples)
      ? (cell.exception_samples as unknown[]).filter(
          (s): s is string => typeof s === "string" && s.length > 0,
        )
      : [];
    const hasDetails =
      samples.length > 0 ||
      (breakdown &&
        Object.values(breakdown).some(
          (v) => typeof v === "number" && v > 0,
        ));

    return (
      <td className="border-b border-slate-100 bg-amber-50/60 px-2 py-1.5 align-top">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-amber-800">
            <CircleSlash className="h-3.5 w-3.5 shrink-0" />
            <span className="text-xs font-semibold">Empty</span>
            <span className="text-[11px] text-amber-900/80 tabular-nums">
              {filled}/{total} written
            </span>
          </div>
          {hasDetails && (
            <>
              <button
                type="button"
                onClick={onToggle}
                className="inline-flex w-fit items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-amber-800 hover:bg-amber-100"
                aria-expanded={isOpen}
              >
                {isOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                Why
              </button>
              {isOpen && (
                <div
                  role="region"
                  aria-label={`Empty-step details for ${outcome.speaker} ${step}`}
                  className="mt-1 rounded border border-amber-200 bg-white p-2 text-[11px] text-amber-900"
                >
                  {breakdown && (
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      {Object.entries(breakdown)
                        .filter(([, v]) => typeof v === "number" && v > 0)
                        .map(([k, v]) => (
                          <React.Fragment key={k}>
                            <dt className="font-mono text-amber-800/80">
                              {k}
                            </dt>
                            <dd className="text-right font-mono tabular-nums">
                              {String(v)}
                            </dd>
                          </React.Fragment>
                        ))}
                    </dl>
                  )}
                  {samples.length > 0 && (
                    <pre className="mt-1 max-h-[160px] overflow-auto whitespace-pre-wrap break-words rounded bg-amber-50 p-1.5 font-mono text-[10.5px] leading-snug text-amber-900">
                      {samples.join("\n")}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </td>
    );
  }

  if (kind === "unknown") {
    // We have a cell but couldn't classify it. Show a neutral marker
    // + tooltip with the raw keys so the user can still tell there's
    // *something* there — far better than a silent em-dash.
    const keys = Object.keys(cell).join(", ");
    return (
      <td
        className="border-b border-slate-100 bg-slate-50 px-2 py-1.5 align-top"
        title={`Step ran but returned an unfamiliar shape. Keys: ${keys}. Use Download report to inspect.`}
      >
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
          <SkipForward className="h-4 w-4" /> Ran (unclassified)
        </span>
      </td>
    );
  }

  // kind === "error"
  const shortError = cell.error ?? "Error";
  const traceback =
    typeof cell.traceback === "string" && cell.traceback.trim()
      ? cell.traceback
      : null;
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1 text-rose-700">
          <XCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="text-xs font-medium">Error</span>
          <span
            className="font-mono text-[11px] text-rose-900/80"
            title={shortError}
          >
            {truncate(shortError)}
          </span>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex w-fit items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-rose-700 hover:bg-rose-100"
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          Details
        </button>
        {isOpen && (
          <DetailsBlock
            speaker={outcome.speaker}
            step={step}
            error={shortError}
            traceback={traceback}
          />
        )}
      </div>
    </td>
  );
}

function SpeakerStatusCell({ outcome }: { outcome: BatchSpeakerOutcome }) {
  if (outcome.status === "complete") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" /> complete
        </span>
      </td>
    );
  }
  if (outcome.status === "error") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span
          className="inline-flex items-center gap-1 text-xs text-rose-700"
          title={outcome.error ?? undefined}
        >
          <XCircle className="h-3.5 w-3.5" /> errored
          {outcome.error && (
            <span className="font-mono text-[11px] text-rose-900/80">
              ({truncate(outcome.error, 30)})
            </span>
          )}
        </span>
      </td>
    );
  }
  if (outcome.status === "running") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-indigo-700">
          <RotateCw className="h-3.5 w-3.5 animate-spin" /> running
        </span>
      </td>
    );
  }
  if (outcome.status === "cancelled") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-amber-700">
          <SkipForward className="h-3.5 w-3.5" /> cancelled
        </span>
      </td>
    );
  }
  // pending
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
        pending
      </span>
    </td>
  );
}

function SpeakerErrorBanner({
  outcome,
  columnCount,
  isOpen,
  onToggle,
}: {
  outcome: BatchSpeakerOutcome;
  columnCount: number;
  isOpen: boolean;
  onToggle: () => void;
}) {
  // Crude traceback detection: if the error text contains "Traceback" keyword,
  // we surface a details expand. Most network errors won't have one — in that
  // case we just show the error message and skip the expand button.
  const hasTraceback =
    outcome.error != null && /traceback/i.test(outcome.error);
  const lostContactAfterStart = outcome.errorPhase === "poll" && !!outcome.jobId;

  return (
    <tr>
      <td
        colSpan={columnCount}
        className="border-b border-amber-200 bg-amber-50 px-3 py-2"
      >
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-amber-900">
              {lostContactAfterStart ? "Lost contact after start:" : "Speaker-level error:"}
            </span>
            <span className="font-mono text-[11px] text-amber-900/90">
              {outcome.error ?? "(no message)"}
            </span>
            {lostContactAfterStart && outcome.jobId && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] text-amber-900">
                job {outcome.jobId}
              </span>
            )}
            {hasTraceback && (
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={isOpen}
                className="ml-auto inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-amber-800 hover:bg-amber-100"
              >
                {isOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                Details
              </button>
            )}
          </div>
          {lostContactAfterStart && (
            <div className="text-[11px] text-amber-900/80">
              The pipeline job was created, but the client lost `/api` connectivity while polling. Reattach or reconcile by backend job id before treating this as a true speaker failure.
            </div>
          )}
          {hasTraceback && isOpen && (
            <DetailsBlock
              speaker={outcome.speaker}
              step="speaker"
              error={outcome.error ?? ""}
              traceback={outcome.error ?? null}
            />
          )}
        </div>
      </td>
    </tr>
  );
}

export function BatchReportModal({
  open,
  onClose,
  outcomes,
  stepsRun,
  onRerunFailed,
}: BatchReportModalProps): JSX.Element | null {
  const [openCells, setOpenCells] = useState<Set<string>>(new Set());
  const [openBanners, setOpenBanners] = useState<Set<string>>(new Set());

  const totals = useMemo(
    () => countTotals(outcomes, stepsRun),
    [outcomes, stepsRun],
  );
  const failedSpeakers = useMemo(
    () => outcomes.filter(speakerHasFailure).map((o) => o.speaker),
    [outcomes],
  );

  const toggleCell = (speaker: string, step: string) => {
    setOpenCells((prev) => {
      const next = new Set(prev);
      const key = `${speaker}:${step}`;
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleBanner = (speaker: string) => {
    setOpenBanners((prev) => {
      const next = new Set(prev);
      if (next.has(speaker)) next.delete(speaker);
      else next.add(speaker);
      return next;
    });
  };

  const handleDownload = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      steps_run: stepsRun,
      outcomes,
    };
    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `parse-batch-report-${new Date().toISOString()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleRerun = () => {
    if (onRerunFailed && failedSpeakers.length > 0) {
      onRerunFailed(failedSpeakers);
    }
  };

  const columnCount = stepsRun.length + 2; // speaker col + steps + trailing status col
  const allClean =
    totals.errored === 0 && totals.skipped === 0 && totals.empty === 0;

  const title = `Batch Report — ${outcomes.length} speakers × ${stepsRun.length} steps`;

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div
        className="flex w-[min(90vw,64rem)] flex-col gap-3"
        data-testid="batch-report-modal"
      >
        {/* Summary chips */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span
            className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
            data-testid="batch-report-chip-ok"
          >
            <CheckCircle2 className="h-3 w-3" />
            {totals.ok} ok
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700"
            data-testid="batch-report-chip-skipped"
          >
            <SkipForward className="h-3 w-3" />
            {totals.skipped} skipped
          </span>
          {totals.empty > 0 && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800"
              data-testid="batch-report-chip-empty"
              title="Step ran but wrote zero intervals — see per-cell details"
            >
              <CircleSlash className="h-3 w-3" />
              {totals.empty} empty
            </span>
          )}
          <span
            className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-800"
            data-testid="batch-report-chip-errored"
          >
            <XCircle className="h-3 w-3" />
            {totals.errored} errored
          </span>
        </div>

        {stepsRun.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500">
            No steps were run.
          </div>
        ) : (
          <>
            {allClean && outcomes.length > 0 && (
              <div
                className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
                data-testid="batch-report-all-clean"
              >
                All {outcomes.length} speaker
                {outcomes.length === 1 ? "" : "s"} processed cleanly.
              </div>
            )}

            <div className="max-h-[60vh] overflow-auto rounded border border-slate-200">
              <table
                className="min-w-full border-collapse text-left text-xs"
                data-testid="batch-report-table"
              >
                <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-600">
                  <tr>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">
                      Speaker
                    </th>
                    {stepsRun.map((step) => (
                      <th
                        key={step}
                        className="border-b border-slate-200 px-2 py-2 font-semibold"
                      >
                        {STEP_LABELS[step]}
                      </th>
                    ))}
                    <th className="border-b border-slate-200 px-2 py-2 font-semibold">
                      Speaker status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {outcomes.map((outcome) => {
                    const isWholeSpeakerError =
                      outcome.status === "error" && outcome.result === null;
                    return (
                      <React.Fragment key={outcome.speaker}>
                        <tr data-testid={`batch-report-row-${outcome.speaker}`}>
                          <td className="border-b border-slate-100 px-3 py-1.5 align-top font-medium text-slate-800">
                            {outcome.speaker}
                          </td>
                          {stepsRun.map((step) => {
                            const key = `${outcome.speaker}:${step}`;
                            return (
                              <StepCell
                                key={step}
                                outcome={outcome}
                                step={step}
                                stepInBatch={true}
                                isOpen={openCells.has(key)}
                                onToggle={() =>
                                  toggleCell(outcome.speaker, step)
                                }
                              />
                            );
                          })}
                          <SpeakerStatusCell outcome={outcome} />
                        </tr>
                        {isWholeSpeakerError && (
                          <SpeakerErrorBanner
                            outcome={outcome}
                            columnCount={columnCount}
                            isOpen={openBanners.has(outcome.speaker)}
                            onToggle={() => toggleBanner(outcome.speaker)}
                          />
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Footer */}
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={handleDownload}
            data-testid="batch-report-download"
            className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <Download className="h-3.5 w-3.5" />
            Download report (JSON)
          </button>
          <div className="flex items-center gap-2">
            {onRerunFailed && (
              <button
                type="button"
                onClick={handleRerun}
                disabled={failedSpeakers.length === 0}
                data-testid="batch-report-rerun-failed"
                className="inline-flex items-center gap-1.5 rounded bg-rose-600 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RotateCw className="h-3.5 w-3.5" />
                Rerun failed ({failedSpeakers.length})
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              data-testid="batch-report-close"
              className="rounded px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
