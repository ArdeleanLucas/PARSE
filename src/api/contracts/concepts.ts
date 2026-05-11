import type { ConceptEntry, ConceptSurveyLinkMutation, ConceptSurveyLinkResponse, ComputeJob, RelinkByGlossRequest, RelinkByGlossResponse } from "../types";
import { apiFetch } from "./shared";
import { startCompute } from "./chat-and-generic-compute";

export interface ConceptDuplicateResponse {
  primary: ConceptEntry;
  sibling: ConceptEntry;
}

/**
 * Duplicate a concept into A/B siblings.
 *
 * The backend renames the original row's `concept_en` from `X` to `X (A)`,
 * appends a new row `X (B)` with the same `source_item`/`source_survey`
 * and a fresh numeric id, then returns both rows. Throws on 409 ("concept
 * already part of an A/B pair") and other non-2xx codes — caller is
 * responsible for surfacing the error message.
 */
export async function duplicateConcept(conceptId: string): Promise<ConceptDuplicateResponse> {
  return apiFetch<ConceptDuplicateResponse>(
    `/api/concepts/${encodeURIComponent(conceptId)}/duplicate`,
    { method: "POST" },
  );
}


export async function setConceptSurveyLink(
  conceptIdOrList: string,
  payload: ConceptSurveyLinkMutation,
): Promise<ConceptSurveyLinkResponse> {
  return apiFetch<ConceptSurveyLinkResponse>(
    `/api/concepts/${encodeConceptIdOrList(conceptIdOrList)}/survey-links`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function deleteConceptSurveyLink(
  conceptIdOrList: string,
  payload: ConceptSurveyLinkMutation,
): Promise<ConceptSurveyLinkResponse> {
  return apiFetch<ConceptSurveyLinkResponse>(
    `/api/concepts/${encodeConceptIdOrList(conceptIdOrList)}/survey-links`,
    { method: "DELETE", body: JSON.stringify(payload) },
  );
}

function encodeConceptIdOrList(conceptIdOrList: string): string {
  return conceptIdOrList.split(",").map((part) => encodeURIComponent(part.trim())).join(",");
}

export async function relinkConceptsByGloss(
  payload: RelinkByGlossRequest = {},
): Promise<RelinkByGlossResponse> {
  return apiFetch<RelinkByGlossResponse>("/api/concepts/relink-by-gloss", {
    method: "POST",
    body: JSON.stringify({ apply: false, ...payload }),
  });
}


// === Tagged-concept queries (Lane A contract — see PR #321) ===

export type TagMatchMode = "any" | "all";

export interface ConceptHit {
  conceptId: string;
  name: string;
  start: number;
  end: number;
  tags: string[];
}

export interface PerSpeakerConceptHits {
  conceptCount: number;
  concepts: ConceptHit[];
}

export interface ConceptsByTagResponse {
  totalConcepts: number;
  perSpeaker: Record<string, PerSpeakerConceptHits>;
  unknownTags: string[];
  ambiguousTags: Record<string, string[]>;
}

export interface ConceptsByTagRequest {
  speakers: string[] | "all";
  tagLabels: string[];
  match?: TagMatchMode;
}

export async function getConceptsByTag(
  payload: ConceptsByTagRequest,
): Promise<ConceptsByTagResponse> {
  return apiFetch<ConceptsByTagResponse>("/api/concepts/by-tag", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type LexemeRerunByTagField = "ipa" | "ortho" | "both";

export interface LexemeRerunByTagRequest {
  speakers: string[] | "all";
  tagLabels: string[];
  match?: TagMatchMode;
  field: LexemeRerunByTagField;
  pad?: number;
}

export interface LexemeRerunByTagResultEntry {
  speaker: string;
  conceptId: string;
  field: "ipa" | "ortho";
  status: "ok" | "error" | "skip";
  text?: string;
  error?: string;
}

export interface LexemeRerunByTagResponse {
  jobId: string | null;
  resolved: ConceptsByTagResponse;
  total: number;
  results: LexemeRerunByTagResultEntry[];
}

export async function runLexemesByTag(
  payload: LexemeRerunByTagRequest,
): Promise<ComputeJob> {
  return startCompute("lexemes_rerun_by_tag", payload as unknown as Record<string, unknown>);
}
