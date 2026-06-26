// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useExport } from "../useExport";

let mockData: Record<string, unknown> = {};

vi.mock("../../api/client", () => ({
  getLingPyExport: vi.fn(),
  getNEXUSExport: vi.fn(),
  getCanonicalLexemesReport: vi.fn(),
  getConceptAppendixExport: vi.fn(),
  getConsolidatedNEXUSExport: vi.fn(),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (state: { data: Record<string, unknown> }) => unknown) =>
    selector({ data: mockData }),
}));

import { getLingPyExport, getNEXUSExport, getCanonicalLexemesReport, getConceptAppendixExport, getConsolidatedNEXUSExport } from "../../api/client";

const mockCreateObjectURL = vi.fn(() => "blob:mock-url");
const mockRevokeObjectURL = vi.fn();
const mockClick = vi.fn();
const originalCreateElement = document.createElement.bind(document);

beforeEach(() => {
  mockData = {};
  vi.clearAllMocks();

  Object.defineProperty(URL, "createObjectURL", {
    value: mockCreateObjectURL,
    writable: true,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    value: mockRevokeObjectURL,
    writable: true,
  });

  vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
    if (tagName.toLowerCase() === "a") {
      const anchor = originalCreateElement("a") as HTMLAnchorElement;
      anchor.click = mockClick;
      return anchor;
    }
    return originalCreateElement(tagName);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useExport", () => {
  it("exportCSV triggers a browser download", () => {
    const { result } = renderHook(() => useExport());

    act(() => {
      result.current.exportCSV();
    });

    expect(mockCreateObjectURL).toHaveBeenCalledOnce();
    expect(mockClick).toHaveBeenCalledOnce();
  });

  it("exportCSV blob contains correct column headers: ID CONCEPT DOCULECT IPA COGID TOKENS BORROWING", () => {
    mockData = {
      water: {
        ipa_computed: { Fail01: "awa" },
      },
    };

    const OriginalBlob = globalThis.Blob;
    let capturedBlobParts: BlobPart[] = [];
    const blobSpy = vi
      .spyOn(globalThis, "Blob")
      .mockImplementation(((parts?: BlobPart[], options?: BlobPropertyBag) => {
        capturedBlobParts = parts ?? [];
        return new OriginalBlob(parts, options);
      }) as (blobParts?: BlobPart[], options?: BlobPropertyBag) => Blob);

    const { result } = renderHook(() => useExport());

    act(() => {
      result.current.exportCSV();
    });

    blobSpy.mockRestore();
    const text = String(capturedBlobParts[0] ?? "");
    expect(text.split("\n")[0]).toBe("ID\tCONCEPT\tDOCULECT\tIPA\tCOGID\tTOKENS\tBORROWING");
  });

  it("exportLingPyTSV calls client.ts getLingPyExport", async () => {
    const lingpyBlob = new Blob(["ID\tCONCEPT\n1\twater\n"], {
      type: "text/tab-separated-values",
    });
    vi.mocked(getLingPyExport).mockResolvedValueOnce(lingpyBlob);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.exportLingPyTSV();
    });

    expect(getLingPyExport).toHaveBeenCalledOnce();
    expect(mockCreateObjectURL).toHaveBeenCalledWith(lingpyBlob);
  });

  it("exportCanonicalLexemesReport calls client.ts getCanonicalLexemesReport and keeps the backend filename hint", async () => {
    const reportBlob = new Blob(["concept_id\tspeaker\n"], { type: "text/tab-separated-values" });
    vi.mocked(getCanonicalLexemesReport).mockResolvedValueOnce(reportBlob);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await (result.current as typeof result.current & { exportCanonicalLexemesReport: () => Promise<void> }).exportCanonicalLexemesReport();
    });

    expect(getCanonicalLexemesReport).toHaveBeenCalledOnce();
    expect(mockCreateObjectURL).toHaveBeenCalledWith(reportBlob);
    const anchor = vi.mocked(document.createElement).mock.results.find(
      (call) => call.type === "return" && (call.value as HTMLElement).tagName === "A",
    )?.value as HTMLAnchorElement | undefined;
    expect(anchor?.download).toBe("canonical-lexemes.tsv");
  });

  it("exportConceptAppendix forwards selected speakers and saves concept-appendix.md", async () => {
    const mdBlob = new Blob(["# Concept Appendix\n"], { type: "text/markdown" });
    vi.mocked(getConceptAppendixExport).mockResolvedValueOnce(mdBlob);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.exportConceptAppendix(["Fail01", "Kalh01"], ["1", "3"]);
    });

    expect(getConceptAppendixExport).toHaveBeenCalledWith({
      includeCognates: true,
      speakers: ["Fail01", "Kalh01"],
      conceptIds: ["1", "3"],
    });
    // No File System Access API in jsdom → saveBlob falls back to an anchor download.
    expect(mockCreateObjectURL).toHaveBeenCalledWith(mdBlob);
    const anchor = vi.mocked(document.createElement).mock.results.find(
      (call) => call.type === "return" && (call.value as HTMLElement).tagName === "A",
    )?.value as HTMLAnchorElement | undefined;
    expect(anchor?.download).toBe("concept-appendix.md");
  });

  it("exportConsolidatedNEXUS forwards the same selection and saves parse-cognates.nex", async () => {
    const nexBlob = new Blob(["#NEXUS\n"], { type: "text/plain" });
    vi.mocked(getConsolidatedNEXUSExport).mockResolvedValueOnce(nexBlob);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.exportConsolidatedNEXUS(["Fail01", "Kalh01"], ["1", "3"]);
    });

    expect(getConsolidatedNEXUSExport).toHaveBeenCalledWith({
      speakers: ["Fail01", "Kalh01"],
      conceptIds: ["1", "3"],
    });
    expect(mockCreateObjectURL).toHaveBeenCalledWith(nexBlob);
    const anchor = vi.mocked(document.createElement).mock.results.find(
      (call) => call.type === "return" && (call.value as HTMLElement).tagName === "A",
    )?.value as HTMLAnchorElement | undefined;
    expect(anchor?.download).toBe("parse-cognates.nex");
  });

  it("exportNEXUS calls client.ts getNEXUSExport", async () => {
    const nexusBlob = new Blob(["#NEXUS\n"], { type: "text/plain" });
    vi.mocked(getNEXUSExport).mockResolvedValueOnce(nexusBlob);

    const { result } = renderHook(() => useExport());

    await act(async () => {
      await result.current.exportNEXUS();
    });

    expect(getNEXUSExport).toHaveBeenCalledOnce();
    expect(mockCreateObjectURL).toHaveBeenCalledWith(nexusBlob);
  });
});
