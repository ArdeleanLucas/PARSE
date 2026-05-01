// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cancelComputeJob, getConfig, runChat, saveAnnotation, startChatSession, tagsApi } from "./client";

describe("chat API client contracts", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("__PARSE_API_TARGET__", "http://127.0.0.1:8766");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("startChatSession unwraps the server's camelCase sessionId payload", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ sessionId: "chat_123" }),
    });

    await expect(startChatSession()).resolves.toMatchObject({ session_id: "chat_123" });
  });

  it("runChat turns raw fetch failures into actionable PARSE API errors", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(runChat("chat_123", "hello")).rejects.toThrow(
      /Could not reach the PARSE API.*8766/i,
    );
  });

  it("uses __PARSE_API_TARGET__ in network error messages", async () => {
    vi.stubGlobal("__PARSE_API_TARGET__", "http://127.0.0.1:8866");
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(runChat("chat_123", "hello")).rejects.toThrow(/127\.0\.0\.1:8866/);
  });
});

describe("cancelComputeJob API client contract", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to the compute cancel endpoint and returns a successful body", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ cancelled: true, job_id: "abc" }),
    });

    await expect(cancelComputeJob("abc")).resolves.toEqual({ cancelled: true, job_id: "abc" });
    expect(fetchMock).toHaveBeenCalledWith("/api/compute/abc/cancel", expect.objectContaining({ method: "POST" }));
  });

  it("resolves with a 404 body instead of throwing", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ cancelled: false, job_id: "abc", reason: "not found" }),
    });

    await expect(cancelComputeJob("abc")).resolves.toEqual({
      cancelled: false,
      job_id: "abc",
      reason: "not found",
    });
  });

  it("resolves network errors instead of throwing", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(cancelComputeJob("abc")).resolves.toEqual({
      cancelled: false,
      job_id: "abc",
      reason: "Failed to fetch",
    });
  });
});

describe("getConfig / unwrapConfig schema-version guard", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves when schema_version matches", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        config: { schema_version: 1, speakers: [], concepts: [], project_name: "t", language_code: "und", audio_dir: "audio", annotations_dir: "annotations" },
      }),
    });
    await expect(getConfig()).resolves.toMatchObject({ schema_version: 1, speakers: [] });
  });

  it("rejects with an actionable message when schema_version is missing", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ config: { project_name: "test" } }),
    });
    await expect(getConfig()).rejects.toThrow(/outdated/i);
  });

  it("rejects when schema_version is a future version", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ config: { schema_version: 99 } }),
    });
    await expect(getConfig()).rejects.toThrow(/outdated/i);
  });

  it("rejects when the {config} wrapper is missing (old flat-format server)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ project_name: "test", speakers: [] }),
    });
    await expect(getConfig()).rejects.toThrow(/outdated/i);
  });
});

describe("annotation API client contracts", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("saveAnnotation unwraps the server-normalized annotation record", async () => {
    const normalized = {
      speaker: "Fail01",
      source_wav: "Fail01.wav",
      tiers: {
        concept: { name: "concept", display_order: 1, intervals: [{ start: 2, end: 3, text: "water" }] },
        ortho_words: { name: "ortho_words", display_order: 4, intervals: [{ start: 2, end: 2.5, text: "ئاو" }] },
      },
    };
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, speaker: "Fail01", annotation: normalized }),
    });

    await expect(saveAnnotation("Fail01", normalized)).resolves.toBe(normalized);
    expect(fetchMock).toHaveBeenCalledWith("/api/annotations/Fail01", expect.objectContaining({ method: "POST" }));
  });
});


describe("concept tags API client contracts", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the global tag registry and concept attachments", async () => {
    const payload = {
      tags: [{ id: "t1", name: "archaic", color: "#3554B8", createdAt: "2026-05-01T00:00:00.000Z" }],
      attachments: { sister: ["t1"] },
    };
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => payload,
    });

    await expect(tagsApi.fetchAll()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/tags", expect.objectContaining({ headers: expect.any(Object) }));
  });

  it("creates tags through POST /api/tags", async () => {
    const tag = { id: "t2", name: "dialectal", color: "#0f766e", createdAt: "2026-05-01T00:00:00.000Z" };
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => tag,
    });

    await expect(tagsApi.create({ name: "dialectal", color: "#0f766e" })).resolves.toEqual(tag);
    expect(fetchMock).toHaveBeenCalledWith("/api/tags", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "dialectal", color: "#0f766e" }),
    }));
  });

  it("treats 204 attach/detach/delete responses as void", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      json: vi.fn(),
    });

    await expect(tagsApi.attach("sister", "t1")).resolves.toBeUndefined();
    await expect(tagsApi.detach("sister", "t1")).resolves.toBeUndefined();
    await expect(tagsApi.delete("t1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/concepts/sister/tags/t1", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/concepts/sister/tags/t1", expect.objectContaining({ method: "DELETE" }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/tags/t1", expect.objectContaining({ method: "DELETE" }));
  });
});
