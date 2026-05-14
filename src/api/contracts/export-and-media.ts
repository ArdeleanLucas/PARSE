export async function getLingPyExport(): Promise<Blob> {
  const response = await fetch("/api/export/lingpy", {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/lingpy failed ${response.status}: ${text}`);
  }
  return response.blob();
}

export function spectrogramUrl(params: {
  speaker: string;
  startSec: number;
  endSec: number;
  audio?: string;
  force?: boolean;
}): string {
  const search = new URLSearchParams({
    speaker: params.speaker,
    start: params.startSec.toFixed(3),
    end: params.endSec.toFixed(3),
  });
  if (params.audio) search.set("audio", params.audio);
  if (params.force) search.set("force", "1");
  return `/api/spectrogram?${search.toString()}`;
}

/** Resolve a workspace-relative source_wav (e.g. "audio/working/Fail01.wav")
 *  to an HTTP URL the browser can fetch. The PARSE server serves files at
 *  workspace-root-relative paths directly, so this is just normalisation:
 *  strip leading slashes/backslashes, re-prefix with "/". Returns "" when
 *  the input is empty. Used by compare-mode SpeakerFormsTable for HTMLAudio
 *  scoped playback (no playback-store coupling). */
export function mediaUrlFromSourceWav(sourceWav: string | null | undefined): string {
  const raw = (sourceWav ?? "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  const cleaned = raw.replace(/\\/g, "/").replace(/^\/+/, "");
  return `/${cleaned}`;
}

export async function getNEXUSExport(): Promise<Blob> {
  const response = await fetch("/api/export/nexus", {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/export/nexus failed ${response.status}: ${text}`);
  }
  return response.blob();
}

export async function getCanonicalLexemesReport(): Promise<Blob> {
  const response = await fetch("/api/exports/canonical-lexemes-report", {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`GET /api/exports/canonical-lexemes-report failed ${response.status}: ${text}`);
  }
  return response.blob();
}
