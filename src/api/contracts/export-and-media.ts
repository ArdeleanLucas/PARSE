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

function normalizeWorkspaceAudioPath(value: string): string {
  return value.trim().replace(/\\/g, "/").replace(/^\/+/, "");
}

function isLikelyProjectRelativeAudioPath(value: string): boolean {
  return normalizeWorkspaceAudioPath(value).includes("/");
}

export function spectrogramUrl(params: {
  speaker: string;
  startSec: number;
  endSec: number;
  audio?: string | null;
  force?: boolean;
}): string {
  const search = new URLSearchParams({
    speaker: params.speaker,
    start: params.startSec.toFixed(3),
    end: params.endSec.toFixed(3),
  });
  const audio = normalizeWorkspaceAudioPath(params.audio ?? "");
  if (audio && isLikelyProjectRelativeAudioPath(audio)) search.set("audio", audio);
  if (params.force) search.set("force", "1");
  return `/api/spectrogram?${search.toString()}`;
}

/** Resolve a workspace-relative source_wav (e.g. "audio/working/Fail01.wav")
 *  to an HTTP URL the browser can fetch. The PARSE server serves files at
 *  workspace-root-relative paths directly, so this is just normalisation:
 *  strip leading slashes/backslashes, re-prefix with "/". If only a basename
 *  is available and the speaker is known, fall back to PARSE's normalized
 *  working-audio convention. Returns "" when the input is empty. Used by
 *  compare-mode SpeakerFormsTable for HTMLAudio scoped playback (no
 *  playback-store coupling). */
export function mediaUrlFromSourceWav(
  sourceWav: string | null | undefined,
  options: { speaker?: string | null } = {},
): string {
  const raw = (sourceWav ?? "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  const cleaned = normalizeWorkspaceAudioPath(raw);
  const speaker = (options.speaker ?? "").trim();
  if (cleaned && !cleaned.includes("/") && speaker) {
    return `/audio/working/${encodeURIComponent(speaker)}/${encodeURIComponent(cleaned)}`;
  }
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
