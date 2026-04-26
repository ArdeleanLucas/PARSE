import type {
  ClefCatalogEntry,
  ClefConfigPayload,
  ClefConfigStatus,
  ClefProviderEntry,
  ClefSourcesReport,
  ComputeJob,
  ContactLexemeCoverage,
  ContactLexemeFetchOptions,
} from "../types";
import { startCompute } from "./chat-and-generic-compute";
import { apiFetch } from "./shared";

export async function getContactLexemeCoverage(): Promise<ContactLexemeCoverage> {
  return apiFetch<ContactLexemeCoverage>("/api/contact-lexemes/coverage");
}

export async function startContactLexemeFetch(
  options: ContactLexemeFetchOptions = {},
): Promise<ComputeJob> {
  return startCompute("contact-lexemes", options as Record<string, unknown>);
}

export async function getClefConfig(): Promise<ClefConfigStatus> {
  return apiFetch<ClefConfigStatus>("/api/clef/config");
}

export async function saveClefConfig(
  payload: ClefConfigPayload,
): Promise<{ success: boolean; config_path: string; primary_contact_languages: string[]; language_count: number }> {
  return apiFetch("/api/clef/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getClefCatalog(): Promise<{ languages: ClefCatalogEntry[] }> {
  return apiFetch<{ languages: ClefCatalogEntry[] }>("/api/clef/catalog");
}

export async function getClefProviders(): Promise<{ providers: ClefProviderEntry[] }> {
  return apiFetch<{ providers: ClefProviderEntry[] }>("/api/clef/providers");
}

export async function getClefSourcesReport(): Promise<ClefSourcesReport> {
  return apiFetch<ClefSourcesReport>("/api/clef/sources-report");
}

export async function saveClefFormSelections(payload: {
  concept_en: string;
  lang_code: string;
  forms: string[];
}): Promise<{ success: boolean; concept_en: string; lang_code: string; forms: string[] }> {
  return apiFetch("/api/clef/form-selections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
