import type { EnrichmentsPayload, Tag, TagsResponse } from "../types";
import { apiFetch, networkError, unwrapEnrichments } from "./shared";

export async function getEnrichments(): Promise<EnrichmentsPayload> {
  const payload = await apiFetch<unknown>("/api/enrichments");
  return unwrapEnrichments(payload);
}

export async function saveEnrichments(data: EnrichmentsPayload): Promise<void> {
  await apiFetch<void>("/api/enrichments", {
    method: "POST",
    body: JSON.stringify({ enrichments: data }),
  });
}

export interface ImportConceptsResult {
  ok: boolean;
  matched: number;
  added: number;
  total: number;
  mode: "merge" | "replace";
}

export async function importConceptsCsv(
  file: File,
  mode: "merge" | "replace" = "merge",
): Promise<ImportConceptsResult> {
  const form = new FormData();
  form.append("csv", file);
  form.append("mode", mode);
  let response: Response;
  try {
    response = await fetch("/api/concepts/import", { method: "POST", body: form });
  } catch (error) {
    throw networkError("/api/concepts/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/concepts/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportConceptsResult>;
}

export interface ImportTagCsvResult {
  ok: boolean;
  tagId: string;
  tagName: string;
  color: string;
  matchedCount: number;
  missedCount: number;
  missedLabels: string[];
  totalTagsInFile: number;
}

export async function importTagCsv(
  file: File,
  options: { tagName?: string; color?: string } = {},
): Promise<ImportTagCsvResult> {
  const form = new FormData();
  form.append("csv", file);
  if (options.tagName) form.append("tagName", options.tagName);
  if (options.color) form.append("color", options.color);
  let response: Response;
  try {
    response = await fetch("/api/tags/import", { method: "POST", body: form });
  } catch (error) {
    throw networkError("/api/tags/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/tags/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportTagCsvResult>;
}

export async function getTags(): Promise<TagsResponse> {
  return apiFetch<TagsResponse>("/api/tags");
}

export async function mergeTags(tags: Tag[]): Promise<{ ok: boolean; tagCount: number }> {
  return apiFetch<{ ok: boolean; tagCount: number }>("/api/tags/merge", {
    method: "POST",
    body: JSON.stringify({ tags }),
  });
}

export interface SaveLexemeNoteBody {
  speaker: string;
  concept_id: string;
  user_note?: string;
  import_note?: string;
  delete?: boolean;
}

export async function saveLexemeNote(
  body: SaveLexemeNoteBody,
): Promise<{ success: boolean; lexeme_notes?: Record<string, Record<string, Record<string, unknown>>> }> {
  return apiFetch<{
    success: boolean;
    lexeme_notes?: Record<string, Record<string, Record<string, unknown>>>;
  }>("/api/lexeme-notes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ImportCommentsCsvResponse {
  success: boolean;
  speaker: string;
  total_rows: number;
  imported: number;
  matched: number;
  lexeme_notes?: Record<string, Record<string, Record<string, unknown>>>;
}

export async function importCommentsCsv(
  speakerId: string,
  csvFile: File,
): Promise<ImportCommentsCsvResponse> {
  const formData = new FormData();
  formData.append("speaker_id", speakerId);
  formData.append("csv", csvFile);
  let response: Response;
  try {
    response = await fetch("/api/lexeme-notes/import", { method: "POST", body: formData });
  } catch (error) {
    throw networkError("/api/lexeme-notes/import", { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST /api/lexeme-notes/import failed ${response.status}: ${text}`);
  }
  return response.json() as Promise<ImportCommentsCsvResponse>;
}
