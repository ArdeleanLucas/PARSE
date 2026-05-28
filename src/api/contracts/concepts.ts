import type {
  ConceptPromoteSurveyPrimaryRequest,
  ConceptPromoteSurveyPrimaryResponse,
  ConceptSurveyLinkMutation,
  ConceptSurveyLinkResponse,
  ComputeJob,
  RelinkByGlossRequest,
  RelinkByGlossResponse,
} from "../types";
import { apiFetch } from "./shared";
import { startCompute } from "./chat-and-generic-compute";

export interface ConceptDeleteResponse {
  ok: true;
  deleted_id: string;
}

export interface ConceptDeleteConflict {
  error: string;
  blocking_speakers: string[];
}

export interface AnnotationIntervalDeleteRequest {
  speaker: string;
  concept_id: string;
  start: number;
  end: number;
}

export interface AnnotationIntervalDeleteResponse {
  ok: true;
  speaker: string;
  concept_id: string;
  start: number;
  end: number;
  removed: Record<"concept" | "ipa" | "ortho" | "ortho_words" | "speaker", number>;
  backup_path: string;
  tolerance_sec: number;
}

export async function deleteAnnotationInterval(
  payload: AnnotationIntervalDeleteRequest,
): Promise<AnnotationIntervalDeleteResponse> {
  return apiFetch<AnnotationIntervalDeleteResponse>(
    "/api/annotations/intervals/delete",
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function deleteConcept(conceptId: string): Promise<ConceptDeleteResponse> {
  return apiFetch<ConceptDeleteResponse>(
    `/api/concepts/${encodeURIComponent(conceptId)}`,
    { method: "DELETE" },
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

export async function promoteConceptSurveyPrimary(
  conceptId: string,
  payload: ConceptPromoteSurveyPrimaryRequest,
): Promise<ConceptPromoteSurveyPrimaryResponse> {
  return apiFetch<ConceptPromoteSurveyPrimaryResponse>(
    `/api/concepts/${encodeURIComponent(conceptId)}/promote-survey-primary`,
    { method: "POST", body: JSON.stringify(payload) },
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
