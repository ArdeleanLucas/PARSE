// PARSE API client — ALL fetch calls go through these typed functions.
// No component may call fetch() directly. Always use this module.
// Proxy: /api/* → http://localhost:8766 (configured in vite.config.ts)

import type {
  AnnotationRecord,
  ProjectConfig,
  EnrichmentsPayload,
  AuthStatus,
  STTJob,
  STTStatus,
  ChatJob,
  ChatStatus,
  ComputeJob,
  ComputeStatus,
} from "./types";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API ${options?.method ?? "GET"} ${path} failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

// Annotations
export async function getAnnotation(speaker: string): Promise<AnnotationRecord> {
  return apiFetch<AnnotationRecord>(`/api/annotations/${encodeURIComponent(speaker)}`);
}

export async function saveAnnotation(speaker: string, record: AnnotationRecord): Promise<void> {
  await apiFetch<void>(`/api/annotations/${encodeURIComponent(speaker)}`, {
    method: "POST",
    body: JSON.stringify(record),
  });
}

// Enrichments
export async function getEnrichments(): Promise<EnrichmentsPayload> {
  return apiFetch<EnrichmentsPayload>("/api/enrichments");
}

export async function saveEnrichments(data: EnrichmentsPayload): Promise<void> {
  await apiFetch<void>("/api/enrichments", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Config
export async function getConfig(): Promise<ProjectConfig> {
  return apiFetch<ProjectConfig>("/api/config");
}

export async function updateConfig(patch: Partial<ProjectConfig>): Promise<void> {
  await apiFetch<void>("/api/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

// Auth
export async function getAuthStatus(): Promise<AuthStatus> {
  return apiFetch<AuthStatus>("/api/auth/status");
}

export async function startAuthFlow(): Promise<void> {
  await apiFetch<void>("/api/auth/start", { method: "POST" });
}

export async function pollAuth(): Promise<AuthStatus> {
  return apiFetch<AuthStatus>("/api/auth/poll", { method: "POST" });
}

export async function logoutAuth(): Promise<void> {
  await apiFetch<void>("/api/auth/logout", { method: "POST" });
}

// STT
export async function startSTT(
  speaker: string,
  sourceWav: string,
  language?: string
): Promise<STTJob> {
  return apiFetch<STTJob>("/api/stt", {
    method: "POST",
    body: JSON.stringify({ speaker, source_wav: sourceWav, language }),
  });
}

export async function pollSTT(jobId: string): Promise<STTStatus> {
  return apiFetch<STTStatus>("/api/stt/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

// IPA
export async function requestIPA(text: string, language?: string): Promise<{ ipa: string }> {
  return apiFetch<{ ipa: string }>("/api/ipa", {
    method: "POST",
    body: JSON.stringify({ text, language }),
  });
}

// Suggestions
export async function requestSuggestions(
  speaker: string,
  conceptIds: string[]
): Promise<unknown[]> {
  return apiFetch<unknown[]>("/api/suggest", {
    method: "POST",
    body: JSON.stringify({ speaker, concept_ids: conceptIds }),
  });
}

// Chat
export async function startChatSession(sessionId?: string): Promise<{ session_id: string }> {
  return apiFetch<{ session_id: string }>("/api/chat/session", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function getChatSession(sessionId: string): Promise<unknown> {
  return apiFetch<unknown>(`/api/chat/session/${encodeURIComponent(sessionId)}`);
}

export async function runChat(sessionId: string, message: string): Promise<ChatJob> {
  return apiFetch<ChatJob>("/api/chat/run", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export async function pollChat(jobId: string): Promise<ChatStatus> {
  return apiFetch<ChatStatus>("/api/chat/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

// Compute
export async function startCompute(speaker: string): Promise<ComputeJob> {
  return apiFetch<ComputeJob>(`/api/compute/${encodeURIComponent(speaker)}`, {
    method: "POST",
  });
}

export async function pollCompute(speaker: string, jobId: string): Promise<ComputeStatus> {
  return apiFetch<ComputeStatus>(`/api/compute/${encodeURIComponent(speaker)}/status`, {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

// Export — returns Blob (file download, not JSON)
export async function getLingPyExport(): Promise<Blob> {
  const response = await fetch("/api/export/lingpy");
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/lingpy failed ${response.status}: ${text}`);
  }
  return response.blob();
}

export async function getNEXUSExport(): Promise<Blob> {
  const response = await fetch("/api/export/nexus");
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/nexus failed ${response.status}: ${text}`);
  }
  return response.blob();
}
