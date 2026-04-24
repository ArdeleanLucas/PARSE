// Shared TypeScript types for PARSE API payloads.
// These mirror the Python backend data structures exactly.
// No component may import from the Python backend directly — always use client.ts.

export interface AnnotationInterval {
  start: number; // seconds — IMMUTABLE once written
  end: number; // seconds — IMMUTABLE once written
  text: string;
}

export interface OrthoWordInterval extends AnnotationInterval {
  confidence?: number;
  source?: "forced_align" | "short_clip_fallback";
}

export interface AnnotationTier {
  name: string;
  display_order: number;
  intervals: AnnotationInterval[];
}

/** A user-confirmed time range for a specific concept on a specific speaker.
 * Lives on AnnotationRecord.confirmed_anchors (sidecar — not inside tiers)
 * so it round-trips Praat/TextGrid cleanly; that format has no slot for
 * confidence or user-confirmation metadata. */
export interface ConfirmedAnchor {
  start: number;
  end: number;
  /** Human-readable provenance — e.g. "user+ortho_words", "manual". */
  source?: string;
  confirmed_at?: string;
  matched_text?: string;
  matched_variant?: string;
  variants_used?: string[];
}

export interface AnnotationRecord {
  speaker: string;
  tiers: Record<string, AnnotationTier>; // keys: ipa_phone, ipa, ortho, ortho_words, stt, concept, sentence, speaker
  /** Keyed by concept id (string). Seeded by the Search & Anchor Lexeme
   * flow; surfaces as cross-speaker signal in other speakers' searches. */
  confirmed_anchors?: Record<string, ConfirmedAnchor>;
  created_at?: string;
  modified_at?: string;
  source_wav?: string;
  /**
   * Project-relative path to the source audio, e.g. "audio/working/Fail02/foo.wav".
   * The Python server normalizer emits this key; `source_wav` is the historical
   * blank-record shape. Prefer `source_audio` when both exist.
   */
  source_audio?: string;
  source_audio_duration_sec?: number;
}

export interface SttSegment {
  start: number;
  end: number;
  text: string;
}

export interface SttSegmentsPayload {
  speaker: string;
  source_wav?: string;
  language?: string | null;
  segments: SttSegment[];
}

export interface ConceptEntry {
  id: string;
  label: string;
  survey_item?: string;
  custom_order?: number;
}

export interface ProjectConfig {
  project_name: string;
  language_code: string;
  speakers?: string[];
  concepts: ConceptEntry[];
  audio_dir: string;
  annotations_dir: string;
  schema_version?: number;
  [key: string]: unknown;
}

export type EnrichmentsPayload = Record<string, unknown>;

export interface Tag {
  id: string; // uuid
  label: string;
  color: string; // hex
  concepts: string[]; // concept ids that carry this tag (concept-level)
  /**
   * Per-lexeme tag targets, each encoded as `${speaker}::${conceptId}`.
   * A lexeme is the intersection of a concept + speaker; tagging a lexeme
   * only colours that speaker's form, not the whole concept row.
   */
  lexemeTargets?: string[];
}

export interface TagsResponse {
  tags: Tag[];
}

export interface LexemeNoteEntry {
  user_note?: string;
  import_note?: string;
  import_raw?: string;
  updated_at?: string;
}

export type LexemeNotesBySpeaker = Record<string, Record<string, LexemeNoteEntry>>;

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
  result?: string | Record<string, unknown>;
  error?: string;
  progress?: number;
  message?: string;
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
  /** Opaque result payload the backend attaches when a compute job
   *  completes (e.g. full_pipeline returns its per-step results here).
   *  Callers cast this to the specific type they expect for their
   *  compute_type — ``PipelineRunResult`` for ``full_pipeline``,
   *  raw objects for the legacy per-step computes. */
  result?: unknown;
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
