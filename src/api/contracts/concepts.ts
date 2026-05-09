import type { ConceptEntry, ConceptSurveyLinkMutation, ConceptSurveyLinkResponse, RelinkByGlossRequest, RelinkByGlossResponse } from "../types";
import { apiFetch } from "./shared";

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
  conceptId: string,
  payload: ConceptSurveyLinkMutation,
): Promise<ConceptSurveyLinkResponse> {
  return apiFetch<ConceptSurveyLinkResponse>(
    `/api/concepts/${encodeURIComponent(conceptId)}/survey-links`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function deleteConceptSurveyLink(
  conceptId: string,
  payload: ConceptSurveyLinkMutation,
): Promise<ConceptSurveyLinkResponse> {
  return apiFetch<ConceptSurveyLinkResponse>(
    `/api/concepts/${encodeURIComponent(conceptId)}/survey-links`,
    { method: "DELETE", body: JSON.stringify(payload) },
  );
}

export async function relinkConceptsByGloss(
  payload: RelinkByGlossRequest = {},
): Promise<RelinkByGlossResponse> {
  return apiFetch<RelinkByGlossResponse>("/api/concepts/relink-by-gloss", {
    method: "POST",
    body: JSON.stringify({ apply: false, ...payload }),
  });
}
