import type { AuthStatus } from "../types";
import { apiFetch } from "./shared";

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
