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
  ContactLexemeCoverage,
  ContactLexemeFetchOptions,
  Tag,
  TagsResponse,
  SttSegmentsPayload,
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

function resolveSessionId(payload: unknown): string {
  if (!isRecord(payload)) {
    return "";
  }

  const fromSnake = payload.session_id;
  if (typeof fromSnake === "string" && fromSnake.trim()) {
    return fromSnake.trim();
  }

  const fromCamel = payload.sessionId;
  if (typeof fromCamel === "string" && fromCamel.trim()) {
    return fromCamel.trim();
  }

  return "";
}

function networkError(path: string, options: RequestInit | undefined, error: unknown): Error {
  const message = error instanceof Error ? error.message : String(error ?? "Unknown fetch error");
  if (/failed to fetch|networkerror/i.test(message)) {
    return new Error(
      `Could not reach the PARSE API for ${options?.method ?? "GET"} ${path}. `
      + `Check that the Python server is running on http://127.0.0.1:8766 and that the Vite /api proxy is active.`,
    );
  }
  return error instanceof Error ? error : new Error(message);
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
  } catch (error) {
    throw networkError(path, options, error);
  }

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

export async function getSttSegments(speaker: string): Promise<SttSegmentsPayload> {
  return apiFetch<SttSegmentsPayload>(`/api/stt-segments/${encodeURIComponent(speaker)}`);
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

export interface ImportConceptsResult {
  ok: boolean;
  matched: number;
  added: number;
  total: number;
  mode: "merge" | "replace";
}

export async function importConceptsCsv(
  file: File,
  mode: "merge" | "replace" = "merge",
): Promise<ImportConceptsResult> {
  const form = new FormData();
  form.append("csv", file);
  form.append("mode", mode);
  let response: Response;
  try {
    response = await fetch("/api/concepts/import", { method: "POST", body: form });
  } catch (error) {
    throw networkError("/api/concepts/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/concepts/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportConceptsResult>;
}

export interface ImportTagCsvResult {
  ok: boolean;
  tagId: string;
  tagName: string;
  color: string;
  matchedCount: number;
  missedCount: number;
  missedLabels: string[];
  totalTagsInFile: number;
}

export async function importTagCsv(
  file: File,
  options: { tagName?: string; color?: string } = {},
): Promise<ImportTagCsvResult> {
  const form = new FormData();
  form.append("csv", file);
  if (options.tagName) form.append("tagName", options.tagName);
  if (options.color) form.append("color", options.color);
  let response: Response;
  try {
    response = await fetch("/api/tags/import", { method: "POST", body: form });
  } catch (error) {
    throw networkError("/api/tags/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/tags/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportTagCsvResult>;
}

// Auth
export async function getAuthStatus(): Promise<AuthStatus> {
  return apiFetch<AuthStatus>("/api/auth/status");
}

export async function startAuthFlow(): Promise<void> {
  await apiFetch<void>("/api/auth/start", { method: "POST" });
}

export interface AuthPollResult {
  status: "pending" | "complete" | "expired" | "error";
  error?: string;
}

export async function pollAuth(): Promise<AuthPollResult> {
  const payload = await apiFetch<unknown>("/api/auth/poll", { method: "POST" });
  if (payload && typeof payload === "object") {
    const p = payload as Record<string, unknown>;
    const status = typeof p.status === "string" ? p.status : "pending";
    const normalized: AuthPollResult["status"] =
      status === "complete" || status === "expired" || status === "error" ? status : "pending";
    const result: AuthPollResult = { status: normalized };
    if (typeof p.error === "string" && p.error) result.error = p.error;
    return result;
  }
  return { status: "pending" };
}

export async function saveApiKey(key: string, provider: string): Promise<AuthStatus> {
  return apiFetch<AuthStatus>("/api/auth/key", {
    method: "POST",
    body: JSON.stringify({ key, provider }),
  });
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

// Timestamp offset — detect a constant CSV/STT misalignment and (optionally) apply it.
export interface OffsetDetectResult {
  speaker: string;
  offsetSec: number;
  confidence: number;
  nAnchors: number;
  totalAnchors: number;
  totalSegments: number;
  method: string;
}

export interface OffsetApplyResult {
  speaker: string;
  appliedOffsetSec: number;
  shiftedIntervals: number;
}

export async function detectTimestampOffset(
  speaker: string,
  options?: { sttJobId?: string; sttSegments?: unknown[] }
): Promise<OffsetDetectResult> {
  return apiFetch<OffsetDetectResult>("/api/offset/detect", {
    method: "POST",
    body: JSON.stringify({
      speaker,
      sttJobId: options?.sttJobId,
      sttSegments: options?.sttSegments,
    }),
  });
}

export async function applyTimestampOffset(
  speaker: string,
  offsetSec: number
): Promise<OffsetApplyResult> {
  return apiFetch<OffsetApplyResult>("/api/offset/apply", {
    method: "POST",
    body: JSON.stringify({ speaker, offsetSec }),
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
export async function startChatSession(sessionId?: string): Promise<{ session_id: string; sessionId?: string }> {
  const payload = await apiFetch<unknown>("/api/chat/session", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  const id = resolveSessionId(payload);
  if (!id) {
    throw new Error("API POST /api/chat/session returned no sessionId");
  }
  return { session_id: id, sessionId: id };
}

export interface ChatSessionPayload {
  sessionId: string;
  tokensUsed: number | null;
  tokensLimit: number | null;
  model?: string;
  messages?: Array<{ role: string; content: string }>;
}

function isRecordShape(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function coerceTokenField(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.round(value);
  }
  return null;
}

function unwrapChatSession(payload: unknown): ChatSessionPayload {
  const empty: ChatSessionPayload = { sessionId: "", tokensUsed: null, tokensLimit: null };
  if (!isRecordShape(payload)) return empty;
  return {
    sessionId: typeof payload.sessionId === "string" ? payload.sessionId : "",
    tokensUsed: coerceTokenField(payload.tokensUsed),
    tokensLimit: coerceTokenField(payload.tokensLimit),
    model: typeof payload.model === "string" ? payload.model : undefined,
    messages: Array.isArray(payload.messages) ? (payload.messages as ChatSessionPayload["messages"]) : undefined,
  };
}

export async function getChatSession(sessionId: string): Promise<ChatSessionPayload> {
  const payload = await apiFetch<unknown>(`/api/chat/session/${encodeURIComponent(sessionId)}`);
  return unwrapChatSession(payload);
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
  return apiFetch<ChatStatus>("/api/chat/run/status", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

// Compute
export async function startCompute(
  computeType: string,
  body?: Record<string, unknown>,
): Promise<ComputeJob> {
  const payload = await apiFetch<unknown>(`/api/compute/${encodeURIComponent(computeType)}`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });

  return { job_id: resolveJobId(payload), jobId: resolveJobId(payload) };
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

// Contact Lexemes
export async function getContactLexemeCoverage(): Promise<ContactLexemeCoverage> {
  return apiFetch<ContactLexemeCoverage>("/api/contact-lexemes/coverage");
}

export async function startContactLexemeFetch(
  options: ContactLexemeFetchOptions = {},
): Promise<ComputeJob> {
  return startCompute("contact-lexemes", options as Record<string, unknown>);
}

// Normalize
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

// Onboard Speaker
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

  // Use raw fetch — FormData sets its own Content-Type with boundary
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

// Tags
export async function getTags(): Promise<TagsResponse> {
  return apiFetch<TagsResponse>("/api/tags");
}

export async function mergeTags(tags: Tag[]): Promise<{ ok: boolean; tagCount: number }> {
  return apiFetch<{ ok: boolean; tagCount: number }>("/api/tags/merge", {
    method: "POST",
    body: JSON.stringify({ tags }),
  });
}

// Lexeme notes
export interface SaveLexemeNoteBody {
  speaker: string;
  concept_id: string;
  user_note?: string;
  import_note?: string;
  delete?: boolean;
}

export async function saveLexemeNote(
  body: SaveLexemeNoteBody,
): Promise<{ success: boolean; lexeme_notes?: Record<string, Record<string, Record<string, unknown>>> }> {
  return apiFetch<{
    success: boolean;
    lexeme_notes?: Record<string, Record<string, Record<string, unknown>>>;
  }>("/api/lexeme-notes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ImportCommentsCsvResponse {
  success: boolean;
  speaker: string;
  total_rows: number;
  imported: number;
  matched: number;
  lexeme_notes?: Record<string, Record<string, Record<string, unknown>>>;
}

export async function importCommentsCsv(
  speakerId: string,
  csvFile: File,
): Promise<ImportCommentsCsvResponse> {
  const formData = new FormData();
  formData.append("speaker_id", speakerId);
  formData.append("csv", csvFile);
  let response: Response;
  try {
    response = await fetch("/api/lexeme-notes/import", { method: "POST", body: formData });
  } catch (error) {
    throw networkError("/api/lexeme-notes/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/lexeme-notes/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportCommentsCsvResponse>;
}

export function spectrogramUrl(params: {
  speaker: string;
  startSec: number;
  endSec: number;
  audio?: string;
  force?: boolean;
}): string {
  const search = new URLSearchParams({
    speaker: params.speaker,
    start: params.startSec.toFixed(3),
    end: params.endSec.toFixed(3),
  });
  if (params.audio) search.set("audio", params.audio);
  if (params.force) search.set("force", "1");
  return `/api/spectrogram?${search.toString()}`;
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
