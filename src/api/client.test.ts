// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cancelComputeJob,
  getConfig,
  getSurveyOverlap,
  getTags,
  putTags,
  runChat,
  rerunLexemeIpa,
  rerunLexemeOrtho,
  saveAnnotation,
  searchLexeme,
  startChatSession,
  updateSurveyOverlap,
} from "./client";

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

/**
 * Wire-format contract for /api/survey-overlap.
 *
 * The endpoint returns the SurveyOverlapState payload BARE — no
 * "survey_overlap": ... envelope, no "success": true wrapper. The
 * paired backend assertion lives in
 * python/test_survey_overlap_routes.py::test_api_survey_overlap_returns_bare_state_without_envelope_keys.
 * If you change the response shape on either side, update both tests.
 */
describe("survey-overlap API client contract", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the normalized survey-overlap sidecar state", async () => {
    const payload = {
      version: 1,
      color_coding_enabled: false,
      surveys: { klq: { display_label: "KLQ", display_color: "slate" } },
      concept_survey_links: { rain: { klq: "KLQ_1.10", jbil: "JBIL_100" } },
      speaker_choices: { Saha01: { rain: "jbil" } },
    };
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => payload });

    await expect(getSurveyOverlap()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/survey-overlap", expect.objectContaining({ headers: expect.any(Object) }));
  });

  it("posts survey-overlap patches and returns the normalized state", async () => {
    const patch = { speaker_choices: { Saha01: { rain: "jbil" } } };
    const normalized = {
      version: 1,
      color_coding_enabled: false,
      surveys: {},
      concept_survey_links: { rain: { klq: "KLQ_1.10", jbil: "JBIL_100" } },
      speaker_choices: patch.speaker_choices,
    };
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => normalized });

    await expect(updateSurveyOverlap(patch)).resolves.toEqual(normalized);
    expect(fetchMock).toHaveBeenCalledWith("/api/survey-overlap", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(patch),
    }));
  });

  it("rejects responses that re-introduce a survey_overlap or success envelope", async () => {
    // Regression for PR #291 / PR #292: the backend originally wrapped the
    // payload in {survey_overlap, success}, the frontend expected bare state,
    // and the configStore silently overwrote in-memory survey settings with
    // undefined. This test pins the contract so the bug cannot recur.
    const stateKeys = ["version", "color_coding_enabled", "surveys", "concept_survey_links", "speaker_choices"];
    const bare = {
      version: 1,
      color_coding_enabled: true,
      surveys: { klq: { display_label: "Kurdish List", display_color: "teal" } },
      concept_survey_links: {},
      speaker_choices: {},
    };

    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers(), json: async () => bare });
    const fromGet = await getSurveyOverlap();
    expect(Object.keys(fromGet).sort()).toEqual(stateKeys.sort());
    expect((fromGet as unknown as Record<string, unknown>).survey_overlap).toBeUndefined();
    expect((fromGet as unknown as Record<string, unknown>).success).toBeUndefined();

    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers(), json: async () => bare });
    const fromPost = await updateSurveyOverlap({ color_coding_enabled: true });
    expect(Object.keys(fromPost).sort()).toEqual(stateKeys.sort());
    expect((fromPost as unknown as Record<string, unknown>).survey_overlap).toBeUndefined();
    expect((fromPost as unknown as Record<string, unknown>).success).toBeUndefined();
  });
});

describe("lexeme search API client contract", () => {
  const fetchMock = vi.fn();
  const searchPayload = {
    speaker: "Fail02",
    concept_id: "1",
    variants: ["water"],
    language: "ku",
    candidates: [],
    signals_available: { phonemizer: false, cross_speaker_anchors: 0, contact_variants: [] },
  };

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => searchPayload,
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("omits tiers when the option is absent or empty", async () => {
    await expect(searchLexeme("Fail02", ["water"], { conceptId: "1" })).resolves.toEqual(searchPayload);
    expect(fetchMock).toHaveBeenLastCalledWith(expect.not.stringContaining("tiers="), expect.any(Object));

    await searchLexeme("Fail02", ["water"], { conceptId: "1", tiers: [] });
    expect(fetchMock).toHaveBeenLastCalledWith(expect.not.stringContaining("tiers="), expect.any(Object));
  });

  it("serializes selected tiers as a comma-joined query param", async () => {
    await searchLexeme("Fail02", ["water"], { conceptId: "1", tiers: ["stt", "ipa"] });

    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("tiers=stt%2Cipa"),
      expect.any(Object),
    );
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

  it("rerunLexemeIpa posts the exact lexeme window and returns the rerun IPA payload", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ipa: "ʃari:", interval: { start: 2795.918, end: 2796.698 }, source: "rerun" }),
    });

    await expect(rerunLexemeIpa({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698 })).resolves.toEqual({
      ipa: "ʃari:",
      interval: { start: 2795.918, end: 2796.698 },
      source: "rerun",
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/lexeme/run_ipa", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698 }),
    }));
  });

  it("rerunLexemeOrtho posts the exact lexeme window and returns the rerun ORTH payload", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ortho: "شار", interval: { start: 2795.918, end: 2796.698 }, source: "rerun" }),
    });

    await expect(rerunLexemeOrtho({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698 })).resolves.toEqual({
      ortho: "شار",
      interval: { start: 2795.918, end: 2796.698 },
      source: "rerun",
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/lexeme/run_ortho", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698 }),
    }));
  });

  it("rerunLexemeOrtho posts pad=0.5 when provided", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ortho: "شار", interval: { start: 2795.918, end: 2796.698 }, source: "rerun" }),
    });

    await rerunLexemeOrtho({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698, pad: 0.5 });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({
      speaker: "Saha01",
      concept_key: "root",
      start: 2795.918,
      end: 2796.698,
      pad: 0.5,
    });
  });

  it("rerunLexemeOrtho omits pad when not provided", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ortho: "شار", interval: { start: 2795.918, end: 2796.698 }, source: "rerun" }),
    });

    await rerunLexemeOrtho({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698 });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).not.toHaveProperty("pad");
  });

  it("rerunLexemeIpa accepts pad too", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ipa: "ʃari:", interval: { start: 2795.918, end: 2796.698 }, source: "rerun" }),
    });

    await rerunLexemeIpa({ speaker: "Saha01", concept_key: "root", start: 2795.918, end: 2796.698, pad: 0.5 });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({
      speaker: "Saha01",
      concept_key: "root",
      start: 2795.918,
      end: 2796.698,
      pad: 0.5,
    });
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


describe("tags API client contracts", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches the unified tag registry", async () => {
    const payload = {
      tags: [{ id: "t1", label: "archaic", color: "#3554B8" }],
    };
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => payload,
    });

    await expect(getTags()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/tags", expect.objectContaining({ headers: expect.any(Object) }));
  });

  it("replaces the unified tag registry through PUT /api/tags", async () => {
    const tags = [{ id: "t2", label: "dialectal", color: "#0f766e" }];
    fetchMock.mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      json: vi.fn(),
    });

    await expect(putTags(tags)).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/tags", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ tags }),
    }));
  });
});
