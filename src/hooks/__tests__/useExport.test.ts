// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useExport } from "../useExport";

vi.mock("../../api/client", () => ({
  getLingPyExport: vi.fn(),
  getNEXUSExport: vi.fn(),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: vi.fn((sel: (s: { data: Record<string, unknown> }) => unknown) =>
    sel({ data: {} })
  ),
}));

const mockCreateObjectURL = vi.fn(() => "blob:mock-url");
const mockRevokeObjectURL = vi.fn();
Object.defineProperty(URL, "createObjectURL", { value: mockCreateObjectURL, writable: true });
Object.defineProperty(URL, "revokeObjectURL", { value: mockRevokeObjectURL, writable: true });

const mockClick = vi.fn();
const origCreateElement = document.createElement.bind(document);
vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
  if (tag === "a") {
    const el = origCreateElement("a") as HTMLAnchorElement;
    el.click = mockClick;
    return el;
  }
  return origCreateElement(tag);
});

import { getLingPyExport, getNEXUSExport } from "../../api/client";

describe("useExport", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { vi.clearAllMocks(); });

  it("exportCSV triggers a browser download", () => {
    const { result } = renderHook(() => useExport());
    act(() => { result.current.exportCSV(); });
    expect(mockCreateObjectURL).toHaveBeenCalled();
    expect(mockClick).toHaveBeenCalled();
  });

  it("exportCSV blob contains correct column headers: ID DOCULECT CONCEPT IPA COGID TOKENS NOTE", () => {
    let capturedParts: BlobPart[] = [];
    const OrigBlob = globalThis.Blob;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).Blob = function (parts?: BlobPart[]) { capturedParts = parts ?? []; return new OrigBlob(parts); };
    try {
    const { result } = renderHook(() => useExport());
    act(() => { result.current.exportCSV(); });
    const text = String(capturedParts[0] ?? "");
    expect(text.split("\n")[0]).toBe("ID\tDOCULECT\tCONCEPT\tIPA\tCOGID\tTOKENS\tNOTE");
    } finally { globalThis.Blob = OrigBlob; }
  });

  it("exportLingPyTSV calls client.ts getLingPyExport", async () => {
    const mockBlob = new Blob(["ID\tDOCULECT\n"], { type: "text/tab-separated-values" });
    vi.mocked(getLingPyExport).mockResolvedValueOnce(mockBlob);
    const { result } = renderHook(() => useExport());
    await act(async () => { await result.current.exportLingPyTSV(); });
    expect(getLingPyExport).toHaveBeenCalledOnce();
    expect(mockCreateObjectURL).toHaveBeenCalledWith(mockBlob);
  });

  it("exportNEXUS calls client.ts getNEXUSExport", async () => {
    const mockBlob = new Blob(["#NEXUS\n"], { type: "text/plain" });
    vi.mocked(getNEXUSExport).mockResolvedValueOnce(mockBlob);
    const { result } = renderHook(() => useExport());
    await act(async () => { await result.current.exportNEXUS(); });
    expect(getNEXUSExport).toHaveBeenCalledOnce();
    expect(mockCreateObjectURL).toHaveBeenCalledWith(mockBlob);
  });
});
