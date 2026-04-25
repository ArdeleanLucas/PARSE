import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  Search, ChevronLeft, ChevronRight, Check, Flag, Split, GitMerge,
  RotateCw, Play, RefreshCw, Save, Upload,
  Layers, ChevronDown, ChevronUp, Plus, X, AlertCircle,
  CheckCircle2, ArrowUpDown, Volume2, Filter, Send,
  Database, Users as UsersIcon, Cpu, KeyRound, Loader2, ArrowLeft, ShieldCheck, Zap, Sparkles,
  PanelRightClose, Tag, Tags, Import, AudioLines, Type, Mic,
  Workflow, Network, Trash2, ChevronDown as CDown,
  Video, Scissors, Activity, SlidersHorizontal, Download,
  Pause, SkipBack, SkipForward, ZoomIn, ZoomOut, MessageSquare, Anchor,
  Sun, Moon, XCircle, Undo2, Redo2
} from 'lucide-react';
import type { AnnotationInterval, AnnotationRecord, Tag as StoreTag } from './api/types';
import { getLingPyExport, saveApiKey, getAuthStatus, pollAuth, startAuthFlow, startCompute, pollCompute, importTagCsv, detectTimestampOffset, detectTimestampOffsetFromPairs, applyTimestampOffset, searchLexeme, pollOffsetDetectJob, OffsetJobError, getJobLogs } from './api/client';
import type { JobLogsPayload } from './api/client';
import type { OffsetDetectResult, OffsetPair, LexemeSearchCandidate } from './api/client';
import { useChatSession, type UseChatSessionResult } from './hooks/useChatSession';
import { compareSurveyKeys, surveyBadgePrefix } from './lib/surveySort';
import { useSpectrogram } from './hooks/useSpectrogram';
import { useWaveSurfer } from './hooks/useWaveSurfer';
import { useAnnotationStore } from './stores/annotationStore';
import { useTranscriptionLanesStore, type LaneKind } from './stores/transcriptionLanesStore';
import { TranscriptionLanes, LABEL_COL_PX } from './components/annotate/TranscriptionLanes';
import { LaneColorPicker } from './components/annotate/LaneColorPicker';
import { useAnnotationSync } from './hooks/useAnnotationSync';
import { useComputeJob } from './hooks/useComputeJob';
import { useActionJob, formatEta } from './hooks/useActionJob';
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
import { ChatMarkdown } from './components/shared/ChatMarkdown';
import { LexemeDetail } from './components/compare/LexemeDetail';
import { CommentsImport } from './components/compare/CommentsImport';
import { SpeakerImport } from './components/compare/SpeakerImport';
import { ClefConfigModal, type ClefConfigModalTab } from './components/compute/ClefConfigModal';
import { ClefPopulateSummaryBanner } from './components/compute/ClefPopulateSummaryBanner';
import { ClefSourcesReportModal } from './components/compute/ClefSourcesReportModal';
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

const tagDot: Record<ConceptTag, string> = {
  untagged: 'bg-slate-300', review: 'bg-amber-400',
  confirmed: 'bg-emerald-500', problematic: 'bg-rose-500',
};
const simColor = (v: number) =>
  v >= 0.8 ? 'text-emerald-600' : v >= 0.5 ? 'text-amber-600' : 'text-slate-400';
const simBar = (v: number) =>
  v >= 0.8 ? 'bg-emerald-500' : v >= 0.5 ? 'bg-amber-400' : 'bg-slate-300';

const REVIEW_TAG_IDS = new Set(['review', 'review-needed']);
const COMPARE_NOTES_STORAGE_KEY = 'parseui-compare-notes-v1';

/** Render a number of seconds as ``MM:SS.cs`` — the same format the
 *  Annotate playback bar shows under the waveform. Lifted to module
 *  scope so the offset-capture toast + manual-anchor chips can mirror
 *  it exactly (so users can verify what was captured against the
 *  readout they were just looking at). */
function formatPlaybackTime(t: number): string {
  if (!Number.isFinite(t) || t < 0) return '00:00.00';
  const m = Math.floor(t / 60).toString().padStart(2, '0');
  const s = Math.floor(t % 60).toString().padStart(2, '0');
  const ms = Math.floor((t * 100) % 100).toString().padStart(2, '0');
  return `${m}:${s}.${ms}`;
}

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


function conceptMatchesIntervalText(concept: Concept, text: string): boolean {
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

function findAnnotationForConcept(record: AnnotationRecord | null | undefined, concept: Concept) {
  if (!record) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const conceptIntervals = record.tiers.concept?.intervals ?? [];
  const conceptInterval = conceptIntervals.find((interval) => conceptMatchesIntervalText(concept, interval.text)) ?? null;

  if (!conceptInterval) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const ipaInterval = (record.tiers.ipa?.intervals ?? []).find((interval) => overlaps(interval, conceptInterval)) ?? null;
  const orthoInterval = pickOrthoIntervalForConcept(record, conceptInterval);

  return { conceptInterval, ipaInterval, orthoInterval };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
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

// null value == "no similarity score recorded for this speaker/concept/lang"
// -- either because the cognate compute hasn't run yet, or because the
// reference-forms dataset had no entry for this language. Rendering "—"
// instead of "0.00" keeps those two cases distinguishable, so the user
// knows to either run Populate or pick a different provider/language
// instead of concluding the speaker really has zero similarity.
const SimBar: React.FC<{ value: number | null }> = ({ value }) => {
  if (value === null) {
    return (
      <div className="flex items-center gap-2" title="No similarity score yet — run Save & populate, or recompute cognate sets.">
        <div className="h-1.5 w-14 rounded-full bg-slate-100" />
        <span className="text-xs font-mono tabular-nums text-slate-300">—</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full ${simBar(value)}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className={`text-xs font-mono tabular-nums ${simColor(value)}`}>{value.toFixed(2)}</span>
    </div>
  );
};

// Per-speaker cognate cell. Click cycles A → B → … → Z → — → A. A long press
// (≥500 ms) resets to —. The button swallows the subsequent click after a
// long-press fires so cycle doesn't also run.
const COGNATE_COLORS: Record<string, string> = {
  A: 'bg-indigo-100 text-indigo-700',
  B: 'bg-violet-100 text-violet-700',
  C: 'bg-fuchsia-100 text-fuchsia-700',
  D: 'bg-rose-100 text-rose-700',
  E: 'bg-orange-100 text-orange-700',
  F: 'bg-amber-100 text-amber-700',
  G: 'bg-lime-100 text-lime-700',
  H: 'bg-emerald-100 text-emerald-700',
  I: 'bg-teal-100 text-teal-700',
  J: 'bg-cyan-100 text-cyan-700',
  K: 'bg-sky-100 text-sky-700',
  L: 'bg-blue-100 text-blue-700',
  M: 'bg-indigo-200 text-indigo-800',
  N: 'bg-violet-200 text-violet-800',
  O: 'bg-fuchsia-200 text-fuchsia-800',
  P: 'bg-rose-200 text-rose-800',
  Q: 'bg-orange-200 text-orange-800',
  R: 'bg-amber-200 text-amber-800',
  S: 'bg-lime-200 text-lime-800',
  T: 'bg-emerald-200 text-emerald-800',
  U: 'bg-teal-200 text-teal-800',
  V: 'bg-cyan-200 text-cyan-800',
  W: 'bg-sky-200 text-sky-800',
  X: 'bg-blue-200 text-blue-800',
  Y: 'bg-slate-200 text-slate-800',
  Z: 'bg-stone-200 text-stone-800',
};

const CognateCell: React.FC<{
  speaker: string;
  group: string;
  onCycle: () => void;
  onReset: () => void;
}> = ({ speaker, group, onCycle, onReset }) => {
  const timerRef = React.useRef<number | null>(null);
  const longPressFiredRef = React.useRef(false);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const startPress = () => {
    longPressFiredRef.current = false;
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      longPressFiredRef.current = true;
      onReset();
    }, 500);
  };

  const cancelPress = () => {
    clearTimer();
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false; // suppress cycle after long-press reset
      return;
    }
    onCycle();
  };

  const colorClass = /^[A-Z]$/.test(group)
    ? COGNATE_COLORS[group] ?? 'bg-slate-200 text-slate-800'
    : 'bg-slate-100 text-slate-400';

  const next = group === '\u2014' || !/^[A-Z]$/.test(group) ? 'A'
    : group === 'Z' ? '\u2014'
    : String.fromCharCode(group.charCodeAt(0) + 1);

  return (
    <button
      data-testid={`cognate-cycle-${speaker}`}
      title={`Click cycles → ${next} · Long-press resets to —`}
      onPointerDown={startPress}
      onPointerUp={cancelPress}
      onPointerLeave={cancelPress}
      onPointerCancel={cancelPress}
      onClick={handleClick}
      className={`inline-flex h-5 min-w-[24px] items-center justify-center rounded px-1 font-mono text-[10px] font-bold hover:ring-2 hover:ring-slate-300 ${colorClass}`}
    >
      {group}
    </button>
  );
};

