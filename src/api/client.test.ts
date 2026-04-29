// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getConfig, runChat, saveAnnotation, startChatSession } from "./client";

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
