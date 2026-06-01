// @vitest-environment node
//
// Runs under the node environment (not jsdom) on purpose. These are pure
// request-shaping/URL contracts plus one download helper; none need the DOM.
// Under jsdom, `fetch`/`Response` come from undici while `Blob`/`FileReader`
// come from jsdom, and `response.blob()` returns an undici Blob in CI but a
// jsdom Blob locally — the two implementations are not interchangeable, so any
// `blob.text()` / `FileReader` read is environment-fragile. In node, the global
// Blob is Node's own (with a working `.text()`), matching the sibling
// node-environment contract test `offset-tools.test.ts`.
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getCanonicalLexemesReport,
  getConceptAppendixExport,
  mediaUrlFromSourceWav,
  spectrogramUrl,
} from "./export-and-media";

describe("export-and-media contracts", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("downloads the canonical-lexemes TSV report with a plain GET request", async () => {
    const fetchMock = vi.fn(async () => new Response("concept_id\tspeaker\n", {
      headers: { "Content-Type": "text/tab-separated-values;charset=utf-8" },
      status: 200,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const blob = await getCanonicalLexemesReport();

    expect(fetchMock).toHaveBeenCalledWith("/api/exports/canonical-lexemes-report", { method: "GET" });
    expect(await blob.text()).toBe("concept_id\tspeaker\n");
  });

  it("posts to the concept-appendix MCP tool and unwraps result.markdown into a Blob", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      new Response(JSON.stringify({ tool: "export_concept_appendix_md", ok: true, result: { markdown: "# Concept Appendix\n" } }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const blob = await getConceptAppendixExport();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/mcp/tools/export_concept_appendix_md?mode=default");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ includeCognates: true });
    expect(blob.type).toContain("text/markdown");
    expect(await blob.text()).toBe("# Concept Appendix\n");
  });

  it("includes a non-empty speaker subset in the concept-appendix request body", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      new Response(JSON.stringify({ ok: true, result: { markdown: "# x\n" } }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getConceptAppendixExport({ speakers: ["Fail01", "Kalh01"] });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      includeCognates: true,
      speakers: ["Fail01", "Kalh01"],
    });
  });

  it("throws when the concept-appendix tool envelope carries no markdown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ ok: true, result: {} }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    ));
    await expect(getConceptAppendixExport()).rejects.toThrow(/no markdown/i);
  });

  it("omits basename-only audio hints from spectrogram URLs so the backend can use speaker fallback", () => {
    expect(
      spectrogramUrl({
        speaker: "Saha01",
        startSec: 1524.743,
        endSec: 1525.583,
        audio: "Saha01.wav",
      }),
    ).toBe("/api/spectrogram?speaker=Saha01&start=1524.743&end=1525.583");
  });

  it("keeps project-relative spectrogram audio hints and normalizes path separators", () => {
    expect(
      spectrogramUrl({
        speaker: "Saha01",
        startSec: 1524.743,
        endSec: 1525.583,
        audio: "\\audio\\working\\Saha01\\Saha01.wav",
        force: true,
      }),
    ).toBe(
      "/api/spectrogram?speaker=Saha01&start=1524.743&end=1525.583&audio=audio%2Fworking%2FSaha01%2FSaha01.wav&force=1",
    );
  });

  it("can map basename-only source_wav values through the normalized working-audio convention when speaker is known", () => {
    expect(mediaUrlFromSourceWav("Saha01.wav", { speaker: "Saha01" })).toBe(
      "/audio/working/Saha01/Saha01.wav",
    );
  });
});
