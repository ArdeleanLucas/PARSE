import type { EnrichmentsPayload, ProjectConfig } from "../types";
import { CONFIG_SCHEMA_VERSION } from "../client";

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export const isRecord = isPlainRecord;

export function resolveJobId(payload: unknown): string {
  if (!isPlainRecord(payload)) {
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

export function resolveSessionId(payload: unknown): string {
  if (!isPlainRecord(payload)) {
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

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;
  readonly method: string;
  readonly body: unknown;

  constructor(status: number, method: string, path: string, body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.method = method;
    this.body = body;
  }
}

export function networkError(path: string, options: RequestInit | undefined, error: unknown): Error {
  const message = error instanceof Error ? error.message : String(error ?? "Unknown fetch error");
  if (/failed to fetch|networkerror/i.test(message)) {
    const target = (typeof __PARSE_API_TARGET__ !== "undefined" && __PARSE_API_TARGET__) || "http://127.0.0.1:8766";
    return new Error(
      `Could not reach the PARSE API for ${options?.method ?? "GET"} ${path}. `
      + `Check that the Python server is running at ${target} and that the Vite /api proxy is active.`,
    );
  }
  return error instanceof Error ? error : new Error(message);
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
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
    let parsedBody: unknown = undefined;
    if (text) {
      try {
        parsedBody = JSON.parse(text);
      } catch {
        parsedBody = text;
      }
    }
    const method = options?.method ?? "GET";
    throw new ApiError(
      response.status,
      method,
      path,
      parsedBody,
      `API ${method} ${path} failed ${response.status}: ${text}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const contentLength = response.headers?.get("content-length");
  if (contentLength === "0") {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function unwrapConfig(payload: unknown): ProjectConfig {
  if (isPlainRecord(payload) && isPlainRecord(payload.config)) {
    const cfg = payload.config;
    if (cfg.schema_version !== CONFIG_SCHEMA_VERSION) {
      const got = cfg.schema_version === undefined ? "missing" : String(cfg.schema_version);
      throw new Error(
        `PARSE server is outdated (config schema_version: ${got}, expected: ${CONFIG_SCHEMA_VERSION}). ` +
        "Restart the Python server with the latest code and reload the page.",
      );
    }
    return cfg as ProjectConfig;
  }
  throw new Error(
    "PARSE server is outdated: /api/config response is missing the expected wrapper. " +
    "Restart the Python server with the latest code and reload the page.",
  );
}

export function unwrapEnrichments(payload: unknown): EnrichmentsPayload {
  if (isPlainRecord(payload) && isPlainRecord(payload.enrichments)) {
    return payload.enrichments as EnrichmentsPayload;
  }
  return (payload ?? {}) as EnrichmentsPayload;
}
