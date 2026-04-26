import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  Search, ChevronLeft, ChevronRight, Check, Flag, Split, GitMerge,
  RotateCw, Save, Upload,
  Layers, ChevronDown, ChevronUp, X, AlertCircle,
  ArrowUpDown, Volume2,
  Loader2,
  Tags, Import, AudioLines, Type, Mic,
  Workflow, Network, Trash2, ChevronDown as CDown,
  Download,
  Anchor,
  Sun, Moon, XCircle,
} from 'lucide-react';
import type { AnnotationInterval, AnnotationRecord, Tag as StoreTag } from './api/types';
import { startCompute, pollCompute, detectTimestampOffset, detectTimestampOffsetFromPairs, applyTimestampOffset, searchLexeme, pollOffsetDetectJob, getJobLogs } from './api/client';
import type { JobLogsPayload } from './api/client';
import type { LexemeSearchCandidate } from './api/client';
import { useChatSession } from './hooks/useChatSession';
import { useOffsetState } from './hooks/useOffsetState';
import { compareSurveyKeys } from './lib/surveySort';
import {
  applyCanonicalDecisionImport,
  buildCanonicalDecisionPayload,
  buildCognateDecisionPatch,
  getStoredCognateDecision,
  PARSE_DECISIONS_FILE_NAME,
  type CognateDecisionValue,
} from './lib/decisionPersistence';
import { useAnnotationStore } from './stores/annotationStore';
import { useTranscriptionLanesStore, type LaneKind } from './stores/transcriptionLanesStore';
import { LaneColorPicker } from './components/annotate/LaneColorPicker';
import { useAnnotationSync } from './hooks/useAnnotationSync';
import { useComputeJob } from './hooks/useComputeJob';
import { useActionJob, formatEta } from './hooks/useActionJob';
import { useExport } from './hooks/useExport';
import { useTagImport } from './hooks/useTagImport';
import { listActiveJobs } from './api/client';
import { useConfigStore } from './stores/configStore';
import { useEnrichmentStore } from './stores/enrichmentStore';
import { usePlaybackStore } from './stores/playbackStore';
import { useTagStore } from './stores/tagStore';
import { useUIStore } from './stores/uiStore';
import { Modal } from './components/shared/Modal';
import {
  TranscriptionRunModal,
  type TranscriptionRunConfirm,
  type PipelineStepId,
} from './components/shared/TranscriptionRunModal';
import { BatchReportModal } from './components/shared/BatchReportModal';
import { useBatchPipelineJob } from './hooks/useBatchPipelineJob';
import { LexemeDetail } from './components/compare/LexemeDetail';
import { CommentsImport } from './components/compare/CommentsImport';
import { SpeakerImport } from './components/compare/SpeakerImport';
import { ManageTagsView } from './components/compare/ManageTagsView';
import { CognateCell, SimBar } from './components/compare/CognateCell';
import { Pill, SectionCard } from './components/compare/UIPrimitives';
import { AnnotateView } from './components/annotate/AnnotateView';
import { ClefConfigModal, type ClefConfigModalTab } from './components/compute/ClefConfigModal';
import { ClefPopulateSummaryBanner } from './components/compute/ClefPopulateSummaryBanner';
import { ClefSourcesReportModal } from './components/compute/ClefSourcesReportModal';
import { ConceptSidebar } from './components/parse/ConceptSidebar';
import { RightPanel } from './components/parse/RightPanel';
import {
  type CompareComputeMode,
} from './components/parse/compareComputeContract';
import { OffsetAdjustmentModal } from './components/parse/modals/OffsetAdjustmentModal';
import { AIChat } from './components/shared/AIChat';
import { getClefConfig, getContactLexemeCoverage, saveClefFormSelections } from './api/client';
import type { ClefConfigStatus } from './api/types';

type ConceptTag = 'untagged' | 'review' | 'confirmed' | 'problematic';
type AppMode = 'annotate' | 'compare' | 'tags';

interface LingTag {
  id: string; name: string; color: string; dotClass: string; count: number;
}

interface Concept {
  id: number;
  key: string;
  name: string;
  tag: ConceptTag;
  surveyItem?: string;
  customOrder?: number;
}

type ConceptSortMode = 'az' | '1n' | 'survey';

interface SpeakerForm {
  speaker: string; ipa: string; ortho: string; utterances: number;
  // Similarity scores keyed by the configured CLEF primary contact-language
  // code (e.g. "ar", "fa", "eng", "spa"). Null means "no score on disk" --
  // either the cognate compute hasn't run, or there was no reference form
  // to score against. The table headers are driven by the same key set so
  // any pair/triple the user configured renders cleanly without a code edit.
  similarityByLang: Record<string, number | null>;
  cognate: string; flagged: boolean;
  startSec: number | null; endSec: number | null;
}

// No fallback data — workspace must supply real speakers and concepts via /api/config.

const REVIEW_TAG_IDS = new Set(['review', 'review-needed']);
const COMPARE_NOTES_STORAGE_KEY = 'parseui-compare-notes-v1';

/** Render a number of seconds as ``MM:SS.cs`` — the same format the
 *  Annotate playback bar shows under the waveform. Lifted to module
 *  scope so the offset-capture toast + manual-anchor chips can mirror
 *  it exactly (so users can verify what was captured against the
 *  readout they were just looking at). */
function isInteractiveHotkeyTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') return true;
  return (target as HTMLElement).isContentEditable;
}

function overlaps(a: AnnotationInterval, b: AnnotationInterval): boolean {
  return a.start <= b.end && b.start <= a.end;
}

// Build a workspace-relative audio URL from an annotation record. Server serves
// static files from the project root, so "audio/working/X/foo.wav" → "/audio/working/X/foo.wav".
function deriveAudioUrl(record: AnnotationRecord | null | undefined): string {
  const raw = (record?.source_audio ?? record?.source_wav ?? '').trim();
  if (!raw) return '';
  const cleaned = raw.replace(/\\/g, '/').replace(/^\/+/, '');
  return '/' + cleaned;
}


function conceptMatchesIntervalText(concept: { name: string; key: string }, text: string): boolean {
  const normalizedText = text.trim().toLowerCase();
  const normalizedName = concept.name.trim().toLowerCase();
  const normalizedKey = concept.key.trim().toLowerCase();

  return normalizedText === normalizedName
    || normalizedText === normalizedKey
    || normalizedText.includes(normalizedName);
}

function getConceptStatus(tags: StoreTag[]): ConceptTag {
  if (tags.some((tag) => tag.id === 'problematic')) return 'problematic';
  if (tags.some((tag) => tag.id === 'confirmed')) return 'confirmed';
  if (tags.some((tag) => REVIEW_TAG_IDS.has(tag.id))) return 'review';
  return 'untagged';
}

// Prefer word-level ortho_words (from Tier-2 forced alignment) over the
// coarse ortho tier. When the coarse tier is one monolithic segment — as
// razhan often produces on long elicited word-list recordings — picking
// the whole-paragraph interval by overlap dumps the entire narrative into
// a single lexeme field. The word-level tier yields a single clean word.
export function pickOrthoIntervalForConcept(
  record: AnnotationRecord,
  conceptInterval: AnnotationInterval,
): AnnotationInterval | null {
  const words = record.tiers.ortho_words?.intervals ?? [];
  if (words.length) {
    const contained = words.find(
      (iv) => iv.start >= conceptInterval.start && iv.end <= conceptInterval.end,
    );
    if (contained) return contained;

    let bestOverlap = 0;
    let bestWord: AnnotationInterval | null = null;
    for (const iv of words) {
      if (iv.end <= conceptInterval.start || iv.start >= conceptInterval.end) continue;
      const ov = Math.min(iv.end, conceptInterval.end) - Math.max(iv.start, conceptInterval.start);
      if (ov > bestOverlap) {
        bestOverlap = ov;
        bestWord = iv;
      }
    }
    if (bestWord) return bestWord;
  }
  return (record.tiers.ortho?.intervals ?? []).find((iv) => overlaps(iv, conceptInterval)) ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readTextBlob(blob: Blob): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function buildSpeakerForm(
  record: AnnotationRecord | null | undefined,
  concept: Concept,
  speaker: string,
  enrichments: Record<string, unknown>,
  flagged: boolean,
  primaryContactCodes: readonly string[],
): SpeakerForm {
  const conceptIntervals = (record?.tiers.concept?.intervals ?? []).filter((interval) => conceptMatchesIntervalText(concept, interval.text));
  const ipaIntervals = record?.tiers.ipa?.intervals ?? [];
  const matchingIpaIntervals = ipaIntervals.filter((ipaInterval) => conceptIntervals.some((conceptInterval) => overlaps(ipaInterval, conceptInterval)));

  const similarityRoot = isRecord(enrichments.similarity) ? enrichments.similarity : null;
  const conceptSimilarity = similarityRoot && isRecord(similarityRoot[concept.key]) ? similarityRoot[concept.key] as Record<string, unknown> : null;
  const speakerSimilarity = conceptSimilarity && isRecord(conceptSimilarity[speaker]) ? conceptSimilarity[speaker] as Record<string, unknown> : null;
  // The backend's compute_similarity_scores writes
  //   similarity[concept][speaker][lang] = { score: number|null,
  //                                          has_reference_data: bool }
  // An earlier revision treated this inner object as if it were a bare
  // number (and read "tr" for Persian), which made every column silently
  // resolve to 0 regardless of compute state. Reading .score from the
  // object -- and using the CLEF-config code "fa" for Persian, not "tr"
  // -- is what actually surfaces the computed distances in the UI.
  // Returns null (not 0) when the score is missing so the UI can render
  // "—" and distinguish "not yet computed" from "computed zero".
  const rawSim = (code: string): number | null => {
    const cell = speakerSimilarity?.[code];
    if (!isRecord(cell)) return null;
    const score = (cell as Record<string, unknown>).score;
    return typeof score === 'number' ? score : null;
  };
  const similarityByLang: Record<string, number | null> = {};
  for (const code of primaryContactCodes) {
    similarityByLang[code] = rawSim(code);
  }

  const overrides = isRecord(enrichments.manual_overrides) ? enrichments.manual_overrides as Record<string, unknown> : null;
  const overrideSets = overrides && isRecord(overrides.cognate_sets) ? overrides.cognate_sets as Record<string, unknown> : null;
  const autoSets = isRecord(enrichments.cognate_sets) ? enrichments.cognate_sets as Record<string, unknown> : null;
  // Manual overrides win over auto-computed cognate sets.
  const conceptCognates = (overrideSets && isRecord(overrideSets[concept.key]) ? overrideSets[concept.key] : null)
    ?? (autoSets && isRecord(autoSets[concept.key]) ? autoSets[concept.key] : null);
  let cognate: SpeakerForm['cognate'] = '—';
  if (conceptCognates && isRecord(conceptCognates)) {
    // Accept any single-letter group A–Z; first match wins.
    for (const [group, members] of Object.entries(conceptCognates)) {
      if (Array.isArray(members) && members.includes(speaker) && /^[A-Z]$/.test(group)) {
        cognate = group;
        break;
      }
    }
  }

  // Per-speaker flag: overrides.speaker_flags[conceptKey][speaker] = true.
  const flagsBlock = overrides && isRecord(overrides.speaker_flags) ? overrides.speaker_flags as Record<string, unknown> : null;
  const conceptFlags = flagsBlock && isRecord(flagsBlock[concept.key]) ? flagsBlock[concept.key] as Record<string, unknown> : null;
  const speakerFlagged = !!(conceptFlags && conceptFlags[speaker]);

  const primaryConceptInterval = conceptIntervals[0] ?? null;
  // Prefer word-level ortho_words over the coarse ortho tier — see the
  // rationale on pickOrthoIntervalForConcept above.
  const orthoText = record && primaryConceptInterval
    ? pickOrthoIntervalForConcept(record, primaryConceptInterval)?.text ?? ''
    : '';

  return {
    speaker,
    ipa: matchingIpaIntervals[0]?.text ?? '',
    ortho: orthoText,
    utterances: matchingIpaIntervals.length,
    similarityByLang,
    cognate,
    flagged: speakerFlagged || flagged,
    startSec: primaryConceptInterval ? primaryConceptInterval.start : null,
    endSec: primaryConceptInterval ? primaryConceptInterval.end : null,
  };
}

// ---------------------------------------------------------------------------
// Reference-form parsing + classification (display-only; no transliteration)
// ---------------------------------------------------------------------------
// The Reference Forms panel renders every form the providers wrote for a
// (concept, language), letting the user pick which ones contribute to the
// similarity score. The functions below are pure *display* helpers: they
// never transliterate script to IPA. A bare string is routed to either the
// ``script`` slot or the ``ipa`` slot based on a conservative Unicode-range
// check, and the raw text is preserved verbatim. See ``classifyRawFormString``
// for the allowed non-Latin scripts. No character substitution happens
// anywhere in this pipeline.

// Unicode blocks we explicitly recognise as "not IPA" for display tagging
// when no per-language script hint is available. A bare string containing
// any char in these blocks is routed to the script slot; everything else
// (Latin + IPA extensions + diacritics) goes to the ipa slot. Greek is
// deliberately *not* in this set because IPA uses several Greek-block
// letters (β, χ, θ, ɣ, ɸ) and a string of phonetic ɣaβa would otherwise
// be misclassified -- Greek-script languages should rely on the
// per-language ISO 15924 script hint instead. This is a tag, not a
// transformation; the raw text is preserved as-is in whichever slot it
// lands.
const NON_LATIN_SCRIPT_RE = /[\u0400-\u04FF\u0500-\u052F\u0530-\u058F\u0590-\u05FF\u0600-\u06FF\u0700-\u074F\u0750-\u077F\u07C0-\u07FF\u0780-\u07BF\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF\u0E00-\u0E7F\u0E80-\u0EFF\u0F00-\u0FFF\u1000-\u109F\u10A0-\u10FF\u1100-\u11FF\u1200-\u137F\u1780-\u17FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\uFB50-\uFDFF\uFE70-\uFEFF]/;

// ISO 15924 codes that mean "Latin script" -- these should route to the
// IPA slot (since Latin-script languages submitting IPA forms is the
// happy path). The rest of the world's scripts route to the script slot
// when the hint is present.
const LATIN_SCRIPT_HINTS = new Set(['Latn', 'latn']);

/** Classify a bare reference-form string as script vs IPA for display.
 *  Display hint only -- the returned object always carries the *same*
 *  raw text in whichever slot it lands. No transliteration ever happens
 *  here.
 *
 *  When ``scriptHint`` is given (an ISO 15924 code from the SIL catalog
 *  or per-language config), the routing is deterministic: Latn -> IPA,
 *  anything else -> script. This is the preferred path because
 *  languages almost always commit to one script and the hint avoids
 *  edge cases the Unicode regex can't disambiguate (e.g. Greek IPA
 *  letters vs Greek-script forms).
 *
 *  Without a hint, falls back to the Unicode-block regex: any char in
 *  ``NON_LATIN_SCRIPT_RE`` -> script slot; otherwise IPA slot. */
function classifyRawFormString(raw: string, scriptHint?: string | null): { script: string; ipa: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { script: '', ipa: '' };
  if (scriptHint) {
    if (LATIN_SCRIPT_HINTS.has(scriptHint)) {
      return { script: '', ipa: trimmed };
    }
    return { script: trimmed, ipa: '' };
  }
  if (NON_LATIN_SCRIPT_RE.test(trimmed)) {
    return { script: trimmed, ipa: '' };
  }
  return { script: '', ipa: trimmed };
}

export interface ReferenceFormEntry {
  /** Exact raw source string. Used as the stable selection key so
   *  ``_meta.form_selections`` persists verbatim across reloads. */
  raw: string;
  script: string;
  ipa: string;
  audioUrl: string | null;
  /** Provenance sources when available (``wikidata``, ``asjp``, ...).
   *  Empty for bare-string legacy entries and rolled-up non-provenance
   *  shapes that had no explicit source list. */
  sources: string[];
}

function _parseOneEntry(raw: unknown, scriptHint?: string | null): ReferenceFormEntry | null {
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    return { raw: trimmed, script, ipa, audioUrl: null, sources: [] };
  }

  if (!isRecord(raw)) return null;

  // Provenance shape: { form: <string>, sources: [<provider>, ...] }.
  // The ``form`` value is the verbatim provider output; we still tag it
  // by script hint / Unicode range so e.g. an LLM response that slipped
  // into Arabic script doesn't display in the IPA slot.
  if (typeof raw.form === 'string' && Array.isArray(raw.sources)) {
    const trimmed = (raw.form as string).trim();
    if (!trimmed) return null;
    const sources = (raw.sources as unknown[]).filter((s): s is string => typeof s === 'string');
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    const audioUrl = typeof raw.audioUrl === 'string' && raw.audioUrl.trim() ? raw.audioUrl : null;
    return { raw: trimmed, script, ipa, audioUrl, sources };
  }

  // Structured provider objects with explicit field labels. Trust the
  // label: if the provider wrote ``ipa: "foo"`` we display "foo" as IPA
  // even if it contains script-range chars -- that's their claim, and
  // it overrides the per-language script hint too.
  const scriptVal = [raw.script, raw.orthography, raw.text].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;
  const ipaVal = [raw.ipa, raw.phonetic, raw.transcription].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;
  const audioUrl = [raw.audioUrl, raw.audio, raw.url].find(
    (v) => typeof v === 'string' && (v as string).trim().length > 0,
  ) as string | undefined;

  // A bare ``form`` field with no sources array -- treat as a generic
  // string and classify (matches the bare-string path).
  if (!scriptVal && !ipaVal && typeof raw.form === 'string' && (raw.form as string).trim()) {
    const trimmed = (raw.form as string).trim();
    const { script, ipa } = classifyRawFormString(trimmed, scriptHint);
    return {
      raw: trimmed,
      script,
      ipa,
      audioUrl: audioUrl ?? null,
      sources: [],
    };
  }

  if (!scriptVal && !ipaVal) return null;

  // Selection keys against structured objects prefer the IPA text (it's
  // the canonical similarity-scoring string), falling back to script.
  const rawKey = (ipaVal ?? scriptVal ?? '').trim();
  if (!rawKey) return null;

  return {
    raw: rawKey,
    script: scriptVal ?? '',
    ipa: ipaVal ?? '',
    audioUrl: audioUrl ?? null,
    sources: [],
  };
}

