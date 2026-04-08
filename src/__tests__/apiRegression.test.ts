// src/__tests__/apiRegression.test.ts
// Live integration tests — run against the Python server at :8766
// Usage: npm run test:api
//
// These tests SKIP automatically if the server is not running.
// Uses 127.0.0.1 (not localhost) because Node resolves localhost to ::1
// but the Python server only binds 127.0.0.1.

import { describe, it, expect, beforeAll } from "vitest";

const API_BASE = "http://127.0.0.1:8766";

let serverAvailable = false;

beforeAll(async () => {
  try {
    const r = await fetch(`${API_BASE}/api/config`, { signal: AbortSignal.timeout(2000) });
    serverAvailable = r.ok;
  } catch {
    serverAvailable = false;
  }
});

function skipIfNoServer() {
  if (!serverAvailable) {
    console.warn("SKIP: Python server not available at :8766");
    return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function json(r: Response): Promise<unknown> {
  return r.json();
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

// ---------------------------------------------------------------------------
// Tests — grouped by domain, covering all 22 client.ts functions
// ---------------------------------------------------------------------------

describe("Python API regression", () => {
  // ── Config ──────────────────────────────────────────────────────────────

  it("GET /api/config → { config: {...} }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/config`);
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    expect(d.config).toBeDefined();
    expect(isRecord(d.config)).toBe(true);
  });

  it("PUT /api/config → 200 (no-op patch)", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
  });

  // ── Annotations ─────────────────────────────────────────────────────────

  it("GET /api/annotations/Fail01 → speaker + tiers", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    expect(d.speaker).toBe("Fail01");
    expect(isRecord(d.tiers)).toBe(true);
  });

  it("POST /api/annotations/Fail01 round-trips data", async () => {
    if (skipIfNoServer()) return;
    const r1 = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(r1.status).toBe(200);
    const original = await json(r1);
    const r2 = await fetch(`${API_BASE}/api/annotations/Fail01`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(original),
    });
    expect(r2.status).toBe(200);
  });

  // ── Enrichments ─────────────────────────────────────────────────────────

  it("GET /api/enrichments → { enrichments: {...} }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/enrichments`);
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    expect(d).toBeDefined();
    expect(typeof d).toBe("object");
  });

  it("POST /api/enrichments → 200 (save)", async () => {
    if (skipIfNoServer()) return;
    // Fetch current, POST back unchanged
    const r1 = await fetch(`${API_BASE}/api/enrichments`);
    expect(r1.status).toBe(200);
    const d = (await json(r1)) as Record<string, unknown>;
    const enrichments = isRecord(d.enrichments) ? d.enrichments : d;
    const r2 = await fetch(`${API_BASE}/api/enrichments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enrichments }),
    });
    expect(r2.status).toBe(200);
  });

  // ── Auth ────────────────────────────────────────────────────────────────

  it("GET /api/auth/status → AuthStatus shape", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/auth/status`);
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    expect(typeof d.authenticated).toBe("boolean");
  });

  it("POST /api/auth/start → 200", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/auth/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
  });

  it("POST /api/auth/poll → 200 (AuthStatus shape)", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/auth/poll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
  });

  it("POST /api/auth/logout → 200", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
  });

  // ── IPA ─────────────────────────────────────────────────────────────────

  it("POST /api/ipa → { ipa: string }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/ipa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "hello", language: "en" }),
    });
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    expect(typeof d.ipa).toBe("string");
  });

  // ── Suggestions ─────────────────────────────────────────────────────────

  it("POST /api/suggest → { suggestions: [...] } (wrapped)", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker: "Fail01", concept_ids: [] }),
    });
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    // Server wraps in { suggestions: [...] }
    expect(Array.isArray(d.suggestions)).toBe(true);
  });

  // ── STT ─────────────────────────────────────────────────────────────────

  it("POST /api/stt → { jobId: string }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/stt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker: "Fail01", source_wav: "test.wav" }),
    });
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    // Server returns camelCase jobId
    expect(typeof d.jobId === "string" || typeof d.job_id === "string").toBe(true);
  });

  it("POST /api/stt/status → status object or error for unknown job", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/stt/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-job-id" }),
    });
    // Accept 200 (with error field) or 404
    expect([200, 404]).toContain(r.status);
    const d = (await json(r)) as Record<string, unknown>;
    expect(d).toBeDefined();
  });

  // ── Chat ────────────────────────────────────────────────────────────────

  it("POST /api/chat/session → { sessionId: string }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    // Server may return sessionId or session_id
    const sid = d.sessionId ?? d.session_id;
    expect(typeof sid).toBe("string");
  });

  it("GET /api/chat/session/{id} → session object", async () => {
    if (skipIfNoServer()) return;
    // Start a session first
    const r1 = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r1.status).toBe(200);
    const d1 = (await json(r1)) as Record<string, unknown>;
    const sid = (d1.sessionId ?? d1.session_id) as string;

    const r2 = await fetch(`${API_BASE}/api/chat/session/${encodeURIComponent(sid)}`);
    expect(r2.status).toBe(200);
    const d2 = (await json(r2)) as Record<string, unknown>;
    expect(d2).toBeDefined();
  });

  it("POST /api/chat/run → { jobId: string } (chat job)", async () => {
    if (skipIfNoServer()) return;
    // Start a session
    const r1 = await fetch(`${API_BASE}/api/chat/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r1.status).toBe(200);
    const d1 = (await json(r1)) as Record<string, unknown>;
    const sid = (d1.sessionId ?? d1.session_id) as string;

    const r2 = await fetch(`${API_BASE}/api/chat/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, message: "test" }),
    });
    expect(r2.status).toBe(200);
    const d2 = (await json(r2)) as Record<string, unknown>;
    const jobId = d2.jobId ?? d2.job_id;
    expect(typeof jobId).toBe("string");
  });

  it("POST /api/chat/status → status object", async () => {
    if (skipIfNoServer()) return;
    // Poll with a fake job_id — server should still respond (200 or 404)
    const r = await fetch(`${API_BASE}/api/chat/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-chat-job" }),
    });
    expect([200, 404]).toContain(r.status);
  });

  // ── Compute ─────────────────────────────────────────────────────────────

  it("POST /api/compute/cognates → { jobId: string }", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/compute/cognates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(200);
    const d = (await json(r)) as Record<string, unknown>;
    const jobId = d.jobId ?? d.job_id;
    expect(typeof jobId).toBe("string");
  });

  it("POST /api/compute/cognates/status → status object", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/compute/cognates/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: "nonexistent-compute-job" }),
    });
    // Accept 200 (with error/status field) or 404
    expect([200, 404]).toContain(r.status);
  });

  // ── Export ──────────────────────────────────────────────────────────────

  it("GET /api/export/lingpy → TSV or 404", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/export/lingpy`);
    expect([200, 404]).toContain(r.status);
    if (r.status === 200) {
      const text = await r.text();
      expect(text.length).toBeGreaterThan(0);
      const firstLine = text.split("\n")[0];
      expect(firstLine).toContain("\t");
      console.info("[lingpy] TSV first line:", firstLine);
    } else {
      console.warn("[lingpy] 404 — endpoint not available on this server version");
    }
  });

  it("GET /api/export/nexus → TSV/NEXUS or 404", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/export/nexus`);
    expect([200, 404]).toContain(r.status);
    if (r.status === 200) {
      const text = await r.text();
      expect(text.length).toBeGreaterThan(0);
      console.info("[nexus] Response length:", text.length);
    } else {
      console.warn("[nexus] 404 — endpoint not available on this server version");
    }
  });
});
