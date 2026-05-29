import { apiFetch } from "./shared";

export interface SpeakerDeleteResponse {
  ok: boolean;
  speaker: string;
  trashDir: string;
  movedFiles: string[];
  prunedRegistry: string[];
}

export async function deleteSpeaker(speaker: string): Promise<SpeakerDeleteResponse> {
  return apiFetch<SpeakerDeleteResponse>(
    `/api/speakers/${encodeURIComponent(speaker)}`,
    { method: "DELETE" },
  );
}
