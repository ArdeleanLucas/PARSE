// Shared TypeScript types for PARSE API payloads.
// These mirror the Python backend data structures exactly.
// No component may import from the Python backend directly — always use client.ts.

export interface AnnotationInterval {
  start: number; // seconds — IMMUTABLE once written
  end: number; // seconds — IMMUTABLE once written
  text: string;
}

export interface AnnotationTier {
  name: string;
  display_order: number;
  intervals: AnnotationInterval[];
}

export interface AnnotationRecord {
  speaker: string;
  tiers: Record<string, AnnotationTier>; // keys: ipa, ortho, concept, speaker
  created_at: string;
  modified_at: string;
  source_wav: string;
}

export interface ConceptEntry {
  id: string;
  label: string;
}

export interface ProjectConfig {
  project_name: string;
  language_code: string;
  speakers?: string[];
  concepts: ConceptEntry[];
  audio_dir: string;
  annotations_dir: string;
  [key: string]: unknown;
}

export type EnrichmentsPayload = Record<string, unknown>;

export interface Tag {
  id: string; // uuid
  label: string;
  color: string; // hex
  concepts: string[]; // concept ids that carry this tag
}

export interface AuthStatus {
  authenticated: boolean;
  provider?: string;
  method?: "api_key" | "oauth";
  flow_active?: boolean;
  user_code?: string;
  verification_uri?: string;
}

export interface STTJob {
  job_id: string;
  jobId?: string;
}

export interface STTStatus {
  status: string;
  progress: number;
  segments: unknown[];
}

export interface ChatJob {
  job_id: string;
  jobId?: string;
}

export interface ChatStatus {
  status: string;
  result?: string;
}

export interface ComputeJob {
  job_id: string;
  jobId?: string;
}

export interface ComputeStatus {
  status: string;
  progress: number;
  message?: string;
  error?: string;
}

export interface ContactLexemeCoverage {
  languages: Record<string, {
    name: string;
    total: number;
    filled: number;
    empty: number;
    concepts: Record<string, string[]>;
  }>;
}

export interface ContactLexemeFetchOptions {
  providers?: string[];
  languages?: string[];
  overwrite?: boolean;
}
