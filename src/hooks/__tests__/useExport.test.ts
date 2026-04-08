// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useExport } from "../useExport";

let mockData: Record<string, unknown> = {};

vi.mock("../../api/client", () => ({
  getLingPyExport: vi.fn(),
  getNEXUSExport: vi.fn(),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (state: { data: Record<string, unknown> }) => unknown) =>
    selector({ data: mockData }),
}));

import { getLingPyExport, getNEXUSExport } from "../../api/client";

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