const Pill: React.FC<{ children: React.ReactNode; tone?: 'slate'|'emerald'|'indigo' }> = ({ children, tone='slate' }) => {
  const tones: Record<string,string> = {
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${tones[tone]}`}>{children}</span>;
};

const SectionCard: React.FC<{ title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ title, aside, children }) => (
  <section className="rounded-xl border border-slate-200/80 bg-white shadow-[0_1px_0_rgba(15,23,42,0.03)]">
    <header className="flex items-center justify-between px-5 pt-4 pb-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.09em] text-slate-500">{title}</h3>
      {aside}
    </header>
    <div className="px-5 pb-5">{children}</div>
  </section>
);

// ---------- AI Chat Panel ----------
interface AIChatProps {
  height: number;
  minimized: boolean;
  onResizeStart: (e: React.MouseEvent) => void;
  onMinimize: () => void;
  conceptName: string;
  conceptId: number | string;
  speakerCount: number;
  chatSession: UseChatSessionResult;
}

const QUICK_ACTIONS = [
  'Analyze cognates',
  'Explain why Fail01 diverges',
  'Suggest borrowings',
  'Help decide grouping',
  'Compare IPA alignments',
];

type AIProvider = 'xai' | 'openai';
type AIConnectionView = 'welcome' | 'form-xai' | 'form-openai' | 'connected';
type TestStatus = 'idle' | 'testing' | 'success' | 'error';
interface ChatMessage { id: number; role: 'ai' | 'user'; content: string; streaming?: boolean; }

const PROVIDER_META: Record<AIProvider, { label: string; model: string; badgeClass: string }> = {
  xai:    { label: 'xAI',    model: 'grok-4.2 reasoning', badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  openai: { label: 'OpenAI', model: 'gpt-5.4',            badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
};

// Narrow the backend's free-form `provider` string (from /api/auth/status) to
// the UI's AIProvider union. Defaults to 'openai' when unset or unrecognized
// — OAuth-only flows don't populate it and historical tokens predate the
// provider field.
function resolveAuthProvider(raw: string | undefined | null): AIProvider {
  return raw === 'xai' ? 'xai' : 'openai';
}

const AIChat: React.FC<AIChatProps> = ({ height, minimized, onResizeStart, onMinimize, conceptName, conceptId, speakerCount, chatSession }) => {
  // Connection state machine
  const [view, setView] = useState<AIConnectionView>('welcome');
  const [provider, setProvider] = useState<AIProvider | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [oauthPending, setOauthPending] = useState(false);
  const [oauthCode, setOauthCode] = useState('');
  const [oauthUri, setOauthUri] = useState('');
  const oauthPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isConnected = view === 'connected' && provider !== null;
  const hasData = speakerCount > 0;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [collapsedInput, setCollapsedInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Seed welcome message once connected, tailored to empty-project case
  useEffect(() => {
    if (isConnected && messages.length === 0) {
      const greet = hasData
        ? `Hi, I'm PARSE AI. I'm looking at concept "${conceptName}" across ${speakerCount} speakers. Ask me to analyze cognates, flag likely borrowings, or explain the similarity scores.`
        : `Hi, I'm PARSE AI. Let's get you set up so I can help analyze concepts, suggest cognates, and explain similarities. Import speakers or load a dataset and I'll start working with your data right away.`;
      setMessages([{ id: 1, role: 'ai', content: greet }]);
    }
  }, [isConnected, hasData, conceptName, speakerCount, messages.length]);

  const handleConnect = async (p: AIProvider) => {
    if (!apiKey.trim()) return;
    setTestStatus('testing');
    setTestMessage('');
    try {
      const result = await saveApiKey(apiKey.trim(), p);
      if (result && result.authenticated) {
        setProvider(p);
        setView('connected');
        setTestStatus('idle');
        setTestMessage('');
      } else {
        setTestStatus('error');
        setTestMessage('Key was saved but could not be verified.');
      }
    } catch (err) {
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'Connection failed.');
    }
  };

  const handleTestConnection = async () => {
    if (!apiKey.trim()) return;
    setTestStatus('testing');
    setTestMessage('');
    try {
      await saveApiKey(apiKey.trim(), provider ?? (view === 'form-xai' ? 'xai' : 'openai'));
      setTestStatus('success');
      setTestMessage('Connection verified — key saved.');
    } catch (err) {
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'Connection failed.');
    }
  };

  const handleDisconnect = () => {
    setView('welcome');
    setProvider(null);
    setApiKey('');
    setTestStatus('idle');
    setTestMessage('');
    setMessages([]);
  };

  const goToProviderForm = (p: AIProvider) => {
    setProvider(p);
    setView(p === 'xai' ? 'form-xai' : 'form-openai');
    setTestStatus('idle');
    setTestMessage('');
  };

  const backToWelcome = () => {
    setView('welcome');
    setTestStatus('idle');
    setTestMessage('');
  };

  // Restore auth state on mount and cleanup poll on unmount.
  useEffect(() => {
    getAuthStatus().then(s => {
      if (s.authenticated) {
        setProvider(resolveAuthProvider(s.provider));
        setView('connected');
      } else if (s.flow_active) {
        // OAuth was started before this mount (page reload mid-flow) — resume.
        setOauthCode(s.user_code ?? '');
        setOauthUri(s.verification_uri ?? '');
        setOauthPending(true);
        oauthPollRef.current = setInterval(async () => {
          try {
            const result = await pollAuth();
            if (result.status === 'complete') {
              if (oauthPollRef.current) clearInterval(oauthPollRef.current);
              oauthPollRef.current = null;
              setOauthPending(false);
              // OAuth device flow is OpenAI-specific today; re-check status so
              // we never hard-code a provider that doesn't match what the
              // backend actually persisted.
              const after = await getAuthStatus().catch(() => null);
              setProvider(resolveAuthProvider(after?.provider));
              setView('connected');
            } else if (result.status === 'expired' || result.status === 'error') {
              if (oauthPollRef.current) clearInterval(oauthPollRef.current);
              oauthPollRef.current = null;
              setOauthPending(false);
              setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
            }
          } catch { /* keep polling */ }
        }, 5000);
      }
    }).catch(() => { /* leave view at welcome */ });
    return () => { if (oauthPollRef.current) clearInterval(oauthPollRef.current); };
  }, []);

  const handleCodexSignIn = async () => {
    setOauthPending(true);
    setOauthCode('');
    setOauthUri('');
    setTestMessage('');
    try {
      await startAuthFlow();
      const status = await getAuthStatus();
      if (status.user_code) {
        setOauthCode(status.user_code);
        setOauthUri(status.verification_uri ?? '');
      }
      oauthPollRef.current = setInterval(async () => {
        try {
          const result = await pollAuth();
          if (result.status === 'complete') {
            if (oauthPollRef.current) clearInterval(oauthPollRef.current);
            oauthPollRef.current = null;
            setOauthPending(false);
            const after = await getAuthStatus().catch(() => null);
            setProvider(resolveAuthProvider(after?.provider));
            setView('connected');
          } else if (result.status === 'expired' || result.status === 'error') {
            if (oauthPollRef.current) clearInterval(oauthPollRef.current);
            oauthPollRef.current = null;
            setOauthPending(false);
            setTestMessage(result.error ?? (result.status === 'expired' ? 'Login code expired — try again' : 'OAuth failed'));
          }
        } catch { /* keep polling */ }
      }, 5000);
    } catch (err) {
      setOauthPending(false);
      setTestStatus('error');
      setTestMessage(err instanceof Error ? err.message : 'OAuth start failed.');
    }
  };

  useEffect(() => {
    if (!minimized) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [chatSession.messages, minimized]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q || chatSession.sending) return;
    setInput('');
    setCollapsedInput('');
    void chatSession.send(q);
  };

  // ---------- Collapsed: thin command bar ----------
  if (minimized) {
    return (
      <div
        className="relative flex h-14 shrink-0 items-center border-t border-slate-200 bg-slate-50/80 backdrop-blur-sm transition-all duration-300 shadow-[0_-1px_0_rgba(15,23,42,0.02)]"
      >
        <form
          onClick={() => onMinimize()}
          onSubmit={e => { e.preventDefault(); if (collapsedInput.trim()) { onMinimize(); setTimeout(() => send(collapsedInput), 250); } }}
          className="mx-auto flex w-full max-w-4xl items-center gap-3 px-6"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">PARSE AI</span>
          <div className="h-4 w-px bg-slate-200"/>
          {chatSession.sending ? (
            <div
              className="flex flex-1 items-center gap-1.5 text-[13px] text-slate-500"
              aria-live="polite"
              aria-label="PARSE AI is thinking"
            >
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]"/>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]"/>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"/>
              <span className="ml-1.5 font-medium">Thinking…</span>
            </div>
          ) : (
            <input
              value={collapsedInput}
              onChange={e => setCollapsedInput(e.target.value)}
              onClick={e => e.stopPropagation()}
              onFocus={() => onMinimize()}
              placeholder={`Ask PARSE AI about ${conceptName} (#${conceptId})…`}
              className="flex-1 bg-transparent text-[13px] text-slate-700 placeholder:text-slate-400 focus:outline-none"
            />
          )}
          <button
            type="submit"
            onClick={e => e.stopPropagation()}
            disabled={chatSession.sending}
            className="grid h-8 w-8 place-items-center rounded-md text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-700 disabled:opacity-40"
            title="Send"
          >
            <Send className="h-3.5 w-3.5"/>
          </button>
        </form>
      </div>
    );
  }

  // ---------- Expanded: elevated panel ----------
  return (
    <div
      className="relative flex flex-col overflow-hidden border-t-2 border-slate-200 bg-indigo-50/40 backdrop-blur-md transition-[height] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] shadow-[0_-12px_40px_-12px_rgba(15,23,42,0.18)]"
      style={{ height }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={onResizeStart}
        className="group absolute inset-x-0 top-0 z-10 flex h-2.5 cursor-ns-resize items-center justify-center"
      >
        <div className="h-1 w-12 rounded-full bg-slate-300 transition group-hover:bg-slate-500"/>
      </div>

      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200/70 px-6 pt-4 pb-3">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="text-[13px] font-semibold tracking-tight text-slate-900">PARSE AI</div>
              {isConnected && provider && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${PROVIDER_META[provider].badgeClass}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/>
                  Connected to {PROVIDER_META[provider].label}
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {isConnected && provider ? (
                <>
                  Model: <span className="font-mono text-slate-600">{PROVIDER_META[provider].model}</span>
                  {hasData && (
                    <>
                      <span className="mx-1.5 text-slate-300">•</span>
                      Asking about <span className="font-semibold text-slate-700">{conceptName}</span>
                      <span className="font-mono text-slate-400"> (#{conceptId})</span>
                      <span className="mx-1.5 text-slate-300">•</span>
                      {speakerCount} speakers
                    </>
                  )}
                </>
              ) : (
                <>Not connected — choose a provider to begin</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isConnected && (
            <>
              <button
                onClick={() => setView('welcome')}
                className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-white/70 hover:text-slate-800"
                title="Switch provider"
              >
                Switch provider
              </button>
              <button
                onClick={handleDisconnect}
                className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-white/70 hover:text-rose-600"
                title="Disconnect"
              >
                Disconnect
              </button>
              <div className="mx-1 h-4 w-px bg-slate-200"/>
            </>
          )}
          <button
            onClick={onMinimize}
            title="Minimize"
            className="grid h-7 w-7 place-items-center rounded-md text-slate-400 hover:bg-white/60 hover:text-slate-700"
          >
            <ChevronDown className="h-4 w-4"/>
          </button>
        </div>
      </div>

      {/* Body — state machine */}
      {view === 'welcome' && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-2xl">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white">
                <Sparkles className="h-5 w-5"/>
              </div>
              <h2 className="text-[18px] font-semibold tracking-tight text-slate-900">Connect PARSE AI</h2>
              <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
                To use PARSE AI for analysis, cognate suggestions, and decision support,
                connect one of the supported providers.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {/* xAI card */}
              <button
                onClick={() => goToProviderForm('xai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <Zap className="h-4 w-4"/>
                </div>
                <div>
                  <div className="text-[13px] font-semibold text-slate-900">xAI / Grok</div>
                  <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                    Sign in with your xAI account to use Grok reasoning models.
                  </div>
                </div>
                <span className="mt-auto inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition group-hover:bg-slate-700">
                  Connect with xAI Account
                </span>
              </button>

              {/* OpenAI card */}
              <button
                onClick={() => goToProviderForm('openai')}
                className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left transition hover:border-slate-400 hover:shadow-[0_4px_16px_-4px_rgba(15,23,42,0.12)]"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <KeyRound className="h-4 w-4"/>
                </div>
                <div>
                  <div className="text-[13px] font-semibold text-slate-900">OpenAI API</div>
                  <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                    Use your own OpenAI API key or sign in with Codex.
                  </div>
                </div>
                <span className="mt-auto inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-900 ring-1 ring-slate-300 transition group-hover:bg-slate-50">
                  Use OpenAI API Key
                </span>
              </button>
            </div>

            <div className="mt-5 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5"/>
              Your API keys are stored securely in the browser and never sent to our servers.
            </div>
          </div>
        </div>
      )}

      {(view === 'form-xai' || view === 'form-openai') && (
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-md">
            <button
              onClick={backToWelcome}
              className="mb-4 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 transition hover:text-slate-900"
            >
              <ArrowLeft className="h-3.5 w-3.5"/> Back
            </button>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_1px_0_rgba(15,23,42,0.03)]">
              <div className="mb-4">
                <div className="text-[13px] font-semibold text-slate-900">
                  Connect to {view === 'form-xai' ? 'xAI / Grok' : 'OpenAI'}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  {view === 'form-xai'
                    ? 'Authenticate with your xAI account to enable Grok models.'
                    : 'Paste your API key or sign in with Codex OAuth.'}
                </div>
              </div>

              {view === 'form-xai' && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-[11px] font-medium text-slate-600">xAI API Key</span>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={e => { setApiKey(e.target.value); setTestStatus('idle'); }}
                      placeholder="xai-..."
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 font-mono text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
                    />
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={!apiKey.trim() || testStatus === 'testing'}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin"/>}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600"/>}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600"/>}
                      Test Connection
                    </button>
                    <button
                      onClick={() => handleConnect('xai')}
                      disabled={!apiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      <Zap className="h-3.5 w-3.5"/> Connect
                    </button>
                  </div>
                  {testMessage && (
                    <div className={`text-[11px] ${testStatus === 'success' ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {testMessage}
                    </div>
                  )}
                </div>
              )}

              {view === 'form-openai' && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-[11px] font-medium text-slate-600">OpenAI API Key</span>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={e => { setApiKey(e.target.value); setTestStatus('idle'); }}
                      placeholder="sk-..."
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 font-mono text-[12px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
                    />
                  </label>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleTestConnection}
                      disabled={!apiKey.trim() || testStatus === 'testing'}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {testStatus === 'testing' && <Loader2 className="h-3 w-3 animate-spin"/>}
                      {testStatus === 'success' && <CheckCircle2 className="h-3 w-3 text-emerald-600"/>}
                      {testStatus === 'error' && <AlertCircle className="h-3 w-3 text-rose-600"/>}
                      Test Connection
                    </button>
                    <button
                      onClick={() => handleConnect('openai')}
                      disabled={!apiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      Save Key
                    </button>
                  </div>

                  {testMessage && (
                    <div className={`text-[11px] ${testStatus === 'success' ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {testMessage}
                    </div>
                  )}

                  <div className="flex items-center gap-3 py-1">
                    <div className="h-px flex-1 bg-slate-200"/>
                    <span className="text-[10px] uppercase tracking-wider text-slate-400">or</span>
                    <div className="h-px flex-1 bg-slate-200"/>
                  </div>

                  <button
                    onClick={handleCodexSignIn}
                    disabled={oauthPending}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-[12px] font-semibold text-slate-800 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {oauthPending ? 'Waiting for sign-in...' : 'Sign in with Codex'}
                  </button>
                  {oauthPending && oauthCode && (
                    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
                      <div className="text-[11px] text-slate-500 mb-1">Enter this code:</div>
                      <div className="text-lg font-mono font-bold tracking-widest text-slate-900">
                        {oauthCode}
                      </div>
                      {oauthUri && (
                        <a href={oauthUri} target="_blank" rel="noreferrer"
                           className="mt-1 block text-[11px] text-indigo-600 hover:underline">
                          {oauthUri}
                        </a>
                      )}
                      <div className="mt-2 text-[10px] text-slate-400">Waiting for confirmation...</div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5"/>
              Keys are saved to your local server config.
            </div>
          </div>
        </div>
      )}

      {view === 'connected' && (
        <>
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto max-w-3xl space-y-3">
              {chatSession.messages.length === 0 && !chatSession.sending && messages.length > 0 && messages.map(m => (
                <div key={m.id} className="flex justify-start">
                  <div className="max-w-[78%] rounded-2xl bg-white px-4 py-2.5 text-[13px] leading-relaxed text-slate-800 ring-1 ring-slate-200/70 shadow-sm">
                    <ChatMarkdown content={m.content} />
                  </div>
                </div>
              ))}
              {chatSession.messages.map((m, i) => (
                <div key={`${m.timestamp}-${i}`} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-slate-900 text-white'
                      : 'bg-white text-slate-800 ring-1 ring-slate-200/70 shadow-sm'
                  }`}>
                    {m.role === 'assistant' ? <ChatMarkdown content={m.content} /> : m.content}
                    {chatSession.sending && i === chatSession.messages.length - 1 && m.role === 'assistant' && (
                      <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-slate-500"/>
                    )}
                  </div>
                </div>
              ))}
              {chatSession.sending &&
                (chatSession.messages.length === 0 ||
                  chatSession.messages[chatSession.messages.length - 1].role === 'user') && (
                  <div className="flex justify-start" aria-live="polite" aria-label="PARSE AI is thinking">
                    <div className="flex max-w-[78%] items-center gap-1.5 rounded-2xl bg-white px-4 py-3 ring-1 ring-slate-200/70 shadow-sm">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]"/>
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]"/>
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"/>
                      <span className="ml-1.5 text-[12px] font-medium text-slate-500">Thinking…</span>
                    </div>
                  </div>
                )}
            </div>
          </div>

          {/* Error display */}
          {chatSession.error && (
            <div className="shrink-0 px-6 py-2">
              <div className="mx-auto max-w-3xl rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-[12px] text-rose-700">
                <span className="font-semibold">Error:</span> {chatSession.error}
              </div>
            </div>
          )}

          {/* Quick actions + input */}
          <div className="shrink-0 border-t border-slate-200/70 bg-white/50 px-6 py-3 backdrop-blur-sm">
            <div className="mx-auto max-w-3xl">
              <div className="mb-2 flex flex-wrap gap-1.5">
                {QUICK_ACTIONS.map(a => (
                  <button
                    key={a}
                    onClick={() => send(a)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
                  >
                    {a}
                  </button>
                ))}
              </div>
              <form
                onSubmit={e => { e.preventDefault(); send(input); }}
                className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-100"
              >
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder={hasData ? `Ask PARSE AI about ${conceptName}…` : `Ask PARSE AI anything to get started…`}
                  className="flex-1 bg-transparent text-[13px] text-slate-800 placeholder:text-slate-400 focus:outline-none"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  Send <Send className="h-3 w-3"/>
                </button>
              </form>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

// ---------- Manage Tags View ----------
interface ManageTagsProps {
  tags: LingTag[];
  concepts: Concept[];
  onCreateTag: (name: string, color: string) => void;
  onUpdateTag: (id: string, name: string) => void;
  tagSearch: string; setTagSearch: (s: string) => void;
  newTagName: string; setNewTagName: (s: string) => void;
  newTagColor: string; setNewTagColor: (s: string) => void;
  showUntagged: boolean; setShowUntagged: (b: boolean) => void;
  selectedTagId: string | null; setSelectedTagId: (s: string | null) => void;
  conceptSearch: string; setConceptSearch: (s: string) => void;
  tagConcept: (tagId: string, conceptKey: string) => void;
  untagConcept: (tagId: string, conceptKey: string) => void;
}

const SWATCHES = ['#6366f1','#10b981','#f59e0b','#f43f5e','#8b5cf6','#06b6d4','#ec4899','#64748b'];

const ManageTagsView: React.FC<ManageTagsProps> = ({
  tags, concepts, onCreateTag, onUpdateTag, tagSearch, setTagSearch, newTagName, setNewTagName,
  newTagColor, setNewTagColor, showUntagged, setShowUntagged,
  selectedTagId, setSelectedTagId, conceptSearch, setConceptSearch,
  tagConcept, untagConcept,
}) => {
  const [editingTagId, setEditingTagId] = useState<string | null>(null);
  const [editingTagName, setEditingTagName] = useState('');
  const storeTags = useTagStore(s => s.tags);
  const filteredTags = tags.filter(t => t.name.toLowerCase().includes(tagSearch.toLowerCase()));
  const selectedTag = tags.find(t => t.id === selectedTagId);
  const filteredConcepts = concepts.filter(c => c.name.toLowerCase().includes(conceptSearch.toLowerCase()));
  const taggedKeys = useMemo<Set<string>>(() => {
    if (!selectedTagId) return new Set();
    const t = storeTags.find(s => s.id === selectedTagId);
    return new Set(t?.concepts ?? []);
  }, [storeTags, selectedTagId]);

  return (
    <div className="flex flex-1 min-h-0 bg-slate-50">
      {/* LEFT: tags panel */}
      <div className="w-[360px] shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
        <div className="p-6">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Linguistic tags</h2>
          <p className="mt-1 text-xs text-slate-400">Organize concepts by review state, borrowing, or custom labels.</p>

          <div className="relative mt-5">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"/>
            <input
              value={tagSearch}
              onChange={e => setTagSearch(e.target.value)}
              placeholder="Filter tags…"
              className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-2 pl-9 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          {/* Create new tag */}
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/40 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Create tag</div>
            <div className="mt-2 flex items-center gap-2">
              <input
                value={newTagName}
                onChange={e => setNewTagName(e.target.value)}
                placeholder="New tag name…"
                className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              />
              <div className="relative">
                <div
                  className="h-7 w-7 rounded-md ring-2 ring-white"
                  style={{ background: newTagColor, boxShadow: '0 0 0 1px rgb(226 232 240)' }}
                />
              </div>
            </div>
            <div className="mt-2 flex gap-1.5">
              {SWATCHES.map(c => (
                <button
                  key={c}
                  onClick={() => setNewTagColor(c)}
                  className={`h-5 w-5 rounded-full transition ${newTagColor===c ? 'ring-2 ring-offset-1 ring-slate-400' : 'ring-1 ring-slate-200 hover:scale-110'}`}
                  style={{ background: c }}
                />
              ))}
            </div>
            <button
              onClick={() => onCreateTag(newTagName, newTagColor)}
              disabled={!newTagName.trim()}
              className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200"
            >
              <Plus className="h-3 w-3"/> Create
            </button>
          </div>

          {/* Toggle */}
          <div className="mt-5 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
            <span className="text-xs font-medium text-slate-700">Show untagged</span>
            <button
              onClick={() => setShowUntagged(!showUntagged)}
              className={`relative h-5 w-9 rounded-full transition ${showUntagged ? 'bg-indigo-600' : 'bg-slate-300'}`}
            >
              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${showUntagged ? 'left-4' : 'left-0.5'}`}/>
            </button>
          </div>

          {/* Tag list */}
          <div className="mt-5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Tags · {filteredTags.length}</div>
            <div className="mt-2 space-y-1">
              {filteredTags.map(t => {
                const active = selectedTagId === t.id;
                const editing = editingTagId === t.id;
                return (
                  <div key={t.id} className={`rounded-lg ${active ? 'bg-indigo-50 ring-1 ring-indigo-200' : 'hover:bg-slate-50'}`}>
                    <div className="flex items-center gap-2 px-3 py-2">
                      <button
                        onClick={() => setSelectedTagId(t.id)}
                        className="group flex min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: t.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }}/>
                        <span className={`flex-1 truncate text-[13px] ${active ? 'font-semibold text-indigo-900' : 'font-medium text-slate-700'}`}>{t.name}</span>
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{t.count}</span>
                      </button>
                      <button
                        type="button"
                        aria-label="Edit tag"
                        onClick={() => {
                          setEditingTagId(t.id);
                          setEditingTagName(t.name);
                        }}
                        className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 hover:bg-white hover:text-slate-800"
                      >
                        Edit
                      </button>
                    </div>
                    {editing && (
                      <div className="border-t border-indigo-100 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <input
                            aria-label="Rename tag"
                            value={editingTagName}
                            onChange={e => setEditingTagName(e.target.value)}
                            className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                          />
                          <button
                            type="button"
                            aria-label="Save tag"
                            onClick={() => {
                              if (!editingTagName.trim()) return;
                              onUpdateTag(t.id, editingTagName.trim());
                              setEditingTagId(null);
                              setEditingTagName('');
                            }}
                            className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            aria-label="Cancel rename"
                            onClick={() => {
                              setEditingTagId(null);
                              setEditingTagName('');
                            }}
                            className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT: concept list panel */}
      <div className="flex flex-1 min-h-0 flex-col">
        {!selectedTag ? (
          <div className="grid h-full place-items-center px-10 py-20">
            <div className="text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-50 ring-1 ring-indigo-100">
                <Tag className="h-6 w-6 text-indigo-500"/>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-900">Select a tag to assign concepts</h3>
              <p className="mt-2 max-w-md text-sm text-slate-500">
                Choose a linguistic tag on the left to browse and bulk-assign it across your {concepts.length} concepts.
                You can also create a new tag above.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="shrink-0 border-b border-slate-200 bg-white px-6 py-4">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full ring-2 ring-white" style={{ background: selectedTag.color, boxShadow: '0 0 0 1px rgb(226 232 240)' }}/>
                <h1 className="text-lg font-semibold tracking-tight text-slate-900">{selectedTag.name}</h1>
                <Pill tone="indigo">{selectedTag.count} concepts</Pill>
              </div>
              <div className="relative mt-3">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"/>
                <input
                  value={conceptSearch}
                  onChange={e => setConceptSearch(e.target.value)}
                  placeholder="Search concepts…"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </div>
            </div>
            <nav className="flex-1 overflow-y-auto px-2 py-2">
              {filteredConcepts.map(c => {
                const tagged = taggedKeys.has(c.key);
                return (
                  <button
                    key={c.id}
                    onClick={() => selectedTagId && (tagged ? untagConcept(selectedTagId, c.key) : tagConcept(selectedTagId, c.key))}
                    className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${tagged ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagDot[c.tag]}`}/>
                    <span className={`flex-1 text-[13px] ${tagged ? 'font-semibold' : 'font-medium'}`}>{c.name}</span>
                    <span className={`font-mono text-[10px] ${tagged ? 'text-indigo-400' : 'text-slate-300'}`}>#{c.id}</span>
                    {tagged && <Check className="h-3.5 w-3.5 shrink-0 text-indigo-500"/>}
                  </button>
                );
              })}
            </nav>
          </>
        )}
      </div>
    </div>
  );
};

// ---------- Annotate View ----------
interface AnnotateViewProps {
  concept: Concept;
  speaker: string;
  totalConcepts: number;
  onPrev: () => void;
  onNext: () => void;
  audioUrl: string;
  peaksUrl?: string;
  onCaptureOffsetAnchor?: () => void;
  captureToast?: string | null;
}

const AnnotateView: React.FC<AnnotateViewProps> = ({ concept, speaker, totalConcepts, onPrev, onNext, audioUrl, peaksUrl, onCaptureOffsetAnchor, captureToast }) => {
  const record = useAnnotationStore(s => s.records[speaker] ?? null);
  const setInterval = useAnnotationStore(s => s.setInterval);
  const moveIntervalAcrossTiers = useAnnotationStore(s => s.moveIntervalAcrossTiers);
  const saveSpeaker = useAnnotationStore(s => s.saveSpeaker);
  const undoAnnotation = useAnnotationStore(s => s.undo);
  const redoAnnotation = useAnnotationStore(s => s.redo);
  const undoRedoHistory = useAnnotationStore(s => s.histories[speaker] ?? null);
  const canUndo = (undoRedoHistory?.undo.length ?? 0) > 0;
  const canRedo = (undoRedoHistory?.redo.length ?? 0) > 0;
  const nextUndoLabel = canUndo ? undoRedoHistory!.undo[undoRedoHistory!.undo.length - 1].label : '';
  const nextRedoLabel = canRedo ? undoRedoHistory!.redo[undoRedoHistory!.redo.length - 1].label : '';
  const [undoToast, setUndoToast] = useState<string | null>(null);
  useEffect(() => {
    if (!undoToast) return;
    const t = window.setTimeout(() => setUndoToast(null), 2200);
    return () => window.clearTimeout(t);
  }, [undoToast]);
  const handleUndo = useCallback(() => {
    const label = undoAnnotation(speaker);
    if (label) setUndoToast(`Undid ${label}`);
  }, [speaker, undoAnnotation]);
  const handleRedo = useCallback(() => {
    const label = redoAnnotation(speaker);
    if (label) setUndoToast(`Redid ${label}`);
  }, [speaker, redoAnnotation]);
  // Ctrl/Cmd+Z = undo, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y = redo. Suppressed while
  // the user is typing in inputs, textareas, selects, or a contenteditable
  // element (the inline lane editor) so their keystrokes don't get hijacked.
  useEffect(() => {
    if (!speaker) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (target.isContentEditable) return;
      }
      const key = e.key.toLowerCase();
      if (key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        e.preventDefault();
        handleRedo();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [speaker, handleUndo, handleRedo]);
  const tagConcept = useTagStore(s => s.tagConcept);

  const { conceptInterval, ipaInterval, orthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept),
    [record, concept]
  );
  const [ipa, setIpa] = useState(ipaInterval?.text ?? '');
  const [ortho, setOrtho] = useState(orthoInterval?.text ?? '');
  // Editable timestamp fields for the current lexeme (seeded from the concept tier interval).
  const [editStart, setEditStart] = useState<string>(conceptInterval ? conceptInterval.start.toFixed(3) : '');
  const [editEnd, setEditEnd] = useState<string>(conceptInterval ? conceptInterval.end.toFixed(3) : '');
  const [timestampSaving, setTimestampSaving] = useState(false);
  const [timestampMessage, setTimestampMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  useEffect(() => {
    setIpa(ipaInterval?.text ?? '');
    setOrtho(orthoInterval?.text ?? '');
    setEditStart(conceptInterval ? conceptInterval.start.toFixed(3) : '');
    setEditEnd(conceptInterval ? conceptInterval.end.toFixed(3) : '');
    setTimestampMessage(null);
  }, [speaker, concept.key, conceptInterval, ipaInterval, orthoInterval]);

  const [spectroOn, setSpectroOn] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [readyAudioUrl, setReadyAudioUrl] = useState('');
  const [zoom, setZoom] = useState(10); // minPxPerSec

  const containerRef = useRef<HTMLDivElement>(null);
  const spectroCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const isPlaying = usePlaybackStore(s => s.isPlaying);
  const currentTime = usePlaybackStore(s => s.currentTime);
  const duration = usePlaybackStore(s => s.duration);
  const selectedRegion = usePlaybackStore(s => s.selectedRegion);
  const annotated = Boolean(conceptInterval && ipaInterval);

  // Ref mirror of the currently stored concept interval. Used from the
  // onRegionCommit closure (which is captured on WaveSurfer init) so it
  // always sees the latest stored start/end when the user releases a drag.
  const storedIntervalRef = useRef<{ start: number; end: number } | null>(null);
  useEffect(() => {
    storedIntervalRef.current = conceptInterval
      ? { start: conceptInterval.start, end: conceptInterval.end }
      : null;
  }, [conceptInterval]);

  const { playPause, playRange, pause, seek, scrollToTimeAtFraction, skip, addRegion, setZoom: wsSetZoom, setRate, wsRef } = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl,
    onTimeUpdate: t => usePlaybackStore.setState({ currentTime: t }),
    onReady: d => {
      usePlaybackStore.setState({ duration: d });
      setAudioReady(true);
      setReadyAudioUrl(audioUrl);
    },
    onPlayStateChange: p => usePlaybackStore.setState({ isPlaying: p }),
    onRegionUpdate: (start, end) => {
      usePlaybackStore.setState({ selectedRegion: { start, end } });
      // Dragging/resizing the waveform region mirrors into the editable fields.
      setEditStart(start.toFixed(3));
      setEditEnd(end.toFixed(3));
    },
    onRegionCommit: (start, end) => {
      // Auto-save: when the user finishes dragging/resizing the region,
      // retime the current lexeme across all tiers and persist to the
      // annotation JSON. No Save button needed for region edits.
      const prev = storedIntervalRef.current;
      if (!prev) return;
      if (Math.abs(prev.start - start) < 0.001 && Math.abs(prev.end - end) < 0.001) return;
      if (end <= start) return;
      const moved = moveIntervalAcrossTiers(speaker, prev.start, prev.end, start, end);
      if (moved > 0) {
        storedIntervalRef.current = { start, end };
        setEditStart(start.toFixed(3));
        setEditEnd(end.toFixed(3));
        void saveSpeaker(speaker);
        setTimestampMessage({ kind: 'ok', text: `Saved · ${moved} tier${moved === 1 ? '' : 's'}` });
      }
    },
  });

  // Press Play (or Space) on a selected region → clip-bounded playback that
  // stops at the region end. No region selected → plain play/pause toggle.
  const handlePlayToggle = useCallback(() => {
    if (isPlaying) {
      pause();
      return;
    }
    if (selectedRegion) {
      playRange(selectedRegion.start, selectedRegion.end);
    } else {
      playPause();
    }
  }, [isPlaying, selectedRegion, pause, playRange, playPause]);

  // Global Space hotkey for play/pause. Skips when the user is typing so the
  // IPA and orthographic fields keep accepting spaces.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== " " && e.code !== "Space") return;
      const t = e.target as HTMLElement | null;
      if (t) {
        const tag = t.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select" || t.isContentEditable) return;
      }
      e.preventDefault();
      handlePlayToggle();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlePlayToggle]);

  // Speaker switches replace the underlying WaveSurfer instance. Reset the
  // ready gate and playback clock first so annotate-side seek/region effects
  // wait for the new audio file instead of operating on a half-torn-down
  // instance from the previous speaker.
  useEffect(() => {
    setAudioReady(false);
    setReadyAudioUrl('');
    usePlaybackStore.setState({
      currentTime: 0,
      duration: 0,
      isPlaying: false,
      selectedRegion: null,
    });
  }, [audioUrl]);

  // When the user picks a concept (and once the waveform is ready): zoom
  // in to 400 px/s, seek to its start, draw the lexeme range as a draggable
  // region, and scroll so the start sits at ~33% from the left of the
  // viewport (leaves more of the trailing audio visible than centering).
  useEffect(() => {
    if (!audioReady || readyAudioUrl !== audioUrl || !conceptInterval) return;
    wsSetZoom(400);
    setZoom(400);
    seek(conceptInterval.start);
    addRegion(conceptInterval.start, conceptInterval.end);
    scrollToTimeAtFraction(conceptInterval.start, 0.33);
  }, [audioReady, readyAudioUrl, audioUrl, conceptInterval?.start, conceptInterval?.end, seek, addRegion, wsSetZoom, scrollToTimeAtFraction]);

  useSpectrogram({ enabled: spectroOn && audioReady, wsRef, canvasRef: spectroCanvasRef });

  // Cross-component seek bridge — the right-panel "Search & anchor" block
  // calls usePlaybackStore.requestSeek(targetSec); we watch the nonce and
  // drive our local wavesurfer seek.
  const pendingSeek = usePlaybackStore(s => s.pendingSeek);
  useEffect(() => {
    if (!pendingSeek) return;
    if (!audioReady || readyAudioUrl !== audioUrl) return;
    seek(pendingSeek.targetSec);
    scrollToTimeAtFraction(pendingSeek.targetSec, 0.33);
  }, [pendingSeek?.nonce, audioReady, readyAudioUrl, audioUrl, seek, scrollToTimeAtFraction]);

  // fmt now lives at module scope (formatPlaybackTime) — kept as a local
  // alias so the inline JSX below stays diff-friendly with prior versions.
  const fmt = formatPlaybackTime;

  return (
    <main className="flex-1 overflow-y-auto bg-slate-50">
      {/* ======= WAVEFORM / VIRTUAL TIMELINE ======= */}
      <section className="border-b border-slate-200 bg-white">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
          <div className="flex items-center gap-1">
            <button
              title="Previous segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const prev = intervals
                  .filter(iv => iv.end < currentTime - 0.1)
                  .sort((a, b) => b.end - a.end)[0];
                if (prev) {
                  skip(-(currentTime - prev.start));
                } else {
                  skip(-currentTime);
                }
              }}
            >
              <SkipBack className="h-3.5 w-3.5"/>
            </button>
            <button
              title="Next segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const next = intervals
                  .filter(iv => iv.start > currentTime + 0.1)
                  .sort((a, b) => a.start - b.start)[0];
                if (next) {
                  skip(next.start - currentTime);
                }
              }}
            >
              <SkipForward className="h-3.5 w-3.5"/>
            </button>
            <div className="mx-2 h-5 w-px bg-slate-200"/>
            <button onClick={() => { const z = Math.max(10, zoom - 20); setZoom(z); wsSetZoom(z); }} title="Zoom out" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomOut className="h-3.5 w-3.5"/>
            </button>
            <div className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">{zoom}px/s</div>
            <button onClick={() => { const z = Math.min(500, zoom + 20); setZoom(z); wsSetZoom(z); }} title="Zoom in" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomIn className="h-3.5 w-3.5"/>
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setSpectroOn(v => !v)}
              title="Toggle spectrogram"
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-semibold transition ${spectroOn ? 'bg-indigo-600 text-white' : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'}`}
            >
              <Activity className="h-3 w-3"/> Spectrogram
            </button>
          </div>
        </div>

        {/* Waveform container — WaveSurfer owns this div. The left padding on
            the inner wrapper matches the lane label gutter so waveform t=0
            lines up with segment t=0 in the STT/IPA/ORTH strips, without
            wrapping WaveSurfer's container in a flex row (which caused the
            container width to be unstable on first render and made the
            Timeline plugin flicker). */}
        <div className="relative px-5 pt-4 pb-2">
          <div className="relative" style={{ paddingLeft: LABEL_COL_PX }}>
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-lg ring-1 ring-slate-100"
              style={{ minHeight: 110 }}
            />
            {spectroOn && (
              <canvas
                ref={spectroCanvasRef}
                className="pointer-events-none absolute inset-y-0 right-0 rounded-lg"
                style={{ left: LABEL_COL_PX, opacity: 0.6, mixBlendMode: 'multiply' }}
              />
            )}
          </div>
        </div>

        {/* Transcription lanes — STT / IPA / ORTH, toggled from the right drawer */}
        <TranscriptionLanes speaker={speaker} wsRef={wsRef} audioReady={audioReady} onSeek={seek}/>
      </section>

      {/* ======= CONCEPT HEADER ======= */}
      <section className="px-8 pt-6">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-center gap-3">
            <button
              onClick={onPrev}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
            >
              <span>←</span>
              <span>Prev</span>
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Concept <span className="font-mono">#{concept.id}</span> <span>·</span> {concept.id} of {totalConcepts}
              </div>
              <div className="mt-0.5 flex items-center gap-3">
                <h1 className="text-[32px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
                <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                  {speaker}
                </span>
                {annotated ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    Annotated
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 ring-1 ring-rose-200">
                    Missing
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
                <span className="text-[9px] uppercase tracking-wider text-slate-400">Source</span>
                <span className="text-slate-500">{speaker}.wav</span>
              </div>
            </div>
            <button
              onClick={onNext}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
            >
              <span>Next</span>
              <span>→</span>
            </button>
          </div>
        </div>
      </section>

      {/* ======= TRANSCRIPTION FIELDS ======= */}
      <section className="px-8 py-6">
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">IPA Transcription</label>
            <input
              value={ipa}
              onChange={e => setIpa(e.target.value)}
              placeholder="Enter IPA…"
              dir="ltr"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-lg text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Orthographic (Kurdish)</label>
            <input
              value={ortho}
              onChange={e => setOrtho(e.target.value)}
              placeholder="Enter orthographic form…"
              dir="rtl"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-serif text-xl text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          {/* Timestamp editor for the current lexeme */}
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Lexeme timestamp (seconds)</label>
              {conceptInterval ? (
                <span className="font-mono text-[10px] text-slate-400">{fmt(conceptInterval.start)}–{fmt(conceptInterval.end)}</span>
              ) : (
                <span className="font-mono text-[10px] text-slate-400">no interval</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-slate-500">Start</span>
                <input
                  data-testid="lexeme-start"
                  type="number"
                  step={0.001}
                  min={0}
                  value={editStart}
                  onChange={e => setEditStart(e.target.value)}
                  disabled={!conceptInterval}
                  className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-slate-500">End</span>
                <input
                  data-testid="lexeme-end"
                  type="number"
                  step={0.001}
                  min={0}
                  value={editEnd}
                  onChange={e => setEditEnd(e.target.value)}
                  disabled={!conceptInterval}
                  className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                />
              </div>
              <button
                data-testid="lexeme-timestamp-save"
                disabled={!conceptInterval || timestampSaving}
                onClick={async () => {
                  if (!conceptInterval) return;
                  const ns = parseFloat(editStart);
                  const ne = parseFloat(editEnd);
                  if (!Number.isFinite(ns) || !Number.isFinite(ne) || ne <= ns) {
                    setTimestampMessage({ kind: 'err', text: 'End must be greater than start.' });
                    return;
                  }
                  setTimestampSaving(true);
                  try {
                    const moved = moveIntervalAcrossTiers(speaker, conceptInterval.start, conceptInterval.end, ns, ne);
                    if (moved === 0) {
                      setTimestampMessage({ kind: 'err', text: 'No matching intervals found to retime.' });
                    } else {
                      await saveSpeaker(speaker);
                      setTimestampMessage({ kind: 'ok', text: `Retimed ${moved} tier${moved === 1 ? '' : 's'}.` });
                      addRegion(ns, ne);
                      seek(ns);
                    }
                  } catch (err) {
                    setTimestampMessage({ kind: 'err', text: err instanceof Error ? err.message : String(err) });
                  } finally {
                    setTimestampSaving(false);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5"/> Save timestamp
              </button>
              <button
                data-testid="lexeme-timestamp-reset"
                disabled={!conceptInterval}
                onClick={() => {
                  if (!conceptInterval) return;
                  setEditStart(conceptInterval.start.toFixed(3));
                  setEditEnd(conceptInterval.end.toFixed(3));
                  addRegion(conceptInterval.start, conceptInterval.end);
                  seek(conceptInterval.start);
                  setTimestampMessage(null);
                }}
                className="text-[11px] font-medium text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline disabled:opacity-50"
              >
                Reset
              </button>
              {timestampMessage && (
                <span data-testid="lexeme-timestamp-msg" className={`ml-auto text-[11px] ${timestampMessage.kind === 'ok' ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {timestampMessage.text}
                </span>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => {
                if (!selectedRegion) return;
                const interval = { start: selectedRegion.start, end: selectedRegion.end };
                setInterval(speaker, 'ipa', { ...interval, text: ipa });
                setInterval(speaker, 'ortho', { ...interval, text: ortho });
                setInterval(speaker, 'concept', { ...interval, text: concept.name });
                void saveSpeaker(speaker);
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700"
            >
              <Save className="h-4 w-4"/> Save Annotation
            </button>
            <button
              onClick={() => tagConcept('confirmed', concept.key)}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
            >
              <Check className="h-4 w-4"/> Mark Done
            </button>
            {onCaptureOffsetAnchor && (
              <div className="relative">
                <button
                  onClick={onCaptureOffsetAnchor}
                  data-testid="annotate-capture-anchor"
                  title="Anchor offset detection to this lexeme + the current playback time. Locks this lexeme against future global offset passes."
                  className="inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-100"
                >
                  <Anchor className="h-4 w-4"/> Anchor offset here
                </button>
                {captureToast && (
                  <div
                    role="status"
                    data-testid="annotate-capture-toast"
                    className="absolute bottom-full left-0 mb-1.5 whitespace-nowrap rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 shadow-md"
                  >
                    {captureToast}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ======= BOTTOM PLAYBACK BAR ======= */}
      <section className="sticky bottom-0 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-8 py-3">
          <button onClick={() => skip(-5)} title="-5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipBack className="h-4 w-4"/></button>
          <button onClick={() => skip(-1)} title="-1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronLeft className="h-4 w-4"/></button>
          <button
            onClick={handlePlayToggle}
            title={selectedRegion ? "Play selected region (Space)" : "Play (Space)"}
            data-testid="annotate-play"
            className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white shadow-sm hover:bg-slate-700"
          >
            {isPlaying ? <Pause className="h-4 w-4"/> : <Play className="h-4 w-4 translate-x-[1px]"/>}
          </button>
          <button onClick={() => skip(1)} title="+1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronRight className="h-4 w-4"/></button>
          <button onClick={() => skip(5)} title="+5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipForward className="h-4 w-4"/></button>

          <div className="ml-2 font-mono text-[11px] tabular-nums text-slate-500">
            {fmt(currentTime)} <span className="text-slate-300">/</span> {fmt(duration)}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <select defaultValue="1" onChange={e => setRate(Number(e.target.value))} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 focus:border-indigo-300 focus:outline-none">
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1">1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
            <button
              onClick={handleUndo}
              disabled={!canUndo}
              data-testid="annotate-undo"
              title={canUndo ? `Undo ${nextUndoLabel} (⌘Z)` : 'Nothing to undo'}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Undo2 className="h-3 w-3"/> Undo
            </button>
            <button
              onClick={handleRedo}
              disabled={!canRedo}
              data-testid="annotate-redo"
              title={canRedo ? `Redo ${nextRedoLabel} (⇧⌘Z)` : 'Nothing to redo'}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Redo2 className="h-3 w-3"/> Redo
            </button>
            <button className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">
              <MessageSquare className="h-3 w-3"/> Chat
            </button>
          </div>
        </div>
        {undoToast && (
          <div
            role="status"
            data-testid="annotate-undo-toast"
            className="pointer-events-none absolute bottom-14 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-indigo-200 bg-white px-3 py-1 text-[11px] text-indigo-700 shadow-md"
          >
            {undoToast}
          </div>
        )}
      </section>
    </main>
  );
};

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
  const [conceptImportError, setConceptImportError] = useState<string | null>(null);
  const [conceptImportSummary, setConceptImportSummary] = useState<string | null>(null);
  const conceptImportInputRef = useRef<HTMLInputElement>(null);
  const [tagFilter, setTagFilter] = useState<string>('all');
  const [conceptId, setConceptId] = useState(1);
  const [selectedSpeakers, setSelectedSpeakers] = useState<string[]>([]);
  const [speakerPicker, setSpeakerPicker] = useState<string | null>(null);
  const [computeMode, setComputeMode] = useState('cognates');
  const { start: startComputeJob, state: computeJobState, reset: resetComputeJob } = useComputeJob(computeMode);
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
    start: () => startCompute('similarity'),
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

  // The ``detecting`` / ``applying`` phases now carry the backend job id
  // and the worker's latest progress checkpoint so the header chip can
  // mirror what the worker is doing in real time. The ``error`` phase
  // keeps ``jobId`` so the "View crash log" button can call
  // ``GET /api/jobs/<id>/logs`` for the full stderr tail + Python
  // traceback.
  const [offsetState, setOffsetState] = useState<
    | { phase: 'idle' }
    | { phase: 'detecting'; jobId: string | null; progress: number; progressMessage?: string; origin: 'auto' | 'manual' }
    | { phase: 'detected'; result: OffsetDetectResult }
    | { phase: 'manual' }
    | { phase: 'applying'; result: OffsetDetectResult }
    | { phase: 'applied'; result: OffsetDetectResult; shifted: number; protected: number }
    | { phase: 'error'; message: string; traceback?: string; jobId?: string }
  >({ phase: 'idle' });

  // Modal for viewing a failed compute job's error + traceback +
  // worker stderr tail. Reachable from the offset header chip's "View
  // crash log" button and from the inline error panel.
  const [jobLogsOpen, setJobLogsOpen] = useState<string | null>(null);

  // Manual-pair anchors live at parent scope so the playback-bar capture
  // button (Annotate mode) and the modal share the same list. Each anchor
  // captures the lexeme's current annotation time *at the moment of
  // capture* — that's the "csv time" — plus the audio cursor position
  // (the "audio time"). Per-pair offset = audioTimeSec − csvTimeSec.
  type ManualAnchor = {
    conceptKey: string;
    conceptName: string;
    csvTimeSec: number;
    audioTimeSec: number;
    capturedAt: number;
  };
  const [manualAnchors, setManualAnchors] = useState<ManualAnchor[]>([]);
  const [manualBusy, setManualBusy] = useState(false);

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

  // Briefly-flashed inline confirmation when the user captures an anchor
  // straight from the playback bar. Vanishes after a couple of seconds so
  // the chrome stays calm.
  const [captureToast, setCaptureToast] = useState<string | null>(null);
  useEffect(() => {
    if (!captureToast) return;
    const handle = window.setTimeout(() => setCaptureToast(null), 2200);
    return () => window.clearTimeout(handle);
  }, [captureToast]);

  // Look up the current annotation interval (start + end) for a concept on
  // the active speaker (read directly from the store so we don't hold a
  // hook subscription at parent scope).
  const lookupConceptInterval = (
    speaker: string,
    concept: Concept,
  ): { start: number; end: number } | null => {
    const records = useAnnotationStore.getState().records;
    const record = records[speaker];
    if (!record) return null;
    const intervals = record.tiers?.concept?.intervals ?? [];
    const interval = intervals.find((iv) => conceptMatchesIntervalText(concept, iv.text));
    return interval ? { start: interval.start, end: interval.end } : null;
  };

  const markLexemeManuallyAdjusted = useAnnotationStore(
    (s) => s.markLexemeManuallyAdjusted,
  );

  // Capture an anchor from the currently-selected concept + the current
  // playback time. Wired to BOTH the in-Annotate "Anchor offset here"
  // button and the modal's "Capture from current selection" button.
  //
  // Capturing an anchor is also an assertion that this lexeme's timing is
  // now correct — so we flag the underlying interval as manuallyAdjusted
  // immediately. A subsequent global offset will skip it, protecting the
  // user's work from being shifted again.
  const captureCurrentAnchor = (): { ok: boolean; message: string } => {
    if (!activeActionSpeaker) {
      return { ok: false, message: 'Select a speaker first.' };
    }
    const conc = concepts.find((c) => c.id === conceptId) ?? null;
    if (!conc) {
      return { ok: false, message: 'Select a lexeme in the sidebar first.' };
    }
    const interval = lookupConceptInterval(activeActionSpeaker, conc);
    if (interval === null) {
      return {
        ok: false,
        message: `No annotation interval for "${conc.name}" — open the lexeme in Annotate first.`,
      };
    }
    const audio = usePlaybackStore.getState().currentTime;
    if (audio <= 0) {
      return {
        ok: false,
        message: 'Scrub the waveform to where the lexeme actually is, then capture again.',
      };
    }
    setManualAnchors((prev) => {
      // Replace any existing anchor for the same concept — capturing
      // again on the same lexeme is a "I changed my mind, this is the
      // right audio position" gesture, not a duplicate.
      const filtered = prev.filter((a) => a.conceptKey !== conc.key);
      return [
        ...filtered,
        {
          conceptKey: conc.key,
          conceptName: conc.name,
          csvTimeSec: interval.start,
          audioTimeSec: audio,
          capturedAt: Date.now(),
        },
      ];
    });
    // Flag this lexeme as manually-adjusted so a later global offset
    // skips it. Scenario: the user fixes lexemes 1–5 (or captures anchors
    // for them), then later anchors lexemes 10–20 and applies +0.5s. The
    // flag is what keeps 1–5 from being shifted again and undoing their
    // verified timing. Capturing an anchor here is an explicit assertion
    // that this lexeme is correctly placed — no reason to wait for the
    // user to press Review & apply before locking it.
    markLexemeManuallyAdjusted(activeActionSpeaker, interval.start, interval.end);
    const offset = audio - interval.start;
    const sign = offset >= 0 ? '+' : '';
    return {
      ok: true,
      message: `Anchored ${conc.name} @ ${formatPlaybackTime(audio)} → ${sign}${offset.toFixed(2)}s offset.`,
    };
  };

  const captureAnchorFromBar = () => {
    const result = captureCurrentAnchor();
    setCaptureToast(result.message);
  };

  const removeManualAnchor = (conceptKey: string) => {
    setManualAnchors((prev) => prev.filter((a) => a.conceptKey !== conceptKey));
  };

  // Live consensus offset across captured anchors — median of per-pair
  // offsets, plus median absolute deviation as a disagreement metric.
  // Computed client-side so the user gets zero-latency feedback as they
  // add or remove anchors. The backend re-derives the same number when
  // the user clicks Apply, so this is purely UI.
  const manualConsensus = useMemo(() => {
    if (!manualAnchors.length) {
      return null;
    }
    const offsets = manualAnchors.map((a) => a.audioTimeSec - a.csvTimeSec);
    const sorted = [...offsets].sort((a, b) => a - b);
    const median =
      sorted.length % 2
        ? sorted[(sorted.length - 1) / 2]
        : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
    const deviations = offsets.map((o) => Math.abs(o - median)).sort((a, b) => a - b);
    const mad =
      deviations.length === 1
        ? 0
        : deviations.length % 2
        ? deviations[(deviations.length - 1) / 2]
        : (deviations[deviations.length / 2 - 1] + deviations[deviations.length / 2]) / 2;
    return {
      median,
      mad,
      offsets,
    };
  }, [manualAnchors]);

  const detectOffsetForSpeaker = async () => {
    setActionsMenuOpen(false);
    if (!activeActionSpeaker) {
      setOffsetState({ phase: 'error', message: 'Select a speaker first.' });
      return;
    }
    setOffsetState({ phase: 'detecting', jobId: null, progress: 0, origin: 'auto' });
    let submittedJobId: string | null = null;
    try {
      const { jobId } = await detectTimestampOffset(activeActionSpeaker);
      if (!jobId) throw new Error('Server did not return a job ID for offset detection');
      submittedJobId = jobId;
      setOffsetState({ phase: 'detecting', jobId, progress: 0, origin: 'auto' });
      const result = await pollOffsetDetectJob(jobId, 'offset_detect', {
        onProgress: ({ progress, message }) => {
          setOffsetState((prev) =>
            prev.phase === 'detecting'
              ? { ...prev, progress, progressMessage: message }
              : prev,
          );
        },
      });
      setOffsetState({ phase: 'detected', result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const traceback = err instanceof OffsetJobError ? err.traceback : undefined;
      const jobId = err instanceof OffsetJobError ? err.jobId : submittedJobId ?? undefined;
      setOffsetState({ phase: 'error', message, traceback, jobId });
    }
  };

  const applyDetectedOffset = async () => {
    if (offsetState.phase !== 'detected') return;
    const { result } = offsetState;
    setOffsetState({ phase: 'applying', result });
    try {
      const apply = await applyTimestampOffset(result.speaker, result.offsetSec);
      await reloadSpeakerAnnotation(result.speaker);
      setOffsetState({
        phase: 'applied',
        result,
        shifted: apply.shiftedIntervals,
        protected: apply.protectedIntervals ?? 0,
      });
    } catch (err) {
      setOffsetState({
        phase: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const submitManualOffset = async () => {
    if (!activeActionSpeaker) {
      setOffsetState({ phase: 'error', message: 'Select a speaker first.' });
      return;
    }
    if (!manualAnchors.length) {
      setOffsetState({
        phase: 'error',
        message: 'Capture at least one anchor before computing the offset.',
      });
      return;
    }
    setManualBusy(true);
    let submittedJobId: string | null = null;
    try {
      const pairs: OffsetPair[] = manualAnchors.map((a) => ({
        audioTimeSec: a.audioTimeSec,
        csvTimeSec: a.csvTimeSec,
      }));
      const { jobId } = await detectTimestampOffsetFromPairs(activeActionSpeaker, pairs);
      if (!jobId) throw new Error('Server did not return a job ID');
      submittedJobId = jobId;
      setOffsetState({ phase: 'detecting', jobId, progress: 0, origin: 'manual' });
      const result = await pollOffsetDetectJob(jobId, 'offset_detect_from_pair', {
        onProgress: ({ progress, message }) => {
          setOffsetState((prev) =>
            prev.phase === 'detecting'
              ? { ...prev, progress, progressMessage: message }
              : prev,
          );
        },
      });
      setOffsetState({ phase: 'detected', result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const traceback = err instanceof OffsetJobError ? err.traceback : undefined;
      const jobId = err instanceof OffsetJobError ? err.jobId : submittedJobId ?? undefined;
      setOffsetState({ phase: 'error', message, traceback, jobId });
    } finally {
      setManualBusy(false);
    }
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
      const blob = await getLingPyExport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'parse-wordlist.tsv';
      a.click();
      URL.revokeObjectURL(url);
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

  // — Derived: tags list from store —
  const tagsList = useMemo<LingTag[]>(() =>
    storeTags.map(t => ({ id: t.id, name: t.label, color: t.color, dotClass: '', count: t.concepts.length })),
    [storeTags]
  );

  // AI bottom panel
  const [aiHeight, setAiHeight] = useState(() => Math.round(window.innerHeight * 0.4));
  const [aiMinimized, setAiMinimized] = useState(true);
  const resizingRef = useRef(false);
  const loadDecisionsRef = useRef<HTMLInputElement>(null);
  const loadDecisionsMenuRef = useRef<HTMLInputElement>(null);

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

  const handleCustomListImport = async (file: File) => {
    setConceptImportError(null);
    setConceptImportSummary(null);
    const defaultName = file.name.replace(/\.csv$/i, '');
    const tagName = window.prompt('Tag name for this concept list:', defaultName);
    if (tagName === null) return; // user cancelled
    try {
      const result = await importTagCsv(file, { tagName: tagName.trim() || defaultName });
      const missedNote = result.missedCount > 0 ? `, ${result.missedCount} unmatched` : '';
      setConceptImportSummary(`Tag "${result.tagName}": ${result.matchedCount} concepts assigned${missedNote}`);
      // Refresh server-backed tags so the new tag appears in the Manage Tags view
      await useTagStore.getState().syncFromServer();
    } catch (err) {
      setConceptImportError(err instanceof Error ? err.message : String(err));
    }
  };

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
                    onClick={() => setJobLogsOpen(offsetState.jobId!)}
                    className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-rose-700 underline hover:text-rose-800"
                    data-testid="topbar-offset-view-log"
                  >
                    View crash log
                  </button>
                )}
                {isError && (
                  <button
                    onClick={() => setOffsetState({ phase: 'idle' })}
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
                      onClick={() => { setActionsMenuOpen(false); loadDecisionsMenuRef.current?.click(); }}
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <Upload className="h-3.5 w-3.5 text-slate-400"/> Load Decisions
                    </button>
                    <button onClick={() => setActionsMenuOpen(false)} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50">
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
                  if (file) void handleCustomListImport(file);
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
        <aside className="w-[250px] shrink-0 border-r border-slate-200/80 bg-white flex flex-col">
          <div className="p-4 shrink-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search concepts…"
                className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"/>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <div className="inline-flex rounded-md bg-slate-100 p-0.5">
                <button data-testid="concept-sort-az" onClick={() => setSortMode('az')} title="Sort alphabetically by label" className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode==='az'?'bg-white text-slate-800 shadow-sm':'text-slate-500'}`}>A→Z</button>
                <button data-testid="concept-sort-1n" onClick={() => setSortMode('1n')} title="Sort by concept id" className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode==='1n'?'bg-white text-slate-800 shadow-sm':'text-slate-500'}`}>1→N</button>
                <button
                  data-testid="concept-sort-survey"
                  onClick={() => setSortMode('survey')}
                  disabled={!hasSurveyItems}
                  title={hasSurveyItems ? 'Sort by original survey item (section.item)' : 'No survey_item values present in concepts.csv'}
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded ${sortMode==='survey'?'bg-white text-slate-800 shadow-sm':'text-slate-500'} ${!hasSurveyItems ? 'cursor-not-allowed opacity-40' : ''}`}
                >Survey</button>
              </div>
              <span className="ml-auto text-[10px] text-slate-400">{filtered.length} concepts</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {/* Built-in filter pills — replace the old header tabs.
                  Order: All (reset) · Unreviewed · Flagged · Borrowings.
                  Each is a tag-shaped pill with a distinctive accent
                  colour so they read as semantic filters, not as user
                  tags. Clicking an active pill returns to "All". */}
              <button
                onClick={() => setTagFilter('all')}
                data-testid="tagfilter-all"
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'all' ? 'bg-slate-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
              >All</button>
              <button
                onClick={() => setTagFilter(tagFilter === 'unreviewed' ? 'all' : 'unreviewed')}
                title="Concepts not yet confirmed and without a cognate assignment"
                data-testid="tagfilter-unreviewed"
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'unreviewed' ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'unreviewed' ? 'bg-white' : 'bg-amber-400'}`}/>
                Unreviewed
              </button>
              <button
                onClick={() => setTagFilter(tagFilter === 'flagged' ? 'all' : 'flagged')}
                title="Concepts tagged problematic, or with a flagged speaker utterance"
                data-testid="tagfilter-flagged"
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'flagged' ? 'bg-rose-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'flagged' ? 'bg-white' : 'bg-rose-400'}`}/>
                Flagged
              </button>
              <button
                onClick={() => setTagFilter(tagFilter === 'borrowings' ? 'all' : 'borrowings')}
                title="Concepts with at least one borrowing"
                data-testid="tagfilter-borrowings"
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === 'borrowings' ? 'bg-violet-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tagFilter === 'borrowings' ? 'bg-white' : 'bg-violet-400'}`}/>
                Borrowings
              </button>
              {/* User-defined tags, appended after the built-ins. */}
              {tagsList.map(t => (
                <button
                  key={t.id}
                  onClick={() => setTagFilter(tagFilter === t.id ? 'all' : t.id)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${tagFilter === t.id ? 'text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                  style={tagFilter === t.id ? { background: t.color } : {}}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: t.color }}/>
                  {t.name}
                </button>
              ))}
            </div>
          </div>
          <nav className="flex-1 overflow-y-auto px-2 pb-6">
            {filtered.map(c => {
              const active = c.id === conceptId;
              const badge = sortMode === 'survey' && c.surveyItem ? c.surveyItem : String(c.id);
              // Badge prefix lives in src/lib/surveySort.ts (empty in Survey
              // mode — the survey_item already carries its source; "#" in
              // numeric-id mode). Shared with the regression test.
              const badgePrefix = surveyBadgePrefix(sortMode);
              return (
                <button key={c.id} onClick={() => setConceptId(c.id)}
                  className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition ${active ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-50'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${tagDot[c.tag]}`} />
                  <span className={`flex-1 text-[13px] ${active ? 'font-semibold' : 'font-medium'}`}>{c.name}</span>
                  <span className={`font-mono text-[10px] ${active ? 'text-indigo-400' : 'text-slate-300'}`}>{badgePrefix}{badge}</span>
                </button>
              );
            })}
          </nav>
        </aside>

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
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'accepted', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <Check className="h-3.5 w-3.5"/> Accept grouping
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'split', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <Split className="h-3.5 w-3.5"/> Split
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const patch = { cognate_decisions: { [concept.key]: { decision: 'merge', ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
                    }}
                  >
                    <GitMerge className="h-3.5 w-3.5"/> Merge
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const current = (enrichmentData?.cognate_decisions as Record<string,{decision:string}>)?.[concept.key]?.decision ?? 'accepted';
                      const next = current === 'accepted' ? 'split' : current === 'split' ? 'merge' : 'accepted';
                      const patch = { cognate_decisions: { [concept.key]: { decision: next, ts: Date.now() } } };
                      void useEnrichmentStore.getState().save(patch);
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
        <aside
          className={`relative shrink-0 border-l border-slate-200/80 bg-white transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? 'w-[250px]' : 'w-[52px]'}`}
        >
          {/* Toggle */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/90 px-3 py-2.5 backdrop-blur">
            <span className={`text-[10px] font-semibold uppercase tracking-wider text-slate-500 transition-opacity duration-300 ${panelOpen ? 'opacity-100' : 'opacity-0'}`}>
              Controls
            </span>
            <button
              onClick={() => setPanelOpen(v => !v)}
              title={panelOpen ? 'Collapse' : 'Expand'}
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            >
              <PanelRightClose className={`h-3.5 w-3.5 transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? '' : 'rotate-180'}`}/>
            </button>
          </div>

          {/* Collapsed icon rail */}
          <div className={`absolute inset-x-0 top-[46px] flex flex-col items-center gap-1 py-3 transition-opacity duration-300 ${panelOpen ? 'pointer-events-none opacity-0' : 'opacity-100 delay-200'}`}>
            {[
              { icon: Database, label: 'Project' },
              { icon: UsersIcon, label: 'Speakers' },
              { icon: Cpu, label: 'Compute' },
              { icon: Filter, label: 'Filters' },
              { icon: Save, label: 'Decisions' },
            ].map(({ icon: Icon, label }) => (
              <button
                key={label}
                title={label}
                onClick={() => setPanelOpen(true)}
                className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600"
              >
                <Icon className="h-4 w-4"/>
              </button>
            ))}
          </div>

          {/* Expanded content */}
          <div className={`h-[calc(100%-46px)] overflow-y-auto overflow-x-hidden transition-opacity duration-300 ${panelOpen ? 'opacity-100 delay-200' : 'pointer-events-none opacity-0'}`} style={{ width: 250 }}>
            {/* --- COMMON: Speakers --- */}
            <div className="border-b border-slate-100 p-4">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Speakers {currentMode === 'annotate' && <span className="ml-1 rounded bg-indigo-50 px-1 py-0.5 font-mono text-[8px] text-indigo-600">SINGLE</span>}
                </h4>
                <span className="text-[10px] text-slate-400">
                  {currentMode === 'annotate' ? '1' : selectedSpeakers.length} / {speakers.length}
                </span>
              </div>
              <div className="mb-2 flex gap-1">
                <select
                  value={currentMode === 'annotate' ? (selectedSpeakers[0] ?? '') : (speakerPicker ?? '')}
                  onChange={e => {
                    if (currentMode === 'annotate') setSelectedSpeakers([e.target.value]);
                    else setSpeakerPicker(e.target.value);
                  }}
                  className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none">
                  {speakers.map(s => <option key={s}>{s}</option>)}
                </select>
                {currentMode === 'compare' && (
                  <button onClick={addSpeaker} className="grid h-6 w-6 place-items-center rounded-md bg-slate-900 text-white hover:bg-slate-700">
                    <Plus className="h-3 w-3"/>
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                {speakers.map(s => {
                  const active = currentMode === 'annotate' ? selectedSpeakers[0] === s : selectedSpeakers.includes(s);
                  return (
                    <button key={s} onClick={() => toggleSpeaker(s)}
                      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10px] transition ${active ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-slate-50 text-slate-400 ring-1 ring-slate-100 hover:text-slate-600'}`}>
                      {s}{active && currentMode === 'compare' && <X className="h-2.5 w-2.5"/>}
                      {active && currentMode === 'annotate' && <Check className="h-2.5 w-2.5"/>}
                    </button>
                  );
                })}
              </div>
              {currentMode === 'annotate' && (
                <p className="mt-2 text-[10px] leading-snug text-slate-400">
                  Concept list scoped to <span className="font-mono text-slate-600">{selectedSpeakers[0]}</span>'s dataset.
                </p>
              )}
            </div>

            {currentMode === 'compare' ? (
              <>
                {/* --- COMPARE: Compute --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Compute</h4>
                  <select value={computeMode} onChange={e => setComputeMode(e.target.value)}
                    className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none">
                    <option value="cognates">Cognates</option>
                    <option value="similarity">Phonetic similarity</option>
                    <option value="contact-lexemes">Borrowing detection (CLEF)</option>
                  </select>
                  <div className="mt-2 grid grid-cols-2 gap-1.5">
                    <button
                      className="inline-flex items-center justify-center gap-1 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                      onClick={handleComputeRun}
                      // Disable Run while *the relevant* job for the
                      // current mode is in flight. contact-lexemes routes
                      // through crossSpeakerJob (header chip); other modes
                      // still flow through the legacy useComputeJob.
                      disabled={
                        computeMode === 'contact-lexemes'
                          ? crossSpeakerJob.state.status === 'running'
                          : computeJobState.status === 'running'
                      }
                    >
                      <Play className="h-3 w-3"/> Run
                    </button>
                    <button
                      className="inline-flex items-center justify-center gap-1 rounded-md border border-slate-200 bg-white py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
                      onClick={() => { void useEnrichmentStore.getState().load(); }}
                    >
                      <RefreshCw className="h-3 w-3"/> Refresh
                    </button>
                  </div>
                  {computeMode === 'contact-lexemes' && (
                    <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px]">
                      <span className={clefConfigured ? "text-emerald-700" : "text-amber-700"}>
                        {clefConfigured === null
                          ? "Checking CLEF config…"
                          : clefConfigured
                            ? "CLEF configured"
                            : "CLEF not configured — Run will open setup"}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setSourcesReportOpen(true)}
                          data-testid="clef-sources-report-open"
                          className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-100"
                          title="Show which providers contributed each reference form (for citation)"
                        >
                          Sources Report
                        </button>
                        <button
                          onClick={() => setClefModalOpen(true)}
                          className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-100"
                        >
                          Configure
                        </button>
                      </div>
                    </div>
                  )}
                  {/* For contact-lexemes, progress + errors render in the
                      global header chip via ``crossSpeakerJob`` (matches
                      STT / IPA / forced-align / full_pipeline). The
                      drawer one-liner stays only for legacy compute
                      modes (cognates / phonetic similarity) that still
                      flow through ``useComputeJob``. */}
                  {computeMode !== 'contact-lexemes' && computeJobState.status === 'running' && (
                    <div className="mt-1 text-[10px] text-indigo-600">
                      Running… {Math.round(computeJobState.progress * 100)}%
                      {computeJobState.etaMs !== null && computeJobState.etaMs > 0 && (
                        <span className="text-slate-400"> · ~{formatEta(computeJobState.etaMs)} left</span>
                      )}
                    </div>
                  )}
                  {computeMode !== 'contact-lexemes' && computeJobState.status === 'error' && (
                    <div className="mt-1 text-[10px] text-rose-600">{computeJobState.error}</div>
                  )}
                </div>

                {/* --- COMPARE: Status --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Status</h4>
                  <div className="mb-2 flex items-center gap-2">
                    {speakers.length > 0 || concepts.length > 0 ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500"/>
                        <span className="text-[11px] font-semibold text-slate-700">project.json</span>
                        <span className="ml-auto text-[10px] text-slate-400">loaded</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-3.5 w-3.5 text-amber-500"/>
                        <span className="text-[11px] font-semibold text-slate-700">Workspace empty</span>
                      </>
                    )}
                  </div>
                  {speakers.length === 0 && concepts.length === 0 ? (
                    <div className="rounded-md bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                      No speakers or concepts imported yet. Use <span className="font-semibold">Import</span> to add data to this workspace.
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div className="rounded-md bg-slate-50 px-2 py-1.5">
                        <div className="font-mono text-sm font-semibold text-slate-900">{speakers.length}</div>
                        <div className="text-[9px] uppercase tracking-wider text-slate-400">speakers</div>
                      </div>
                      <div className="rounded-md bg-slate-50 px-2 py-1.5">
                        <div className="font-mono text-sm font-semibold text-slate-900">{concepts.length}</div>
                        <div className="text-[9px] uppercase tracking-wider text-slate-400">concepts</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* --- COMPARE: Filter by tag --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Filter className="h-3 w-3"/> Filter by tag
                  </h4>
                  <div className="space-y-1">
                    {([
                      ['all','All concepts','bg-slate-400'],
                      ['untagged','Untagged','bg-slate-300'],
                      ['review','Review needed','bg-amber-400'],
                      ['confirmed','Confirmed','bg-emerald-500'],
                      ['problematic','Problematic','bg-rose-500'],
                    ] as const).map(([key,label,dot]) => (
                      <button key={key} onClick={() => setTagFilter(key)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-[11px] transition ${tagFilter===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-600 hover:bg-slate-50'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${dot}`}/>{label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-4">
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Decisions</h4>
                  <div className="space-y-1.5">
                    <button
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                      onClick={() => loadDecisionsRef.current?.click()}
                    >
                      <Upload className="h-3 w-3"/> Load decisions
                    </button>
                    <button
                      className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
                      onClick={() => {
                        const json = JSON.stringify(enrichmentData, null, 2);
                        const blob = new Blob([json], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'parse-decisions.json';
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <Save className="h-3 w-3"/> Save decisions
                    </button>
                    <button
                      onClick={handleExportLingPy}
                      disabled={exporting}
                      className="flex w-full items-center gap-2 rounded-md bg-indigo-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      <Download className="h-3 w-3"/>
                      {exporting ? 'Exporting…' : 'Export LingPy TSV'}
                    </button>
                    <button
                      data-testid="open-comments-import"
                      onClick={() => setCommentsImportOpen(true)}
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <Upload className="h-3 w-3"/> Import Audition comments
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* --- ANNOTATE: Timestamp Tools --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Anchor className="h-3 w-3"/> Timestamp tools
                  </h4>
                  <p className="mb-3 text-[10px] leading-snug text-slate-400">
                    Shift every lexeme on this speaker by a constant offset.
                    Lexemes you have manually retimed or anchored are
                    protected and stay put.
                  </p>
                  <div className="space-y-1.5">
                    <button
                      onClick={() => { void detectOffsetForSpeaker(); }}
                      disabled={!activeActionSpeaker || offsetState.phase === 'detecting' || offsetState.phase === 'applying'}
                      data-testid="drawer-detect-offset"
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Anchor className="h-3 w-3 text-slate-400"/>
                      {offsetState.phase === 'detecting' ? 'Detecting offset…' : 'Detect Timestamp Offset'}
                    </button>
                    <button
                      onClick={() => setOffsetState({ phase: 'manual' })}
                      disabled={!activeActionSpeaker || offsetState.phase === 'detecting' || offsetState.phase === 'applying'}
                      data-testid="drawer-detect-offset-manual"
                      title="Skip auto-detect and anchor the offset from captured lexeme pairs directly."
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Anchor className="h-3 w-3 text-slate-400"/>
                      Detect offset (manual anchors)
                    </button>
                  </div>
                </div>

                {/* --- ANNOTATE: Phonetic Tools --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Activity className="h-3 w-3"/> Phonetic tools
                  </h4>
                  <p className="mb-3 text-[10px] leading-snug text-slate-400">
                    Tools operate on PARSE's virtual timeline — every action is scoped to the current audio segment.
                  </p>

                  {selectedSpeakers[0] && (
                    <LexemeSearchBlock speaker={selectedSpeakers[0]} conceptId={concept.id}/>
                  )}

                  <TranscriptionLanesControls/>

                  <button className="mb-1.5 flex w-full items-center gap-2 rounded-md bg-indigo-50 px-2.5 py-1.5 text-[11px] font-semibold text-indigo-800 ring-1 ring-indigo-200 hover:bg-indigo-100">
                    <Layers className="h-3.5 w-3.5"/>
                    <span className="flex-1 text-left">Spectrogram workspace</span>
                    <span className="rounded bg-white/70 px-1 font-mono text-[9px] text-indigo-600">ON</span>
                  </button>

                  <div className="space-y-1">
                    {([
                      { icon: AudioLines, label: 'Waveform view', hint: 'Segment-aware' },
                      { icon: Video, label: 'Video clip', hint: 'Synced to timeline' },
                      { icon: Scissors, label: 'Segment controls', hint: 'Split · Trim · Join' },
                      { icon: SlidersHorizontal, label: 'Formant tracker', hint: 'Praat-compatible' },
                      { icon: Mic, label: 'Re-record utterance', hint: 'Overlay on segment' },
                    ] as const).map(({ icon: Icon, label, hint }) => (
                      <button key={label} className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-slate-50">
                        <Icon className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-600"/>
                        <div className="flex-1 min-w-0">
                          <div className="text-[11px] font-medium text-slate-700 truncate">{label}</div>
                          <div className="text-[9px] text-slate-400 truncate">{hint}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* --- ANNOTATE: Tag filter + Save --- */}
                <div className="border-b border-slate-100 p-4">
                  <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    <Filter className="h-3 w-3"/> Filter concepts
                  </h4>
                  <div className="space-y-1">
                    {([
                      ['all','All concepts','bg-slate-400'],
                      ['untagged','Untagged','bg-slate-300'],
                      ['review','Review needed','bg-amber-400'],
                      ['confirmed','Confirmed','bg-emerald-500'],
                      ['problematic','Problematic','bg-rose-500'],
                    ] as const).map(([key,label,dot]) => (
                      <button key={key} onClick={() => setTagFilter(key)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-[11px] transition ${tagFilter===key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-600 hover:bg-slate-50'}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${dot}`}/>{label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-4">
                  <button
                    className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
                    onClick={() => {
                      const speaker = selectedSpeakers[0];
                      if (speaker) void useAnnotationStore.getState().saveSpeaker(speaker);
                    }}
                  >
                    <Save className="h-3 w-3"/> Save annotations
                  </button>
                </div>
              </>
            )}
          </div>
        </aside>
      </div>

      <input
        type="file"
        accept=".json"
        ref={loadDecisionsMenuRef}
        style={{ display: 'none' }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            const text = await file.text();
            const data = JSON.parse(text) as Record<string, unknown>;
            await useEnrichmentStore.getState().save(data);
          } catch {
            // non-fatal
          }
          e.target.value = '';
        }}
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
      <Modal
        open={offsetState.phase !== 'idle'}
        onClose={() => setOffsetState({ phase: 'idle' })}
        title="Timestamp Offset"
        // While the async job is actually running, lock the modal. A
        // stray click on the backdrop or the Escape key used to drop
        // the user out of the flow while the worker kept computing —
        // the progress was also invisible because nothing persisted in
        // the header. The header chip now covers the "I want to dismiss
        // this and come back" case, so blocking dismissal here is safe.
        dismissible={offsetState.phase !== 'detecting' && offsetState.phase !== 'applying'}
      >
        <div className="space-y-3 text-sm" data-testid="offset-modal">
          {offsetState.phase === 'detecting' && (
            <div className="space-y-2" data-testid="offset-detecting">
              <div className="flex items-center gap-2 text-slate-600">
                <Loader2 className="h-4 w-4 animate-spin"/>
                <span>{offsetState.progressMessage ?? 'Detecting offset…'}</span>
                <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-400">
                  {Math.round(offsetState.progress)}%
                </span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all"
                  style={{ width: `${Math.max(2, Math.round(offsetState.progress))}%` }}
                />
              </div>
              <p className="text-[11px] text-slate-400">
                This window stays open while the worker is running — a
                single click used to dismiss it silently and lose the
                progress indicator. The header also mirrors the status.
              </p>
            </div>
          )}
          {offsetState.phase === 'manual' && (() => {
            const consensus = manualConsensus;
            const directionWord =
              !consensus
                ? null
                : consensus.median > 0.001
                ? 'later (toward the end)'
                : consensus.median < -0.001
                ? 'earlier (toward the start)'
                : 'no shift';
            const arrow =
              !consensus
                ? null
                : consensus.median > 0.001
                ? '→'
                : consensus.median < -0.001
                ? '←'
                : '·';
            const noisy = consensus !== null && consensus.mad > 2.0;
            return (
              <div className="space-y-3" data-testid="offset-manual">
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                  <p className="leading-snug">
                    Capture one trusted lexeme at a time. In Annotate, click a lexeme,
                    scrub to where you actually hear it, then press
                    <span className="mx-1 inline-flex items-center gap-1 rounded bg-indigo-100 px-1.5 py-0.5 font-semibold text-indigo-700">
                      <Anchor className="h-3 w-3"/>Anchor offset here
                    </span>
                    on the playback bar. Captured pairs accumulate below — adding
                    more refines the offset.
                  </p>
                </div>

                {manualAnchors.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-slate-300 p-4 text-xs text-slate-500">
                    <Anchor className="h-5 w-5 text-slate-300"/>
                    No anchors captured yet.
                    <span className="text-[11px] text-slate-400">
                      Switch to Annotate, select a lexeme, scrub the waveform, then click
                      <em> Anchor offset here</em>.
                    </span>
                  </div>
                ) : (
                  <ul className="space-y-1.5" data-testid="offset-manual-anchor-list">
                    {manualAnchors.map((a) => {
                      const pairOffset = a.audioTimeSec - a.csvTimeSec;
                      const disagrees =
                        consensus !== null && Math.abs(pairOffset - consensus.median) > 1.5;
                      const sign = pairOffset >= 0 ? '+' : '';
                      return (
                        <li
                          key={a.conceptKey}
                          className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${disagrees ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}
                          data-testid="offset-manual-anchor"
                        >
                          <div className="flex-1 truncate">
                            <span className="font-semibold text-slate-800">{a.conceptName}</span>
                            <span className="ml-1 font-mono text-slate-400">{a.conceptKey}</span>
                          </div>
                          <div className="font-mono text-[11px] text-slate-500 tabular-nums" title={`csv ${a.csvTimeSec.toFixed(3)}s → audio ${a.audioTimeSec.toFixed(3)}s`}>
                            {formatPlaybackTime(a.csvTimeSec)} <span className="text-slate-300">→</span> {formatPlaybackTime(a.audioTimeSec)}
                          </div>
                          <div className={`w-16 text-right font-mono text-[11px] tabular-nums ${disagrees ? 'text-rose-600' : 'text-slate-700'}`}>
                            {sign}{pairOffset.toFixed(2)}s
                          </div>
                          <button
                            onClick={() => removeManualAnchor(a.conceptKey)}
                            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600"
                            title="Remove this anchor"
                            data-testid={`offset-manual-anchor-remove-${a.conceptKey}`}
                          >
                            <X className="h-3 w-3"/>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}

                {consensus !== null && (
                  <div className={`rounded-md border p-3 text-xs ${noisy ? 'border-amber-300 bg-amber-50' : 'border-emerald-200 bg-emerald-50'}`}>
                    <div className="font-mono text-base text-slate-900" data-testid="offset-manual-consensus">
                      {consensus.median >= 0 ? '+' : ''}{consensus.median.toFixed(3)} s <span className="text-slate-400">{arrow}</span>
                    </div>
                    <div className="mt-1 text-slate-700">
                      Apply will move every interval <strong>{Math.abs(consensus.median).toFixed(3)} s {directionWord}</strong>.
                    </div>
                    <div className="mt-1 text-slate-500">
                      {manualAnchors.length} anchor{manualAnchors.length === 1 ? '' : 's'}
                      {consensus.mad > 0 && (
                        <> · spread ±{consensus.mad.toFixed(2)}s</>
                      )}
                      {noisy && (
                        <> — anchors disagree, review the rose-highlighted ones above</>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      const r = captureCurrentAnchor();
                      if (!r.ok) {
                        setOffsetState({ phase: 'error', message: r.message });
                      }
                    }}
                    title="Use the lexeme currently selected in the sidebar plus the current playback time"
                    data-testid="offset-manual-capture"
                  >
                    <Plus className="h-3 w-3"/> Capture from current selection
                  </button>
                  <div className="flex gap-2">
                    <button
                      className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                      onClick={() => setOffsetState({ phase: 'idle' })}
                    >
                      Close
                    </button>
                    <button
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                      onClick={() => { void submitManualOffset(); }}
                      disabled={!manualAnchors.length || manualBusy}
                      data-testid="offset-manual-submit"
                    >
                      {manualBusy ? 'Computing…' : 'Review & apply →'}
                    </button>
                  </div>
                </div>
              </div>
            );
          })()}
          {offsetState.phase === 'detected' && (
            <>
              {(() => {
                const r = offsetState.result;
                const direction = r.direction ?? (r.offsetSec >= 0 ? 'later' : 'earlier');
                const sign = r.offsetSec >= 0 ? '+' : '';
                const lowConf = (r.confidence ?? 0) < 0.5;
                const directionWord =
                  direction === 'later' ? 'later (toward the end)' :
                  direction === 'earlier' ? 'earlier (toward the start)' :
                  'no-op (no shift)';
                const arrow = direction === 'later' ? '→' : direction === 'earlier' ? '←' : '·';
                const isManual = r.method === 'manual_pair';
                return (
                  <>
                    <div className={`rounded-md border p-3 text-xs ${lowConf ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-slate-50'}`}>
                      <div className="font-mono text-base text-slate-900" data-testid="offset-value">
                        {sign}{r.offsetSec.toFixed(3)} s <span className="text-slate-400">{arrow}</span>
                      </div>
                      <div className="mt-1 text-slate-700" data-testid="offset-direction-label">
                        Apply will move every interval <strong>{Math.abs(r.offsetSec).toFixed(3)} s {directionWord}</strong>.
                      </div>
                      <div className="mt-2 text-slate-500">
                        {isManual ? (
                          <>From single trusted pair · confidence {Math.round((r.confidence ?? 0) * 100)}%</>
                        ) : (
                          <>
                            Confidence {Math.round((r.confidence ?? 0) * 100)}% · {r.nAnchors}/{r.totalAnchors} anchors matched · {r.totalSegments} STT segments
                            {typeof r.spreadSec === 'number' && r.spreadSec > 0 && (
                              <> · spread ±{r.spreadSec.toFixed(2)}s</>
                            )}
                            {r.method && <> · {r.method.replace('_', ' ')}</>}
                          </>
                        )}
                      </div>
                    </div>
                    {(r.warnings?.length ?? 0) > 0 && (
                      <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
                        {r.warnings!.map((w, i) => (
                          <li key={i} className="flex items-start gap-1.5">
                            <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0"/>{w}
                          </li>
                        ))}
                      </ul>
                    )}
                    {protectedLexemeCount > 0 && (
                      <div
                        data-testid="offset-protected-notice"
                        className="flex items-start gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-[11px] text-emerald-900"
                      >
                        <Anchor className="mt-0.5 h-3 w-3 flex-shrink-0"/>
                        <span>
                          <strong>{protectedLexemeCount}</strong> lexeme{protectedLexemeCount === 1 ? '' : 's'} will be protected — you have manually adjusted {protectedLexemeCount === 1 ? 'its' : 'their'} timing and the offset will skip {protectedLexemeCount === 1 ? 'it' : 'them'}.
                        </span>
                      </div>
                    )}
                    {(r.matches?.length ?? 0) > 0 && (
                      <details className="text-[11px] text-slate-600">
                        <summary className="cursor-pointer select-none text-slate-500 hover:text-slate-700">
                          Show matched anchor pairs ({r.matches!.length})
                        </summary>
                        <table className="mt-1 w-full table-fixed border-separate border-spacing-y-0.5 font-mono">
                          <thead className="text-[10px] text-slate-400">
                            <tr>
                              <th className="text-left">Anchor text</th>
                              <th className="text-right">CSV t</th>
                              <th className="text-right">Audio t</th>
                              <th className="text-right">Δ</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.matches!.slice(0, 8).map((m, i) => (
                              <tr key={i} className="text-slate-700">
                                <td className="truncate">{m.anchor_text}</td>
                                <td className="text-right">{m.anchor_start?.toFixed(2) ?? '—'}</td>
                                <td className="text-right">{m.segment_start?.toFixed(2) ?? '—'}</td>
                                <td className={`text-right ${Math.abs(m.offset_sec - r.offsetSec) > 1.5 ? 'text-rose-600' : ''}`}>
                                  {m.offset_sec >= 0 ? '+' : ''}{m.offset_sec.toFixed(2)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </details>
                    )}
                    <div className="flex justify-between gap-2">
                      <button
                        className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                        onClick={() => setOffsetState({ phase: 'manual' })}
                        data-testid="offset-use-known-anchor"
                      >
                        Use a known anchor instead
                      </button>
                      <div className="flex gap-2">
                        <button
                          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                          onClick={() => setOffsetState({ phase: 'idle' })}
                        >
                          Cancel
                        </button>
                        <button
                          className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 ${lowConf ? 'bg-amber-600' : 'bg-indigo-600'}`}
                          onClick={() => { void applyDetectedOffset(); }}
                          data-testid="offset-apply"
                          title={lowConf ? 'Low confidence — review the matches before applying' : undefined}
                        >
                          {lowConf ? 'Apply anyway' : 'Apply offset'}
                        </button>
                      </div>
                    </div>
                  </>
                );
              })()}
            </>
          )}
          {offsetState.phase === 'applying' && (
            <div className="flex items-center gap-2 text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin"/> Applying offset…
            </div>
          )}
          {offsetState.phase === 'applied' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-emerald-700">
                <CheckCircle2 className="h-4 w-4"/> Shifted {offsetState.shifted} interval{offsetState.shifted === 1 ? '' : 's'} by {offsetState.result.offsetSec.toFixed(3)}s
              </div>
              {offsetState.protected > 0 && (
                <div
                  data-testid="offset-applied-protected"
                  className="flex items-start gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-[11px] text-emerald-900"
                >
                  <Anchor className="mt-0.5 h-3 w-3 flex-shrink-0"/>
                  <span>
                    Left <strong>{offsetState.protected}</strong> interval row{offsetState.protected === 1 ? '' : 's'} untouched — they were previously locked by manual timestamp edits or anchor captures.
                  </span>
                </div>
              )}
              <div className="flex justify-end">
                <button
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={() => setOffsetState({ phase: 'idle' })}
                >
                  Close
                </button>
              </div>
            </div>
          )}
          {offsetState.phase === 'error' && (
            <div className="space-y-2">
              <div className="flex items-start gap-2 text-rose-700">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0"/>
                <span data-testid="offset-error">{offsetState.message}</span>
              </div>
              {offsetState.jobId && (
                <div className="text-[11px] text-slate-500">
                  Job <span className="font-mono text-slate-700">{offsetState.jobId}</span>
                  {' — '}
                  <button
                    className="font-semibold text-indigo-700 underline hover:text-indigo-800"
                    onClick={() => setJobLogsOpen(offsetState.jobId!)}
                    data-testid="offset-error-view-log"
                  >
                    View crash log
                  </button>
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={() => setOffsetState({ phase: 'manual' })}
                >
                  Try a known anchor
                </button>
                <button
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={() => setOffsetState({ phase: 'idle' })}
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </Modal>
      <JobLogsModal
        jobId={jobLogsOpen}
        onClose={() => setJobLogsOpen(null)}
      />
      <Modal open={commentsImportOpen} onClose={() => setCommentsImportOpen(false)} title="Import Audition Comments">
        <CommentsImport onImportComplete={() => setCommentsImportOpen(false)} />
      </Modal>
      <input
        type="file"
        accept=".json"
        ref={loadDecisionsRef}
        style={{ display: 'none' }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            const text = await file.text();
            const data = JSON.parse(text) as Record<string, unknown>;
            await useEnrichmentStore.getState().save(data);
          } catch {
            // non-fatal
          }
          e.target.value = '';
        }}
      />
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
const LANE_ORDER: LaneKind[] = ['ipa_phone', 'ipa', 'stt', 'ortho'];
const LANE_DISPLAY: Record<LaneKind, { label: string; hint: string }> = {
  ipa_phone: { label: 'Phones tier', hint: 'Phone-level IPA' },
  ipa: { label: 'IPA tier', hint: 'Word/lexeme IPA' },
  stt: { label: 'STT segments', hint: 'Coarse transcript' },
  ortho: { label: 'Ortho tier', hint: 'Orthographic' },
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