/** Parse any provider-shaped reference data into an ordered list of
 *  display entries. Accepts the legacy string/array/object shapes the
 *  Reference Forms pipeline has seen. Duplicates (by raw text) collapse
 *  so a form fetched by multiple providers shows up once.
 *
 *  ``scriptHint`` is an ISO 15924 code (Arab, Latn, ...) attached to the
 *  language this concept belongs to. When present, bare strings route
 *  deterministically to the script vs IPA slot; explicit ``ipa``/``script``
 *  field labels still override (we trust the provider's claim). */
export function parseReferenceFormList(raw: unknown, scriptHint?: string | null): ReferenceFormEntry[] {
  const out: ReferenceFormEntry[] = [];
  const seen = new Set<string>();
  const push = (entry: ReferenceFormEntry | null) => {
    if (!entry || seen.has(entry.raw)) return;
    seen.add(entry.raw);
    out.push(entry);
  };
  if (Array.isArray(raw)) {
    for (const item of raw) push(_parseOneEntry(item, scriptHint));
  } else {
    push(_parseOneEntry(raw, scriptHint));
  }
  return out;
}

/** List-shaped resolver that preserves every
 *  provider-returned form instead of collapsing to the first one. Drives
 *  the Reference Forms panel's multi-form display + selection UI. Keyed
 *  by primary contact-language code; absent codes mean no populated
 *  forms were found (or the fallback SIL entry was empty too).
 *
 *  ``scriptByCode`` maps each language code to its ISO 15924 script
 *  hint (when known). The hint is propagated into ``parseReferenceFormList``
 *  so bare-string entries route deterministically to the script vs IPA
 *  slot per language, instead of relying on the Unicode-block heuristic. */
export function resolveReferenceFormLists(
  enrichments: Record<string, unknown>,
  silConcepts: Record<string, Record<string, unknown>>,
  concept: Concept,
  codes: readonly string[],
  scriptByCode?: Readonly<Record<string, string | null | undefined>>,
): Record<string, ReferenceFormEntry[]> {
  const root = isRecord(enrichments.reference_forms) ? enrichments.reference_forms as Record<string, unknown> : null;
  const conceptEntry = root ? root[concept.key] ?? root[concept.name] : null;
  const conceptRecord = isRecord(conceptEntry) ? conceptEntry : {};

  const out: Record<string, ReferenceFormEntry[]> = {};
  for (const code of codes) {
    const hint = scriptByCode?.[code] ?? null;
    const primary = parseReferenceFormList(conceptRecord[code], hint);
    if (primary.length > 0) {
      out[code] = primary;
      continue;
    }
    const silForConcept = silConcepts[code]?.[concept.name];
    const fallback = parseReferenceFormList(silForConcept, hint);
    if (fallback.length > 0) out[code] = fallback;
  }
  return out;
}

/** Read the user's persisted form-selection allow-list for one
 *  (concept, lang) out of ``clefStatus.meta.form_selections``. Returns
 *  ``null`` when no explicit selection exists for that pair -- the
 *  caller should treat that as "every populated form is selected"
 *  (the default). Returns ``[]`` for explicit opt-out. */
export function resolveFormSelection(
  clefMeta: Record<string, unknown> | null | undefined,
  conceptEn: string,
  langCode: string,
): string[] | null {
  const selections = clefMeta && isRecord(clefMeta.form_selections)
    ? (clefMeta.form_selections as Record<string, unknown>)
    : null;
  if (!selections) return null;
  const perConcept = selections[conceptEn];
  if (!isRecord(perConcept)) return null;
  const entry = perConcept[langCode];
  if (!Array.isArray(entry)) return null;
  return entry.filter((v): v is string => typeof v === 'string');
}

/** Map a language code to a display tone + text direction for the
 *  Reference Forms cards. Known RTL scripts get `dir="rtl"`; the tone
 *  cycles over a short palette so two configured primaries always look
 *  distinct. Falls back to a neutral tone + LTR for anything we don't
 *  recognise -- good enough until the catalog ships script metadata. */
const RTL_CODES = new Set([
  "ar", "arc", "ara",
  "fa", "pes", "prs",
  "he", "heb",
  "ur", "urd",
  "ckb", "sdh", "sor",
  "ps", "pus", "pbt",
  "syr",
]);
const CARD_TONES = [
  "text-rose-500",
  "text-indigo-500",
  "text-emerald-500",
  "text-amber-600",
];
function referenceCardStyle(code: string, idx: number): { tone: string; dir: "ltr" | "rtl" } {
  return {
    tone: CARD_TONES[idx % CARD_TONES.length],
    dir: RTL_CODES.has(code.toLowerCase()) ? "rtl" : "ltr",
  };
}

