// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { saveBlob } from "../fileSave";

const originalCreateElement = document.createElement.bind(document);

beforeEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:mock"), writable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true });
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as { showSaveFilePicker?: unknown }).showSaveFilePicker;
});

describe("saveBlob", () => {
  it("uses the File System Access picker when available, writing the blob to the chosen handle", async () => {
    const write = vi.fn(async () => {});
    const close = vi.fn(async () => {});
    const createWritable = vi.fn(async () => ({ write, close }));
    const showSaveFilePicker = vi.fn(
      async (_opts?: { suggestedName?: string; types?: unknown[] }) => ({ createWritable }),
    );
    (window as unknown as { showSaveFilePicker: unknown }).showSaveFilePicker = showSaveFilePicker;

    const blob = new Blob(["# md"], { type: "text/markdown" });
    await saveBlob(blob, "concept-appendix.md", { mimeType: "text/markdown" });

    expect(showSaveFilePicker).toHaveBeenCalledOnce();
    const opts = showSaveFilePicker.mock.calls[0][0];
    expect(opts?.suggestedName).toBe("concept-appendix.md");
    expect(opts?.types).toEqual([{ accept: { "text/markdown": [".md"] } }]);
    expect(write).toHaveBeenCalledWith(blob);
    expect(close).toHaveBeenCalledOnce();
  });

  it("treats picker cancellation (AbortError) as a no-op without falling back to a download", async () => {
    const showSaveFilePicker = vi.fn(async () => {
      throw new DOMException("cancelled", "AbortError");
    });
    (window as unknown as { showSaveFilePicker: unknown }).showSaveFilePicker = showSaveFilePicker;
    const clickSpy = vi.spyOn(document, "createElement");

    await saveBlob(new Blob(["x"]), "concept-appendix.md");

    expect(showSaveFilePicker).toHaveBeenCalledOnce();
    expect(clickSpy).not.toHaveBeenCalledWith("a");
  });

  it("falls back to an anchor download when the picker is unavailable", async () => {
    const click = vi.fn();
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag.toLowerCase() === "a") {
        const a = originalCreateElement("a") as HTMLAnchorElement;
        a.click = click;
        return a;
      }
      return originalCreateElement(tag);
    });

    await saveBlob(new Blob(["x"]), "concept-appendix.md");

    expect(click).toHaveBeenCalledOnce();
  });
});
