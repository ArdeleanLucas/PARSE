import { apiFetch, isRecord } from "./shared";

export interface ActiveJobSnapshot {
  jobId: string;
  type: string;
  status: string;
  progress: number;
  message?: string;
  error?: string;
  speaker?: string;
  language?: string;
}

export async function listActiveJobs(): Promise<ActiveJobSnapshot[]> {
  const payload = await apiFetch<{ jobs?: unknown }>("/api/jobs/active");
  const raw = Array.isArray(payload?.jobs) ? payload.jobs : [];
  const out: ActiveJobSnapshot[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const jobId = String(record.jobId ?? record.job_id ?? "").trim();
    const type = String(record.type ?? "").trim();
    if (!jobId || !type) continue;
    const progressRaw = Number(record.progress ?? 0);
    const snapshot: ActiveJobSnapshot = {
      jobId,
      type,
      status: String(record.status ?? "running"),
      progress: Number.isFinite(progressRaw) ? progressRaw : 0,
    };
    if (typeof record.message === "string" && record.message.trim()) {
      snapshot.message = record.message;
    }
    if (typeof record.error === "string" && record.error.trim()) {
      snapshot.error = record.error;
    }
    if (typeof record.speaker === "string" && record.speaker.trim()) {
      snapshot.speaker = record.speaker.trim();
    }
    if (typeof record.language === "string" && record.language.trim()) {
      snapshot.language = record.language.trim();
    }
    out.push(snapshot);
  }
  return out;
}

export interface JobLogsPayload {
  jobId: string;
  status: string;
  type?: string;
  error?: string;
  traceback?: string;
  message?: string;
  stderrLog?: string;
  workerStderrLog?: string;
}

export async function getJobLogs(jobId: string): Promise<JobLogsPayload> {
  const payload = await apiFetch<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/logs`);
  if (!isRecord(payload)) {
    throw new Error("Invalid job logs payload");
  }
  const out: JobLogsPayload = {
    jobId: typeof payload.jobId === "string" ? payload.jobId : jobId,
    status: typeof payload.status === "string" ? payload.status : "",
  };
  if (typeof payload.type === "string") out.type = payload.type;
  if (typeof payload.error === "string") out.error = payload.error;
  if (typeof payload.traceback === "string") out.traceback = payload.traceback;
  if (typeof payload.message === "string") out.message = payload.message;
  if (typeof payload.stderrLog === "string") out.stderrLog = payload.stderrLog;
  if (typeof payload.workerStderrLog === "string") out.workerStderrLog = payload.workerStderrLog;
  return out;
}
