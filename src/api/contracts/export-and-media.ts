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

/** Build the per-concept markdown appendix (forms + cognate decisions) via the
 *  `export_concept_appendix_md` MCP tool and return it as a downloadable Blob.
 *  Runs the tool with no outputPath so the full markdown is returned in the
 *  response envelope rather than written server-side. */
export async function getConceptAppendixExport(
  options: { includeCognates?: boolean; tagId?: string; speakers?: string[] } = {},
): Promise<Blob> {
  const body: Record<string, unknown> = {
    includeCognates: options.includeCognates ?? true,
  };
  if (options.tagId) body.tagId = options.tagId;
  if (options.speakers && options.speakers.length > 0) body.speakers = options.speakers;
  // mode=default serves the full *safe* MCP surface (read + curated writes), which always
  // includes this first-party export tool — unlike mode=active, which honors the workspace's
  // external-client curation (config/mcp_config.json expose_all_tools=false → curated subset).
  const response = await fetch("/api/mcp/tools/export_concept_appendix_md?mode=default", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`POST /api/mcp/tools/export_concept_appendix_md failed ${response.status}: ${text}`);
  }
  const envelope = (await response.json()) as { ok?: boolean; result?: { markdown?: unknown } };
  const markdown = envelope?.result?.markdown;
  if (typeof markdown !== "string") {
    throw new Error("Concept appendix export returned no markdown");
  }
  return new Blob([markdown], { type: "text/markdown;charset=utf-8" });
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
