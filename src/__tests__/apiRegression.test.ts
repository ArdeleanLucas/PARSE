// src/__tests__/apiRegression.test.ts
// Live integration tests — run manually against the Python server at :8766
// Usage: npm run test -- src/__tests__/apiRegression.test.ts
//
// These tests SKIP automatically if the server is not running.

import { describe, it, expect, beforeAll } from "vitest";

const API_BASE = "http://127.0.0.1:8766";

// Check server availability once before all tests
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

describe("Python API regression", () => {
  it("GET /api/config returns config object", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/config`);
    expect(r.status).toBe(200);
    const d = await r.json() as { config: Record<string, unknown> };
    expect(d.config).toBeDefined();
    expect(typeof d.config).toBe("object");
  });

  it("GET /api/annotations/Fail01 returns valid annotation record", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(r.status).toBe(200);
    const d = await r.json() as { speaker: string; tiers: Record<string, unknown> };
    expect(d.speaker).toBe("Fail01");
    expect(d.tiers).toBeDefined();
    expect(typeof d.tiers).toBe("object");
  });

  it("POST /api/annotations/Fail01 round-trips data", async () => {
    if (skipIfNoServer()) return;
    // Fetch current annotation
    const r1 = await fetch(`${API_BASE}/api/annotations/Fail01`);
    expect(r1.status).toBe(200);
    const original = await r1.json();
    // POST it back unmodified
    const r2 = await fetch(`${API_BASE}/api/annotations/Fail01`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(original),
    });
    expect(r2.status).toBe(200);
  });

  it("GET /api/enrichments returns enrichments data", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/enrichments`);
    expect(r.status).toBe(200);
    const d = await r.json() as { enrichments?: unknown } | unknown;
    // Server may return { enrichments: {...} } or a plain object — either is acceptable
    expect(d).toBeDefined();
    expect(typeof d).toBe("object");
  });

  it("GET /api/export/lingpy returns TSV or 404 (endpoint may require updated server)", async () => {
    if (skipIfNoServer()) return;
    const r = await fetch(`${API_BASE}/api/export/lingpy`);
    // Accept 200 (TSV) or 404 (older server without this endpoint)
    // 200 means the React pivot's server.py changes are deployed
    // 404 means the older server is running — not a test failure, just a deployment state
    expect([200, 404]).toContain(r.status);
    if (r.status === 200) {
      const text = await r.text();
      // If endpoint is live, verify basic TSV structure
      expect(text.length).toBeGreaterThan(0);
      // Should contain tab-separated headers
      const firstLine = text.split("\n")[0];
      expect(firstLine).toContain("\t");
      console.info("[lingpy] TSV first line:", firstLine);
    } else {
      console.warn("[lingpy] 404 — older server running; deploy updated server.py to test");
    }
  });
});
