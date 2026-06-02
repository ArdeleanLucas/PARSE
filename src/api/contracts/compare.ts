import type {
  CanonicalLexemeDeleteResponse,
  CanonicalLexemePutRequest,
  CanonicalLexemePutResponse,
  CompareBundlesResponse,
  ConceptIdentityResponse,
} from "../types";
import { apiFetch } from "./shared";

export interface CompareBundlesQuery {
  speaker?: string;
  bundleId?: string;
}

function queryString(query: CompareBundlesQuery = {}): string {
  const params = new URLSearchParams();
  if (query.speaker) params.set("speaker", query.speaker);
  if (query.bundleId) params.set("bundle_id", query.bundleId);
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function getCompareBundles(query: CompareBundlesQuery = {}): Promise<CompareBundlesResponse> {
  // Spec source: MC-368-A audit lane-1 examples; MC-368-B OpenAPI was not present on origin/main at implementation time.
  return apiFetch<CompareBundlesResponse>(`/api/compare/bundles${queryString(query)}`);
}

export async function getConceptIdentity(): Promise<ConceptIdentityResponse> {
  return apiFetch<ConceptIdentityResponse>("/api/concept-identity");
}

export async function putCanonicalLexeme(
  bundleId: string,
  speaker: string,
  payload: CanonicalLexemePutRequest,
): Promise<CanonicalLexemePutResponse> {
  return apiFetch<CanonicalLexemePutResponse>(
    `/api/compare/canonical-lexemes/${encodeURIComponent(bundleId)}/${encodeURIComponent(speaker)}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export async function deleteCanonicalLexeme(
  bundleId: string,
  speaker: string,
): Promise<CanonicalLexemeDeleteResponse> {
  return apiFetch<CanonicalLexemeDeleteResponse>(
    `/api/compare/canonical-lexemes/${encodeURIComponent(bundleId)}/${encodeURIComponent(speaker)}`,
    { method: "DELETE" },
  );
}
