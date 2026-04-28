import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  ChevronLeft, ChevronRight, Check, Flag, Split, GitMerge,
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
import { startCompute, pollCompute, detectTimestampOffset, detectTimestampOffsetFromPairs, applyTimestampOffset, pollOffsetDetectJob } from './api/client';
import { useChatSession } from './hooks/useChatSession';
import { useOffsetState } from './hooks/useOffsetState';
import { useParseUIModals } from './hooks/useParseUIModals';
import { useParseUIPipeline } from './hooks/useParseUIPipeline';
import { compareSurveyKeys } from './lib/surveySort';
import {
  conceptMatchesIntervalText,
  deriveAudioUrl,
  getConceptStatus,
  isInteractiveHotkeyTarget,
  isRecord,
  readTextBlob,
  resolveAssetUrl,
} from './lib/parseUIUtils';
import type { ConceptTag } from './lib/parseUIUtils';
import {
  referenceCardStyle,
  resolveFormSelection,
  resolveReferenceFormLists,
} from './lib/referenceFormParsing';
import { buildSpeakerForm } from './lib/speakerForm';
import type { Concept, SpeakerForm } from './lib/speakerForm';
import {
  applyCanonicalDecisionImport,
  buildCanonicalDecisionPayload,
  buildCognateDecisionPatch,
  getStoredCognateDecision,
  PARSE_DECISIONS_FILE_NAME,
  type CognateDecisionValue,
} from './lib/decisionPersistence';
import { useAnnotationStore } from './stores/annotationStore';
import { useTranscriptionLanesStore } from './stores/transcriptionLanesStore';
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
} from './components/shared/TranscriptionRunModal';
import { BatchReportModal } from './components/shared/BatchReportModal';
import { LexemeDetail } from './components/compare/LexemeDetail';
import { CommentsImport } from './components/compare/CommentsImport';
import { SpeakerImport } from './components/compare/SpeakerImport';
import { ManageTagsView } from './components/compare/ManageTagsView';
import { CognateCell, SimBar } from './components/compare/CognateCell';
import { Pill, SectionCard } from './components/compare/UIPrimitives';
import { AnnotateView } from './components/annotate/AnnotateView';
import { JobLogsModal } from './components/annotate/JobLogsModal';
import { LexemeSearchBlock } from './components/annotate/LexemeSearchBlock';
import { TranscriptionLanesControls } from './components/annotate/TranscriptionLanesControls';
import { ClefConfigModal } from './components/compute/ClefConfigModal';
import { ClefPopulateSummaryBanner, type PopulateSummary } from './components/compute/ClefPopulateSummaryBanner';
import { ClefSourcesReportModal } from './components/compute/ClefSourcesReportModal';
import { ConceptSidebar } from './components/parse/ConceptSidebar';
import { RightPanel } from './components/parse/RightPanel';
import {
  type CompareComputeMode,
} from './components/parse/compareComputeContract';
import { OffsetAdjustmentModal } from './components/parse/modals/OffsetAdjustmentModal';
import { AIChat } from './components/shared/AIChat';
import { getClefConfig, getContactLexemeCoverage, saveClefFormSelections } from './api/client';
import type { ClefConfigStatus, ContactLexemePopulateResult } from './api/types';

type AppMode = 'annotate' | 'compare' | 'tags';

interface LingTag {
  id: string; name: string; color: string; dotClass: string; count: number;
}

type ConceptSortMode = 'az' | '1n' | 'survey';

// No fallback data — workspace must supply real speakers and concepts via /api/config.

const COMPARE_NOTES_STORAGE_KEY = 'parseui-compare-notes-v1';