// ---------- Main Component ----------
export function ParseUI() {
  // — Stores —
  const loadConfig       = useConfigStore(s => s.load);
  const rawSpeakers      = useConfigStore(s => s.config?.speakers ?? []);
  const rawConcepts      = useConfigStore(s => s.config?.concepts ?? []);
  const configError      = useConfigStore(s => s.error);
  const [dismissedConfigError, setDismissedConfigError] = useState<string | null>(null);
  const storeTags        = useTagStore(s => s.tags);
  const storeAddTag      = useTagStore(s => s.addTag);
  const hydrateTagStore  = useTagStore(s => s.hydrate);
  const syncTagStoreFromServer = useTagStore(s => s.syncFromServer);
  const updateStoreTag   = useTagStore(s => s.updateTag);
  const tagConcept       = useTagStore(s => s.tagConcept);
  const untagConcept     = useTagStore(s => s.untagConcept);
  const getTagsForConcept = useTagStore(s => s.getTagsForConcept);
  const annotationRecords = useAnnotationStore(s => s.records);
  const enrichmentData = useEnrichmentStore(s => s.data);
  const setActiveSpeakerUI = useUIStore(s => s.setActiveSpeaker);
  const setActiveConceptUI = useUIStore(s => s.setActiveConcept);
  // — Chat session (one instance for the whole UI) —
  const chatSession = useChatSession();
  // — Annotation sync (auto-loads record when activeSpeaker changes) —
  useAnnotationSync();
  // — Bootstrap —
  useEffect(() => {
    loadConfig().catch(console.error);
    hydrateTagStore();
    syncTagStoreFromServer().catch(console.error);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<ConceptSortMode>('1n');
  const conceptImportInputRef = useRef<HTMLInputElement>(null);
  const { exportLingPyTSV } = useExport();
  const {
    summary: conceptImportSummary,
    error: conceptImportError,
    importFile: importConceptTagFile,
  } = useTagImport();
  const [tagFilter, setTagFilter] = useState<string>('all');
  const [conceptId, setConceptId] = useState(1);
  const [selectedSpeakers, setSelectedSpeakers] = useState<string[]>([]);
  const [speakerPicker, setSpeakerPicker] = useState<string | null>(null);
  const [computeMode, setComputeMode] = useState<CompareComputeMode>('cognates');
  const compareComputePayload = useMemo(() => {
    const speakers = selectedSpeakers.filter((speaker) => speaker.trim().length > 0);
    if (speakers.length === 0) return undefined;
    return { speakers };
  }, [selectedSpeakers]);
  const computeJobLabel = useMemo(() => {
    if (computeMode === 'cognates') return 'Recomputing cognates + similarity…';
    if (computeMode === 'similarity') return 'Recomputing shared similarity path…';
    return `Computing ${computeMode}…`;
  }, [computeMode]);
  const { start: startComputeJob, state: computeJobState, reset: resetComputeJob } = useComputeJob(computeMode, {
    body: compareComputePayload,
    label: computeJobLabel,
  });
  const [clefModalOpen, setClefModalOpen] = useState(false);
  // Sources Report modal — shows provider attribution for every populated
  // reference form. Opened from the Compute panel's CLEF status row; read-
  // only so it's safe to surface even when Borrowing detection is running.
  const [sourcesReportOpen, setSourcesReportOpen] = useState(false);
  // Which tab ClefConfigModal should open on. Defaults to "languages"; the
  // empty-populate banner's "Retry with different providers" action flips
  // this to "populate" so the user lands directly on the provider picker.
  // Reset to "languages" on close so the next gear/Run click lands on the
  // languages tab again.
  const [clefInitialTab, setClefInitialTab] = useState<ClefConfigModalTab>('languages');
  // Full CLEF status so the Reference Forms section can render exactly
  // the user's configured primary languages (not a hardcoded Arabic +
  // Persian pair). `null` means "not yet loaded" so the UI can render a
  // neutral placeholder instead of flashing the configured branch.
  const [clefStatus, setClefStatus] = useState<ClefConfigStatus | null>(null);
  // Coverage cache — {[code]: {[concept_en]: string[]}} — so the
  // Reference Forms cards can surface forms the user just populated via
  // "Save & populate" without waiting for a full enrichments recompute.
  const [silConcepts, setSilConcepts] = useState<Record<string, Record<string, unknown>>>({});

  const clefConfigured = clefStatus
    ? clefStatus.configured && (clefStatus.primary_contact_languages?.length ?? 0) > 0
    : null;
  const primaryContactCodes = useMemo(
    () => (clefStatus?.primary_contact_languages ?? []).map((c) => c.toLowerCase()),
    [clefStatus],
  );
  const contactLanguageNames = useMemo(() => {
    const out: Record<string, string> = {};
    for (const entry of clefStatus?.languages ?? []) {
      out[entry.code] = entry.name;
    }
    return out;
  }, [clefStatus]);
  // Per-language ISO 15924 script hint (Arab, Latn, Hebr, ...). Drives
  // deterministic script-vs-IPA routing in the Reference Forms panel.
  // Sourced from the SIL contact-language config; missing values fall
  // back to the Unicode-block heuristic in ``classifyRawFormString``.
  const contactLanguageScripts = useMemo(() => {
    const out: Record<string, string | null> = {};
    for (const entry of clefStatus?.languages ?? []) {
      out[entry.code] = entry.script ?? null;
    }
    return out;
  }, [clefStatus]);

  const refreshClefStatus = useCallback(async () => {
    try {
      const [s, coverage] = await Promise.all([
        getClefConfig(),
        getContactLexemeCoverage().catch(() => ({ languages: {} as Record<string, { concepts: Record<string, unknown> }> })),
      ]);
      setClefStatus(s);
      const next: Record<string, Record<string, unknown>> = {};
      for (const [code, lang] of Object.entries(coverage.languages ?? {})) {
        next[code] = lang.concepts ?? {};
      }
      setSilConcepts(next);
    } catch {
      setClefStatus({
        configured: false,
        primary_contact_languages: [],
        languages: [],
        config_path: "",
        concepts_csv_exists: false,
        meta: {},
      });
      setSilConcepts({});
    }
  }, []);

  // Load CLEF status once on mount so the Reference Forms gate decides
  // correctly on first render (not only when the user clicks Compute).
  useEffect(() => {
    void refreshClefStatus();
  }, [refreshClefStatus]);

  // Optimistic overlay for Reference Forms selections. Clicks in the
  // panel update this map immediately while the POST writes through to
  // ``_meta.form_selections``. Keyed by ``"<concept_en>|<lang_code>"``
  // so re-selecting across concepts doesn't clobber in-flight saves. A
  // ``null`` value means "no explicit selection" (use every populated
  // form); a ``string[]`` is the exact allow-list; empty array means
  // "none selected" -- similarity will be skipped for that pair. Matches
  // the backend contract in ``_api_post_clef_form_selections``.
  const [localFormSelections, setLocalFormSelections] = useState<Record<string, string[] | null>>({});
  const saveFormSelection = useCallback(
    async (conceptEn: string, langCode: string, forms: string[]) => {
      const key = `${conceptEn}|${langCode}`;
      setLocalFormSelections((prev) => ({ ...prev, [key]: forms }));
      try {
        await saveClefFormSelections({ concept_en: conceptEn, lang_code: langCode, forms });
        // Pull fresh meta so a reload or other consumer sees authoritative
        // state, not just the optimistic overlay. The overlay stays in
        // place meanwhile so there's no flash between save + refresh.
        await refreshClefStatus();
      } catch (err) {
        // On error, drop the optimistic entry so the UI falls back to
        // whatever ``clefStatus.meta.form_selections`` reports.
        setLocalFormSelections((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        console.error('[clef] form selection save failed:', err);
      }
    },
    [refreshClefStatus],
  );

  // ``handleComputeRun`` is defined further down (after ``crossSpeakerJob``
  // is in scope) so it can dispatch the contact-lexemes path through the
  // header-chip job hook instead of the drawer-tied ``startComputeJob``.
  const [notes, setNotes] = useState('');
  const [borrowingsOpen, setBorrowingsOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const [expandedLexemes, setExpandedLexemes] = useState<Set<string>>(new Set());
  const [commentsImportOpen, setCommentsImportOpen] = useState(false);

  const toggleLexemeExpanded = (speaker: string) => {
    setExpandedLexemes((prev) => {
      const next = new Set(prev);
      if (next.has(speaker)) next.delete(speaker);
      else next.add(speaker);
      return next;
    });
  };

  const writeSpeakerCognate = (conceptKey: string, speaker: string, nextGroup: string | null) => {
    const store = useEnrichmentStore.getState();
    const overrides = (isRecord(store.data.manual_overrides) ? store.data.manual_overrides : {}) as Record<string, unknown>;
    const prevSets = isRecord(overrides.cognate_sets) ? overrides.cognate_sets as Record<string, Record<string, string[]>> : {};
    const autoSets = isRecord(store.data.cognate_sets) ? store.data.cognate_sets as Record<string, Record<string, string[]>> : {};
    const baseline = (prevSets[conceptKey] ?? autoSets[conceptKey] ?? {}) as Record<string, string[]>;
    // Include every existing group (even if now empty) so the enrichment
    // store's deep-merge writes an actual empty array rather than preserving
    // the prior membership.
    const cleaned: Record<string, string[]> = {};
    for (const [group, members] of Object.entries(baseline)) {
      cleaned[group] = (Array.isArray(members) ? members : []).filter((m) => m !== speaker);
    }
    if (nextGroup) {
      const existing = cleaned[nextGroup] ?? [];
      if (!existing.includes(speaker)) cleaned[nextGroup] = [...existing, speaker];
    }
    const patch = { manual_overrides: { cognate_sets: { [conceptKey]: cleaned } } };
    void store.save(patch);
  };

  const cycleSpeakerCognate = (conceptKey: string, speaker: string, current: string) => {
    // A → B → C → … → Z → — → A.
    let next: string | null;
    if (current === '\u2014' || !/^[A-Z]$/.test(current)) {
      next = 'A';
    } else if (current === 'Z') {
      next = null;
    } else {
      next = String.fromCharCode(current.charCodeAt(0) + 1);
    }
    writeSpeakerCognate(conceptKey, speaker, next);
  };

  const resetSpeakerCognate = (conceptKey: string, speaker: string) => {
    writeSpeakerCognate(conceptKey, speaker, null);
  };

  const toggleSpeakerFlag = (conceptKey: string, speaker: string, current: boolean) => {
    const store = useEnrichmentStore.getState();
    const overrides = (isRecord(store.data.manual_overrides) ? store.data.manual_overrides : {}) as Record<string, unknown>;
    const prevFlags = isRecord(overrides.speaker_flags) ? overrides.speaker_flags as Record<string, Record<string, boolean>> : {};
    // The enrichment store's deep-merge only walks keys present in the patch,
    // so `delete`-ing the key would leave the stored `true` intact. Explicitly
    // write `false` to clear the flag instead.
    const conceptBlock: Record<string, boolean> = { ...(prevFlags[conceptKey] ?? {}) };
    conceptBlock[speaker] = !current;
    const patch = { manual_overrides: { speaker_flags: { [conceptKey]: conceptBlock } } };
    void store.save(patch);
  };

  // Auto-select speakers when config loads and we have none selected
  useEffect(() => {
    if (rawSpeakers.length > 0 && selectedSpeakers.length === 0) {
      setSelectedSpeakers(rawSpeakers);
      setSpeakerPicker(rawSpeakers.find(s => !rawSpeakers.includes(s)) ?? rawSpeakers[0] ?? null);
    }
  }, [rawSpeakers]); // eslint-disable-line react-hooks/exhaustive-deps
  // Persist the active mode so an accidental unmount (HMR, error boundary
  // reset, or a root-level remount) doesn't snap the user back to Compare
  // and away from an in-flight Annotate session.
  const [currentMode, setCurrentMode] = useState<AppMode>(() => {
    try {
      const raw = localStorage.getItem('parse.currentMode');
      if (raw === 'annotate' || raw === 'compare' || raw === 'tags') return raw;
    } catch { /* localStorage disabled — fall through */ }
    return 'compare';
  });
  useEffect(() => {
    try { localStorage.setItem('parse.currentMode', currentMode); }
    catch { /* non-fatal */ }
  }, [currentMode]);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [actionsMenuOpen, setActionsMenuOpen] = useState(false);
  const [sttLanguage, setSttLanguage] = useState<string>(() => {
    try { return (localStorage.getItem('parse.stt.language') ?? '').trim(); }
    catch { return ''; }
  });
  const sttLanguageRef = useRef(sttLanguage);
  useEffect(() => {
    sttLanguageRef.current = sttLanguage;
    try { localStorage.setItem('parse.stt.language', sttLanguage); }
    catch { /* storage unavailable */ }
  }, [sttLanguage]);
  const activeActionSpeaker = selectedSpeakers[0] ?? null;
  const loadSpeaker = useAnnotationStore((s) => s.loadSpeaker);
  const loadEnrichments = useEnrichmentStore((s) => s.load);

  useEffect(() => {
    for (const speaker of selectedSpeakers) {
      loadSpeaker(speaker).catch((err) => {
        console.error('[ParseUI] loadSpeaker failed:', speaker, err);
      });
    }
  }, [selectedSpeakers, loadSpeaker]);

  useEffect(() => {
    // Wrap in Promise.resolve because tests mock the store's `load` as a
    // no-op that returns undefined; `.catch` on undefined would throw.
    Promise.resolve(loadEnrichments?.()).catch((err) => {
      console.error('[ParseUI] loadEnrichments failed:', err);
    });
  }, [loadEnrichments]);

  const reloadSpeakerAnnotation = async (speakerId: string | null) => {
    if (!speakerId) {
      return;
    }

    useAnnotationStore.setState((store: { dirty: Record<string, boolean> }) => ({
      dirty: { ...store.dirty, [speakerId]: true },
    }));
    await loadSpeaker(speakerId);
  };

  // Single unified batch runner replaces the previous per-model hooks
  // (normalizeJob / sttJob / ipaJob / orthoJob / pipelineJob). Every
  // transcription action — single-model or full-pipeline — now goes
  // through this batch pipeline: the TranscriptionRunModal picks
  // speakers + steps, this hook iterates them sequentially, and
  // BatchReportModal surfaces outcomes with expandable tracebacks.
  // Continues on per-speaker failure; the walk-away-friendly design.
  const batch = useBatchPipelineJob();

  // Transcription run modal — state holds the `fixedSteps` and title
  // that the action-menu button supplied (null when closed). When
  // `fixedSteps` is undefined, the modal renders step checkboxes;
  // otherwise those checkboxes are locked to the supplied steps.
  const [runModal, setRunModal] = useState<
    | { title: string; fixedSteps: PipelineStepId[] | undefined }
    | null
  >(null);

  // Post-batch report modal. Opens when a batch finishes so the user
  // sees what was done, what was skipped, and the full error traceback
  // for each failure — the "come back from coffee, see the outcome" UX.
  const [reportOpen, setReportOpen] = useState(false);
  const [reportStepsRun, setReportStepsRun] = useState<PipelineStepId[]>([]);
  const previousBatchStatusRef = useRef<typeof batch.state.status>('idle');
  useEffect(() => {
    if (previousBatchStatusRef.current === 'running' && batch.state.status === 'complete') {
      setReportOpen(true);
      void (async () => {
        // Reload stores for every speaker that actually had work done
        // so the transcription lanes / annotations refresh without a
        // page reload.
        for (const outcome of batch.state.outcomes) {
          if (outcome.status === 'complete') {
            void useTranscriptionLanesStore.getState().reloadStt(outcome.speaker);
            await reloadSpeakerAnnotation(outcome.speaker);
          }
        }
        await loadEnrichments();
      })();
    }
    previousBatchStatusRef.current = batch.state.status;
  }, [batch.state.status, batch.state.outcomes, loadEnrichments]);

  const openRunModal = (title: string, fixedSteps?: PipelineStepId[]) => {
    setRunModal({ title, fixedSteps });
  };

  const handleRunConfirm = (confirm: TranscriptionRunConfirm) => {
    setRunModal(null);
    if (confirm.speakers.length === 0 || confirm.steps.length === 0) return;
    void batch.run({
      speakers: confirm.speakers,
      steps: confirm.steps,
      overwrites: confirm.overwrites,
      language: sttLanguageRef.current || undefined,
      refineLexemes: confirm.refineLexemes,
    });
  };

  const handleRerunFailed = (speakers: string[]) => {
    if (speakers.length === 0 || reportStepsRun.length === 0) return;

    // For each failed speaker, rerun ONLY the steps that errored last
    // time — preserves steps that succeeded. Whole-speaker failures
    // (result === null, typically a network error before the pipeline
    // even started) retry the full step list.
    const stepsBySpeaker: Partial<Record<string, PipelineStepId[]>> = {};
    for (const outcome of batch.state.outcomes) {
      if (!speakers.includes(outcome.speaker)) continue;
      if (outcome.result == null) {
        // Whole-speaker error → rerun everything the batch was asked to do.
        stepsBySpeaker[outcome.speaker] = reportStepsRun;
        continue;
      }
      const failedSteps = reportStepsRun.filter((step) => {
        const stepResult = outcome.result?.results[step];
        return stepResult?.status === 'error';
      });
      stepsBySpeaker[outcome.speaker] = failedSteps;
    }

    // Build the overwrite map from the UNION of all steps actually being
    // rerun. Failed steps either produced no output or partial output,
    // so overwrite=true is safe and often necessary.
    const stepsToRerun = new Set<PipelineStepId>();
    for (const steps of Object.values(stepsBySpeaker)) {
      for (const step of steps ?? []) stepsToRerun.add(step);
    }
    if (stepsToRerun.size === 0) return;  // nothing to do

    setReportOpen(false);
    void batch.run({
      speakers,
      // The global `steps` list is a fallback for any speaker without an
      // entry in stepsBySpeaker (shouldn't happen, but defensive).
      steps: Array.from(stepsToRerun).sort((a, b) => {
        const order: PipelineStepId[] = ['normalize', 'stt', 'ortho', 'ipa'];
        return order.indexOf(a) - order.indexOf(b);
      }),
      stepsBySpeaker,
      overwrites: Array.from(stepsToRerun).reduce<Partial<Record<PipelineStepId, boolean>>>(
        (acc, step) => { acc[step] = true; return acc; },
        {},
      ),
      language: sttLanguageRef.current || undefined,
    });
  };

  // Single source of truth for the contact-lexemes / CLEF populate job in
  // the header. Both the "Run Cross-Speaker Match" button (kept for the
  // legacy compute path) and the CLEF configure modal's Save & populate
  // action flow through this hook: the modal starts the job, then ParseUI
  // calls `adopt()` so the header's running-process chip picks it up and
  // behaves exactly like STT / forced-align / the batch pipeline.
  // Last completed-populate summary: `{ok, totalFilled, perLang, warning}`.
  // Set by `crossSpeakerJob.onComplete` from the backend's `result` payload
  // so Compare mode can render a contextual banner when the job technically
  // succeeded but produced zero forms (providers offline, concepts outside
  // ASJP's Swadesh list, etc.) -- previously that case showed as plain
  // green "complete" with no visible signal.
  const [populateSummary, setPopulateSummary] = useState<
    | { state: 'ok' | 'empty' | 'error'; totalFilled: number; perLang: Record<string, number>; warning: string | null }
    | null
  >(null);

  // Similarity follow-up: after the populate job succeeds with forms
  // filled, the reference data on disk is fresh but the similarity block
  // inside parse-enrichments.json is still whatever the last cognate
  // compute wrote (often empty / all-null on first configure). Without a
  // follow-up compute the Arabic / Persian Sim. columns stay at "—"
  // even though the reference forms clearly exist. This hook owns that
  // follow-up step so the user doesn't have to manually trigger
  // "Compute cognate sets" after every populate.
  const similarityJob = useActionJob({
    start: () => startCompute('similarity', compareComputePayload),
    poll: (id) => pollCompute('similarity', id),
    label: 'Computing similarity scores…',
    onComplete: async () => {
      // Only enrichments need a reload -- CLEF config/reference forms
      // didn't change during this step.
      await loadEnrichments();
    },
  });

  const crossSpeakerJob = useActionJob({
    start: () => startCompute('contact-lexemes'),
    poll: (id) => pollCompute('contact-lexemes', id),
    label: 'Populating CLEF reference data…',
    onComplete: async (result) => {
      await loadEnrichments();
      await refreshClefStatus();
      // The backend's `_compute_contact_lexemes` returns
      // `{filled, total_filled, warning?}`. Inspect it so we can show a
      // non-fatal "0 forms found" banner near Reference Forms.
      const payload = (result && typeof result === 'object') ? result as Record<string, unknown> : {};
      const totalFilled = typeof payload.total_filled === 'number' ? payload.total_filled : NaN;
      const rawPerLang = payload.filled && typeof payload.filled === 'object' ? payload.filled as Record<string, unknown> : {};
      const perLang: Record<string, number> = {};
      for (const [code, count] of Object.entries(rawPerLang)) {
        if (typeof count === 'number' && Number.isFinite(count)) perLang[code] = count;
      }
      const warning = typeof payload.warning === 'string' && payload.warning.trim() ? payload.warning : null;
      const resolvedTotal = Number.isFinite(totalFilled)
        ? totalFilled
        : Object.values(perLang).reduce((a, b) => a + b, 0);
      setPopulateSummary({
        state: resolvedTotal > 0 ? 'ok' : 'empty',
        totalFilled: resolvedTotal,
        perLang,
        warning,
      });
      // When populate actually delivered forms, chain a similarity
      // recompute so the Sim. columns catch up to the new reference data
      // without requiring a second manual click on the user. Skipped on
      // the empty/zero-forms path because the refs on disk didn't
      // change, so there's nothing new to score against.
      if (resolvedTotal > 0) {
        void similarityJob.run();
      }
    },
  });

  const activeJobs = [
    ...(crossSpeakerJob.state.status !== 'idle' ? [crossSpeakerJob] : []),
    ...(similarityJob.state.status !== 'idle' ? [similarityJob] : []),
  ];

  // Drawer "Run" button. ``contact-lexemes`` (Borrowing detection / CLEF)
  // routes through ``crossSpeakerJob`` so progress / ETA / completion
  // surface in the global header chip alongside STT / IPA / forced-align,
  // not as a duplicate one-line indicator inside the drawer. The
  // ``onComplete`` hook on ``crossSpeakerJob`` already handles the
  // populate-summary banner + auto-chained similarity recompute (#208),
  // so this dispatch keeps both paths (header click via Save & populate,
  // drawer click via Run) on the same wiring. Other compute modes
  // (cognates / phonetic similarity) still use the legacy drawer-tied
  // ``startComputeJob`` since they don't have a useActionJob counterpart.
  const handleComputeRun = useCallback(() => {
    if (computeMode === 'contact-lexemes') {
      if (clefConfigured !== true) {
        setClefModalOpen(true);
        return;
      }
      void crossSpeakerJob.run();
      return;
    }
    void startComputeJob();
  }, [computeMode, clefConfigured, startComputeJob, crossSpeakerJob]);

  // On mount, adopt any in-flight backend jobs so progress bars survive
  // a page reload. STT (and similar) run in a background thread that
  // outlives the browser tab — before this, the UI had no way to
  // reconnect, making the process look dead even though it was still
  // burning GPU cycles on the PC.
  // Rehydrate cross-speaker-match jobs on mount — it's the only remaining
  // long-lived job that runs outside the batch runner. Per-speaker
  // transcription jobs (STT / normalize / ortho / ipa / full_pipeline)
  // now flow through the batch runner; those are re-kicked from the
  // TranscriptionRunModal rather than adopted here.
  const didRehydrateJobsRef = useRef(false);
  useEffect(() => {
    if (didRehydrateJobsRef.current) return;
    didRehydrateJobsRef.current = true;
    void (async () => {
      let snapshots;
      try {
        snapshots = await listActiveJobs();
      } catch {
        return;
      }
      for (const snap of snapshots) {
        if (snap.type === 'compute:contact-lexemes') {
          crossSpeakerJob.adopt(snap.jobId);
        } else if (snap.type === 'compute:similarity' || snap.type === 'compute:cognates') {
          // The auto-chained similarity follow-up after populate runs as
          // a distinct job on the backend; rehydrate it too so a reload
          // mid-compute doesn't leave the header chip blank while the
          // worker is still busy.
          similarityJob.adopt(snap.jobId);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const [importModalOpen, setImportModalOpen] = useState(false);

  // Count of lexemes on the active speaker that the user has already
  // locked (direct timestamp edit or anchor capture). Surfaces in the
  // offset Review & apply modal and the header status chip so the user
  // knows which previously-fixed lexemes will be protected before they
  // confirm. Reactive: updates the moment the store flag flips.
  const protectedLexemeCount = useAnnotationStore((s) => {
    const speaker = selectedSpeakers[0] ?? null;
    if (!speaker) return 0;
    const record = s.records[speaker];
    const intervals = record?.tiers?.concept?.intervals ?? [];
    let count = 0;
    for (const iv of intervals) {
      if (iv.manuallyAdjusted) count += 1;
    }
    return count;
  });

  // Look up the current annotation interval (start + end) for a concept on
  // the active speaker (read directly from the store so we don't hold a
  // hook subscription at parent scope).
  const lookupConceptInterval = (
    speaker: string,
    concept: { name: string; key: string },
  ): { start: number; end: number } | null => {
    const records = useAnnotationStore.getState().records;
    const record = records[speaker];
    if (!record) return null;
    const intervals = record.tiers?.concept?.intervals ?? [];
    const interval = intervals.find((iv) => conceptMatchesIntervalText(concept, iv.text));
    return interval ? { start: interval.start, end: interval.end } : null;
  };

  const [exporting, setExporting] = useState(false);

  const resetProject = () => {
    setActionsMenuOpen(false);
    if (!window.confirm('Reset project? This will clear all in-memory store state. Saved files on disk are not affected.')) return;
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
    useEnrichmentStore.setState({ data: {}, loading: false });
    useTagStore.setState({ tags: [] });
    usePlaybackStore.setState({ activeSpeaker: null, currentTime: 0 });
    useConfigStore.setState({ config: null, loading: false, error: null });
    crossSpeakerJob.reset();
    batch.reset();
    resetComputeJob();
  };

  const handleExportLingPy = async () => {
    setExporting(true);
    setActionsMenuOpen(false);
    try {
      await exportLingPyTSV();
    } catch (err) {
      console.error('[ParseUI] LingPy export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  const [tagSearch, setTagSearch] = useState('');
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#6366f1');
  const [showUntagged, setShowUntagged] = useState(true);
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [tagConceptSearch, setTagConceptSearch] = useState('');
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
      const stored = raw ? JSON.parse(raw) as Record<string, string> : {};
      setNotes(stored[conceptId.toString()] ?? '');
    } catch {
      setNotes('');
    }
  }, [conceptId]);

  // — Derived: real speakers (no fallback — empty until workspace provides them) —
  const speakers = rawSpeakers;

  // — Derived: real concepts with live tag state —
  const concepts = useMemo<Concept[]>(() => {
    if (rawConcepts.length === 0) return [];
    return rawConcepts.map((c, i) => ({
      id: i + 1,
      key: c.id,
      name: c.label,
      tag: getConceptStatus(getTagsForConcept(c.id)),
      surveyItem: c.survey_item,
      customOrder: c.custom_order,
    }));
  }, [rawConcepts, getTagsForConcept]);

  const selectedConcept = concepts.find((c) => c.id === conceptId) ?? null;
  const markLexemeManuallyAdjusted = useAnnotationStore((s) => s.markLexemeManuallyAdjusted);
  const {
    offsetState,
    setOffsetState,
    jobLogsOpen,
    openJobLogs,
    closeJobLogs,
    manualAnchors,
    manualBusy,
    captureToast,
    manualConsensus,
    openManualOffset,
    closeOffsetModal,
    captureCurrentAnchor,
    captureAnchorFromBar,
    removeManualAnchor,
    detectOffsetForSpeaker,
    applyDetectedOffset,
    submitManualOffset,
  } = useOffsetState({
    activeActionSpeaker,
    selectedConcept,
    protectedLexemeCount,
    getCurrentTime: () => usePlaybackStore.getState().currentTime,
    lookupConceptInterval,
    markLexemeManuallyAdjusted,
    detectTimestampOffset,
    detectTimestampOffsetFromPairs,
    pollOffsetDetectJob,
    applyTimestampOffset,
    reloadSpeakerAnnotation,
    onCloseActionsMenu: () => setActionsMenuOpen(false),
  });

  // — Derived: tags list from store —
  const tagsList = useMemo<LingTag[]>(() =>
    storeTags.map(t => ({ id: t.id, name: t.label, color: t.color, dotClass: '', count: t.concepts.length })),
    [storeTags]
  );

  // AI bottom panel
  const [aiHeight, setAiHeight] = useState(() => Math.round(window.innerHeight * 0.4));
  const [aiMinimized, setAiMinimized] = useState(true);
  const resizingRef = useRef(false);
  const decisionsImportRef = useRef<HTMLInputElement>(null);

  const openDecisionsImport = useCallback((closeActionsMenu: boolean) => {
    if (closeActionsMenu) setActionsMenuOpen(false);
    decisionsImportRef.current?.click();
  }, []);

  const handleSaveDecisions = useCallback((closeActionsMenu: boolean) => {
    if (closeActionsMenu) setActionsMenuOpen(false);
    const payload = buildCanonicalDecisionPayload(enrichmentData);
    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = PARSE_DECISIONS_FILE_NAME;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [enrichmentData]);

  const handleDecisionsImport = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await readTextBlob(file);
      const parsed = JSON.parse(text) as unknown;
      const store = useEnrichmentStore.getState();
      const nextData = applyCanonicalDecisionImport(store.data, parsed);
      if (nextData) {
        await store.replace(nextData);
      }
    } catch {
      // non-fatal
    }
    event.target.value = '';
  }, []);

  const persistCognateDecision = useCallback((conceptKey: string, decision: CognateDecisionValue) => {
    const patch = buildCognateDecisionPatch(conceptKey, decision, Date.now());
    void useEnrichmentStore.getState().save(patch);
  }, []);

  useEffect(() => {
    if (currentMode === 'annotate') {
      setSelectedSpeakers(sel => sel.length ? [sel[0]] : ['Fail01']);
    }
  }, [currentMode]);

  const onResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    const startY = e.clientY;
    const startH = aiHeight;
    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const dy = startY - ev.clientY;
      const next = Math.min(Math.max(startH + dy, 120), window.innerHeight - 180);
      setAiHeight(next);
    };
    const onUp = () => {
      resizingRef.current = false;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const filtered = useMemo(() => {
    const overrides = isRecord(enrichmentData?.manual_overrides) ? enrichmentData.manual_overrides as Record<string, unknown> : {};
    const overrideSets = isRecord(overrides.cognate_sets) ? overrides.cognate_sets as Record<string, unknown> : {};
    const autoSets = isRecord(enrichmentData?.cognate_sets) ? enrichmentData.cognate_sets as Record<string, unknown> : {};
    const speakerFlags = isRecord(overrides.speaker_flags) ? overrides.speaker_flags as Record<string, unknown> : {};
    const borrowingFlags = isRecord(enrichmentData?.borrowing_flags) ? enrichmentData.borrowing_flags as Record<string, unknown> : {};
    const borrowingRoot = isRecord(enrichmentData?.borrowings) ? enrichmentData.borrowings as Record<string, unknown>
      : isRecord(enrichmentData?.borrowing_candidates) ? enrichmentData.borrowing_candidates as Record<string, unknown>
      : {};

    const hasCognateAssignment = (key: string): boolean => {
      const block = (isRecord(overrideSets[key]) ? overrideSets[key] : isRecord(autoSets[key]) ? autoSets[key] : null) as Record<string, unknown> | null;
      if (!block) return false;
      return Object.values(block).some((members) => Array.isArray(members) && members.length > 0);
    };
    const hasSpeakerFlag = (key: string): boolean => {
      const block = speakerFlags[key];
      if (!isRecord(block)) return false;
      return Object.values(block).some((v) => !!v);
    };
    const hasBorrowing = (key: string): boolean => {
      if (key in borrowingRoot) return true;
      const flags = borrowingFlags[key];
      if (!isRecord(flags)) return false;
      return Object.values(flags).some((v) => v === 'borrowed' || v === 'uncertain');
    };

    let list = concepts.filter(c => c.name.toLowerCase().includes(query.toLowerCase()));
    if (tagFilter === 'untagged') {
      list = list.filter(c => c.tag === 'untagged');
    } else if (tagFilter === 'review') {
      list = list.filter(c => c.tag === 'review');
    } else if (tagFilter === 'unreviewed') {
      // Unreviewed ≡ not yet confirmed AND no cognate assignment yet.
      // Formerly lived as a separate header tab; now a left-panel pill.
      list = list.filter(c => !hasCognateAssignment(c.key) && c.tag !== 'confirmed');
    } else if (tagFilter === 'flagged') {
      list = list.filter(c => c.tag === 'problematic' || hasSpeakerFlag(c.key));
    } else if (tagFilter === 'borrowings') {
      list = list.filter(c => hasBorrowing(c.key));
    } else if (tagFilter !== 'all') {
      const storeTag = storeTags.find(t => t.id === tagFilter);
      if (storeTag) list = list.filter(c => storeTag.concepts.includes(c.key));
    }
    // In annotate mode, show all concepts for the selected speaker (filter by real data when available)
    if (currentMode === 'annotate') {
      // No synthetic filtering — show the full concept list
    }
    if (sortMode === 'az') {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortMode === 'survey') {
      // Natural sort lives in src/lib/surveySort.ts — the same module the
      // regression tests import, so any future branch that reverts the
      // sidebar sort will fail CI instead of landing silently.
      list = [...list].sort((a, b) => {
        const av = a.surveyItem ?? '';
        const bv = b.surveyItem ?? '';
        if (av && !bv) return -1;
        if (!av && bv) return 1;
        return compareSurveyKeys(av, bv);
      });
    } else {
      list = [...list].sort((a, b) => a.id - b.id);
    }
    return list;
  }, [query, tagFilter, sortMode, currentMode, selectedSpeakers, enrichmentData, concepts, storeTags]);

  const hasSurveyItems = useMemo(() => concepts.some(c => !!c.surveyItem), [concepts]);

  const concept = concepts.find(c => c.id === conceptId) ?? concepts[0] ?? { id: 1, key: '1', name: '—', tag: 'untagged' as ConceptTag };
  const referenceFormLists = useMemo(
    () => resolveReferenceFormLists(enrichmentData, silConcepts, concept, primaryContactCodes, contactLanguageScripts),
    [concept, enrichmentData, silConcepts, primaryContactCodes, contactLanguageScripts],
  );
  const borrowingCandidates = useMemo<unknown>(() => {
    const borrowingRoot = isRecord(enrichmentData.borrowings) ? enrichmentData.borrowings
      : isRecord(enrichmentData.borrowing_candidates) ? enrichmentData.borrowing_candidates
      : null;
    if (!borrowingRoot) return null;
    return borrowingRoot[concept.key] ?? borrowingRoot[concept.name] ?? null;
  }, [concept, enrichmentData]);
  const speakerForms = useMemo<SpeakerForm[]>(() => {
    const activeSpeakers = selectedSpeakers.filter((speaker) => speakers.includes(speaker));
    const flagged = getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic');

    return activeSpeakers.map((speaker) => buildSpeakerForm(
      annotationRecords[speaker],
      concept,
      speaker,
      enrichmentData,
      flagged,
      primaryContactCodes,
    ));
  }, [annotationRecords, concept, enrichmentData, getTagsForConcept, selectedSpeakers, speakers, primaryContactCodes]);
  const reviewed = concepts.filter(c => c.tag === 'confirmed').length;
  const total = concepts.length;

  const goPrev = () => setConceptId(id => Math.max(1, id - 1));
  const goNext = () => setConceptId(id => Math.min(total, id + 1));

  useEffect(() => {
    setActiveConceptUI(concept.key);
  }, [concept.key, setActiveConceptUI]);

  useEffect(() => {
    function onGlobalKeyDown(e: KeyboardEvent) {
      if (e.defaultPrevented) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isInteractiveHotkeyTarget(e.target)) return;

      const key = e.key.toLowerCase();
      if (key === 'a') {
        e.preventDefault();
        setCurrentMode('annotate');
        setModeMenuOpen(false);
        setActionsMenuOpen(false);
        return;
      }
      if (key === 'c') {
        e.preventDefault();
        setCurrentMode('compare');
        setModeMenuOpen(false);
        setActionsMenuOpen(false);
        return;
      }
      if (key === 't') {
        e.preventDefault();
        setCurrentMode('tags');
        setModeMenuOpen(false);
        setActionsMenuOpen(false);
        return;
      }

      if (currentMode === 'tags' || total <= 1) return;

      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        goNext();
      }
    }

    window.addEventListener('keydown', onGlobalKeyDown);
    return () => window.removeEventListener('keydown', onGlobalKeyDown);
  }, [currentMode, total, setActiveConceptUI]);

  const toggleSpeaker = (s: string) => {
    if (currentMode === 'annotate') {
      setSelectedSpeakers([s]);
      setActiveSpeakerUI(s);
      usePlaybackStore.setState({ activeSpeaker: s });
      return;
    }
    setSelectedSpeakers(sel => sel.includes(s) ? sel.filter(x => x !== s) : [...sel, s]);
  };
  const addSpeaker = () => {
    if (speakerPicker && !selectedSpeakers.includes(speakerPicker)) setSelectedSpeakers([...selectedSpeakers, speakerPicker]);
  };
  const openImportModal = () => {
    setActionsMenuOpen(false);
    setImportModalOpen(true);
  };
  const handleImportComplete = (speakerId: string) => {
    setImportModalOpen(false);
    if (!speakerId) return;
    setSpeakerPicker(speakerId);
    if (currentMode === 'annotate') {
      setSelectedSpeakers([speakerId]);
      setActiveSpeakerUI(speakerId);
      usePlaybackStore.setState({ activeSpeaker: speakerId });
      return;
    }
    setSelectedSpeakers((existing) => existing.includes(speakerId) ? existing : [...existing, speakerId]);
  };

  return (
    <div className="h-screen overflow-hidden bg-slate-50 text-slate-800 font-sans antialiased flex flex-col">
      {/* ============ MINIMAL TOP BAR ============ */}
      <header className="relative z-50 shrink-0 h-14 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="relative flex h-full items-center justify-between px-5">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
                <Layers className="h-4 w-4" />
              </div>
              <span className="text-[15px] font-semibold tracking-tight text-slate-900">PARSE</span>
            </div>
            <div className="hidden items-center gap-3 md:flex">
              <div className="text-[11px] font-medium text-slate-500 tabular-nums">{reviewed} / {total} reviewed</div>
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" style={{ width: `${(reviewed/total)*100}%` }}/>
              </div>
            </div>
          </div>

          {/* The All / Unreviewed / Flagged / Borrowings tabs that used
              to live here are now left-panel tag pills (so this row
              has room to show batch status during long GPU runs). */}

          {/* ===== Inline batch status — reclaims the space freed by
               moving the filter tabs down into the left panel. Only
               renders when a batch is running / cancelling / has just
               completed. ===== */}
          {(batch.state.status === 'running' || batch.state.status === 'cancelling') && (
            <div
              className={`flex items-center gap-2 rounded-md border px-2.5 py-1 ${
                batch.state.status === 'cancelling'
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-indigo-200 bg-indigo-50'
              }`}
              data-testid="topbar-batch-status"
            >
              <Loader2 className={`h-3 w-3 shrink-0 animate-spin ${batch.state.status === 'cancelling' ? 'text-amber-600' : 'text-indigo-600'}`} />
              <span className={`text-[11px] font-medium ${batch.state.status === 'cancelling' ? 'text-amber-900' : 'text-indigo-900'}`}>
                {batch.state.status === 'cancelling'
                  ? 'Cancelling…'
                  : `Batch ${Math.min(batch.state.currentSpeakerIndex !== null ? batch.state.currentSpeakerIndex + 1 : batch.state.completedSpeakers, batch.state.totalSpeakers)}/${batch.state.totalSpeakers}`}
              </span>
              {batch.state.currentSpeaker && (
                <span className={`text-[11px] ${batch.state.status === 'cancelling' ? 'text-amber-700' : 'text-indigo-700'}`}>— {batch.state.currentSpeaker}</span>
              )}
              <div className={`h-1.5 w-16 shrink-0 overflow-hidden rounded-full ${batch.state.status === 'cancelling' ? 'bg-amber-100' : 'bg-indigo-100'}`}>
                {batch.state.currentProgress < 0.02 ? (
                  <div className={`h-full w-1/3 animate-pulse rounded-full ${batch.state.status === 'cancelling' ? 'bg-amber-400' : 'bg-indigo-400'}`} />
                ) : (
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${batch.state.status === 'cancelling' ? 'bg-amber-600' : 'bg-indigo-600'}`}
                    style={{ width: `${Math.round(batch.state.currentProgress * 100)}%` }}
                  />
                )}
              </div>
              {batch.state.currentMessage && (
                <span className={`hidden max-w-[180px] truncate text-[11px] lg:inline ${batch.state.status === 'cancelling' ? 'text-amber-600' : 'text-indigo-600'}`} title={batch.state.currentMessage}>
                  {batch.state.currentMessage}
                </span>
              )}
              {batch.state.status === 'running' && (
                <button
                  onClick={() => batch.cancel()}
                  className="rounded border border-indigo-300 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700 hover:bg-indigo-100"
                  data-testid="topbar-batch-cancel"
                  title="Stop after the current speaker finishes. Current speaker's compute continues — razhan/whisper can't be aborted mid-transcription."
                >
                  Cancel
                </button>
              )}
            </div>
          )}
          {/* Persistent offset-job status chip. Survives modal dismissal
              (even though we now lock the modal while the job runs, a
              separate header indicator matters for the applying phase
              and gives the user a single "what is PARSE doing" glance).
              Idle state → renders nothing. Error state → click re-opens
              the modal so the traceback + crash log are one click away. */}
          {offsetState.phase !== 'idle' && (offsetState.phase === 'detecting' || offsetState.phase === 'applying' || offsetState.phase === 'error') && (() => {
            const isError = offsetState.phase === 'error';
            const isApplying = offsetState.phase === 'applying';
            const isDetecting = offsetState.phase === 'detecting';
            const label = isError
              ? 'Offset failed'
              : isApplying
              ? 'Applying offset…'
              : (offsetState.phase === 'detecting' && offsetState.progressMessage) || 'Detecting offset…';
            return (
              <div
                className={`flex items-center gap-2 rounded-md border px-2.5 py-1 ${
                  isError
                    ? 'border-rose-200 bg-rose-50'
                    : 'border-indigo-200 bg-indigo-50'
                }`}
                data-testid="topbar-offset-status"
              >
                {isError ? (
                  <AlertCircle className="h-3 w-3 shrink-0 text-rose-600"/>
                ) : (
                  <Loader2 className="h-3 w-3 shrink-0 animate-spin text-indigo-600"/>
                )}
                <span className={`max-w-[200px] truncate text-[11px] font-medium ${isError ? 'text-rose-900' : 'text-indigo-900'}`} title={isError ? offsetState.message : label}>
                  {label}
                </span>
                {isDetecting && (
                  <div className="h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-indigo-100">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                      style={{ width: `${Math.max(3, Math.round(offsetState.progress))}%` }}
                    />
                  </div>
                )}
                {!isError && protectedLexemeCount > 0 && (
                  <span
                    data-testid="topbar-offset-protected-badge"
                    title={`${protectedLexemeCount} lexeme${protectedLexemeCount === 1 ? '' : 's'} locked — will be skipped by the offset`}
                    className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700"
                  >
                    <Anchor className="h-2.5 w-2.5"/>
                    {protectedLexemeCount} locked
                  </span>
                )}
                {isError && offsetState.jobId && (
                  <button
                    onClick={() => openJobLogs(offsetState.jobId!)}
                    className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-rose-700 underline hover:text-rose-800"
                    data-testid="topbar-offset-view-log"
                  >
                    View crash log
                  </button>
                )}
                {isError && (
                  <button
                    onClick={closeOffsetModal}
                    className="rounded px-1 text-[11px] text-slate-500 hover:text-slate-700"
                    aria-label="Dismiss offset status"
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })()}

          {batch.state.status === 'complete' && !reportOpen && (
            <div
              className={`flex items-center gap-2 rounded-md border px-2.5 py-1 ${
                batch.state.cancelled
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-emerald-200 bg-emerald-50'
              }`}
              data-testid="topbar-batch-complete"
            >
              <Check className={`h-3 w-3 shrink-0 ${batch.state.cancelled ? 'text-amber-600' : 'text-emerald-600'}`} />
              <span className={`text-[11px] font-medium ${batch.state.cancelled ? 'text-amber-900' : 'text-emerald-900'}`}>
                {batch.state.cancelled ? 'Cancelled' : 'Done'} · {batch.state.outcomes.filter(o => o.status === 'complete').length} ok
                {batch.state.outcomes.filter(o => o.status === 'error').length > 0 && `, ${batch.state.outcomes.filter(o => o.status === 'error').length} err`}
                {batch.state.outcomes.filter(o => o.status === 'cancelled').length > 0 && `, ${batch.state.outcomes.filter(o => o.status === 'cancelled').length} skip`}
              </span>
              <button
                onClick={() => setReportOpen(true)}
                className={`rounded px-1.5 py-0.5 text-[11px] font-semibold underline ${batch.state.cancelled ? 'text-amber-700 hover:text-amber-800' : 'text-emerald-700 hover:text-emerald-800'}`}
                data-testid="topbar-batch-view-report"
              >
                View report
              </button>
              <button
                onClick={() => batch.reset()}
                className="rounded px-1 text-[11px] text-slate-500 hover:text-slate-700"
                aria-label="Dismiss batch status"
              >
                ×
              </button>
            </div>
          )}

          <div className="flex items-center gap-2">
            {/* Mode dropdown */}
            <div className="relative">
              <button
                onClick={() => { setModeMenuOpen(v => !v); setActionsMenuOpen(false); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                {currentMode === 'annotate' ? 'Annotate' : currentMode === 'compare' ? 'Compare' : 'Tags'}
                <CDown className="h-3 w-3 text-slate-400"/>
              </button>
              {modeMenuOpen && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setModeMenuOpen(false)}/>
                  <div className="absolute right-0 z-[60] mt-1.5 w-48 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    {([
                      ['annotate','Annotate', 'A', Type],
                      ['compare','Compare', 'C', Layers],
                      ['tags','Tags', 'T', Tags],
                    ] as const).map(([key,label,hotkey,Icon]) => (
                      <button
                        key={key}
                        onClick={() => { setCurrentMode(key); setModeMenuOpen(false); }}
                        className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition ${currentMode===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-700 hover:bg-slate-50'}`}
                      >
                        <Icon className="h-3.5 w-3.5 text-slate-400"/>
                        <span className="flex-1">{label}</span>
                        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{hotkey}</span>
                        {currentMode===key && <Check className="h-3.5 w-3.5 text-indigo-600"/>}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Actions dropdown */}
            <div className="relative">
              <button
                onClick={() => { setActionsMenuOpen(v => !v); setModeMenuOpen(false); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Actions
                <CDown className="h-3 w-3 text-slate-400"/>
              </button>
              {actionsMenuOpen && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setActionsMenuOpen(false)}/>
                  <div className="absolute right-0 z-[60] mt-1.5 w-60 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
                    <button
                      onClick={openImportModal}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Import className="h-3.5 w-3.5 text-slate-400"/> Import Speaker Data…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); openRunModal('Run Audio Normalization', ['normalize']); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-normalize"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <AudioLines className="h-3.5 w-3.5 text-slate-400"/>
                      Run Audio Normalization…
                    </button>
                    <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-slate-700">
                      <Mic className="h-3.5 w-3.5 shrink-0 text-slate-400"/>
                      <label htmlFor="stt-language" className="shrink-0 text-[11px] text-slate-500">Language</label>
                      <input
                        id="stt-language"
                        value={sttLanguage}
                        onChange={e => setSttLanguage(e.target.value.trim().toLowerCase())}
                        placeholder="auto"
                        maxLength={8}
                        spellCheck={false}
                        className="w-16 rounded border border-slate-200 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none"
                        title="ISO 639-1 code (e.g. en, de, ar). Whisper does not accept ISO 639-3 codes like ckb. Leave blank to auto-detect."
                      />
                      <button
                        onClick={() => { setActionsMenuOpen(false); openRunModal('Run STT', ['stt']); }}
                        disabled={batch.state.status === 'running'}
                        data-testid="actions-stt"
                        className="ml-auto inline-flex items-center gap-1 rounded bg-indigo-600 px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Run STT…
                      </button>
                    </div>
                    <button
                      onClick={() => { setActionsMenuOpen(false); openRunModal('Generate ORTH (razhan)', ['ortho']); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-generate-ortho"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Type className="h-3.5 w-3.5 text-slate-400"/>
                      Generate ORTH (razhan)…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); openRunModal('Run IPA Transcription', ['ipa']); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-ipa"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Type className="h-3.5 w-3.5 text-slate-400"/>
                      Run IPA Transcription…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); openRunModal('Run Full Pipeline'); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-run-full-pipeline"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Workflow className="h-3.5 w-3.5 text-slate-400"/>
                      Run Full Pipeline…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); void crossSpeakerJob.run(); }}
                      disabled={crossSpeakerJob.state.status === 'running'}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Network className="h-3.5 w-3.5 text-slate-400"/>
                      {crossSpeakerJob.state.status === 'running' ? 'Matching…' : 'Run Cross-Speaker Match'}
                    </button>
                    <div className="my-1 border-t border-slate-100"/>
                    <button
                      data-testid="concept-import-menu"
                      onClick={() => { setActionsMenuOpen(false); conceptImportInputRef.current?.click(); }}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Upload className="h-3.5 w-3.5 text-slate-400"/> Import Custom Tags
                    </button>
                    <button
                      onClick={() => openDecisionsImport(true)}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Upload className="h-3.5 w-3.5 text-slate-400"/> Load Decisions
                    </button>
                    <button onClick={() => handleSaveDecisions(true)} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50">
                      <Save className="h-3.5 w-3.5 text-slate-400"/> Save Decisions
                    </button>
                    <button
                      onClick={handleExportLingPy}
                      disabled={exporting}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                    >
                      <Download className="h-3.5 w-3.5 text-indigo-400"/>
                      {exporting ? 'Exporting…' : 'Export LingPy TSV'}
                    </button>
                    <div className="my-1 border-t border-slate-100"/>
                    <button
                      onClick={resetProject}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-rose-600 hover:bg-rose-50"
                    >
                      <Trash2 className="h-3.5 w-3.5"/> Reset Project
                    </button>
                  </div>
                </>
              )}
              <input
                ref={conceptImportInputRef}
                data-testid="concept-import-input"
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void importConceptTagFile(file);
                  if (conceptImportInputRef.current) conceptImportInputRef.current.value = '';
                }}
              />
              {conceptImportSummary && (
                <div data-testid="concept-import-summary" className="absolute right-0 top-full z-[70] mt-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] text-emerald-700 shadow-sm">{conceptImportSummary}</div>
              )}
              {conceptImportError && (
                <div data-testid="concept-import-error" className="absolute right-0 top-full z-[70] mt-1 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[10px] text-rose-700 shadow-sm">{conceptImportError}</div>
              )}
            </div>

            {/* Batch banners moved INTO the header above — previously
                floated below the topbar and obscured the mode tabs +
                Actions menu + waveform controls. */}
            {activeJobs.length > 0 && (
              <div className="pointer-events-auto absolute right-5 top-full z-40 mt-1 flex flex-col gap-1 rounded-md border border-slate-200 bg-white/95 px-3 py-1 shadow-sm backdrop-blur" data-testid="topbar-action-statuses">
                {activeJobs.map((job, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    {job.state.status === 'running' && (
                      <>
                        <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
                        <span className="text-slate-600">{job.state.label}</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200">
                          {job.state.progress < 0.05 ? (
                            <div className="h-full w-2/5 animate-pulse rounded-full bg-indigo-400" />
                          ) : (
                            <div
                              className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                              style={{ width: `${Math.round(job.state.progress * 100)}%` }}
                            />
                          )}
                        </div>
                        {job.state.progress < 0.05 ? (
                          <span className="text-slate-400">{job.state.message ?? 'Starting…'}</span>
                        ) : (
                          <span className="tabular-nums text-slate-400">{Math.round(job.state.progress * 100)}%</span>
                        )}
                        {job.state.etaMs !== null && job.state.etaMs > 0 && (
                          <span className="tabular-nums text-slate-400" title="Estimated time remaining">
                            · ~{formatEta(job.state.etaMs)} left
                          </span>
                        )}
                      </>
                    )}
                    {job.state.status === 'complete' && (
                      <>
                        <Check className="h-3 w-3 text-emerald-500" />
                        <span className="text-emerald-600">{job.state.label?.replace('…', '')} done</span>
                      </>
                    )}
                    {job.state.status === 'error' && (
                      <>
                        <XCircle className="h-3 w-3 text-rose-500" />
                        <span
                          className="max-w-[560px] truncate text-rose-600"
                          title={job.state.error ?? ''}
                          data-testid="job-error-text"
                        >
                          {job.state.error}
                        </span>
                        <button
                          onClick={() => {
                            if (job.state.error) {
                              console.error('[PARSE action job]', job.state.label, job.state.error);
                              alert(`${job.state.label}\n\n${job.state.error}`);
                            }
                          }}
                          className="text-[10px] text-rose-600 underline hover:text-rose-700"
                          title="Show full error"
                          data-testid="job-error-details"
                        >
                          Details
                        </button>
                        <button
                          onClick={() => { void job.run(); }}
                          className="text-[10px] text-rose-600 underline hover:text-rose-700"
                        >
                          Retry
                        </button>
                        <button
                          onClick={job.reset}
                          className="text-[10px] text-slate-500 underline hover:text-slate-700"
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => setDarkMode(v => !v)}
              title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              {darkMode ? <Sun className="h-4 w-4"/> : <Moon className="h-4 w-4"/>}
            </button>
          </div>
        </div>
      </header>
      {configError && configError !== dismissedConfigError && (
        <div className="shrink-0 flex items-center gap-3 border-b border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="flex-1">
            <span className="font-semibold">Server error—speakers may not load. </span>
            {configError}
          </div>
          <button
            onClick={() => { setDismissedConfigError(null); loadConfig(); }}
            className="shrink-0 rounded px-2 py-1 text-xs font-medium hover:bg-rose-100"
          >Retry</button>
          <button
            onClick={() => setDismissedConfigError(configError)}
            className="shrink-0 rounded p-1 hover:bg-rose-100"
            aria-label="Dismiss"
          ><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      {/* ============ BODY: left sidebar / main / right panel ============ */}
      <div className="flex min-h-0 flex-1">
        {/* LEFT SIDEBAR */}
        <ConceptSidebar
          query={query}
          onQueryChange={setQuery}
          sortMode={sortMode}
          onSortModeChange={setSortMode}
          hasSurveyItems={hasSurveyItems}
          filteredConcepts={filtered}
          tagFilter={tagFilter}
          onTagFilterChange={setTagFilter}
          tags={tagsList}
          activeConceptId={conceptId}
          onConceptSelect={setConceptId}
        />

        {/* MAIN + AI STACK */}
        <div className="flex min-w-0 flex-1 flex-col">
          {currentMode === 'tags' ? (
          <>
            <ManageTagsView
              tags={tagsList}
              concepts={concepts}
              onCreateTag={(name, color) => { if (!name.trim()) return; storeAddTag(name, color); setNewTagName(''); }}
              onUpdateTag={(id, name) => {
                const existing = storeTags.find(t => t.id === id);
                if (!existing || !name.trim()) return;
                updateStoreTag(id, { label: name.trim(), color: existing.color });
              }}
              tagSearch={tagSearch}
              setTagSearch={setTagSearch}
              newTagName={newTagName}
              setNewTagName={setNewTagName}
              newTagColor={newTagColor}
              setNewTagColor={setNewTagColor}
              showUntagged={showUntagged}
              setShowUntagged={setShowUntagged}
              selectedTagId={selectedTagId}
              setSelectedTagId={setSelectedTagId}
              conceptSearch={tagConceptSearch}
              setConceptSearch={setTagConceptSearch}
              tagConcept={tagConcept}
              untagConcept={untagConcept}
            />
            <AIChat
              height={aiHeight}
              minimized={aiMinimized}
              onResizeStart={onResizeStart}
              onMinimize={() => setAiMinimized(v => !v)}
              conceptName={concept.name}
              conceptId={concept.id}
              speakerCount={selectedSpeakers.length}
              chatSession={chatSession}
            />
          </>
          ) : currentMode === 'annotate' ? (
          <>
            <AnnotateView
              concept={concept}
              speaker={selectedSpeakers[0] ?? 'Mand01'}
              totalConcepts={total}
              onPrev={goPrev}
              onNext={goNext}
              audioUrl={deriveAudioUrl(annotationRecords[selectedSpeakers[0] ?? ''])}
              peaksUrl={selectedSpeakers[0] ? `/peaks/${selectedSpeakers[0]}.json` : undefined}
              onCaptureOffsetAnchor={captureAnchorFromBar}
              captureToast={captureToast}
            />
            <AIChat
              height={aiHeight}
              minimized={aiMinimized}
              onResizeStart={onResizeStart}
              onMinimize={() => setAiMinimized(v => !v)}
              conceptName={concept.name}
              conceptId={concept.id}
              speakerCount={selectedSpeakers.length}
              chatSession={chatSession}
            />
          </>
          ) : (
          <>
          <main className="flex-1 overflow-y-auto px-8 py-6">
            <div className="mx-auto max-w-5xl space-y-5">

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <button onClick={goPrev} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800">
                    <ChevronLeft className="h-4 w-4"/>
                  </button>
                  <div>
                    <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                      Concept <span className="font-mono">#{concept.id}</span> <span>·</span> <span>{concept.id} of {total}</span>
                    </div>
                    <h1 className="mt-0.5 text-[28px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
                  </div>
                  <button onClick={goNext} className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-800">
                    <ChevronRight className="h-4 w-4"/>
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic')
                      ? null
                      : tagConcept('problematic', concept.key)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${getTagsForConcept(concept.key).some((tag) => tag.id === 'problematic') ? 'border-amber-300 bg-amber-100 text-amber-800' : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'}`}
                  >
                    <Flag className="h-3.5 w-3.5"/> Flag
                  </button>
                  <button
                    onClick={() => getTagsForConcept(concept.key).some((tag) => tag.id === 'confirmed')
                      ? null
                      : tagConcept('confirmed', concept.key)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold shadow-sm transition ${getTagsForConcept(concept.key).some((tag) => tag.id === 'confirmed') ? 'bg-emerald-700 text-white' : 'bg-emerald-600 text-white hover:bg-emerald-700'}`}
                  >
                    <Check className="h-3.5 w-3.5"/> Accept concept
                  </button>
                </div>
              </div>

              {/* Populate-summary banner — appears after a Save & populate
                  job finishes. The green variant confirms N forms landed;
                  the amber variant surfaces the backend's explicit
                  warning when 0 forms were fetched (offline providers,
                  concepts outside ASJP's list, etc.) instead of silently
                  showing "complete" and an empty Reference Forms grid. */}
              {populateSummary && primaryContactCodes.length > 0 && (
                <ClefPopulateSummaryBanner
                  summary={populateSummary}
                  onDismiss={() => setPopulateSummary(null)}
                  onRetryWithProviders={() => {
                    setClefInitialTab('populate');
                    setClefModalOpen(true);
                  }}
                />
              )}

              {/* Reference forms — gated on the user's CLEF configuration.
                  Hidden entirely when no primary contact languages are
                  set; renders exactly one card per configured primary
                  otherwise. Each card lists every populated form with
                  a checkbox so the user picks which forms contribute
                  to the similarity score. Selections persist into
                  ``_meta.form_selections`` via the backend; default is
                  "all selected". No orthography -> IPA conversion
                  happens -- forms are tagged by Unicode block (see
                  ``classifyRawFormString``) and displayed verbatim. */}
              {primaryContactCodes.length > 0 && (
                <SectionCard title="Reference forms">
                  <div className={`grid gap-4 ${primaryContactCodes.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
                    {primaryContactCodes.map((code, idx) => {
                      const { tone, dir } = referenceCardStyle(code, idx);
                      const label = contactLanguageNames[code] ?? code.toUpperCase();
                      const entries = referenceFormLists[code] ?? [];
                      const selectionKey = `${concept.name}|${code}`;
                      const persistedSelection = resolveFormSelection(clefStatus?.meta, concept.name, code);
                      const localSelection = selectionKey in localFormSelections ? localFormSelections[selectionKey] : undefined;
                      // Effective selection: local overlay takes precedence
                      // over persisted meta; null from either means "no
                      // explicit selection" -> all forms active by default.
                      const effective: string[] | null = localSelection !== undefined ? localSelection : persistedSelection;
                      const allSelected = effective === null;
                      const selectedSet = new Set(effective ?? []);
                      const isSelected = (rawForm: string) => allSelected || selectedSet.has(rawForm);
                      const selectedCount = allSelected ? entries.length : entries.filter((e) => selectedSet.has(e.raw)).length;

                      // Click handlers -- each call writes the next explicit
                      // list (never null) so we always persist intent. "Select
                      // all" writes the full list of raw strings rather than
                      // passing null so the selection survives even if a
                      // future populate adds new forms and the user re-opens
                      // this concept without re-clicking.
                      const rawAll = entries.map((e) => e.raw);
                      const onToggle = (rawForm: string) => {
                        const current = new Set(allSelected ? rawAll : rawAll.filter((r) => selectedSet.has(r)));
                        if (current.has(rawForm)) current.delete(rawForm);
                        else current.add(rawForm);
                        // Preserve the entries' natural order in the persisted list.
                        void saveFormSelection(concept.name, code, rawAll.filter((r) => current.has(r)));
                      };
                      const onSelectAll = () => { void saveFormSelection(concept.name, code, rawAll.slice()); };
                      const onSelectNone = () => { void saveFormSelection(concept.name, code, []); };

                      return (
                        <div key={code} className="rounded-lg border border-slate-100 bg-slate-50/40 p-4" data-testid={`reference-form-${code}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`text-[10px] font-semibold uppercase tracking-wider ${tone}`}>
                              {label} <span className="ml-1 font-mono text-slate-300">({code})</span>
                            </span>
                            {entries.length > 0 && (
                              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                                <span data-testid={`reference-form-${code}-count`}>{selectedCount}/{entries.length} selected</span>
                                {entries.length > 1 && (
                                  <>
                                    <button
                                      type="button"
                                      className="text-slate-500 hover:text-slate-800 underline-offset-2 hover:underline"
                                      data-testid={`reference-form-${code}-select-all`}
                                      onClick={onSelectAll}
                                    >
                                      All
                                    </button>
                                    <button
                                      type="button"
                                      className="text-slate-500 hover:text-slate-800 underline-offset-2 hover:underline"
                                      data-testid={`reference-form-${code}-select-none`}
                                      onClick={onSelectNone}
                                    >
                                      None
                                    </button>
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                          {entries.length === 0 ? (
                            <div className="mt-2 text-sm text-slate-400">No reference data</div>
                          ) : (
                            <ul className="mt-2 space-y-1.5">
                              {entries.map((entry, entryIdx) => {
                                const selected = isSelected(entry.raw);
                                return (
                                  <li
                                    key={entry.raw}
                                    data-testid={`reference-form-${code}-entry-${entryIdx}`}
                                    data-selected={selected}
                                    className={
                                      'flex items-start gap-3 rounded-md border px-2.5 py-1.5 transition-colors ' +
                                      (selected
                                        ? 'border-slate-300 bg-white'
                                        : 'border-transparent bg-slate-100/50 opacity-60')
                                    }
                                  >
                                    <input
                                      type="checkbox"
                                      checked={selected}
                                      onChange={() => onToggle(entry.raw)}
                                      data-testid={`reference-form-${code}-checkbox-${entryIdx}`}
                                      className="mt-1 h-3.5 w-3.5 cursor-pointer accent-slate-700"
                                      aria-label={`Select ${entry.raw}`}
                                    />
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-baseline gap-2">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-400">Script</span>
                                        <span className="font-serif text-lg text-slate-900" dir={entry.script ? dir : 'ltr'}>
                                          {entry.script || '—'}
                                        </span>
                                      </div>
                                      <div className="mt-0.5 flex items-baseline gap-2">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-400">IPA</span>
                                        <span className="font-mono text-[12px] text-slate-600">
                                          {entry.ipa ? `/${entry.ipa}/` : '—'}
                                        </span>
                                      </div>
                                      {entry.sources.length > 0 && (
                                        <div className="mt-0.5 text-[10px] font-mono text-slate-400">
                                          {entry.sources.join(', ')}
                                        </div>
                                      )}
                                    </div>
                                    {entry.audioUrl && (
                                      <button
                                        type="button"
                                        title="Play reference audio"
                                        onClick={() => { void new Audio(entry.audioUrl!).play().catch(() => {}); }}
                                        className="text-slate-300 hover:text-slate-500"
                                      >
                                        <Volume2 className="h-3.5 w-3.5"/>
                                      </button>
                                    )}
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                          {entries.length > 0 && effective !== null && effective.length === 0 && (
                            <div className="mt-2 text-[11px] text-amber-600" data-testid={`reference-form-${code}-opt-out-warning`}>
                              No forms selected — similarity for {label} will be skipped.
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </SectionCard>
              )}

              <SectionCard title={`Speaker forms · ${selectedSpeakers.length} selected`}
                aside={<button className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-slate-800"><ArrowUpDown className="h-3 w-3"/> Sort by similarity</button>}>
                <div className="overflow-hidden rounded-lg border border-slate-100">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50/70 text-[10px] uppercase tracking-wider text-slate-500">
                        <th className="px-3 py-2 text-left font-semibold">Speaker</th>
                        <th className="px-3 py-2 text-left font-semibold">IPA & utterances</th>
                        {primaryContactCodes.map((code) => (
                          <th
                            key={code}
                            className="px-3 py-2 text-left font-semibold"
                            data-testid={`sim-col-header-${code}`}
                          >
                            {(contactLanguageNames[code] ?? code.toUpperCase())} sim.
                          </th>
                        ))}
                        <th className="px-3 py-2 text-left font-semibold">Cognate</th>
                        <th className="px-3 py-2 text-right font-semibold">Flag</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {speakerForms.map(f => {
                        const isExpanded = expandedLexemes.has(f.speaker);
                        const cognateColor =
                          f.cognate === 'A' ? '#dcfce7' :
                          f.cognate === 'B' ? '#dbeafe' :
                          f.cognate === 'C' ? '#fef9c3' :
                          null;
                        return (
                        <React.Fragment key={f.speaker}>
                        <tr
                          data-testid={`speaker-row-${f.speaker}`}
                          role="button"
                          onClick={() => toggleLexemeExpanded(f.speaker)}
                          className={`cursor-pointer bg-white transition hover:bg-indigo-50/30 ${isExpanded ? 'bg-indigo-50/40' : ''}`}
                        >
                          <td className="px-3 py-2.5 font-mono text-[11px] font-medium text-slate-700">{f.speaker}</td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-2">
                              <span
                                data-testid={`lexeme-toggle-${f.speaker}`}
                                className="font-mono text-[13px] text-indigo-700"
                              >
                                /{f.ipa || '—'}/
                              </span>
                              <ChevronDown
                                className={`h-3 w-3 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                              />
                            </div>
                            <div className="text-[10px] text-slate-400">{f.utterances} utterance{f.utterances!==1?'s':''}</div>
                          </td>
                          {primaryContactCodes.map((code) => (
                            <td
                              key={code}
                              className="px-3 py-2.5"
                              data-testid={`sim-cell-${f.speaker}-${code}`}
                            >
                              <SimBar value={f.similarityByLang[code] ?? null}/>
                            </td>
                          ))}
                          <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                            <CognateCell
                              speaker={f.speaker}
                              group={f.cognate}
                              onCycle={() => cycleSpeakerCognate(concept.key, f.speaker, f.cognate)}
                              onReset={() => resetSpeakerCognate(concept.key, f.speaker)}
                            />
                          </td>
                          <td className="px-3 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                            <button
                              data-testid={`speaker-flag-${f.speaker}`}
                              title={`Toggle flag for ${f.speaker}`}
                              onClick={() => toggleSpeakerFlag(concept.key, f.speaker, f.flagged)}
                              className={`inline-grid h-6 w-6 place-items-center rounded-md ${f.flagged?'bg-amber-100 text-amber-600':'text-slate-300 hover:bg-slate-100 hover:text-slate-500'}`}
                            >
                              <Flag className="h-3 w-3"/>
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr data-testid={`lexeme-detail-row-${f.speaker}`}>
                            {/* Speaker + IPA + N sim columns + Cognate + Flag. */}
                            <td colSpan={4 + primaryContactCodes.length} className="bg-slate-50 p-2">
                              <LexemeDetail
                                speaker={f.speaker}
                                conceptId={concept.key}
                                conceptLabel={concept.name}
                                ipa={f.ipa}
                                ortho={f.ortho}
                                startSec={f.startSec}
                                endSec={f.endSec}
                                cognateGroup={f.cognate !== '—' ? f.cognate : null}
                                cognateColor={cognateColor}
                              />
                            </td>
                          </tr>
                        )}
                        </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </SectionCard>

              <SectionCard title="Cognate decision" aside={<Pill tone="indigo">2 groups proposed</Pill>}>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                    onClick={() => persistCognateDecision(concept.key, 'accepted')}
                  >
                    <Check className="h-3.5 w-3.5"/> Accept grouping
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => persistCognateDecision(concept.key, 'split')}
                  >
                    <Split className="h-3.5 w-3.5"/> Split
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => persistCognateDecision(concept.key, 'merge')}
                  >
                    <GitMerge className="h-3.5 w-3.5"/> Merge
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const current = getStoredCognateDecision(enrichmentData, concept.key)?.decision ?? 'accepted';
                      const next: CognateDecisionValue = current === 'accepted'
                        ? 'split'
                        : current === 'split'
                          ? 'merge'
                          : 'accepted';
                      persistCognateDecision(concept.key, next);
                    }}
                  >
                    <RotateCw className="h-3.5 w-3.5"/> Cycle
                  </button>
                </div>
              </SectionCard>

              <SectionCard title="Potential borrowings"
                aside={<button onClick={() => setBorrowingsOpen(v=>!v)} className="text-slate-400 hover:text-slate-700">{borrowingsOpen ? <ChevronUp className="h-4 w-4"/> : <ChevronDown className="h-4 w-4"/>}</button>}>
                {borrowingsOpen ? (
                  borrowingCandidates != null ? (
                    Array.isArray(borrowingCandidates)
                      ? <div className="space-y-2">
                          {(borrowingCandidates as unknown[]).map((entry, i) => (
                            <div key={i} className="flex items-start gap-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3">
                              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"/>
                              <div className="text-xs text-slate-600">{String(entry)}</div>
                            </div>
                          ))}
                        </div>
                      : <div className="flex items-start gap-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3">
                          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"/>
                          <div className="text-xs text-slate-600">{String(borrowingCandidates)}</div>
                        </div>
                  ) : (
                    <div className="text-xs text-slate-400">No borrowing candidates detected for this concept.</div>
                  )
                ) : (
                  <div className="text-xs text-slate-400">{borrowingCandidates != null ? '1 candidate hidden' : 'No borrowing data'}</div>
                )}
              </SectionCard>

              <SectionCard title="Notes">
                <textarea value={notes} onChange={e => setNotes(e.target.value)}
                  onBlur={() => {
                    try {
                      const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
                      const stored = raw ? JSON.parse(raw) as Record<string, string> : {};
                      stored[conceptId.toString()] = notes;
                      window.localStorage.setItem(COMPARE_NOTES_STORAGE_KEY, JSON.stringify(stored));
                    } catch {
                      // non-fatal localStorage failure
                    }
                  }}
                  placeholder="Add observations, etymological notes, or questions for review…"
                  className="min-h-[90px] w-full resize-none rounded-lg border border-slate-200 bg-slate-50/40 p-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"/>
              </SectionCard>

              <div className="flex items-center justify-between border-t border-slate-200 pt-5">
                <span className="text-[11px] text-slate-400">Concept {concept.id} of {total}</span>
                <div className="flex gap-2">
                  <button onClick={goPrev} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
                    <ChevronLeft className="h-3.5 w-3.5"/> Previous
                  </button>
                  <button onClick={goNext} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
                    Next <ChevronRight className="h-3.5 w-3.5"/>
                  </button>
                </div>
              </div>
            </div>
          </main>

          {/* BOTTOM AI CHAT */}
          <AIChat
            height={aiHeight}
            minimized={aiMinimized}
            onResizeStart={onResizeStart}
            onMinimize={() => setAiMinimized(v => !v)}
            conceptName={concept.name}
            conceptId={concept.id}
            speakerCount={selectedSpeakers.length}
            chatSession={chatSession}
          />
          </>
          )}
        </div>

        {/* RIGHT PANEL */}
        <RightPanel
          panelOpen={panelOpen}
          onTogglePanel={() => setPanelOpen((v) => !v)}
          currentMode={currentMode}
          selectedSpeakers={selectedSpeakers}
          speakers={speakers}
          conceptCount={concepts.length}
          speakerPicker={speakerPicker}
          onSpeakerSelect={(speakerId) => {
            if (currentMode === 'annotate') setSelectedSpeakers([speakerId]);
            else setSpeakerPicker(speakerId);
          }}
          onAddSpeaker={addSpeaker}
          onToggleSpeaker={toggleSpeaker}
          computeMode={computeMode}
          onComputeModeChange={setComputeMode}
          onComputeRun={handleComputeRun}
          crossSpeakerJobStatus={crossSpeakerJob.state.status}
          computeJobStatus={computeJobState.status}
          computeJobProgress={computeJobState.progress}
          computeJobEtaMs={computeJobState.etaMs}
          computeJobError={computeJobState.error}
          clefConfigured={clefConfigured}
          onOpenSourcesReport={() => setSourcesReportOpen(true)}
          onOpenClefConfig={() => setClefModalOpen(true)}
          onRefreshEnrichments={() => { void useEnrichmentStore.getState().load(); }}
          tagFilter={tagFilter}
          onTagFilterChange={setTagFilter}
          onOpenLoadDecisions={() => openDecisionsImport(false)}
          onSaveDecisions={() => handleSaveDecisions(false)}
          onExportLingPy={handleExportLingPy}
          exporting={exporting}
          onOpenCommentsImport={() => setCommentsImportOpen(true)}
          activeActionSpeaker={activeActionSpeaker}
          offsetPhase={offsetState.phase}
          onDetectOffset={() => { void detectOffsetForSpeaker(); }}
          onOpenManualOffset={openManualOffset}
          annotateSpeakerTools={selectedSpeakers[0] ? <LexemeSearchBlock speaker={selectedSpeakers[0]} conceptId={concept.id} /> : null}
          annotateAuxTools={<TranscriptionLanesControls />}
          onSaveAnnotations={() => {
            const speaker = selectedSpeakers[0];
            if (speaker) void useAnnotationStore.getState().saveSpeaker(speaker);
          }}
        />
      </div>

      <input
        type="file"
        accept=".json"
        ref={decisionsImportRef}
        style={{ display: 'none' }}
        onChange={handleDecisionsImport}
      />
      <Modal open={importModalOpen} onClose={() => setImportModalOpen(false)} title="Import Speaker">
        <SpeakerImport onImportComplete={handleImportComplete} />
      </Modal>
      <TranscriptionRunModal
        open={runModal !== null}
        title={runModal?.title ?? 'Run transcription'}
        fixedSteps={runModal?.fixedSteps}
        speakers={Object.keys(annotationRecords).sort()}
        defaultSelectedSpeaker={activeActionSpeaker}
        onClose={() => setRunModal(null)}
        onConfirm={(confirm) => {
          // Capture which steps the user asked for so the batch report
          // modal knows which columns to render.
          setReportStepsRun(confirm.steps);
          handleRunConfirm(confirm);
        }}
      />
      <BatchReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        outcomes={batch.state.outcomes}
        stepsRun={reportStepsRun}
        onRerunFailed={handleRerunFailed}
      />
      <ClefConfigModal
        open={clefModalOpen}
        initialTab={clefInitialTab}
        onClose={() => {
          setClefModalOpen(false);
          setClefInitialTab('languages');
        }}
        onSaved={() => {
          // Save-only (no populate): just refresh our cached CLEF status
          // so the Reference Forms panel re-renders with the new primary
          // languages. No compute job is started here — the modal's
          // "Save & populate" button is the only path that triggers work.
          void refreshClefStatus();
        }}
        onPopulateStarted={(jobId) => {
          // Hand the running contact-lexemes job to crossSpeakerJob so it
          // surfaces in the global header chip just like STT / IPA /
          // forced-align / full_pipeline. The onComplete hook on
          // crossSpeakerJob will reload enrichments + CLEF status when
          // the backend finishes, so the Reference Forms cards populate
          // automatically without a manual refresh.
          void refreshClefStatus();
          crossSpeakerJob.adopt(jobId);
        }}
      />
      <ClefSourcesReportModal
        open={sourcesReportOpen}
        onClose={() => setSourcesReportOpen(false)}
      />
      <OffsetAdjustmentModal
        open={offsetState.phase !== 'idle'}
        offsetState={offsetState}
        manualAnchors={manualAnchors}
        manualConsensus={manualConsensus}
        manualBusy={manualBusy}
        protectedLexemeCount={protectedLexemeCount}
        onClose={closeOffsetModal}
        onCaptureCurrentSelection={() => {
          const result = captureCurrentAnchor();
          if (!result.ok) {
            setOffsetState({ phase: 'error', message: result.message });
          }
        }}
        onRemoveManualAnchor={removeManualAnchor}
        onSubmitManualOffset={() => { void submitManualOffset(); }}
        onApplyDetectedOffset={() => { void applyDetectedOffset(); }}
        onOpenManualOffset={openManualOffset}
        onOpenJobLogs={openJobLogs}
      />
      <JobLogsModal
        jobId={jobLogsOpen}
        onClose={closeJobLogs}
      />
      <Modal open={commentsImportOpen} onClose={() => setCommentsImportOpen(false)} title="Import Audition Comments">
        <CommentsImport onImportComplete={() => setCommentsImportOpen(false)} />
      </Modal>
    </div>
  );
}

// Crash-log modal. Fetches the worker error + traceback + stderr tail
// for a given job id via /api/jobs/<id>/logs and renders it in a
// scrollable <pre>. Rendered as null when no job id is selected so it
// shares one mount point.
function JobLogsModal({ jobId, onClose }: { jobId: string | null; onClose: () => void }) {
  const [payload, setPayload] = useState<JobLogsPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setPayload(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPayload(null);
    void (async () => {
      try {
        const data = await getJobLogs(jobId);
        if (!cancelled) setPayload(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return (
    <Modal open={jobId !== null} onClose={onClose} title="Job Crash Log">
      <div className="space-y-3 text-sm" data-testid="job-logs-modal">
        {jobId && (
          <div className="text-[11px] text-slate-500">
            Job <span className="font-mono text-slate-700">{jobId}</span>
          </div>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin"/> Fetching logs…
          </div>
        )}
        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
            Failed to load logs: {error}
          </div>
        )}
        {payload && (
          <div className="space-y-3">
            {payload.error && (
              <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-900">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-rose-700">Error</div>
                <div className="whitespace-pre-wrap break-words">{payload.error}</div>
              </div>
            )}
            {payload.traceback && (
              <details className="rounded-md border border-slate-200" open>
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Python traceback
                </summary>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800" data-testid="job-logs-traceback">{payload.traceback}</pre>
              </details>
            )}
            {payload.stderrLog && (
              <details className="rounded-md border border-slate-200">
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Per-job stderr
                </summary>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800">{payload.stderrLog}</pre>
              </details>
            )}
            {payload.workerStderrLog && (
              <details className="rounded-md border border-slate-200">
                <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Worker stderr tail
                </summary>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words border-t border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800">{payload.workerStderrLog}</pre>
              </details>
            )}
            {!payload.error && !payload.traceback && !payload.stderrLog && !payload.workerStderrLog && (
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                No crash log captured for this job. The worker may have
                exited cleanly, or the stderr log was not written yet.
              </div>
            )}
          </div>
        )}
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}

// Visual order mirrors TranscriptionLanes.tsx: phone IPA → word IPA → STT → ORTH.
const LANE_ORDER: LaneKind[] = ['ipa_phone', 'ipa', 'stt', 'ortho', 'stt_words', 'boundaries'];
const LANE_DISPLAY: Record<LaneKind, { label: string; hint: string }> = {
  ipa_phone: { label: 'Phones tier', hint: 'Phone-level IPA' },
  ipa: { label: 'IPA tier', hint: 'Word/lexeme IPA' },
  stt: { label: 'STT segments', hint: 'Coarse transcript' },
  ortho: { label: 'Ortho tier', hint: 'Orthographic' },
  stt_words: { label: 'Words (Tier 1)', hint: 'Raw faster-whisper word boundaries' },
  boundaries: { label: 'Boundaries (Tier 2)', hint: 'Forced-aligned edges; colored by Tier 1 ↔ Tier 2 shift' },
};

function LexemeSearchBlock({ speaker, conceptId }: { speaker: string; conceptId: string | number }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<LexemeSearchCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeek = usePlaybackStore(s => s.requestSeek);

  useEffect(() => {
    const q = query.trim();
    if (!q || !speaker) { setResults([]); setError(null); return; }
    const variants = q.split(/[\s,;/]+/).filter(Boolean);
    if (variants.length === 0) { setResults([]); setError(null); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await searchLexeme(speaker, variants, { conceptId: String(conceptId) });
        setResults(res.candidates);
      } catch (err) {
        setResults([]);
        setError(err instanceof Error ? err.message : 'Search failed');
      } finally { setLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [query, speaker, conceptId]);

  return (
    <div className="mb-3">
      <div className="mb-1.5 flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 py-1.5">
        <Search className="h-3 w-3 shrink-0 text-slate-400"/>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search & anchor lexeme…"
          aria-label="Search lexeme variants"
          className="min-w-0 flex-1 bg-transparent text-[11px] focus:outline-none"
        />
        {loading && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-slate-400"/>}
        {query && !loading && (
          <button onClick={() => setQuery('')} aria-label="Clear search" className="shrink-0 text-slate-400 hover:text-slate-600"><X className="h-3 w-3"/></button>
        )}
      </div>
      {(error || (query.trim() && !loading && results.length === 0) || results.length > 0) && (
        <div className="max-h-56 overflow-y-auto rounded-md border border-slate-200 bg-white" role="listbox">
          {error && <div className="px-2 py-1.5 text-[10px] text-rose-600">{error}</div>}
          {!error && !loading && results.length === 0 && query.trim() && (
            <div className="px-2 py-1.5 text-[10px] text-slate-400">No matches</div>
          )}
          {results.map((r, i) => (
            <button
              key={`${r.tier}:${r.start}:${i}`}
              role="option"
              onClick={() => requestSeek(r.start)}
              className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-indigo-50"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-[11px] font-semibold text-slate-700">{r.matched_text}</span>
                <span className="text-[9px] text-slate-400">
                  {r.tier} · {r.start.toFixed(2)}s · &ldquo;{r.matched_variant}&rdquo;
                </span>
              </div>
              <span className="shrink-0 rounded-full bg-indigo-50 px-1.5 py-0.5 font-mono text-[9px] text-indigo-700">
                {Math.round(r.score * 100)}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function TranscriptionLanesControls() {
  const lanes = useTranscriptionLanesStore(s => s.lanes);
  const toggleLane = useTranscriptionLanesStore(s => s.toggleLane);
  const setLaneColor = useTranscriptionLanesStore(s => s.setLaneColor);

  return (
    <div className="mb-3 rounded-md bg-slate-50 p-2">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Transcription lanes
      </div>
      <div className="space-y-1">
        {LANE_ORDER.map(kind => {
          const cfg = lanes[kind];
          const { label, hint } = LANE_DISPLAY[kind];
          return (
            <div
              key={kind}
              className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-white"
            >
              <input
                id={`lane-toggle-${kind}`}
                type="checkbox"
                checked={cfg.visible}
                onChange={() => toggleLane(kind)}
                className="h-3.5 w-3.5 cursor-pointer rounded border-slate-300 text-indigo-600 focus:ring-indigo-400"
              />
              <LaneColorPicker
                value={cfg.color}
                onChange={c => setLaneColor(kind, c)}
                ariaLabel={`Color for ${label}`}
              />
              <label htmlFor={`lane-toggle-${kind}`} className="flex-1 min-w-0 cursor-pointer">
                <div className="text-[11px] font-medium text-slate-700 truncate">{label}</div>
                <div className="text-[9px] text-slate-400 truncate">{hint}</div>
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
