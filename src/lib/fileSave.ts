// File-save helper that prefers a native "Save As" folder/filename picker (File
// System Access API, Chromium browsers) and falls back to a normal anchor
// download (Firefox/Safari, or when the picker is unavailable or fails).
//
// `window.showSaveFilePicker` is not part of the standard DOM lib types, so the
// minimal subset we use is declared locally and accessed through a guarded cast.

interface FsSaveFilePickerOptions {
  suggestedName?: string;
  types?: Array<{ description?: string; accept: Record<string, string[]> }>;
}

interface FsWritableFileStream {
  write(data: Blob): Promise<void>;
  close(): Promise<void>;
}

interface FsSaveFileHandle {
  createWritable(): Promise<FsWritableFileStream>;
}

type ShowSaveFilePicker = (options?: FsSaveFilePickerOptions) => Promise<FsSaveFileHandle>;

function getSaveFilePicker(): ShowSaveFilePicker | null {
  const candidate = (window as unknown as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  return typeof candidate === "function" ? (candidate as ShowSaveFilePicker) : null;
}

function downloadViaAnchor(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/**
 * Save `blob` as `filename`. On browsers with the File System Access API this
 * opens a native dialog so the user picks the destination folder and name; if
 * the user cancels, nothing is written. Everywhere else (or on picker error) it
 * falls back to a standard download into the browser's Downloads folder.
 */
export async function saveBlob(
  blob: Blob,
  filename: string,
  options: { mimeType?: string } = {},
): Promise<void> {
  const picker = getSaveFilePicker();
  if (picker) {
    const extension = filename.includes(".") ? filename.slice(filename.lastIndexOf(".")) : "";
    const types = extension
      ? [{ accept: { [options.mimeType ?? "application/octet-stream"]: [extension] } }]
      : undefined;
    try {
      const handle = await picker({ suggestedName: filename, types });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      // User dismissed the picker — treat as a no-op, not an error.
      if (err instanceof DOMException && err.name === "AbortError") return;
      // Any other failure (permissions, unsupported) falls back to a download.
    }
  }
  downloadViaAnchor(blob, filename);
}
