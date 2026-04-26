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
