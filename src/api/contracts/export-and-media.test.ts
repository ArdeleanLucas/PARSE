// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getCanonicalLexemesReport, mediaUrlFromSourceWav, spectrogramUrl } from "./export-and-media";

// jsdom's Blob lacks `.text()`/`.arrayBuffer()` (unlike a real browser or Node Blob),
// so read the body through FileReader, which jsdom does implement.
function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

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
    expect(await readBlobText(blob)).toBe("concept_id\tspeaker\n");
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
