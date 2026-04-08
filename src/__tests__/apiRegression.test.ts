// src/__tests__/apiRegression.test.ts
// Live integration tests — run against the Python server.
// Usage: npm run test:api
// Optional override: PARSE_API_BASE_URL=http://127.0.0.1:8766 npm run test:api

import { beforeAll, describe, expect, it } from "vitest";

const envBase = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
  ?.PARSE_API_BASE_URL;
const API_BASE = (envBase ?? "http://127.0.0.1:8766").replace(/\/+$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

async function json(response: Response): Promise<unknown> {
  return response.json();
}

function errorMessage(payload: unknown): string {
  if (isRecord(payload) && typeof payload.error === "string") {
    return payload.error;
  }
  return "";
}

function resolveJobId(payload: unknown): string {
  if (!isRecord(payload)) {
    return "";
  }
  const camel = payload.jobId;
  if (typeof camel === "string" && camel.trim()) {
    return camel.trim();
  }
  const snake = payload.job_id;
  if (typeof snake === "string" && snake.trim()) {
    return snake.trim();
  }
  return "";
}

beforeAll(async () => {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/config`, { signal: AbortSignal.timeout(3000) });
  } catch (error) {
    throw new Error(
      `Python API regression requires a running server at ${API_BASE}. Connection failed: ${String(error)}`
    );
  }

  if (!response.ok) {
    throw new Error(
      `Python API regression requires a healthy server at ${API_BASE}. GET /api/config returned ${response.status}.`
    );
  }
});

describe("Python API regression", () => {
  // ── Config ──────────────────────────────────────────────────────────────

  it("GET /api/config → { config: {...} }", async () => {
    const r = await fetch(`${API_BASE}/api/config`);
    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    expect(isRecord(d.config)).toBe(true);
  });

  it("PUT /api/config → 200 (no-op patch)", async () => {
    const r = await fetch(`${API_BASE}/api/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);
  });

  // ── Annotations ─────────────────────────────────────────────────────────

  it("GET /api/annotations/Fail01 → speaker + tiers", async () => {
    const r = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    expect(d.speaker).toBe("Fail01");
    expect(isRecord(d.tiers)).toBe(true);
  });

  it("POST /api/annotations/Fail01 accepts valid payload or returns structured path-guard error", async () => {
    const getResponse = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(getResponse.status).toBe(200);

    const original = await json(getResponse);
    const postResponse = await fetch(`${API_BASE}/api/annotations/Fail01`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(original),
    });

    expect([200, 400]).toContain(postResponse.status);
    if (postResponse.status === 400) {
      const payload = await json(postResponse);
      expect(errorMessage(payload)).toContain("Path escapes project root");
    }
  });

  // ── Enrichments ─────────────────────────────────────────────────────────

  it("GET /api/enrichments → object payload", async () => {
    const r = await fetch(`${API_BASE}/api/enrichments`);
    expect(r.status).toBe(200);

    const d = await json(r);
    expect(isRecord(d)).toBe(true);
  });

  it("POST /api/enrichments → 200 (save unchanged)", async () => {
    const getResponse = await fetch(`${API_BASE}/api/enrichments`);
    expect(getResponse.status).toBe(200);

    const payload = (await json(getResponse)) as Record<string, unknown>;
    const enrichments = isRecord(payload.enrichments) ? payload.enrichments : payload;

    const postResponse = await fetch(`${API_BASE}/api/enrichments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enrichments }),
    });

    expect(postResponse.status).toBe(200);
  });

  // ── Auth ────────────────────────────────────────────────────────────────

  it("GET /api/auth/status → AuthStatus shape", async () => {
    const r = await fetch(`${API_BASE}/api/auth/status`);
    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    expect(typeof d.authenticated).toBe("boolean");
  });

  it("POST /api/auth/start → 200", async () => {
    const r = await fetch(`${API_BASE}/api/auth/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);
  });

  it("POST /api/auth/poll → 200", async () => {
    const r = await fetch(`${API_BASE}/api/auth/poll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);
  });

  it("POST /api/auth/logout → 200", async () => {
    const r = await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);
  });

  // ── IPA + Suggestions ───────────────────────────────────────────────────

  it("POST /api/ipa → { ipa: string }", async () => {
    const r = await fetch(`${API_BASE}/api/ipa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "hello", language: "en" }),
    });

    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    expect(typeof d.ipa).toBe("string");
  });

  it("POST /api/suggest → wrapped suggestions array", async () => {
    const r = await fetch(`${API_BASE}/api/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker: "Fail01", concept_ids: [] }),
    });

    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    expect(Array.isArray(d.suggestions)).toBe(true);
  });

  // ── STT ─────────────────────────────────────────────────────────────────

  it("POST /api/stt → returns job id", async () => {
    const r = await fetch(`${API_BASE}/api/stt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker: "Fail01", source_wav: "test.wav" }),
    });

    expect(r.status).toBe(200);

    const d = await json(r);
    expect(resolveJobId(d).length).toBeGreaterThan(0);
  });

  it("POST /api/stt/status unknown job → 404 Unknown jobId", async () => {
    const r = await fetch(`${API_BASE}/api/stt/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-stt-job" }),
    });

    expect(r.status).toBe(404);

    const d = await json(r);
    expect(errorMessage(d)).toContain("Unknown jobId");
  });

  // ── Chat ────────────────────────────────────────────────────────────────

  it("POST /api/chat/session → returns session id", async () => {
    const r = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);

    const d = (await json(r)) as Record<string, unknown>;
    const sessionId = d.sessionId ?? d.session_id;
    expect(typeof sessionId).toBe("string");
  });

  it("GET /api/chat/session/{id} → session object", async () => {
    const start = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(start.status).toBe(200);

    const startPayload = (await json(start)) as Record<string, unknown>;
    const sessionId = String(startPayload.sessionId ?? startPayload.session_id ?? "");
    expect(sessionId.length).toBeGreaterThan(0);

    const getSession = await fetch(`${API_BASE}/api/chat/session/${encodeURIComponent(sessionId)}`);
    expect(getSession.status).toBe(200);

    const sessionPayload = await json(getSession);
    expect(isRecord(sessionPayload)).toBe(true);
  });

  it("POST /api/chat/run → returns job id", async () => {
    const start = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(start.status).toBe(200);

    const startPayload = (await json(start)) as Record<string, unknown>;
    const sessionId = String(startPayload.sessionId ?? startPayload.session_id ?? "");

    const run = await fetch(`${API_BASE}/api/chat/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: "test" }),
    });

    expect(run.status).toBe(200);

    const runPayload = await json(run);
    expect(resolveJobId(runPayload).length).toBeGreaterThan(0);
  });

  it("POST /api/chat/run/status unknown job → 404 Unknown jobId", async () => {
    const r = await fetch(`${API_BASE}/api/chat/run/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-chat-job" }),
    });

    expect(r.status).toBe(404);

    const d = await json(r);
    expect(errorMessage(d)).toContain("Unknown jobId");
  });

  // ── Compute ─────────────────────────────────────────────────────────────

  it("POST /api/compute/cognates → returns job id", async () => {
    const r = await fetch(`${API_BASE}/api/compute/cognates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    expect(r.status).toBe(200);

    const d = await json(r);
    expect(resolveJobId(d).length).toBeGreaterThan(0);
  });

  it("POST /api/compute/cognates/status unknown job → 404 Unknown jobId", async () => {
    const r = await fetch(`${API_BASE}/api/compute/cognates/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-compute-job" }),
    });

    expect(r.status).toBe(404);

    const d = await json(r);
    expect(errorMessage(d)).toContain("Unknown jobId");
  });

  // ── Export ──────────────────────────────────────────────────────────────

  it("GET /api/export/lingpy → endpoint exists (TSV success or structured 500)", async () => {
    const r = await fetch(`${API_BASE}/api/export/lingpy`);

    // 200: valid export
    // 500: dataset/project-root problem (e.g., missing parse-enrichments.json)
    // 404 is NOT acceptable here — it means route mismatch/regression.
    expect([200, 500]).toContain(r.status);

    if (r.status === 200) {
      const text = await r.text();
      expect(text.length).toBeGreaterThan(0);

      const header = text.split("\n")[0]?.trim() ?? "";
      expect(header).toContain("ID");
      expect(header).toContain("DOCULECT");
      expect(header).toContain("CONCEPT");
      expect(header).toContain("IPA");
      expect(header).toContain("COGID");
      expect(header).toContain("TOKENS");
      expect(header).toContain("BORROWING");
      return;
    }

    const payload = await json(r);
    const msg = errorMessage(payload).toLowerCase();
    expect(msg).toContain("parse-enrichments");
  });

  it("GET /api/export/nexus → 501 not implemented (route exists)", async () => {
    const r = await fetch(`${API_BASE}/api/export/nexus`);
    expect(r.status).toBe(501);

    const d = await json(r);
    expect(errorMessage(d).toLowerCase()).toContain("not yet implemented");
  });
});
