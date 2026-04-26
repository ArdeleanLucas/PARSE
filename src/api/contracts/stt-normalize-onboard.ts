import type { STTJob, STTStatus } from "../types";
import { apiFetch, resolveJobId } from "./shared";

export async function startSTT(
  speaker: string,
  sourceWav: string,
  language?: string,
): Promise<STTJob> {
  const payload = await apiFetch<unknown>("/api/stt", {
    method: "POST",
    body: JSON.stringify({ speaker, source_wav: sourceWav, language }),
  });

  return { job_id: resolveJobId(payload) };
}

export async function pollSTT(jobId: string): Promise<STTStatus> {
  return apiFetch<STTStatus>("/api/stt/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

export async function startNormalize(speaker: string, sourceWav?: string): Promise<{ job_id: string }> {
  const body: Record<string, string> = { speaker };
  if (sourceWav) {
    body.source_wav = sourceWav;
  }
  const payload = await apiFetch<unknown>("/api/normalize", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return { job_id: resolveJobId(payload) };
}

export async function pollNormalize(jobId: string): Promise<STTStatus> {
  return apiFetch<STTStatus>("/api/normalize/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

export async function onboardSpeaker(
  speakerId: string,
  audioFile: File,
  csvFile?: File | null,
): Promise<{ job_id: string }> {
  const formData = new FormData();
  formData.append("speaker_id", speakerId);
  formData.append("audio", audioFile);
  if (csvFile) {
    formData.append("csv", csvFile);
  }

  const response = await fetch("/api/onboard/speaker", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Onboarding endpoint not available");
    }
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`Upload failed (${response.status}): ${text}`);
  }
  const payload = await response.json();
  return { job_id: resolveJobId(payload) };
}

export async function pollOnboardSpeaker(jobId: string): Promise<STTStatus> {
  return apiFetch<STTStatus>("/api/onboard/speaker/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}
