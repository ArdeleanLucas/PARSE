// Shared TypeScript types for PARSE API payloads.
// These mirror the Python backend data structures exactly.
// No component may import from the Python backend directly — always use client.ts.

export interface AnnotationInterval {
  start: number; // seconds — IMMUTABLE once written
  end: number; // seconds — IMMUTABLE once written
  text: string;
  /** True once the user has manually set this lexeme's timing — via direct
   * start/end edit, or by capturing a manual-anchor offset pair for it.
   * Global offset application skips flagged intervals so previously-fixed
   * timings don't get shifted again. Persisted in the annotation JSON. */
  manuallyAdjusted?: boolean;
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

export interface SttWord {
  word: string;
  start: number;
  end: number;
  prob?: number;
}

export interface SttSegment {
  start: number;
  end: number;
  text: string;
  /** Optional Tier 1 word-level boundaries from faster-whisper word_timestamps.
   * Already returned by `/api/stt-segments/<speaker>`; previously stripped from
   * the type. Consumed by the Boundaries lane to compare Tier 1 vs Tier 2
   * (forced-aligned) word boundaries. */
  words?: SttWord[];
}

export interface SttSegmentsPayload {
  speaker: string;
  source_wav?: string;
  language?: string | null;
  segments: SttSegment[];
  /** Provenance marker for the cached STT payload. Set to
   * ``"boundary_constrained"`` when the cache was populated by the
   * BND-anchored re-transcription flow instead of vanilla STT. */
  source?: string;
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
  /** Full Python traceback captured by the worker when the job errored.
   *  Present on terminal-error snapshots only; the UI renders it in the
   *  crash-log modal alongside the short ``error`` message. */
  traceback?: string;
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

export interface ContactLexemePopulateResult {
  filled: Record<string, number>;
  total_filled: number;
  warning?: string | null;
  warnings?: string[];
}

export interface ClefLanguageEntry {
  code: string;
  name: string;
  family?: string | null;
  /** Optional ISO 15924 script code (Arab, Latn, Hebr, Cyrl, Grek, ...).
   *  Drives deterministic script-vs-IPA routing in the Reference Forms
   *  panel; absent values fall back to the Unicode-block heuristic in
   *  ``classifyRawFormString``. */
  script?: string | null;
  filled?: number;
  total?: number;
}

export interface ClefConfigStatus {
  configured: boolean;
  primary_contact_languages: string[];
  languages: ClefLanguageEntry[];
  config_path: string;
  concepts_csv_exists: boolean;
  meta: Record<string, unknown>;
}

export interface ClefCatalogEntry {
  code: string;
  name: string;
  family?: string;
  /** ISO 15924 script code (e.g. "Arab", "Latn"). When present, the
   *  Reference Forms panel uses this to route bare strings instead of
   *  guessing from Unicode blocks. */
  script?: string;
}

export interface ClefProviderEntry {
  id: string;
  name: string;
}

export interface ClefConfigPayload {
  primary_contact_languages: string[];
  languages: Array<{ code: string; name: string; family?: string; script?: string }>;
}

/** One form in the Sources Report, annotated with the provider(s) that
 *  contributed it. ``sources`` contains one or more provider ids
 *  (``wikidata``, ``asjp``, ...). Legacy data predating provenance is
 *  surfaced with the single sentinel source ``"unknown"``. */
export interface ClefSourcesReportForm {
  concept_en: string;
  form: string;
  sources: string[];
}

/** Per-language slice of the Sources Report. ``per_provider`` totals
 *  are computed over ``forms`` for convenience so the modal can render
 *  a summary bar without re-aggregating client-side. */
export interface ClefSourcesReportLanguage {
  code: string;
  name: string;
  family: string | null;
  /** ISO 15924 script code (Arab, Latn, ...) when known. Optional
   *  metadata, mostly informational for the Sources Report header. */
  script?: string | null;
  total_forms: number;
  concepts_covered: number;
  concepts_total: number;
  per_provider: Record<string, number>;
  forms: ClefSourcesReportForm[];
}

/** Academic citation block for one provider id, surfaced by the Sources
 *  Report endpoint so the modal can render full bibliographic references
 *  alongside each provider chip. Citations are *dataset-level* -- per-form
 *  metadata (URL, dataset version, retrieval date) is a follow-up change
 *  that requires extending the FetchResult shape across all providers.
 *
 *  ``type`` lets the modal flag entries differently:
 *    - "dataset" / "tool" -> standard provider, render normally
 *    - "ai"               -> LLM, show a "must be verified" warning
 *    - "manual"           -> user-curated, point at the workspace config
 *    - "sentinel"         -> "unknown" legacy entry, render as caveat */
export interface ClefSourceCitation {
  label: string;
  type: "dataset" | "tool" | "ai" | "manual" | "sentinel";
  authors: string | null;
  year: number | null;
  title: string;
  venue?: string;
  doi?: string;
  url?: string;
  license?: string;
  note?: string;
  /** Free-text citation suitable for pasting into a footnote. */
  citation: string;
  /** BibTeX entry suitable for an ``Export BibTeX`` action. Empty
   *  string for non-bibliographic providers (LLM, manual overrides). */
  bibtex: string;
}

export interface ClefSourcesReport {
  generated_at: string;
  providers: Array<{ id: string; total_forms: number }>;
  languages: ClefSourcesReportLanguage[];
  concepts_total: number;
  /** Per-provider citation blocks keyed by provider id. Includes the
   *  ``unknown`` sentinel for legacy entries. */
  citations: Record<string, ClefSourceCitation>;
  /** Stable display order for the citations section -- matches
   *  ``CITATION_DISPLAY_ORDER`` in the backend. */
  citation_order: string[];
}
