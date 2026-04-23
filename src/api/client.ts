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

const CONFIG_SCHEMA_VERSION = 1;

// Validates the {config: ...} wrapper and schema_version added in PR #155.
// Before that fix, a stale server (pre-PR #24 code) returned speakers as a
// plain dict instead of string[]; TypeScript cast it silently and the UI
// rendered an empty workspace with no error. schema_version makes the mismatch
// explicit so the banner fires instead.
function unwrapConfig(payload: unknown): ProjectConfig {
  if (isRecord(payload) && isRecord(payload.config)) {
    const cfg = payload.config;
    if (cfg.schema_version !== CONFIG_SCHEMA_VERSION) {
      const got = cfg.schema_version === undefined ? "missing" : String(cfg.schema_version);
      throw new Error(
        `PARSE server is outdated (config schema_version: ${got}, expected: ${CONFIG_SCHEMA_VERSION}). ` +
        "Restart the Python server with the latest code and reload the page."
      );
    }
    return cfg as ProjectConfig;
  }
  throw new Error(
    "PARSE server is outdated: /api/config response is missing the expected wrapper. " +
    "Restart the Python server with the latest code and reload the page."
  );
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

export interface ActiveJobSnapshot {
  jobId: string;
  type: string;
  status: string;
  progress: number;
  message?: string;
  error?: string;
  /** Only set for speaker-scoped jobs (STT, normalize, IPA). */
  speaker?: string;
  language?: string;
}

/** List currently-running backend jobs so the UI can rehydrate progress
 * indicators after a page reload. Backend threads outlive the browser. */
export async function listActiveJobs(): Promise<ActiveJobSnapshot[]> {
  const payload = await apiFetch<{ jobs?: unknown }>("/api/jobs/active");
  const raw = Array.isArray(payload?.jobs) ? payload!.jobs : [];
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

// Timestamp offset — detect a constant CSV/STT misalignment and (optionally) apply it.
export interface OffsetMatch {
  anchor_index: number;
  anchor_text: string;
  anchor_start: number | null;
  segment_index: number;
  segment_text: string;
  segment_start: number | null;
  score: number;
  offset_sec: number;
}

export type OffsetDirection = "earlier" | "later" | "none";

export interface OffsetDetectResult {
  speaker: string;
  offsetSec: number;
  confidence: number;
  nAnchors: number;
  totalAnchors: number;
  totalSegments: number;
  method: string;
  // Fields below were added when the detector switched to monotonic
  // alignment + manual-pair detection. Optional for back-compat with
  // any cached payloads from earlier server builds.
  spreadSec?: number;
  direction?: OffsetDirection;
  directionLabel?: string;
  anchorDistribution?: string;
  reliable?: boolean;
  warnings?: string[];
  matches?: OffsetMatch[];
}

export interface OffsetApplyResult {
  speaker: string;
  appliedOffsetSec: number;
  shiftedIntervals: number;
}

export async function detectTimestampOffset(
  speaker: string,
  options?: {
    sttJobId?: string;
    sttSegments?: unknown[];
    anchorDistribution?: "quantile" | "earliest";
    nAnchors?: number;
  }
): Promise<OffsetDetectResult> {
  return apiFetch<OffsetDetectResult>("/api/offset/detect", {
    method: "POST",
    body: JSON.stringify({
      speaker,
      sttJobId: options?.sttJobId,
      sttSegments: options?.sttSegments,
      anchorDistribution: options?.anchorDistribution,
      nAnchors: options?.nAnchors,
    }),
  });
}

export interface OffsetPair {
  audioTimeSec: number;
  csvTimeSec?: number;
  conceptId?: string;
}

export async function detectTimestampOffsetFromPair(
  speaker: string,
  audioTimeSec: number,
  options: { csvTimeSec?: number; conceptId?: string }
): Promise<OffsetDetectResult> {
  return apiFetch<OffsetDetectResult>("/api/offset/detect-from-pair", {
    method: "POST",
    body: JSON.stringify({
      speaker,
      audioTimeSec,
      csvTimeSec: options.csvTimeSec,
      conceptId: options.conceptId,
    }),
  });
}

export async function detectTimestampOffsetFromPairs(
  speaker: string,
  pairs: OffsetPair[]
): Promise<OffsetDetectResult> {
  return apiFetch<OffsetDetectResult>("/api/offset/detect-from-pair", {
    method: "POST",
    body: JSON.stringify({ speaker, pairs }),
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

// IPA is now generated acoustically by the server (wav2vec2 on audio
// slices). The former text → IPA endpoint POST /api/ipa has been removed
// in the Tier 3 purge — regenerate the IPA tier via the ipa_only compute
// job (Actions → Run IPA transcription).

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
    // Forward the backend's opaque ``result`` field. ``full_pipeline``
    // returns its per-step results here; ``useBatchPipelineJob`` reads
    // this to populate the BatchReportModal. Previously this field was
    // silently dropped, causing every batch report to show 0/0/0 with
    // em-dashes even when the server completed the work. Callers that
    // don't care about the payload ignore it; typed callers cast to
    // their expected compute-specific shape.
    result: payload.result,
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

// Pipeline state — powers the pre-flight speaker/step grid shown before
// running a transcription batch. Each entry carries three orthogonal
// dimensions:
//   - `done`     : tier has ≥1 non-empty interval (legacy signal,
//                  useful for the "will overwrite" warning)
//   - `can_run`  : the step can be invoked right now (prerequisites met)
//   - `full_coverage` : the intervals actually span the entire audio
//                       (not merely the legacy timestamps). THIS is the
//                       signal to gate "needs re-run" decisions on; a
//                       tier can be `done: true, full_coverage: false`
//                       when old runs only transcribed the slice where
//                       stale concept timestamps lived.
export interface PipelineStepState {
  done: boolean;
  can_run: boolean;
  reason: string | null;
  // Coverage metadata — `null` when the step doesn't apply (normalize)
  // or the audio duration couldn't be determined.
  coverage_start_sec?: number | null;
  coverage_end_sec?: number | null;
  coverage_fraction?: number | null;
  full_coverage?: boolean | null;
}

export interface PipelineNormalizeState extends PipelineStepState {
  path: string | null;
}

export interface PipelineSttState extends PipelineStepState {
  segments: number;
}

export interface PipelineTierState extends PipelineStepState {
  intervals: number;
}

export interface PipelineState {
  speaker: string;
  /** Audio duration in seconds, resolved from the WAV header (preferred)
   *  or the annotation's ``source_audio_duration_sec`` hint. Null when
   *  neither is available. */
  duration_sec?: number | null;
  normalize: PipelineNormalizeState;
  stt: PipelineSttState;
  ortho: PipelineTierState;
  ipa: PipelineTierState;
}

export async function getPipelineState(speaker: string): Promise<PipelineState> {
  return apiFetch<PipelineState>(
    `/api/pipeline/state/${encodeURIComponent(speaker)}`,
  );
}

// Pipeline run result — returned from `startCompute('full_pipeline')`
// after completion. Step-level `status` is the primary dimension the UI
// cares about ("ok" / "skipped" / "error"); `traceback` is surfaced in
// the Report modal's expand-for-details disclosure.
export type PipelineStepStatus = "ok" | "skipped" | "error";

export interface PipelineStepResultBase {
  /** Optional — older servers and direct per-step endpoints may omit it.
   *  The UI classifier in ``BatchReportModal`` falls back to heuristics
   *  (positive counts, skipped flag, error string) when missing. */
  status?: PipelineStepStatus;
  reason?: string;
  error?: string;
  traceback?: string;
  // Shape overlaps below are step-specific; carry them loosely — the
  // UI only pulls what it knows about.
  [key: string]: unknown;
}

export interface PipelineRunResult {
  speaker: string;
  steps_run: string[];
  results: Partial<Record<"normalize" | "stt" | "ortho" | "ipa", PipelineStepResultBase>>;
  summary: { ok: number; skipped: number; error: number };
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
