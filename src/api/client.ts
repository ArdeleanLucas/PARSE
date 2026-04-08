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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resolveJobId(payload: unknown): string {
  if (!isRecord(payload)) {
    return "";
  }

  const fromSnake = payload.job_id;
  if (typeof fromSnake === "string" && fromSnake.trim()) {
    return fromSnake.trim();
  }

  const fromCamel = payload.jobId;
  if (typeof fromCamel === "string" && fromCamel.trim()) {
    return fromCamel.trim();
  }

  return "";
}

function unwrapConfig(payload: unknown): ProjectConfig {
  if (isRecord(payload) && isRecord(payload.config)) {
    return payload.config as ProjectConfig;
  }
  return (payload ?? {}) as ProjectConfig;
}

function unwrapEnrichments(payload: unknown): EnrichmentsPayload {
  if (isRecord(payload) && isRecord(payload.enrichments)) {
    return payload.enrichments as EnrichmentsPayload;
  }
  return (payload ?? {}) as EnrichmentsPayload;
}

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
  const payload = await apiFetch<unknown>("/api/enrichments");
  return unwrapEnrichments(payload);
}

export async function saveEnrichments(data: EnrichmentsPayload): Promise<void> {
  await apiFetch<void>("/api/enrichments", {
    method: "POST",
    body: JSON.stringify({ enrichments: data }),
  });
}

// Config
export async function getConfig(): Promise<ProjectConfig> {
  const payload = await apiFetch<unknown>("/api/config");
  return unwrapConfig(payload);
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

// IPA
export async function requestIPA(text: string, language?: string): Promise<{ ipa: string }> {
  return apiFetch<{ ipa: string }>("/api/ipa", {
    method: "POST",
    body: JSON.stringify({ text, language }),
  });
}

// Suggestions
function unwrapSuggestions(payload: unknown): unknown[] {
  if (isRecord(payload) && Array.isArray(payload.suggestions)) {
    return payload.suggestions;
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  return [];
}

export async function requestSuggestions(
  speaker: string,
  conceptIds: string[]
): Promise<unknown[]> {
  const payload = await apiFetch<unknown>("/api/suggest", {
    method: "POST",
    body: JSON.stringify({ speaker, concept_ids: conceptIds }),
  });
  return unwrapSuggestions(payload);
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
  const payload = await apiFetch<unknown>("/api/chat/run", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  const id = resolveJobId(payload);
  return { job_id: id, jobId: id };
}

export async function pollChat(jobId: string): Promise<ChatStatus> {
  return apiFetch<ChatStatus>("/api/chat/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

// Compute
export async function startCompute(computeType: string): Promise<ComputeJob> {
  const payload = await apiFetch<unknown>(`/api/compute/${encodeURIComponent(computeType)}`, {
    method: "POST",
  });

  return { job_id: resolveJobId(payload) };
}

export async function pollCompute(computeType: string, jobId: string): Promise<ComputeStatus> {
  const payload = await apiFetch<unknown>(`/api/compute/${encodeURIComponent(computeType)}/status`, {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });

  if (!isRecord(payload)) {
    return { status: "error", progress: 0, message: "Invalid compute status payload" };
  }

  const rawProgress = Number(payload.progress ?? 0);
  const progress = Number.isFinite(rawProgress) ? rawProgress : 0;

  return {
    status: String(payload.status ?? "error"),
    progress,
    message:
      typeof payload.message === "string"
        ? payload.message
        : typeof payload.error === "string"
          ? payload.error
          : undefined,
    error: typeof payload.error === "string" ? payload.error : undefined,
  };
}

// Export — returns Blob (file download, not JSON)
export async function getLingPyExport(): Promise<Blob> {
  const response = await fetch("/api/export/lingpy", {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/lingpy failed ${response.status}: ${text}`);
  }
  return response.blob();
}

export async function getNEXUSExport(): Promise<Blob> {
  const response = await fetch("/api/export/nexus", {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/nexus failed ${response.status}: ${text}`);
  }
  return response.blob();
}
