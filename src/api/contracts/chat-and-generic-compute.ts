import type { ChatJob, ChatStatus, ComputeJob, ComputeStatus } from "../types";
import { apiFetch, isRecord, resolveJobId, resolveSessionId } from "./shared";

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

function coerceTokenField(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.round(value);
  }
  return null;
}

function unwrapChatSession(payload: unknown): ChatSessionPayload {
  const empty: ChatSessionPayload = { sessionId: "", tokensUsed: null, tokensLimit: null };
  if (!isRecord(payload)) return empty;
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
    ...(typeof payload.traceback === "string" ? { traceback: payload.traceback } : {}),
    result: payload.result,
  };
}