function persistCompareNotes(conceptId: number, value: string) {
  try {
    const raw = window.localStorage.getItem(COMPARE_NOTES_STORAGE_KEY);
    const stored = raw ? JSON.parse(raw) as Record<string, string> : {};
    stored[conceptId.toString()] = value;
    window.localStorage.setItem(COMPARE_NOTES_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // non-fatal localStorage failure
  }
}

export { pickOrthoIntervalForConcept } from './lib/parseUIUtils';
export {
  parseReferenceFormList,
  resolveReferenceFormLists,
  resolveFormSelection,
  type ReferenceFormEntry,
} from './lib/referenceFormParsing';

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
  const modals = useParseUIModals();
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
  const [boundariesSpeaker, setBoundariesSpeaker] = useState<string | null>(null);
  const [bndSttSpeaker, setBndSttSpeaker] = useState<string | null>(null);
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

  const {
    batch,
    reportStepsRun,
    handleRunConfirm,
    handleRerunFailed,
    showBatchCompleteBanner,
    completedCount,
    errorCount,
    cancelledCount,
    dismissBatchStatus,
    openBatchReport,
  } = useParseUIPipeline({
    closeRunModal: modals.run.close,
    openBatchReport: modals.batchReport.open,
    closeBatchReport: modals.batchReport.close,
    isBatchReportOpen: modals.batchReport.isOpen,
    getLanguage: () => sttLanguageRef.current || undefined,
    reloadSpeakerAnnotation,
    reloadStt: (speakerId) => {
      void useTranscriptionLanesStore.getState().reloadStt(speakerId);
    },
    loadEnrichments,
  });

  // Single source of truth for the contact-lexemes / CLEF populate job in
  // the header. Both the "Run Cross-Speaker Match" button (kept for the
  // legacy compute path) and the CLEF configure modal's Save & populate
  // action flow through this hook: the modal starts the job, then ParseUI
  // calls `adopt()` so the header's running-process chip picks it up and
  // behaves exactly like STT / forced-align / the batch pipeline.
  // Last completed-populate summary: `{ok, totalFilled, perLang, warning, warnings}`.
  // Set by `crossSpeakerJob.onComplete` from the backend's `result` payload
  // so Compare mode can render a contextual banner when the job technically
  // succeeded but produced zero forms (providers offline, concepts outside
  // ASJP's list, etc.) -- previously that case showed as plain
  // green "complete" with no visible signal.
  const [populateSummary, setPopulateSummary] = useState<PopulateSummary | null>(null);

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
      // `{filled, total_filled, warning?, warnings?}`. Inspect it so we can show a
      // non-fatal "0 forms found" banner near Reference Forms and surface
      // provider-readiness caveats even on successful populates.
      const payload = (result && typeof result === 'object') ? result as Partial<ContactLexemePopulateResult> : {};
      const totalFilled = typeof payload.total_filled === 'number' ? payload.total_filled : NaN;
      const rawPerLang = payload.filled && typeof payload.filled === 'object' ? payload.filled as Record<string, unknown> : {};
      const perLang: Record<string, number> = {};
      for (const [code, count] of Object.entries(rawPerLang)) {
        if (typeof count === 'number' && Number.isFinite(count)) perLang[code] = count;
      }
      const warning = typeof payload.warning === 'string' && payload.warning.trim() ? payload.warning : null;
      const warnings = Array.isArray(payload.warnings)
        ? payload.warnings.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
        : [];
      const resolvedTotal = Number.isFinite(totalFilled)
        ? totalFilled
        : Object.values(perLang).reduce((a, b) => a + b, 0);
      setPopulateSummary({
        state: resolvedTotal > 0 ? 'ok' : 'empty',
        totalFilled: resolvedTotal,
        perLang,
        warning,
        warnings,
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

  const boundariesJob = useActionJob({
    start: () => {
      if (!boundariesSpeaker) {
        return Promise.reject(new Error('Pick a speaker before refining boundaries.'));
      }
      return startCompute('boundaries', { speaker: boundariesSpeaker });
    },
    poll: (jobId) => pollCompute('boundaries', jobId),
    label: 'Refining word boundaries…',
    onComplete: async () => {
      if (boundariesSpeaker) {
        await loadSpeaker(boundariesSpeaker);
      }
    },
    autoDismissMs: 4000,
  });

  const bndSttJob = useActionJob({
    start: () => {
      if (!bndSttSpeaker) {
        return Promise.reject(new Error('Pick a speaker before re-transcribing with boundaries.'));
      }
      return startCompute('retranscribe_with_boundaries', {
        speaker: bndSttSpeaker,
        language: sttLanguageRef.current || undefined,
      });
    },
    poll: (jobId) => pollCompute('retranscribe_with_boundaries', jobId),
    label: 'Re-transcribing with BND…',
    onComplete: async () => {
      if (bndSttSpeaker) {
        await useTranscriptionLanesStore.getState().reloadStt(bndSttSpeaker);
        await loadSpeaker(bndSttSpeaker);
      }
    },
    autoDismissMs: 4000,
  });

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
        modals.clef.open();
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

  const bndIntervalCount = useAnnotationStore((s) => {
    const speaker = selectedSpeakers[0] ?? null;
    if (!speaker) return 0;
    return s.records[speaker]?.tiers?.ortho_words?.intervals?.length ?? 0;
  });

  const sttHasWordTimestamps = useTranscriptionLanesStore((s) => {
    const speaker = selectedSpeakers[0] ?? null;
    if (!speaker) return false;
    const segs = s.sttBySpeaker[speaker] ?? [];
    return segs.some((seg) => Array.isArray(seg.words) && seg.words.length > 0);
  });

  const annotatePhoneticTools = selectedSpeakers[0] ? (
    <>
      <div className="mb-2">
        <button
          data-testid="phonetic-refine-boundaries"
          onClick={() => {
            const speaker = selectedSpeakers[0] ?? null;
            if (!speaker) return;
            setBoundariesSpeaker(speaker);
            void boundariesJob.run();
          }}
          disabled={!selectedSpeakers[0] || !sttHasWordTimestamps || boundariesJob.state.status === 'running'}
          title={
            !selectedSpeakers[0]
              ? 'Select a speaker first.'
              : !sttHasWordTimestamps
                ? 'No STT word timestamps for this speaker yet. Run STT first (Actions → Run STT) — boundary refinement uses those words as alignment seeds.'
                : 'Run fast boundary refinement independently. Useful before running slow ORTH/IPA models.'
          }
          className="mb-1.5 flex w-full items-center gap-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Split className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">
            {boundariesJob.state.status === 'running' ? 'Refining boundaries…' : 'Refine Boundaries (BND)'}
          </span>
          {boundariesJob.state.status === 'running' ? (
            <span className="rounded bg-white/70 px-1 font-mono text-[9px] text-amber-700">
              {Math.round(boundariesJob.state.progress * 100)}%
            </span>
          ) : null}
        </button>
        {boundariesJob.state.status === 'running' && boundariesJob.state.etaMs !== null && boundariesJob.state.etaMs > 0 ? (
          <div className="mb-1 text-[10px] text-amber-700">~{formatEta(boundariesJob.state.etaMs)} left</div>
        ) : null}
        {boundariesJob.state.status === 'complete' ? (
          <div className="mb-1 text-[10px] text-emerald-700">Boundaries refreshed.</div>
        ) : null}
        {boundariesJob.state.status === 'error' ? (
          <div className="mb-1 text-[10px] text-rose-700">
            {boundariesJob.state.error?.includes('Run STT first')
              ? 'Please run STT first before refining boundaries.'
              : (boundariesJob.state.error ?? 'Boundary refinement failed.')}
          </div>
        ) : null}

        <button
          data-testid="phonetic-retranscribe-with-boundaries"
          onClick={() => {
            const speaker = selectedSpeakers[0] ?? null;
            if (!speaker) return;
            setBndSttSpeaker(speaker);
            void bndSttJob.run();
          }}
          disabled={!selectedSpeakers[0] || bndIntervalCount === 0 || bndSttJob.state.status === 'running'}
          title={
            !selectedSpeakers[0]
              ? 'Select a speaker first.'
              : bndIntervalCount === 0
                ? 'No BND intervals yet for this speaker. Refine boundaries (Refine Boundaries (BND) above) before re-running STT.'
                : "Re-transcribe using the current BND boundaries. This respects your manual boundary corrections."
          }
          className="flex w-full items-center gap-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Mic className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">
            {bndSttJob.state.status === 'running' ? 'Re-transcribing with BND…' : 'Re-run STT with Boundaries'}
          </span>
          {bndSttJob.state.status === 'running' ? (
            <span className="rounded bg-white/70 px-1 font-mono text-[9px] text-amber-700">
              {Math.round(bndSttJob.state.progress * 100)}%
            </span>
          ) : null}
        </button>
        {bndSttJob.state.status === 'running' && bndSttJob.state.etaMs !== null && bndSttJob.state.etaMs > 0 ? (
          <div className="mt-1 text-[10px] text-amber-700">~{formatEta(bndSttJob.state.etaMs)} left</div>
        ) : null}
        {bndSttJob.state.status === 'complete' ? (
          <div className="mt-1 text-[10px] text-emerald-700">STT re-transcribed using BND boundaries.</div>
        ) : null}
        {bndSttJob.state.status === 'error' ? (
          <div className="mt-1 text-[10px] text-rose-700">
            {bndSttJob.state.error?.includes('No BND intervals')
              ? 'Refine boundaries (BND) first before re-running STT.'
              : (bndSttJob.state.error ?? 'BND-constrained STT failed.')}
          </div>
        ) : null}
      </div>

      <LexemeSearchBlock speaker={selectedSpeakers[0]} conceptId={conceptId} />
    </>
  ) : null;

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
    modals.import.open();
  };
  const handleImportComplete = (speakerId: string) => {
    modals.import.close();
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

          {showBatchCompleteBanner && (
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
                {batch.state.cancelled ? 'Cancelled' : 'Done'} · {completedCount} ok
                {errorCount > 0 && `, ${errorCount} err`}
                {cancelledCount > 0 && `, ${cancelledCount} skip`}
              </span>
              <button
                onClick={openBatchReport}
                className={`rounded px-1.5 py-0.5 text-[11px] font-semibold underline ${batch.state.cancelled ? 'text-amber-700 hover:text-amber-800' : 'text-emerald-700 hover:text-emerald-800'}`}
                data-testid="topbar-batch-view-report"
              >
                View report
              </button>
              <button
                onClick={dismissBatchStatus}
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
                      onClick={() => { setActionsMenuOpen(false); modals.run.open('Run Audio Normalization', ['normalize']); }}
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
                        onClick={() => { setActionsMenuOpen(false); modals.run.open('Run STT', ['stt']); }}
                        disabled={batch.state.status === 'running'}
                        data-testid="actions-stt"
                        className="ml-auto inline-flex items-center gap-1 rounded bg-indigo-600 px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Run STT…
                      </button>
                    </div>
                    <button
                      onClick={() => { setActionsMenuOpen(false); modals.run.open('Generate ORTH (razhan)', ['ortho']); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-generate-ortho"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Type className="h-3.5 w-3.5 text-slate-400"/>
                      Generate ORTH (razhan)…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); modals.run.open('Run IPA Transcription', ['ipa']); }}
                      disabled={batch.state.status === 'running'}
                      data-testid="actions-ipa"
                      className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Type className="h-3.5 w-3.5 text-slate-400"/>
                      Run IPA Transcription…
                    </button>
                    <button
                      onClick={() => { setActionsMenuOpen(false); modals.run.open('Run Full Pipeline'); }}
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
              peaksUrl={selectedSpeakers[0] ? resolveAssetUrl(`/peaks/${selectedSpeakers[0]}.json`) : undefined}
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
                    modals.clef.open('populate');
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
                <textarea value={notes} onChange={e => {
                  const nextValue = e.target.value;
                  setNotes(nextValue);
                  persistCompareNotes(conceptId, nextValue);
                }}
                  onBlur={() => persistCompareNotes(conceptId, notes)}
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
          onOpenSourcesReport={modals.sourcesReport.open}
          onOpenClefConfig={modals.clef.open}
          onRefreshEnrichments={() => { void useEnrichmentStore.getState().load(); }}
          tagFilter={tagFilter}
          onTagFilterChange={setTagFilter}
          onOpenLoadDecisions={() => openDecisionsImport(false)}
          onSaveDecisions={() => handleSaveDecisions(false)}
          onExportLingPy={handleExportLingPy}
          exporting={exporting}
          onOpenCommentsImport={modals.commentsImport.open}
          activeActionSpeaker={activeActionSpeaker}
          offsetPhase={offsetState.phase}
          onDetectOffset={() => { void detectOffsetForSpeaker(); }}
          onOpenManualOffset={openManualOffset}
          annotateSpeakerTools={annotatePhoneticTools}
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
      <Modal open={modals.import.isOpen} onClose={modals.import.close} title="Import Speaker">
        <SpeakerImport onImportComplete={handleImportComplete} />
      </Modal>
      <TranscriptionRunModal
        open={modals.run.state !== null}
        title={modals.run.state?.title ?? 'Run transcription'}
        fixedSteps={modals.run.state?.fixedSteps}
        speakers={Object.keys(annotationRecords).sort()}
        defaultSelectedSpeaker={activeActionSpeaker}
        onClose={modals.run.close}
        onConfirm={handleRunConfirm}
      />
      <BatchReportModal
        open={modals.batchReport.isOpen}
        onClose={modals.batchReport.close}
        outcomes={batch.state.outcomes}
        stepsRun={reportStepsRun}
        onRerunFailed={handleRerunFailed}
      />
      <ClefConfigModal
        open={modals.clef.isOpen}
        initialTab={modals.clef.initialTab}
        onClose={modals.clef.close}
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
        open={modals.sourcesReport.isOpen}
        onClose={modals.sourcesReport.close}
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
      <Modal open={modals.commentsImport.isOpen} onClose={modals.commentsImport.close} title="Import Audition Comments">
        <CommentsImport onImportComplete={modals.commentsImport.close} />
      </Modal>
    </div>
  );
}
