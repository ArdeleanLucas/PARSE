// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getCanonicalLexemesReport } from "./export-and-media";

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
});
