import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import { cancelComputeJob } from "../../api/client";
import type { ActiveJobSnapshot } from "../../api/contracts/job-observability";
import { formatEta } from "../../hooks/useActionJob";

const FRIENDLY_LABELS: Record<string, string> = {
  "compute:full_pipeline": "Pipeline",
  "compute:ortho": "ORTH",
  "compute:ipa": "IPA",
  "compute:stt": "STT",
  "compute:forced_align": "Forced align",
  "compute:boundaries": "Boundaries",
  "compute:retranscribe_with_boundaries": "BND retranscribe",
  "compute:lexemes_rerun_by_tag": "Tagged rerun",
  "compute:lexeme_rerun_ipa": "Lexeme IPA",
  "compute:lexeme_rerun_ortho": "Lexeme ORTH",
  "compute:cognates": "Cognates",
  "compute:similarity": "Similarity",
  "compute:contact-lexemes": "Contact lexemes",
  "compute:offset_detect": "Offset detect",
  "compute:offset_detect_from_pair": "Offset detect",
  "compute:train_ipa_model": "Train IPA",
  stt: "STT",
  normalize: "Normalize",
  "onboard:speaker": "Onboarding",
};

function titleCase(raw: string): string {
  return raw
    .replace(/[-_]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function friendlyLabel(jobType: string): string {
  const direct = FRIENDLY_LABELS[jobType];
  if (direct) return direct;
  const segment = jobType.includes(":") ? jobType.split(":").pop() ?? jobType : jobType;
  return titleCase(segment) || jobType;
}

const CHUNK_PROGRESS_RE = /ORTH chunk (\d+)\/(\d+) \(\d+s-\d+s\)/;

export function chunkInfoFromMessage(message: string | undefined): { current: number; total: number } | null {
  if (!message) return null;
  const match = CHUNK_PROGRESS_RE.exec(message);
  if (!match) return null;
  const current = Number(match[1]);
  const total = Number(match[2]);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
  return { current, total };
}

function isCompleteStatus(status: string): boolean {
  const normalized = status.toLowerCase();
  return normalized === "complete" || normalized === "completed" || normalized === "done";
}

function isErrorStatus(status: string): boolean {
  const normalized = status.toLowerCase();
  return normalized === "error" || normalized === "failed";
}

function isCancelledStatus(status: string): boolean {
  const normalized = status.toLowerCase();
  return normalized === "cancelled" || normalized === "canceled";
}

interface HeaderJobStripProps {
  jobs: ActiveJobSnapshot[];
  onCancel?: (jobId: string) => Promise<unknown> | unknown;
  onOpenLogs?: (jobId: string) => void;
  autoDismissMs?: number;
}

export function HeaderJobStrip({
  jobs,
  onCancel = cancelComputeJob,
  onOpenLogs,
  autoDismissMs = 4000,
}: HeaderJobStripProps) {
  const insertionOrderRef = useRef(new Map<string, number>());
  const nextOrderRef = useRef(0);
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());

  for (const job of jobs) {
    if (!insertionOrderRef.current.has(job.jobId)) {
      insertionOrderRef.current.set(job.jobId, nextOrderRef.current++);
    }
  }

  useEffect(() => {
    const terminalJobs = jobs.filter((job) => (isCompleteStatus(job.status) || isErrorStatus(job.status) || isCancelledStatus(job.status)) && !dismissed.has(job.jobId));
    if (terminalJobs.length === 0) return;
    const timers = terminalJobs.map((job) => window.setTimeout(() => {
      setDismissed((existing) => {
        const next = new Set(existing);
        next.add(job.jobId);
        return next;
      });
    }, autoDismissMs));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [autoDismissMs, dismissed, jobs]);

  const visibleJobs = useMemo(() => {
    return jobs
      .filter((job) => !dismissed.has(job.jobId))
      .slice()
      .sort((a, b) => {
        const aTs = typeof a.startedTs === "number" ? a.startedTs : null;
        const bTs = typeof b.startedTs === "number" ? b.startedTs : null;
        if (aTs !== null || bTs !== null) return (bTs ?? -Infinity) - (aTs ?? -Infinity);
        return (insertionOrderRef.current.get(a.jobId) ?? 0) - (insertionOrderRef.current.get(b.jobId) ?? 0);
      });
  }, [dismissed, jobs]);

  return (
    <div data-testid="topbar-job-strip" className="flex items-center gap-2">
      {visibleJobs.map((job) => {
        const label = friendlyLabel(job.type);
        const progress = Math.max(0, Math.min(1, Number.isFinite(job.progress) ? job.progress : 0));
        const pct = Math.round(progress * 100);
        const error = job.error || job.message || "Job failed";
        const complete = isCompleteStatus(job.status);
        const errored = isErrorStatus(job.status);
        const cancelled = isCancelledStatus(job.status);
        const chunkInfo = !errored && !complete && !cancelled ? chunkInfoFromMessage(job.message) : null;

        return (
          <div
            key={job.jobId}
            data-testid={`topbar-job-strip-row-${job.jobId}`}
            className={`flex items-center gap-2 rounded-md border px-2.5 py-1 text-[11px] ${cancelled ? "border-amber-200 bg-amber-50" : errored ? "border-rose-200 bg-rose-50" : complete ? "border-emerald-200 bg-emerald-50" : "border-indigo-200 bg-indigo-50"}`}
          >
            {cancelled ? (
              <>
                <AlertCircle className="h-3 w-3 shrink-0 text-amber-600" />
                <span className="font-medium text-amber-900">{label} cancelled</span>
              </>
            ) : errored ? (
              <>
                <AlertCircle className="h-3 w-3 shrink-0 text-rose-600" />
                <span className="font-medium text-rose-900">{label} failed</span>
                <span className="max-w-[260px] truncate text-rose-600" title={error} data-testid={`topbar-job-error-${job.jobId}`}>{error}</span>
                {onOpenLogs && (
                  <button
                    onClick={() => onOpenLogs(job.jobId)}
                    className="rounded px-1.5 py-0.5 font-semibold text-rose-700 underline hover:text-rose-800"
                  >
                    View crash log
                  </button>
                )}
              </>
            ) : complete ? (
              <>
                <Check className="h-3 w-3 shrink-0 text-emerald-600" />
                <span className="font-medium text-emerald-700">{label} done</span>
              </>
            ) : (
              <>
                <Loader2 className="h-3 w-3 shrink-0 animate-spin text-indigo-600" />
                <span className="font-medium text-indigo-900">{label}</span>
                <div className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-indigo-100">
                  {progress < 0.05 ? (
                    <div data-testid={`topbar-job-progress-placeholder-${job.jobId}`} className="h-full w-1/3 animate-pulse rounded-full bg-indigo-400" />
                  ) : (
                    <div
                      data-testid={`topbar-job-progress-${job.jobId}`}
                      className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  )}
                </div>
                <span className="tabular-nums text-indigo-700">{pct}%</span>
                {chunkInfo && (
                  <span
                    data-testid="chunk-progress-overlay"
                    className="rounded-sm bg-indigo-100 px-1.5 py-0.5 font-medium tabular-nums text-indigo-800"
                    title={job.message}
                  >
                    Chunk {chunkInfo.current} of {chunkInfo.total}
                  </span>
                )}
                {typeof job.etaMs === "number" && job.etaMs > 0 && (
                  <span className="tabular-nums text-indigo-600" title="Estimated time remaining">· ~{formatEta(job.etaMs)} left</span>
                )}
                {job.message && !chunkInfo && (
                  <span className="hidden max-w-[180px] truncate text-indigo-600 lg:inline" title={job.message}>{job.message}</span>
                )}
                <button
                  onClick={() => { void onCancel(job.jobId); }}
                  aria-label={`Cancel ${job.jobId}`}
                  className="rounded border border-indigo-300 bg-white px-1.5 py-0.5 font-semibold text-indigo-700 hover:bg-indigo-100"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
