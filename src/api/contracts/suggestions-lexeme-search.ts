import { apiFetch, isRecord } from "./shared";

export interface LexemeSearchCandidate {
  start: number;
  end: number;
  tier: "ortho_words" | "ortho" | "stt" | "ipa";
  matched_text: string;
  matched_variant: string;
  score: number;
  phonetic_score: number;
  cross_speaker_score: number;
  confidence_weight: number;
  source_label: string;
}

export interface LexemeSearchResponse {
  speaker: string;
  concept_id: string | null;
  variants: string[];
  language: string;
  candidates: LexemeSearchCandidate[];
  signals_available: {
    phonemizer: boolean;
    cross_speaker_anchors: number;
    contact_variants: string[];
  };
}

export interface LexemeSearchOptions {
  conceptId?: string;
  language?: string;
  tiers?: string[];
  limit?: number;
  maxDistance?: number;
}

export async function searchLexeme(
  speaker: string,
  variants: string[],
  options: LexemeSearchOptions = {},
): Promise<LexemeSearchResponse> {
  const params = new URLSearchParams();
  params.set("speaker", speaker);
  params.set("variants", variants.join(","));
  if (options.conceptId) params.set("concept_id", options.conceptId);
  if (options.language) params.set("language", options.language);
  if (options.tiers && options.tiers.length > 0) params.set("tiers", options.tiers.join(","));
  if (options.limit) params.set("limit", String(options.limit));
  if (options.maxDistance != null) params.set("max_distance", String(options.maxDistance));
  return apiFetch<LexemeSearchResponse>(`/api/lexeme/search?${params.toString()}`);
}

function unwrapSuggestions(payload: unknown): unknown[] {
  if (isRecord(payload) && Array.isArray(payload.suggestions)) {
    return payload.suggestions;
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  return [];
}

export async function requestSuggestions(
  speaker: string,
  conceptIds: string[],
): Promise<unknown[]> {
  const payload = await apiFetch<unknown>("/api/suggest", {
    method: "POST",
    body: JSON.stringify({ speaker, concept_ids: conceptIds }),
  });
  return unwrapSuggestions(payload);
}
