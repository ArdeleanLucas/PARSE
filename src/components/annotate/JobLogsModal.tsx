import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { getJobLogs, type JobLogsPayload } from '../../api/client';
import { Modal } from '../shared/Modal';

export interface JobLogsModalProps {
  jobId: string | null;
  onClose: () => void;
}

export function JobLogsModal({ jobId, onClose }: JobLogsModalProps) {
  const [payload, setPayload] = useState<JobLogsPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setPayload(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPayload(null);
    void (async () => {
      try {
        const data = await getJobLogs(jobId);
        if (!cancelled) setPayload(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return (
    <Modal open={jobId !== null} onClose={onClose} title="Job Crash Log">
      <div className="space-y-3 text-sm" data-testid="job-logs-modal">
        {jobId && (
          <div className="text-[11px] text-slate-500">
            Job <span className="font-mono text-slate-700">{jobId}</span>
          </div>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin" /> Fetching logs…
          </div>
        )}
        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            Failed to load logs: {error}
          </div>
        )}
        {payload && (
          <div className="space-y-3">
            {payload.error && (
              <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-900">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-rose-700">Error</div>
                <div className="whitespace-pre-wrap break-words">{payload.error}</div>
              </div>
            )}
            {payload.traceback && (
              <details className="rounded-md border border-slate-200" open>
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Python traceback
                </summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800" data-testid="job-logs-traceback">{payload.traceback}</pre>
              </details>
            )}
            {payload.stderrLog && (
              <details className="rounded-md border border-slate-200">
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Per-job stderr
                </summary>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800">{payload.stderrLog}</pre>
              </details>
            )}
            {payload.workerStderrLog && (
              <details className="rounded-md border border-slate-200">
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Worker stderr tail
                </summary>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800">{payload.workerStderrLog}</pre>
              </details>
            )}
            {!payload.error && !payload.traceback && !payload.stderrLog && !payload.workerStderrLog && (
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                No crash log captured for this job. The worker may have
                exited cleanly, or the stderr log was not written yet.
              </div>
            )}
          </div>
        )}
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
