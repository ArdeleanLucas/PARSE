// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, AnnotationInterval, ProjectConfig, SurveyOverlapState, Tag } from "./api/types";
import type { ActiveJobSnapshot } from "./api/contracts/job-observability";
import { useTranscriptionLanesStore } from "./stores/transcriptionLanesStore";
import { useCompareReturnStore } from "./stores/compareReturnStore";
import { usePlaybackStore } from "./stores/playbackStore";

const { mockGetAuthStatus, mockPollAuth, mockStartAuthFlow, mockGetConfig, mockGetSurveyOverlap } = vi.hoisted(() => ({
  mockGetAuthStatus: vi.fn(),
  mockPollAuth: vi.fn(),
  mockStartAuthFlow: vi.fn(),
  mockGetConfig: vi.fn(),
  mockGetSurveyOverlap: vi.fn(),
}));

let mockConfig: ProjectConfig | null = null;
let mockTags: Tag[] = [];
let mockRecords: Record<string, AnnotationRecord> = {};
let mockSelectedRegion: { start: number; end: number } | null = { start: 1.25, end: 2.5 };
let mockPlaybackActiveSpeaker: string | null = null;
let mockPendingSeek: { targetSec: number; nonce: number } | null = null;
let mockCurrentTime = 0;

const mockLoadConfig = vi.fn().mockResolvedValue(undefined);
const mockHydrateTags = vi.fn();
const mockSyncTagsFromServer = vi.fn().mockResolvedValue(undefined);
const mockLoadSpeaker = vi.fn().mockResolvedValue(undefined);
const mockSetInterval = vi.fn();
const mockSaveLexemeAnnotation = vi.fn().mockReturnValue({ ok: true, moved: 4 });
const mockCreateConceptInterval = vi.fn();
const mockSaveSpeaker = vi.fn().mockResolvedValue(undefined);
const mockMarkLexemeManuallyAdjusted = vi.fn();
const mockFlushAutosave = vi.fn();
const mockSetConceptTag = vi.fn((speaker: string, conceptId: string, tagId: string) => {
  const record = mockRecords[speaker] ?? { speaker_id: speaker, intervals: {}, modified_at: '' };
  const nextTags = new Set(record.concept_tags?.[conceptId] ?? []);
  nextTags.add(tagId);
  mockRecords = {
    ...mockRecords,
    [speaker]: {
      ...record,
      concept_tags: { ...(record.concept_tags ?? {}), [conceptId]: Array.from(nextTags) },
    },
  };
});
const mockClearConceptTag = vi.fn((speaker: string, conceptId: string, tagId: string) => {
  const record = mockRecords[speaker];
  if (!record) return;
  const nextTags = (record.concept_tags?.[conceptId] ?? []).filter((id) => id !== tagId);
  const concept_tags = { ...(record.concept_tags ?? {}) };
  if (nextTags.length) concept_tags[conceptId] = nextTags;
  else delete concept_tags[conceptId];
  mockRecords = { ...mockRecords, [speaker]: { ...record, concept_tags } };
});
const mockSetConfirmedAnchor = vi.fn();
const mockClearConfirmedAnchor = vi.fn();
const mockUpdateTag = vi.fn();
const mockSetSelectedRegion = vi.fn();
const mockSetActiveSpeaker = vi.fn();
const mockSetActiveConcept = vi.fn();
const mockSetSelectedSpeakers = vi.fn();
const mockChatSend = vi.fn();
const mockPlayPause = vi.fn();
const mockSkip = vi.fn();
const mockSeek = vi.fn();
const mockAddRegion = vi.fn();
const mockScrollToTimeAtFraction = vi.fn();
const mockSetWaveZoom = vi.fn();
const mockSetRate = vi.fn();
const mockAnnotationSetState = vi.fn((...args: unknown[]) => {
  const patch = args[0];
  if (typeof patch === "function") {
    const next = (patch as (state: { records: Record<string, AnnotationRecord> }) => { records?: Record<string, AnnotationRecord> } | void)({ records: mockRecords });
    if (next?.records) mockRecords = next.records;
    return;
  }
  if (patch && typeof patch === "object" && "records" in patch) {
    mockRecords = (patch as { records: Record<string, AnnotationRecord> }).records;
  }
});
const mockEnrichmentSetState = vi.fn();
const mockTagSetState = vi.fn();
const mockPlaybackSetState = vi.fn();
const mockConfigSetState = vi.fn();
const mockLoadEnrichments = vi.fn().mockResolvedValue(undefined);
const mockSaveEnrichments = vi.fn();
const mockReplaceEnrichments = vi.fn();
const mockPatchCanonicalLexeme = vi.fn();
const mockGetCompareBundles = vi.fn().mockResolvedValue({ bundles: [] });
const mockGetConceptIdentity = vi.fn();
let mockEnrichmentData: Record<string, unknown> = {};
let mockEnrichmentSaveUsesDeepMerge = false;

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function deepMergeRecords(base: Record<string, unknown>, patch: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const current = merged[key];
    merged[key] = isPlainRecord(current) && isPlainRecord(value)
      ? deepMergeRecords(current, value)
      : value;
  }
  return merged;
}
let mockChatMessages: Array<{ role: "user" | "assistant"; content: string; timestamp: string }> = [];
let mockChatSending = false;
let mockChatError: string | null = null;
let mockWaveOptions: Array<{ audioUrl?: string; onReady?: (duration: number) => void }> = [];
let mockWaveSurferInstance: unknown = null;

const mockReloadConfig = vi.fn().mockResolvedValue(undefined);
const mockUpdateSurveyOverlap = vi.fn().mockResolvedValue(undefined);
const mockConfigGetState = vi.fn(() => ({ config: mockConfig }));
vi.mock("./stores/configStore", () => {
  const useConfigStore = (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig, load: mockLoadConfig, reload: mockReloadConfig, updateSurveyOverlap: mockUpdateSurveyOverlap });
  (useConfigStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockConfigSetState(...args);
  (useConfigStore as unknown as { getState: () => unknown }).getState = () => mockConfigGetState();
  return { useConfigStore };
});

vi.mock("./stores/tagStore", () => {
  const useTagStore = (selector: (s: unknown) => unknown) =>
    selector({
      tags: mockTags,
      hydrate: mockHydrateTags,
      syncFromServer: mockSyncTagsFromServer,
      updateTag: mockUpdateTag,
    });
  (useTagStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockTagSetState(...args);
  return { useTagStore };
});

vi.mock("./stores/annotationStore", () => {
  const useAnnotationStore = (selector: (s: unknown) => unknown) =>
    selector({
      records: mockRecords,
      histories: {},
      loadSpeaker: mockLoadSpeaker,
      setInterval: mockSetInterval,
      setConceptTag: mockSetConceptTag,
      clearConceptTag: mockClearConceptTag,
      setConfirmedAnchor: mockSetConfirmedAnchor,
      clearConfirmedAnchor: mockClearConfirmedAnchor,
      saveLexemeAnnotation: mockSaveLexemeAnnotation,
      createConceptInterval: mockCreateConceptInterval,
      saveSpeaker: mockSaveSpeaker,
      markLexemeManuallyAdjusted: mockMarkLexemeManuallyAdjusted,
      flushAutosave: mockFlushAutosave,
      moveIntervalAcrossTiers: vi.fn(),
      undo: vi.fn(),
      redo: vi.fn(),
    });
  (useAnnotationStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockAnnotationSetState(...args);
  (useAnnotationStore as unknown as { getState: () => { records: Record<string, AnnotationRecord> } }).getState = () => ({
    records: mockRecords,
  });
  return { useAnnotationStore };
});

vi.mock("./stores/playbackStore", () => {
  const setActiveSpeaker = (speaker: string) => {
    mockPlaybackActiveSpeaker = speaker;
    mockCurrentTime = 0;
    mockSetActiveSpeaker(speaker);
  };
  const requestSeek = (targetSec: number) => {
    mockPendingSeek = { targetSec, nonce: (mockPendingSeek?.nonce ?? 0) + 1 };
  };
  const usePlaybackStore = (selector: (s: unknown) => unknown) =>
    selector({
      activeSpeaker: mockPlaybackActiveSpeaker,
      isPlaying: false,
      currentTime: mockCurrentTime,
      duration: 4,
      selectedRegion: mockSelectedRegion,
      pendingSeek: mockPendingSeek,
      setActiveSpeaker,
      requestSeek,
      setSelectedRegion: mockSetSelectedRegion,
    });
  (usePlaybackStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockPlaybackSetState(...args);
  (usePlaybackStore as unknown as { getState: () => unknown }).getState = () => ({
    activeSpeaker: mockPlaybackActiveSpeaker,
    isPlaying: false,
    currentTime: mockCurrentTime,
    duration: 4,
    selectedRegion: mockSelectedRegion,
    pendingSeek: mockPendingSeek,
    setActiveSpeaker,
    requestSeek,
    setSelectedRegion: mockSetSelectedRegion,
  });
  return { usePlaybackStore };
});

vi.mock("./hooks/useChatSession", () => ({
  useChatSession: () => ({
    messages: mockChatMessages,
    sessionId: "test-session",
    sending: mockChatSending,
    error: mockChatError,
    send: mockChatSend,
    clear: vi.fn(),
  }),
}));

vi.mock("./hooks/useWaveSurfer", () => ({
  useWaveSurfer: (options: { audioUrl?: string; onReady?: (duration: number) => void }) => {
    mockWaveOptions.push(options);
    return {
      playPause: mockPlayPause,
      seek: mockSeek,
      scrollToTimeAtFraction: mockScrollToTimeAtFraction,
      skip: mockSkip,
      addRegion: mockAddRegion,
      clearQuickRetimeSelection: vi.fn(),
      enableDragToCreate: vi.fn(() => vi.fn()),
      disableDragToCreate: vi.fn(),
      setZoom: mockSetWaveZoom,
      setRate: mockSetRate,
      setVolume: vi.fn(),
      wsRef: { current: mockWaveSurferInstance },
    };
  },
}));

vi.mock("./stores/enrichmentStore", () => {
  const useEnrichmentStore = (selector: (s: unknown) => unknown) =>
    selector({
      data: mockEnrichmentData,
      loading: false,
      load: mockLoadEnrichments,
      save: (patch: Record<string, unknown>) => {
        if (mockEnrichmentSaveUsesDeepMerge) {
          const merged = deepMergeRecords(mockEnrichmentData, patch);
          mockEnrichmentData = merged;
          return mockSaveEnrichments(merged);
        }
        return mockSaveEnrichments(patch);
      },
      replace: mockReplaceEnrichments,
      patchCanonicalLexeme: mockPatchCanonicalLexeme,
    });
  (useEnrichmentStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockEnrichmentSetState(...args);
  // cycleSpeakerCognate / toggleSpeakerFlag read manual_overrides via
  // .getState() — provide a zustand-shaped accessor that resolves lazily
  // (not at mock-hoist time) so `mockEnrichmentData` is initialised.
  (useEnrichmentStore as unknown as {
    getState: () => {
      data: Record<string, unknown>;
      loading: boolean;
      load: () => Promise<void>;
      save: (patch: Record<string, unknown>) => unknown;
      replace: typeof mockReplaceEnrichments;
      patchCanonicalLexeme: typeof mockPatchCanonicalLexeme;
    };
  }).getState = () => ({
    data: mockEnrichmentData,
    loading: false,
    load: mockLoadEnrichments,
    save: (patch: Record<string, unknown>) => {
      if (mockEnrichmentSaveUsesDeepMerge) {
        const merged = deepMergeRecords(mockEnrichmentData, patch);
        mockEnrichmentData = merged;
        return mockSaveEnrichments(merged);
      }
      return mockSaveEnrichments(patch);
    },
    replace: mockReplaceEnrichments,
    patchCanonicalLexeme: mockPatchCanonicalLexeme,
  });
  return { useEnrichmentStore };
});

vi.mock("./stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({
      setActiveSpeaker: mockSetActiveSpeaker,
      setActiveConcept: mockSetActiveConcept,
      setSelectedSpeakers: mockSetSelectedSpeakers,
    }),
}));

// Per-test overrides for the CLEF endpoints. Defaults to "not configured"
// so the Reference Forms section stays hidden (the production gate). The
// two reference-forms tests flip these to the configured state.
let mockClefConfig: {
  configured: boolean;
  primary_contact_languages: string[];
  languages: Array<{ code: string; name: string; family?: string | null; filled?: number; total?: number }>;
  config_path: string;
  concepts_csv_exists: boolean;
  meta: Record<string, unknown>;
} = {
  configured: false,
  primary_contact_languages: [],
  languages: [],
  config_path: "",
  concepts_csv_exists: false,
  meta: {},
};
let mockCoverage: { languages: Record<string, { name: string; total: number; filled: number; empty: number; concepts: Record<string, string[]> }> } = {
  languages: {},
};
let mockSourcesReport = {
  generated_at: '2026-04-25T16:00:00Z',
  providers: [
    { id: 'wikidata', total_forms: 3 },
    { id: 'asjp', total_forms: 1 },
  ],
  languages: [
    {
      code: 'ar',
      name: 'Arabic',
      family: 'Semitic',
      script: 'Arab',
      total_forms: 4,
      concepts_covered: 4,
      concepts_total: 20,
      per_provider: { wikidata: 3, asjp: 1 },
      forms: [
        { concept_en: 'water', form: 'ماء', sources: ['wikidata'] },
      ],
    },
  ],
  concepts_total: 20,
  citations: {
    wikidata: {
      label: 'Wikidata',
      type: 'dataset' as const,
      authors: 'Vrandečić, D. & Krötzsch, M.',
      year: 2014,
      title: 'Wikidata: a free collaborative knowledgebase',
      doi: '10.1145/2629489',
      url: 'https://www.wikidata.org',
      license: 'CC0-1.0',
      citation: 'Vrandečić, D. & Krötzsch, M. 2014. Wikidata: a free collaborative knowledgebase.',
      bibtex: '@article{wikidata2014, title={Wikidata}, year={2014}}',
    },
    asjp: {
      label: 'ASJP',
      type: 'dataset' as const,
      authors: 'Wichmann, S., Holman, E. W., & Brown, C. H. (eds.)',
      year: 2022,
      title: 'The ASJP Database (version 20)',
      url: 'https://asjp.clld.org',
      license: 'CC-BY-4.0',
      citation: 'Wichmann, S., Holman, E. W., & Brown, C. H. (eds.). 2022. The ASJP Database (version 20).',
      bibtex: '@misc{asjp2022, title={{The ASJP Database (version 20)}}, year={2022}}',
    },
    unknown: {
      label: 'Unattributed (legacy)',
      type: 'sentinel' as const,
      authors: null,
      year: null,
      title: 'Pre-provenance bare-string entry',
      citation: 'Unattributed legacy entry: provider not recorded.',
      bibtex: '',
    },
  },
  citation_order: ['wikidata', 'asjp', 'unknown'],
};

vi.mock("./api/client", () => ({
  getConfig: mockGetConfig,
  getSurveyOverlap: mockGetSurveyOverlap,
  getLingPyExport: vi.fn().mockResolvedValue(''),
  getConceptAppendixExport: vi.fn().mockResolvedValue(new Blob(['# Concept Appendix\n'], { type: 'text/markdown' })),
  getCompareBundles: (...args: unknown[]) => mockGetCompareBundles(...args),
  getConceptIdentity: (...args: unknown[]) => mockGetConceptIdentity(...args),
  postConceptIdentityOverride: vi.fn().mockResolvedValue({ version: 1, concepts: [], uid_by_row: {}, warnings: [] }),
  putCanonicalLexeme: vi.fn().mockResolvedValue({ bundle: { bundle_id: 'water', label: 'water', row_ids: [], buckets: [] } }),
  deleteCanonicalLexeme: vi.fn().mockResolvedValue({ bundle: { bundle_id: 'water', label: 'water', row_ids: [], buckets: [] } }),
  importTagCsv: vi.fn().mockResolvedValue({
    ok: true,
    tagId: 'custom-sk-concept-list',
    tagName: 'custom-sk-concept-list',
    color: '#6366f1',
    matchedCount: 2,
    missedCount: 1,
    missedLabels: [],
    totalTagsInFile: 1,
  }),
  saveApiKey: vi.fn().mockResolvedValue(undefined),
  getAuthStatus: mockGetAuthStatus,
  pollAuth: mockPollAuth,
  startAuthFlow: mockStartAuthFlow,
  startSTT: vi.fn().mockResolvedValue({ job_id: 'stt-job-1' }),
  startCompute: vi.fn().mockResolvedValue({ job_id: 'compute-job-1' }),
  startNormalize: vi.fn().mockResolvedValue({ job_id: 'normalize-job-1' }),
  pollSTT: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
  pollNormalize: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
  pollCompute: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
  detectTimestampOffset: vi.fn().mockResolvedValue({ job_id: 'offset-job-default', jobId: 'offset-job-default' }),
  detectTimestampOffsetFromPairs: vi.fn().mockResolvedValue({ job_id: 'offset-job-default', jobId: 'offset-job-default' }),
  pollOffsetDetectJob: vi.fn().mockResolvedValue({
    speaker: 'Fail01',
    offsetSec: 0.75,
    basedOn: 'automatic anchors',
    candidateCount: 3,
    protectedLexemeCount: 0,
  }),
  applyTimestampOffset: vi.fn().mockResolvedValue({ shifted: 3, protected: 0 }),
  getJobLogs: vi.fn().mockResolvedValue({ lines: [] }),
  getClefConfig: vi.fn(() => Promise.resolve(mockClefConfig)),
  getContactLexemeCoverage: vi.fn(() => Promise.resolve(mockCoverage)),
  getClefSourcesReport: vi.fn(() => Promise.resolve(mockSourcesReport)),
  getClefCatalog: vi.fn().mockResolvedValue({ languages: [] }),
  getClefProviders: vi.fn().mockResolvedValue({ providers: [] }),
  saveClefConfig: vi.fn().mockResolvedValue(undefined),
  startContactLexemeFetch: vi.fn().mockResolvedValue({ job_id: 'contact-fetch-job-1' }),
  listActiveJobs: vi.fn().mockResolvedValue([]),
  cancelComputeJob: vi.fn().mockResolvedValue({ cancelled: true, job_id: 'compute-job-1' }),
  deleteConcept: vi.fn().mockResolvedValue({ ok: true, deleted_id: '618' }),
  deleteAnnotationInterval: vi.fn().mockResolvedValue({ ok: true, speaker: 'Fail01', concept_id: '527', start: 10, end: 11, removed: { concept: 1, ipa: 1, ortho: 0, ortho_words: 0, speaker: 0 }, backup_path: 'backup.json', tolerance_sec: 0.001 }),
  promoteConceptSurveyPrimary: vi.fn().mockResolvedValue({ ok: true, concept: { id: '1', label: 'nose', source_survey: 'jbil', source_item: '34' } }),
}));

import { ParseUI } from "./ParseUI";
import * as apiClient from "./api/client";
import { ApiError } from "./api/contracts/shared";


function makeFakeBundleMatchingConceptKey() {
  const firstConcept = mockConfig?.concepts?.[0];
  if (!firstConcept) return { bundles: [] };
  const rowId = String(firstConcept.id);
  const label = firstConcept.label;
  const candidates: Record<string, Record<string, unknown>> = {};
  for (const speaker of mockConfig?.speakers ?? []) {
    const record = mockRecords[speaker];
    const conceptInterval = record?.tiers?.concept?.intervals?.find((iv) => String(iv.concept_id ?? '') === rowId || iv.text === label);
    if (!conceptInterval) continue;
    const ipa = record.tiers?.ipa?.intervals?.find((iv) => iv.start === conceptInterval.start && iv.end === conceptInterval.end)?.text ?? '';
    const ortho = record.tiers?.ortho?.intervals?.find((iv) => iv.start === conceptInterval.start && iv.end === conceptInterval.end)?.text ?? '';
    candidates[speaker] = { [rowId]: { csv_row_id: rowId, ipa, ortho, start_sec: conceptInterval.start, end_sec: conceptInterval.end, source_wav: record.source_wav, realization_index: 0 } };
  }
  return {
    bundles: [{
      bundle_id: rowId,
      uid: `c-${rowId}`,
      label,
      row_ids: [rowId],
      buckets: [{ bucket_key: `default\u0000${rowId}`, survey_id: 'default', source_item: rowId, variants: [{ csv_row_id: rowId, concept_en: label, variant_label: 'A' }] }],
      candidates,
      canonical: {},
    }],
  };
}

function makeBeShapedBigCompareBundles() {
  return {
    bundles: [{
      bundle_id: "bundle:big",
      uid: "c-53",
      label: "big",
      row_ids: ["53", "619", "150"],
      buckets: [
        {
          bucket_key: "klq\u00004.1",
          survey_id: "klq",
          source_item: "4.1",
          variants: [
            { csv_row_id: "53", concept_en: "big", variant_label: "A" },
            { csv_row_id: "619", concept_en: "big", variant_label: "B" },
          ],
        },
        {
          bucket_key: "jbil\u0000169",
          survey_id: "jbil",
          source_item: "169",
          variants: [{ csv_row_id: "150", concept_en: "big", variant_label: "A" }],
        },
      ],
      candidates: {
        Fail01: {
          "53": { csv_row_id: "53", ipa: "gawra", ortho: "big", start_sec: 1, end_sec: 2, realization_index: 0 },
          "619": null,
          "150": null,
        },
        Kalh01: {
          "53": null,
          "619": { csv_row_id: "619", ipa: "gewr", ortho: "big", start_sec: 3, end_sec: 4, realization_index: 1 },
          "150": null,
        },
      },
      canonical: { Fail01: null, Kalh01: null },
    }],
  };
}

function makeUnmatchedCompareBundles() {
  return {
    bundles: [{
      ...makeBeShapedBigCompareBundles().bundles[0],
      bundle_id: "bundle:small",
      label: "small",
      row_ids: ["999"],
    }],
  };
}

function makeRecord(
  speaker: string,
  concepts: Array<{ conceptText: string; conceptId?: string; ipa?: string; ortho?: string; start: number; end: number; importIndex?: number; importedCsvStart?: number; importedCsvEnd?: number }>,
): AnnotationRecord {
  const tier = (intervals: AnnotationInterval[]) => ({
    name: "tier",
    display_order: 1,
    intervals,
  });

  return {
    speaker,
    tiers: {
      ipa: tier(concepts.filter((c) => c.ipa != null).map((c) => ({ start: c.start, end: c.end, text: c.ipa ?? "" }))),
      ortho: tier(concepts.filter((c) => c.ortho != null).map((c) => ({ start: c.start, end: c.end, text: c.ortho ?? "" }))),
      concept: {
        name: "concept",
        display_order: 3,
        intervals: concepts.map((c) => ({
          start: c.start,
          end: c.end,
          text: c.conceptText,
          concept_id: c.conceptId ?? '1',
          ...(c.importIndex !== undefined ? { import_index: c.importIndex } : {}),
          ...(c.importedCsvStart !== undefined ? { imported_csv_start: c.importedCsvStart } : {}),
          ...(c.importedCsvEnd !== undefined ? { imported_csv_end: c.importedCsvEnd } : {}),
        })),
      },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: `${speaker}.wav`,
  };
}

function configureBigCompareWorkspace(concepts = [
  { id: "53", label: "big" },
  { id: "999", label: "small" },
]) {
  mockConfig = {
    project_name: "PARSE",
    language_code: "ku",
    speakers: ["Fail01", "Kalh01"],
    concepts,
    audio_dir: "audio",
    annotations_dir: "annotations",
  };
  mockRecords = {
    Fail01: makeRecord("Fail01", [
      { conceptText: "big", conceptId: "53", ipa: "gawra", ortho: "big", start: 1, end: 2 },
    ]),
    Kalh01: makeRecord("Kalh01", [
      { conceptText: "big", conceptId: "619", ipa: "gewr", ortho: "big", start: 3, end: 4 },
    ]),
  };
}


async function hydrateMockConfigThroughRealConfigStore(config: ProjectConfig, overlap: SurveyOverlapState): Promise<void> {
  mockGetConfig.mockResolvedValueOnce(structuredClone(config));
  mockGetSurveyOverlap.mockResolvedValueOnce(structuredClone(overlap));
  const actualConfigStore = await vi.importActual<typeof import("./stores/configStore")>("./stores/configStore");
  actualConfigStore.useConfigStore.setState({ config: null, loading: false, error: null });

  await actualConfigStore.useConfigStore.getState().load();

  mockConfig = actualConfigStore.useConfigStore.getState().config;
}

async function switchToAnnotateMode() {
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  fireEvent.click(await screen.findByRole("button", { name: /Annotate\s*A/i }));
}

async function switchToCompareMode() {
  fireEvent.click(screen.getByRole("button", { name: "Annotate" }));
  fireEvent.click(await screen.findByRole("button", { name: /Compare\s*C/i }));
}

function getCompareComputeModePicker() {
  const rightPanel = screen.getByTestId('right-panel');
  return within(rightPanel).getAllByRole('combobox')[1] as HTMLSelectElement;
}

async function switchCompareComputeMode(mode: 'cognates' | 'similarity' | 'contact-lexemes') {
  fireEvent.change(getCompareComputeModePicker(), { target: { value: mode } });
  await act(async () => {
    await Promise.resolve();
  });
}

function createMockWaveSurferForLanes() {
  const viewport = document.createElement("div");
  Object.defineProperty(viewport, "clientWidth", { value: 640, configurable: true });
  const wrapper = document.createElement("div");
  Object.defineProperty(wrapper, "clientWidth", { value: 640, configurable: true });
  viewport.appendChild(wrapper);

  const listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  return {
    options: { minPxPerSec: 120 },
    getDuration: () => 10,
    getWrapper: () => wrapper,
    on: (event: string, handler: (...args: unknown[]) => void) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)?.add(handler);
    },
    un: (event: string, handler: (...args: unknown[]) => void) => {
      listeners.get(event)?.delete(handler);
    },
    getCurrentTime: () => 0,
  };
}

function installBlobDownloadCapture() {
  const blobs: Blob[] = [];
  const originalCreate = (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
  const originalRevoke = (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
  (URL as unknown as { createObjectURL: (blob: Blob) => string }).createObjectURL = () => "blob:mock-url";
  (URL as unknown as { revokeObjectURL: (url: string) => void }).revokeObjectURL = () => {};

  const createObjectURL = vi
    .spyOn(URL, "createObjectURL")
    .mockImplementation((value: Blob | MediaSource) => {
      if (value instanceof Blob) blobs.push(value);
      return "blob:mock-url";
    });
  const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

  const realCreateElement = document.createElement.bind(document);
  const anchorClick = vi.fn();
  const createElement = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
    const element = realCreateElement(tag) as HTMLElement;
    if (tag === "a") {
      (element as HTMLAnchorElement).click = anchorClick;
    }
    return element;
  });

  return {
    blobs,
    anchorClick,
    createObjectURL,
    revokeObjectURL,
    restore() {
      createObjectURL.mockRestore();
      revokeObjectURL.mockRestore();
      createElement.mockRestore();
      if (originalCreate === undefined) {
        delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
      } else {
        (URL as unknown as { createObjectURL: unknown }).createObjectURL = originalCreate;
      }
      if (originalRevoke === undefined) {
        delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
      } else {
        (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = originalRevoke;
      }
    },
  };
}

async function readBlobText(blob: Blob): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

beforeEach(() => {
  window.localStorage.clear();
  // Default every test to "CLEF not configured" so the Reference Forms
  // gate stays closed unless the test opts into the configured state.
  mockClefConfig = {
    configured: false,
    primary_contact_languages: [],
    languages: [],
    config_path: "",
    concepts_csv_exists: false,
    meta: {},
  };
  mockCoverage = { languages: {} };
  mockConfig = {
    project_name: "PARSE",
    language_code: "ku",
    speakers: ["Fail01", "Kalh01"],
    concepts: [
      { id: "1", label: "water" },
      { id: "2", label: "fire" },
    ],
    audio_dir: "audio",
    annotations_dir: "annotations",
  };
  mockTags = [
    { id: "review-needed", label: "Review needed", color: "#f59e0b" },
    { id: "confirmed", label: "Confirmed", color: "#10b981" },
    { id: "problematic", label: "Problematic", color: "#ef4444" },
  ];
  mockRecords = {};
  mockEnrichmentData = {};
  mockEnrichmentSaveUsesDeepMerge = false;
  mockGetCompareBundles.mockReset();
  mockGetCompareBundles.mockImplementation(() => Promise.resolve(makeFakeBundleMatchingConceptKey()));
  mockGetConceptIdentity.mockReset();
  mockGetConceptIdentity.mockImplementation(() => Promise.resolve({ version: 1, concepts: [], uid_by_row: {}, warnings: [] }));
  mockPatchCanonicalLexeme.mockClear();
  mockSelectedRegion = { start: 1.25, end: 2.5 };
  mockPlaybackActiveSpeaker = null;
  mockPendingSeek = null;
  mockCurrentTime = 0;
  mockChatMessages = [];
  mockChatSending = false;
  mockChatError = null;
  mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
  mockPollAuth.mockResolvedValue({ status: "pending" });
  mockStartAuthFlow.mockResolvedValue(undefined);
  vi.mocked(apiClient.startCompute).mockResolvedValue({ job_id: 'compute-job-1', jobId: 'compute-job-1' });
  vi.mocked(apiClient.pollCompute).mockResolvedValue({ status: 'running', progress: 0 });
  vi.mocked(apiClient.getClefCatalog).mockResolvedValue({ languages: [] });
  vi.mocked(apiClient.getClefProviders).mockResolvedValue({ providers: [] });
  vi.mocked(apiClient.saveClefConfig).mockResolvedValue({
    success: true,
    config_path: 'config/sil_contact_languages.json',
    primary_contact_languages: [],
    language_count: 0,
  });
  vi.mocked(apiClient.startContactLexemeFetch).mockResolvedValue({ job_id: 'contact-fetch-job-1', jobId: 'contact-fetch-job-1' });
  vi.mocked(apiClient.listActiveJobs).mockResolvedValue([]);

  mockLoadConfig.mockClear();
  mockGetConfig.mockReset();
  mockGetSurveyOverlap.mockReset();
  mockReloadConfig.mockClear();
  mockUpdateSurveyOverlap.mockClear();
  mockHydrateTags.mockClear();
  mockLoadSpeaker.mockClear();
  mockSetInterval.mockClear();
  mockSaveLexemeAnnotation.mockReset();
  mockSaveLexemeAnnotation.mockReturnValue({ ok: true, moved: 4 });
  mockCreateConceptInterval.mockClear();
  mockSaveSpeaker.mockClear();
  mockMarkLexemeManuallyAdjusted.mockClear();
  mockFlushAutosave.mockClear();
  mockSetConceptTag.mockClear();
  mockClearConceptTag.mockClear();
  mockSetConfirmedAnchor.mockClear();
  mockClearConfirmedAnchor.mockClear();
  mockUpdateTag.mockClear();
  mockSetSelectedRegion.mockClear();
  mockSetActiveSpeaker.mockClear();
  mockSetActiveConcept.mockClear();
  mockSetSelectedSpeakers.mockClear();
  mockChatSend.mockClear();
  mockPlayPause.mockClear();
  mockSkip.mockClear();
  mockSeek.mockClear();
  mockAddRegion.mockClear();
  mockScrollToTimeAtFraction.mockClear();
  mockSetWaveZoom.mockClear();
  mockSetRate.mockClear();
  mockGetAuthStatus.mockClear();
  mockPollAuth.mockClear();
  mockStartAuthFlow.mockClear();
  vi.mocked(apiClient.startNormalize).mockClear();
  vi.mocked(apiClient.pollNormalize).mockClear();
  vi.mocked(apiClient.startSTT).mockClear();
  vi.mocked(apiClient.pollSTT).mockClear();
  vi.mocked(apiClient.startCompute).mockClear();
  vi.mocked(apiClient.pollCompute).mockClear();
  vi.mocked(apiClient.detectTimestampOffset).mockClear();
  vi.mocked(apiClient.detectTimestampOffsetFromPairs).mockClear();
  vi.mocked(apiClient.pollOffsetDetectJob).mockClear();
  vi.mocked(apiClient.applyTimestampOffset).mockClear();
  vi.mocked(apiClient.getJobLogs).mockClear();
  vi.mocked(apiClient.getLingPyExport).mockClear();
  vi.mocked(apiClient.saveApiKey).mockClear();
  vi.mocked(apiClient.getClefCatalog).mockClear();
  vi.mocked(apiClient.getClefProviders).mockClear();
  vi.mocked(apiClient.saveClefConfig).mockClear();
  vi.mocked(apiClient.startContactLexemeFetch).mockClear();
  vi.mocked(apiClient.listActiveJobs).mockClear();
  vi.mocked(apiClient.cancelComputeJob).mockClear();
  vi.mocked(apiClient.deleteConcept).mockReset();
  vi.mocked(apiClient.deleteConcept).mockResolvedValue({ ok: true, deleted_id: '618' });
  vi.mocked(apiClient.deleteAnnotationInterval).mockReset();
  vi.mocked(apiClient.deleteAnnotationInterval).mockResolvedValue({ ok: true, speaker: 'Fail01', concept_id: '527', start: 10, end: 11, removed: { concept: 1, ipa: 1, ortho: 0, ortho_words: 0, speaker: 0 }, backup_path: 'backup.json', tolerance_sec: 0.001 });
  vi.mocked(apiClient.promoteConceptSurveyPrimary).mockReset();
  vi.mocked(apiClient.promoteConceptSurveyPrimary).mockResolvedValue({ ok: true, concept: { id: '1', label: 'nose', source_survey: 'jbil', source_item: '34' } });

  mockAnnotationSetState.mockClear();
  mockEnrichmentSetState.mockClear();
  mockSaveEnrichments.mockClear();
  mockReplaceEnrichments.mockClear();
  mockTagSetState.mockClear();
  mockPlaybackSetState.mockClear();
  mockConfigSetState.mockClear();
  mockWaveOptions = [];
  mockWaveSurferInstance = null;
  useTranscriptionLanesStore.setState({
    sttBySpeaker: {},
    sttStatus: {},
    sttSourceBySpeaker: {},
    selectedInterval: null,
  });
  useCompareReturnStore.getState().clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});



describe("MC-418-B add elicitation", () => {
  it("replaces duplicate variant with + Add elicitation and creates another interval on the same concept id", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      ...mockConfig!,
      speakers: ["Fail01"],
      concepts: [{ id: "527", label: "head", source_item: "10", source_survey: "jbil" }],
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "sær", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    const rowButton = await screen.findByRole("button", { name: /head.*JBIL 10/i });
    fireEvent.contextMenu(rowButton);

    expect(screen.queryByText(/Duplicate/)).not.toBeTruthy();
    fireEvent.click(await screen.findByRole("menuitem", { name: /\+ Add elicitation/i }));

    expect(mockCreateConceptInterval).toHaveBeenCalledWith("Fail01", "527", 4.5, 5.5);
  });

  it("renders per-speaker interval-rank variant chips without persisted concept variants", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      ...mockConfig!,
      speakers: ["Fail01"],
      concepts: [{ id: "527", label: "head", source_item: "10", source_survey: "jbil" }],
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
        { conceptText: "head", conceptId: "527", ipa: "early", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    const rowButton = await screen.findByRole("button", { name: /head.*JBIL 10/i });
    const row = rowButton.closest("[data-testid^=\"concept-row-\"]") as HTMLElement;
    expect(within(row).getByRole("button", { name: "head (A)" })).toBeTruthy();
    expect(within(row).getByRole("button", { name: "head (B)" })).toBeTruthy();
  });
});

describe('ParseUI survey primary promotion', () => {
  it('promotes primary survey from the no-speaker sidebar badge and refreshes config', async () => {
    window.localStorage.setItem('parse.currentMode', 'compare');
    mockConfig = {
      ...mockConfig!,
      speakers: [],
      concepts: [
        { id: '1', label: 'nose', source_survey: 'klq', source_item: '1.5', surveys: { klq: '1.5', jbil: '34' } },
      ],
      concept_survey_links: { '1': { klq: '1.5', jbil: '34' } },
      survey_settings: {
        klq: { display_label: 'KLQ', display_color: 'violet' },
        jbil: { display_label: 'JBIL', display_color: 'rose' },
      },
      survey_color_coding_enabled: true,
    };

    render(<ParseUI />);

    const badge = await screen.findByRole('button', {
      name: 'Promote survey for nose from KLQ 1.5 to JBIL 34',
    });
    fireEvent.click(badge);

    await waitFor(() => expect(apiClient.promoteConceptSurveyPrimary).toHaveBeenCalledWith('1', {
      survey_id: 'jbil',
      source_item: '34',
    }));
    await waitFor(() => expect(mockReloadConfig).toHaveBeenCalled());
  });
});

describe("ParseUI", () => {


  it('surfaces both canonical and sidecar survey chips for the four concept in Annotate', async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      ...mockConfig!,
      speakers: ["Qasr01"],
      concepts: [
        { id: "220", label: "four", source_item: "4", source_survey: "jbil", surveys: { jbil: "4" } },
      ],
      concept_survey_links: { "220": { klq: "13.4" } },
      survey_settings: {
        jbil: { display_label: "JBIL", display_color: "violet" },
        klq: { display_label: "KLQ", display_color: "emerald" },
      },
      survey_color_coding_enabled: true,
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [
        { conceptText: "four", conceptId: "220", ipa: "tʃwar", ortho: "four", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    const chipRow = await screen.findByTestId('annotate-survey-chip-row');
    expect(within(chipRow).getAllByRole('button')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Current survey JBIL 4' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Switch four to KLQ 13.4' })).toBeTruthy();
  });


  it('honors speakerSurveyChoices override so user toggle flips the resolved chip', async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      ...mockConfig!,
      speakers: ["Qasr01"],
      concepts: [
        { id: "220", label: "four", source_item: "4", source_survey: "jbil", surveys: { jbil: "4" } },
      ],
      concept_survey_links: { "220": { klq: "13.4" } },
      speaker_survey_choices: { Qasr01: { "220": "klq" } },
      survey_settings: {
        jbil: { display_label: "JBIL", display_color: "violet" },
        klq: { display_label: "KLQ", display_color: "emerald" },
      },
      survey_color_coding_enabled: true,
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [
        { conceptText: "four", conceptId: "220", ipa: "tʃwar", ortho: "four", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    const chipRow = await screen.findByTestId('annotate-survey-chip-row');
    expect(within(chipRow).getAllByRole('button')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Current survey KLQ 13.4' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Switch four to JBIL 4' })).toBeTruthy();
  });


  it('renders survey chips from configStore.load-merged canonical and sidecar surveys for hair', async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    await hydrateMockConfigThroughRealConfigStore(
      {
        ...mockConfig!,
        speakers: ["Fail01"],
        concepts: [
          { id: "249", label: "hair (men)", source_item: "32", source_survey: "JBIL", surveys: { jbil: "32" } },
          { id: "250", label: "hair (women)", source_item: "32", source_survey: "JBIL", surveys: { jbil: "32" } },
        ],
      },
      {
        version: 1,
        color_coding_enabled: true,
        surveys: {
          jbil: { display_label: "JBIL", display_color: "violet" },
          klq: { display_label: "KLQ", display_color: "emerald" },
        },
        concept_survey_links: {
          "249": { klq: "1.1" },
          "250": { klq: "1.1" },
        },
        speaker_choices: {},
        speaker_concept_survey_links: {},
      },
    );
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "hair (men)", conceptId: "249", ipa: "prʧ", ortho: "hair", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    const chipRow = await screen.findByTestId('annotate-survey-chip-row');
    expect(within(chipRow).getAllByRole('button')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Current survey JBIL 32' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Switch hair (men) to KLQ 1.1' })).toBeTruthy();
  });

  function seedSingleSpeakerProject() {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [{ conceptText: "water", conceptId: "1", ipa: "aw", ortho: "ئاو", start: 1, end: 2 }]),
    };
  }

  const terminalSnapshot = (overrides: Partial<ActiveJobSnapshot>): ActiveJobSnapshot => ({
    jobId: "terminal-job",
    type: "compute:full_pipeline",
    status: "complete",
    progress: 1,
    startedTs: 1_716_000_000,
    ...overrides,
  });

  it("renders any active backend job in the generic header strip and removes legacy header job chips", async () => {
    seedSingleSpeakerProject();
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      {
        jobId: "lexeme-ortho-job",
        type: "compute:lexeme_rerun_ortho",
        status: "running",
        progress: 0.4,
        message: "Running ORTH rerun",
      },
    ]);

    render(<ParseUI />);

    const strip = await screen.findByTestId("topbar-job-strip");
    const row = await screen.findByTestId("topbar-job-strip-row-lexeme-ortho-job");
    expect(strip).toBeTruthy();
    expect(row.textContent).toContain("Lexeme ORTH");
    expect(row.textContent).toContain("40%");
    expect(screen.queryByTestId("topbar-action-statuses")).toBeNull();
    expect(screen.queryByTestId("topbar-batch-status")).toBeNull();
  });

  it("renders mid-flight progress correctly when /api/jobs/active returns the backend's 0-100 percentage scale", async () => {
    seedSingleSpeakerProject();
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      {
        jobId: "khan02-tagged-orth-job",
        type: "compute:lexeme_rerun_ortho",
        status: "running",
        // Post-parser snapshot fraction from the backend's 42% wire value; the API contract test pins that conversion.
        progress: 0.42,
        message: "Loading ORTH provider",
      },
    ]);

    render(<ParseUI />);

    const row = await screen.findByTestId("topbar-job-strip-row-khan02-tagged-orth-job");
    expect(row.textContent).toContain("42%");
    expect(row.textContent).not.toContain("100%");
  });

  it("shows the terminal state from /api/jobs/active when the backend retains a recently-completed job, then auto-dismisses after the configured delay", async () => {
    vi.useFakeTimers();
    seedSingleSpeakerProject();
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      terminalSnapshot({
        jobId: "full-pipeline-complete",
        type: "compute:full_pipeline",
        status: "complete",
        progress: 1,
      }),
    ]);

    render(<ParseUI />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const strip = screen.getByTestId("topbar-job-strip");
    const row = screen.getByTestId("topbar-job-strip-row-full-pipeline-complete");
    expect(strip).toBeTruthy();
    expect(row.textContent).toContain("Pipeline done");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-full-pipeline-complete")).toBeNull();
    expect(screen.getByTestId("topbar-job-strip")).toBeTruthy();
  });

  it("shows the error state from /api/jobs/active for a recently-failed terminal snapshot and dismisses it on the same cadence", async () => {
    vi.useFakeTimers();
    seedSingleSpeakerProject();
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      terminalSnapshot({
        jobId: "lexeme-ortho-error",
        type: "compute:lexeme_rerun_ortho",
        status: "error",
        progress: 1,
        error: "CUDA OOM at chunk 42",
      }),
    ]);

    render(<ParseUI />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const row = screen.getByTestId("topbar-job-strip-row-lexeme-ortho-error");
    expect(row.textContent).toContain("Lexeme ORTH failed");
    expect(row.textContent).toContain("CUDA OOM");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-lexeme-ortho-error")).toBeNull();
  });

  it("shows the cancelled state from /api/jobs/active for a recently-cancelled terminal snapshot and dismisses it on the same cadence", async () => {
    vi.useFakeTimers();
    seedSingleSpeakerProject();
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      terminalSnapshot({
        jobId: "stt-cancelled",
        type: "compute:stt",
        status: "cancelled",
        progress: 1,
      }),
    ]);

    render(<ParseUI />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const strip = screen.getByTestId("topbar-job-strip");
    const row = screen.getByTestId("topbar-job-strip-row-stt-cancelled");
    expect(strip).toBeTruthy();
    expect(row.textContent).toContain("STT cancelled");
    expect(row.className).toContain("border-amber-200");
    expect(row.className).toContain("bg-amber-50");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-stt-cancelled")).toBeNull();
    expect(screen.getByTestId("topbar-job-strip")).toBeTruthy();
  });

  it("keeps a terminal snapshot dismissed even when /api/jobs/active keeps returning it during the backend dwell window", async () => {
    vi.useFakeTimers();
    seedSingleSpeakerProject();
    const snapshot = terminalSnapshot({
      jobId: "dwell-job",
      type: "compute:ortho",
      status: "complete",
      progress: 1,
    });
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([snapshot]);

    render(<ParseUI />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const row = screen.getByTestId("topbar-job-strip-row-dwell-job");
    expect(row.textContent).toContain("ORTH done");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.queryByTestId("topbar-job-strip-row-dwell-job")).toBeNull();

    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([snapshot]);
    await act(async () => {
      window.dispatchEvent(new Event("parse:active-jobs-refresh"));
      await Promise.resolve();
    });

    expect(screen.queryByTestId("topbar-job-strip-row-dwell-job")).toBeNull();
  });

  it("scopes Annotate sidebar and reviewed counter to the active speaker's elicited concepts by default", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Fail02"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
        { id: "3", label: "earth" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: {
        ...makeRecord("Fail01", [
          { conceptText: "water", conceptId: "1", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
          { conceptText: "earth", conceptId: "3", ipa: "xak", ortho: "خاک", start: 3, end: 4 },
        ]),
        concept_tags: { "1": ["confirmed"], "2": ["confirmed"] },
      },
      Fail02: makeRecord("Fail02", [
        { conceptText: "fire", conceptId: "2", ipa: "agir", ortho: "ئاگر", start: 5, end: 6 },
      ]),
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByText("1 / 2 reviewed for Fail01")).toBeTruthy());
    expect(screen.getByText("2 of 3 master concepts elicited")).toBeTruthy();
    const sidebar = screen.getByTestId("concept-sidebar");
    const breadcrumb = within(sidebar).getByTestId("concept-scope-breadcrumb");
    expect(breadcrumb.textContent).toContain("2 in Fail01");
    expect(within(sidebar).getByRole("button", { name: /show all/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /water/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /earth/i })).toBeTruthy();
    expect(within(sidebar).queryByRole("button", { name: /fire/i })).toBeNull();
  });

  it("keeps Compare mode on the global sidebar and reviewed denominator by default", () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Fail02"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
        { id: "3", label: "earth" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: { ...makeRecord("Fail01", [{ conceptText: "water", conceptId: "1", start: 1, end: 2 }]), concept_tags: { "1": ["confirmed"] } },
    };

    render(<ParseUI />);

    expect(screen.getByText("1 / 3 reviewed")).toBeTruthy();
    const sidebar = screen.getByTestId("concept-sidebar");
    expect(within(sidebar).getByRole("button", { name: /water/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /fire/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /earth/i })).toBeTruthy();
  });

  it("persists Annotate Show all sidebar scope and updates elicited counts on speaker switch", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    window.localStorage.setItem("parse.sidebar.scopedToSpeaker.annotate", "false");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Fail02"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
        { id: "3", label: "earth" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [{ conceptText: "water", conceptId: "1", start: 1, end: 2 }]),
      Fail02: {
        ...makeRecord("Fail02", [
          { conceptText: "fire", conceptId: "2", start: 3, end: 4 },
          { conceptText: "earth", conceptId: "3", start: 5, end: 6 },
        ]),
        concept_tags: { "2": ["confirmed"] },
      },
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByText("0 / 1 reviewed for Fail01")).toBeTruthy());
    const sidebar = screen.getByTestId("concept-sidebar");
    const breadcrumb = within(sidebar).getByTestId("concept-scope-breadcrumb");
    expect(breadcrumb.textContent).toContain("3 concepts");
    expect(within(sidebar).getByRole("button", { name: /scope to speaker/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /fire/i }).textContent ?? "").toContain("no data");

    fireEvent.click(screen.getAllByRole("button", { name: "Fail02" })[0]);

    await waitFor(() => expect(screen.getByText("1 / 2 reviewed for Fail02")).toBeTruthy());
    expect(screen.getByText("2 of 3 master concepts elicited")).toBeTruthy();
  });
  it("loads config and tag hydration on mount and computes reviewed count from confirmed tags", () => {
    mockRecords = { Fail01: { ...makeRecord("Fail01", []), concept_tags: { "1": ["confirmed"] } } };

    render(<ParseUI />);

    expect(mockLoadConfig).toHaveBeenCalledOnce();
    expect(mockHydrateTags).toHaveBeenCalledOnce();
    expect(mockSyncTagsFromServer).toHaveBeenCalled();
    expect(screen.getByText("1 / 2 reviewed")).toBeTruthy();
  });

  const sidebarConceptNames = () => Array.from(screen.getByTestId("concept-sidebar").querySelectorAll('[data-testid^="concept-row-"]'))
    .map((row) => row.querySelector('button[aria-label] span.flex-1')?.childNodes[0]?.textContent?.trim() ?? "")
    .filter(Boolean);

  function configureSourceSortFixture(sourceSub: "time" | "row") {
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: sourceSub }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01"],
      concepts: [
        { id: "1", label: "one" },
        { id: "2", label: "two" },
        { id: "3", label: "three" },
        { id: "4", label: "four" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [
        { conceptText: "one", conceptId: "1", start: 5.0, end: 5.5, importIndex: 3 },
        { conceptText: "two", conceptId: "2", start: 0.5, end: 1.0, importIndex: 0 },
        { conceptText: "three", conceptId: "3", start: 12.0, end: 12.5, importIndex: 1 },
        { conceptText: "four", conceptId: "4", start: 2.0, end: 2.5, importIndex: 2 },
      ]),
    };
  }

  it("orders the sidebar by per-speaker concept start time when Source / Time is restored", async () => {
    configureSourceSortFixture("time");

    render(<ParseUI />);

    await waitFor(() => expect(sidebarConceptNames()).toEqual(["two", "four", "one", "three"]));
  });

  it("orders the sidebar by per-speaker import_index when Source / Row is restored", async () => {
    configureSourceSortFixture("row");

    render(<ParseUI />);

    await waitFor(() => expect(sidebarConceptNames()).toEqual(["two", "three", "four", "one"]));
  });

  it("sinks concepts without active-speaker source keys to the bottom in 1–N order", async () => {
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: "time" }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01"],
      concepts: [
        { id: "1", label: "one" },
        { id: "2", label: "two" },
        { id: "3", label: "three" },
        { id: "4", label: "four" },
        { id: "5", label: "five" },
        { id: "6", label: "six" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [
        { conceptText: "three", conceptId: "3", start: 12.0, end: 12.5, importIndex: 1 },
        { conceptText: "one", conceptId: "1", start: 5.0, end: 5.5, importIndex: 3 },
      ]),
    };

    render(<ParseUI />);

    await waitFor(() => expect(sidebarConceptNames()).toEqual(["one", "three", "two", "four", "five", "six"]));
  });

  it("disables Source ordering without exactly one selected speaker and preserves the Concept sub-mode", async () => {
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "az", source_sub: "row" }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: [],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    const { unmount } = render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBe("true"));
    fireEvent.click(screen.getByTestId("concept-sort-parent-source"));
    expect(screen.getByTestId("concept-sort-parent-concept").className).toContain("bg-white");
    expect(screen.getByTestId("concept-sort-az").className).toContain("bg-white");
    expect(screen.getByTestId("concept-sort-az")).toBeTruthy();
    expect(screen.queryByTestId("concept-sort-source-time")).toBeNull();

    unmount();
    cleanup();
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "az", source_sub: "row" }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kalh01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBe("true"));
    fireEvent.click(screen.getByTestId("concept-sort-parent-source"));
    expect(screen.getByTestId("concept-sort-parent-concept").className).toContain("bg-white");
    expect(screen.getByTestId("concept-sort-az").className).toContain("bg-white");
    expect(screen.getByTestId("concept-sort-az")).toBeTruthy();
    expect(screen.queryByTestId("concept-sort-source-time")).toBeNull();
  });

  it("sorts by Concept 1–N when Source is persisted but no speaker is selected", async () => {
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: "time" }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: [],
      concepts: [
        { id: "1", label: "one" },
        { id: "2", label: "two" },
        { id: "3", label: "three" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [
        { conceptText: "three", conceptId: "3", start: 0.5, end: 1.0, importIndex: 0 },
        { conceptText: "two", conceptId: "2", start: 2.0, end: 2.5, importIndex: 1 },
        { conceptText: "one", conceptId: "1", start: 5.0, end: 5.5, importIndex: 2 },
      ]),
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBe("true"));
    expect(screen.getByTestId("concept-sort-1n")).toBeTruthy();
    expect(screen.queryByTestId("concept-sort-source-time")).toBeNull();
    expect(sidebarConceptNames()).toEqual(["one", "two", "three"]);
  });

  it("preserves persisted Source preference through a multi-select detour", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01"],
      concepts: [{ id: "1", label: "one" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Qasr01: makeRecord("Qasr01", [{ conceptText: "one", conceptId: "1", start: 1, end: 2, importIndex: 1 }]) };

    const { unmount } = render(<ParseUI />);
    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBeNull());
    fireEvent.click(screen.getByTestId("concept-sort-parent-source"));
    fireEvent.click(screen.getByTestId("concept-sort-source-row"));

    await waitFor(() => expect(window.localStorage.getItem("parse.concept-sort.v1")).toBe(JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: "row" })));
    unmount();
    cleanup();

    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01", "Khan01"],
      concepts: [{ id: "1", label: "one" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [{ conceptText: "one", conceptId: "1", start: 1, end: 2, importIndex: 1 }]),
      Khan01: makeRecord("Khan01", [{ conceptText: "one", conceptId: "1", start: 3, end: 4, importIndex: 1 }]),
    };

    const multi = render(<ParseUI />);
    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBe("true"));
    expect(screen.getByTestId("concept-sort-1n")).toBeTruthy();
    expect(screen.queryByTestId("concept-sort-source-row")).toBeNull();
    expect(window.localStorage.getItem("parse.concept-sort.v1")).toBe(JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: "row" }));
    multi.unmount();
    cleanup();

    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01"],
      concepts: [{ id: "1", label: "one" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Qasr01: makeRecord("Qasr01", [{ conceptText: "one", conceptId: "1", start: 1, end: 2, importIndex: 1 }]) };

    render(<ParseUI />);
    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").className).toContain("bg-sky-600"));
    expect(screen.getByTestId("concept-sort-source-row").className).toContain("bg-sky-600");
  });

  it("does not demote raw Source state when mounted with multiple selected speakers", async () => {
    window.localStorage.setItem("parse.concept-sort.v1", JSON.stringify({ parent: "source", concept_sub: "az", source_sub: "time" }));
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01", "Khan01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Qasr01: makeRecord("Qasr01", [{ conceptText: "water", conceptId: "1", start: 1, end: 2 }]),
      Khan01: makeRecord("Khan01", [{ conceptText: "fire", conceptId: "2", start: 3, end: 4 }]),
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBe("true"));
    expect(screen.getByTestId("concept-sort-az")).toBeTruthy();
    expect(screen.queryByTestId("concept-sort-source-time")).toBeNull();
    expect(window.localStorage.getItem("parse.concept-sort.v1")).toBe(JSON.stringify({ parent: "source", concept_sub: "az", source_sub: "time" }));
  });

  it("persists the split concept sort state under parse.concept-sort.v1", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Qasr01"],
      concepts: [
        { id: "1", label: "one" },
        { id: "2", label: "two" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Qasr01: makeRecord("Qasr01", [{ conceptText: "one", conceptId: "1", start: 1, end: 2, importIndex: 1 }]) };

    const { unmount } = render(<ParseUI />);
    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").getAttribute("aria-disabled")).toBeNull());
    fireEvent.click(screen.getByTestId("concept-sort-parent-source"));
    fireEvent.click(screen.getByTestId("concept-sort-source-row"));

    await waitFor(() => expect(window.localStorage.getItem("parse.concept-sort.v1")).toBe(JSON.stringify({ parent: "source", concept_sub: "1n", source_sub: "row" })));
    unmount();
    cleanup();

    render(<ParseUI />);
    await waitFor(() => expect(screen.getByTestId("concept-sort-parent-source").className).toContain("bg-sky-600"));
    expect(screen.getByTestId("concept-sort-source-row").className).toContain("bg-sky-600");
  });

  it("groups source_item sibling rows into one sidebar entry while leaving singleton concepts visible", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "concept-a", label: "brother of husband A", source_item: "2.15", source_survey: "KLQ", custom_order: 1 },
        { id: "concept-b", label: "brother of husband B", source_item: "2.15", source_survey: "KLQ", custom_order: 2 },
        { id: "concept-c", label: "sister of husband", source_item: "2.16", source_survey: "KLQ", custom_order: 3 },
        { id: "concept-d", label: "water" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    render(<ParseUI />);

    // Compare mode hides the variant pill strip to prevent flood (MC-402);
    // grouped-variant rendering is asserted in annotate mode where the strip is on.
    await switchToAnnotateMode();

    const sidebar = screen.getByTestId("concept-sidebar");
    expect(within(sidebar).getByText("3 concepts")).toBeTruthy();
    expect(within(sidebar).getByText("brother of husband")).toBeTruthy();
    expect(within(sidebar).getByTestId("concept-variant-pill-concept-a").textContent ?? "").toContain("brother of husband A");
    expect(within(sidebar).getByTestId("concept-variant-pill-concept-b").textContent ?? "").toContain("brother of husband B");
    expect(within(sidebar).getByText("sister of husband")).toBeTruthy();
    expect(within(sidebar).getByText("water")).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /brother of husband.*KLQ 2\.15/i })).toBeTruthy();
  });

  it("hides concept variant pills in compare mode to prevent flood (MC-402)", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "concept-a", label: "brother of husband A", source_item: "2.15", source_survey: "KLQ", custom_order: 1 },
        { id: "concept-b", label: "brother of husband B", source_item: "2.15", source_survey: "KLQ", custom_order: 2 },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    render(<ParseUI />);

    const sidebar = screen.getByTestId("concept-sidebar");
    // Default mount lands in compare mode (ParseUI.tsx default).
    expect(within(sidebar).getByText("brother of husband")).toBeTruthy();
    expect(within(sidebar).queryByTestId("concept-variant-pill-concept-a")).toBeNull();
    expect(within(sidebar).queryByTestId("concept-variant-pill-concept-b")).toBeNull();
  });

  it("pre-populates annotate fields from stored intervals and shows Complete badge", async () => {
    mockRecords = {
      Fail01: {
        ...makeRecord("Fail01", [
          { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        ]),
        concept_tags: { "1": ["confirmed"] },
      },
    };

    render(<ParseUI />);

    await switchToAnnotateMode();

    expect(await screen.findByDisplayValue("aw")).toBeTruthy();
    expect(screen.getByDisplayValue("ئاو")).toBeTruthy();
    expect(screen.getByText("Complete")).toBeTruthy();
    expect(screen.queryByText("Annotated")).toBeNull();
    expect(screen.queryByText("Missing")).toBeNull();
  });

  it("switches Compare → Annotate without crashing when TranscriptionLanes initializes waveform metrics", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    mockWaveSurferInstance = createMockWaveSurferForLanes();

    render(<ParseUI />);
    await switchToAnnotateMode();

    const latestWaveOptions = () => mockWaveOptions[mockWaveOptions.length - 1];
    await act(async () => {
      latestWaveOptions()?.onReady?.(10);
    });

    expect(await screen.findByTitle("IPA lane")).toBeTruthy();
    expect(screen.getByPlaceholderText("Enter IPA…")).toBeTruthy();
  });

  it("saves annotation tiers for the selected region and persists the speaker record", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", start: 1.25, end: 2.5 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.change(screen.getByPlaceholderText("Enter IPA…"), { target: { value: "aβ" } });
    fireEvent.change(screen.getByPlaceholderText("Enter orthographic form…"), { target: { value: "ئاو" } });
    fireEvent.click(screen.getAllByTestId("save-lexeme-annotation")[0]);

    expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith({
      speaker: "Fail01",
      oldStart: 1.25,
      oldEnd: 2.5,
      newStart: 1.25,
      newEnd: 2.5,
      ipaText: "aβ",
      orthoText: "ئاو",
      orthoEdited: true,
      conceptName: "water",
    });
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith("Fail01", expect.anything()));
    expect(mockSetInterval).not.toHaveBeenCalled();
  });

  it("marks the current concept confirmed from annotate mode", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", conceptId: "1", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByRole("button", { name: /Mark Done/i }));
    expect(mockSetConceptTag).toHaveBeenCalledWith("Fail01", "1", "confirmed");
  });

  it("turns the sidebar dot green after Mark Done", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", conceptId: "1", start: 1, end: 2 },
      ]),
    };

    const { rerender } = render(<ParseUI />);
    await switchToAnnotateMode();

    const waterButton = () =>
      within(screen.getByTestId("concept-sidebar"))
        .getAllByRole("button")
        .find((button) => button.textContent?.includes("water"));
    const dotForWater = () => waterButton()?.querySelector("span");

    expect(dotForWater()?.className).toContain("bg-slate-300");

    fireEvent.click(screen.getByRole("button", { name: /Mark Done/i }));
    rerender(<ParseUI />);

    await waitFor(() => {
      expect(dotForWater()?.className).toContain("bg-emerald-500");
    });
  });

  it("scopes annotate sidebar status filters to the active speaker when that speaker has no annotation record", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Khan03", "Saha01"],
      concepts: [
        { id: "1", label: "water", source_item: "1.1", source_survey: "KLQ" },
        { id: "1.5", label: "nose", source_item: "1.5", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Saha01: { ...makeRecord("Saha01", []), concept_tags: { "1.5": ["confirmed", "problematic"] } },
    };

    const { rerender } = render(<ParseUI />);
    await switchToAnnotateMode();
    const sidebar = () => screen.getByTestId("concept-sidebar");
    const noseButton = () => within(sidebar()).queryByRole("button", { name: /nose.*KLQ 1\.5/i });

    expect(noseButton()?.querySelector("span")?.className).toContain("bg-slate-300");

    fireEvent.click(screen.getByTestId("tagfilter-unreviewed"));
    expect(noseButton()).toBeTruthy();

    fireEvent.click(screen.getByTestId("tagfilter-unreviewed"));
    fireEvent.click(screen.getByTestId("tagfilter-flagged"));
    expect(noseButton()).toBeNull();

    mockSetConceptTag("Saha01", "1.5", "confirmed");
    rerender(<ParseUI />);
    fireEvent.click(screen.getByTestId("tagfilter-flagged"));
    fireEvent.click(screen.getByTestId("tagfilter-unreviewed"));
    expect(noseButton()).toBeTruthy();
  });

  it("scopes annotate custom tag filters to the active speaker and preserves compare union semantics", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Khan03", "Saha01"],
      concepts: [
        { id: "1", label: "water", source_item: "1.1", source_survey: "KLQ" },
        { id: "1.5", label: "nose", source_item: "1.5", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockTags = [...mockTags, { id: "thesis", label: "Thesis", color: "#6366f1" }];
    mockRecords = {
      Khan03: { ...makeRecord("Khan03", []), concept_tags: { "1.5": ["thesis"] } },
      Saha01: makeRecord("Saha01", []),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();
    const sidebar = () => screen.getByTestId("concept-sidebar");
    const noseButton = () => within(sidebar()).queryByRole("button", { name: /nose.*KLQ 1\.5/i });
    const thesisFilter = () => within(sidebar()).getByRole("button", { name: /Thesis/i });

    fireEvent.click(thesisFilter());
    expect(noseButton()).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Saha01" })[0]);
    await waitFor(() => expect(noseButton()).toBeNull());

    await switchToCompareMode();
    fireEvent.click(thesisFilter());
    expect(noseButton()).toBeTruthy();
  });

  it("keeps grouped variant concepts in speaker-scoped custom tag filters and excludes untagged elicited concepts", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Saha01"],
      concepts: [
        { id: "367", label: "cold (A)", source_item: "157", source_survey: "JBIL" },
        { id: "368", label: "cold (B)", source_item: "157", source_survey: "JBIL" },
        { id: "540", label: "cold", source_item: "157", source_survey: "JBIL" },
        { id: "521", label: "they", source_item: "323", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockTags = [...mockTags, { id: "thesis", label: "Thesis", color: "#6366f1" }];
    mockRecords = {
      Saha01: {
        ...makeRecord("Saha01", [
          { conceptText: "cold", conceptId: "540", start: 0, end: 1 },
          { conceptText: "they", conceptId: "521", start: 1, end: 2 },
        ]),
        concept_tags: { "540": ["thesis"] },
      },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();
    const sidebar = () => screen.getByTestId("concept-sidebar");
    fireEvent.click(within(sidebar()).getByRole("button", { name: /Thesis/i }));

    expect(within(sidebar()).queryByRole("button", { name: /cold.*JBIL 157/i })).toBeTruthy();
    expect(within(sidebar()).queryByRole("button", { name: /they.*JBIL 323/i })).toBeNull();
  });

  it("scopes annotate right-panel tag rows to the active speaker", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Khan03", "Saha01"],
      concepts: [
        { id: "1.5", label: "nose", source_item: "1.5", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Saha01: { ...makeRecord("Saha01", []), concept_tags: { "1.5": ["confirmed", "problematic"] } },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const rightPanel = () => screen.getByTestId("right-panel");
    const confirmedRow = () => within(rightPanel()).getByRole("button", { name: /Confirmed\s+1/i });
    const problematicRow = () => within(rightPanel()).getByRole("button", { name: /Problematic\s+1/i });
    expect(confirmedRow().getAttribute("aria-pressed")).toBe("false");
    expect(problematicRow().getAttribute("aria-pressed")).toBe("false");
    expect(confirmedRow().className).not.toContain("bg-indigo-50");
    expect(problematicRow().className).not.toContain("bg-indigo-50");

    fireEvent.click(screen.getAllByRole("button", { name: "Saha01" })[0]);
    await waitFor(() => expect(confirmedRow().getAttribute("aria-pressed")).toBe("true"));
    expect(problematicRow().getAttribute("aria-pressed")).toBe("true");
    expect(confirmedRow().className).toContain("bg-indigo-50");
    expect(problematicRow().className).toContain("bg-indigo-50");
  });

  it("other speakers' annotated variants do not appear in a scoped grouped row", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kalh01"],
      concepts: [
        { id: "247", label: "head (A)", source_item: "31", source_survey: "JBIL" },
        { id: "527", label: "head", source_item: "31", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [{ conceptText: "head", conceptId: "527", start: 1, end: 2 }]),
      Kalh01: makeRecord("Kalh01", [{ conceptText: "head (A)", conceptId: "247", start: 3, end: 4 }]),
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    const parent = await within(sidebar).findByRole("button", { name: /head.*JBIL 31/i });

    expect(parent).toBeTruthy();
    expect(within(sidebar).queryByTestId("concept-variant-pill-247")).toBeNull();
  });

  it("right-click → Delete variant opens the confirmation modal", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "365", label: "new (A)", source_item: "154", source_survey: "JBIL" },
        { id: "618", label: "new (B)", source_item: "154", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    await waitFor(() => expect(within(sidebar).getByTestId("concept-variant-pill-618")).toBeTruthy());
    fireEvent.contextMenu(within(sidebar).getByTestId("concept-variant-pill-618"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete variant/i }));

    expect(screen.getByText("Delete new (B)?")).toBeTruthy();
    expect(screen.getByText(/permanently removes new \(B\)/i)).toBeTruthy();
  });

  it("successful delete reloads config and closes without a viewport toast", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "365", label: "new (A)", source_item: "154", source_survey: "JBIL" },
        { id: "618", label: "new (B)", source_item: "154", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockResolvedValueOnce({ ok: true, deleted_id: "618" });
    mockReloadConfig.mockClear();
    mockSyncTagsFromServer.mockClear();

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    await waitFor(() => expect(within(sidebar).getByTestId("concept-variant-pill-618")).toBeTruthy());
    fireEvent.contextMenu(within(sidebar).getByTestId("concept-variant-pill-618"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete variant/i }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("618"));
    await waitFor(() => expect(mockReloadConfig).toHaveBeenCalled());
    expect(mockSyncTagsFromServer).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("Delete new (B)?")).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
  });


  it("annotate-panel Delete concept opens the shared modal and navigates to the previous concept on success", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockResolvedValueOnce({ ok: true, deleted_id: "2" });

    render(<ParseUI />);

    fireEvent.click(await screen.findByRole("button", { name: /hair/i }));
    expect(await screen.findByRole("heading", { name: "hair" })).toBeTruthy();
    mockSetActiveConcept.mockClear();

    fireEvent.click(screen.getByTestId("annotate-delete-concept"));
    expect(screen.getByText("Delete hair?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("2"));
    await waitFor(() => expect(mockReloadConfig).toHaveBeenCalled());
    expect(mockSyncTagsFromServer).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("Delete hair?")).toBeNull());
    expect(await screen.findByRole("heading", { name: "water" })).toBeTruthy();
    await waitFor(() => expect(mockSetActiveConcept).toHaveBeenCalledWith("1"));
  });

  it("annotate-panel Delete concept keeps the modal open on 409 and does not navigate", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockRejectedValueOnce(
      new ApiError(409, "DELETE", "/api/concepts/2", { error: "blocked", blocking_speakers: ["Qasr01"] }, "API DELETE /api/concepts/2 failed 409"),
    );

    render(<ParseUI />);

    fireEvent.click(await screen.findByRole("button", { name: /hair/i }));
    expect(await screen.findByRole("heading", { name: "hair" })).toBeTruthy();
    mockSetActiveConcept.mockClear();

    fireEvent.click(screen.getByTestId("annotate-delete-concept"));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("2"));
    expect(screen.getByText("Delete hair?")).toBeTruthy();
    expect(screen.getByText(/1 speaker\(s\) have annotated this lexeme: Qasr01/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.getByRole("heading", { name: "hair" })).toBeTruthy();
    expect(mockSetActiveConcept).not.toHaveBeenCalledWith("1");
  });

  it("sidebar right-click delete success keeps the current post-delete navigation behavior", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockResolvedValueOnce({ ok: true, deleted_id: "2" });

    render(<ParseUI />);

    fireEvent.click(await screen.findByRole("button", { name: /hair/i }));
    expect(await screen.findByRole("heading", { name: "hair" })).toBeTruthy();
    mockSetActiveConcept.mockClear();

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.contextMenu(within(sidebar).getByRole("button", { name: /hair/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete variant/i }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("2"));
    await waitFor(() => expect(mockReloadConfig).toHaveBeenCalled());
    expect(mockSyncTagsFromServer).toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "hair" })).toBeTruthy();
    expect(mockSetActiveConcept).not.toHaveBeenCalledWith("1");
  });

  it("delete network error surfaces inline in the delete modal and keeps it open", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "365", label: "new (A)", source_item: "154", source_survey: "JBIL" },
        { id: "618", label: "new (B)", source_item: "154", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockRejectedValueOnce(new Error("Could not reach the PARSE API"));

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    await waitFor(() => expect(within(sidebar).getByTestId("concept-variant-pill-618")).toBeTruthy());
    fireEvent.contextMenu(within(sidebar).getByTestId("concept-variant-pill-618"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete variant/i }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("618"));
    expect(screen.getByText("Delete new (B)?")).toBeTruthy();
    const modalError = screen.getByText("Delete failed.").parentElement as HTMLElement;
    expect(modalError.textContent ?? "").toContain("Could not reach the PARSE API");
    expect(modalError.className).toContain("bg-rose-50");
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("409 delete keeps the modal open and surfaces blocking speakers", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "365", label: "new (A)", source_item: "154", source_survey: "JBIL" },
        { id: "618", label: "new (B)", source_item: "154", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockRejectedValueOnce(
      new ApiError(409, "DELETE", "/api/concepts/618", { error: "blocked", blocking_speakers: ["Qasr01"] }, "API DELETE /api/concepts/618 failed 409"),
    );

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    await waitFor(() => expect(within(sidebar).getByTestId("concept-variant-pill-618")).toBeTruthy());
    fireEvent.contextMenu(within(sidebar).getByTestId("concept-variant-pill-618"));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete variant/i }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("618"));
    expect(screen.getByText("Delete new (B)?")).toBeTruthy();
    expect(screen.getByText(/1 speaker\(s\) have annotated this lexeme: Qasr01/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("treats an explicit empty annotate tag scope as untagged", () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Khan03", "Saha01"],
      concepts: [
        { id: "1.5", label: "nose", source_item: "1.5", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Saha01: { ...makeRecord("Saha01", []), concept_tags: { "1.5": ["confirmed"] } },
    };

    render(<ParseUI />);

    const sidebar = screen.getByTestId("concept-sidebar");
    const noseButton = within(sidebar).getByRole("button", { name: /nose.*KLQ 1\.5/i });
    expect(noseButton.querySelector("span")?.className).toContain("bg-slate-300");
    expect(noseButton.querySelector("span")?.className).not.toContain("bg-emerald-500");
  });

  it("keeps compare action buttons checked from the selected-speaker tag union", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Khan03", "Saha01"],
      concepts: [
        { id: "1", label: "water", source_item: "1.1", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Khan03: makeRecord("Khan03", []),
      Saha01: { ...makeRecord("Saha01", []), concept_tags: { "1": ["confirmed"] } },
    };

    render(<ParseUI />);

    const sidebar = screen.getByTestId("concept-sidebar");
    const waterButton = within(sidebar).getByRole("button", { name: /water.*KLQ 1\.1/i });
    expect(waterButton.querySelector("span")?.className).toContain("bg-emerald-500");
    expect(screen.getByRole("button", { name: /Accept concept/i }).className).toContain("bg-emerald-700");
  });


  it("waits for the newly selected speaker audio to become ready before seeking and drawing a region", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Fail02"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
      Fail02: makeRecord("Fail02", [
        { conceptText: "water", ipa: "aβ", ortho: "ئاڤ", start: 5, end: 6 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const latestWaveOptions = () => mockWaveOptions[mockWaveOptions.length - 1];

    expect(latestWaveOptions()?.audioUrl).toContain("/Fail01.wav");

    await act(async () => {
      latestWaveOptions()?.onReady?.(10);
    });

    expect(mockSeek).toHaveBeenCalledWith(1);
    expect(mockAddRegion).toHaveBeenCalledWith(1, 2);

    mockSeek.mockClear();
    mockAddRegion.mockClear();
    mockScrollToTimeAtFraction.mockClear();

    fireEvent.click(screen.getAllByRole("button", { name: "Fail02" })[0]);

    await waitFor(() => expect(latestWaveOptions()?.audioUrl).toContain("/Fail02.wav"));
    expect(mockSeek).not.toHaveBeenCalled();
    expect(mockAddRegion).not.toHaveBeenCalled();
    expect(mockScrollToTimeAtFraction).not.toHaveBeenCalled();

    await act(async () => {
      latestWaveOptions()?.onReady?.(12);
    });

    expect(mockSeek).toHaveBeenCalledWith(5);
    expect(mockAddRegion).toHaveBeenCalledWith(5, 6);
    expect(mockScrollToTimeAtFraction).toHaveBeenCalledWith(5, 0.33);
  });

  it("renders compare reference forms from enrichment data", async () => {
    // Opt into CLEF-configured state so the Reference Forms section
    // actually renders. The gate hides the whole section when
    // primary_contact_languages is empty.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockEnrichmentData = {
      reference_forms: {
        "1": {
          ar: { script: "ماء", ipa: "maːʔ" },
          fa: { script: "آب", ipa: "ɒːb" },
        },
      },
    };

    render(<ParseUI />);

    expect(await screen.findByText("ماء")).toBeTruthy();
    expect(screen.getByText("/maːʔ/")).toBeTruthy();
    expect(screen.getByText("آب")).toBeTruthy();
    expect(screen.getByText("/ɒːb/")).toBeTruthy();
    expect(screen.queryByText("رماد")).toBeNull();
  });

  it("shows real Arabic + Persian similarity scores from enrichment .ar/.fa fields and renders em-dash when missing", async () => {
    // Regression for a typo where persianSim was reading speakerSimilarity.tr
    // (Turkish) instead of .fa (Farsi/Persian). The backend writes under the
    // primary contact-language code -- which is "fa" for Persian -- so the
    // UI column was always 0.00 regardless of compute state.
    // Also covers the missing-score path: a speaker with no similarity entry
    // should render "—" so "not yet computed" reads differently from "0.00".
    // The column set is driven by the CLEF primary_contact_languages config
    // now, so this test seeds ar + fa explicitly.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kzn03"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
      Kzn03: makeRecord("Kzn03", [
        { conceptText: "water", ipa: "awa", ortho: "ئاوا", start: 1, end: 2 },
      ]),
    };
    mockEnrichmentData = {
      similarity: {
        "1": {
          Fail01: {
            ar: { score: 0.42, has_reference_data: true },
            fa: { score: 0.81, has_reference_data: true },
          },
          // Kzn03 intentionally absent -- should render "—".
        },
      },
    };

    render(<ParseUI />);

    // Sanity: both speaker rows are in the DOM. SpeakerFormsTable expands
    // the first row by default, so `/aw/` appears in both the row IPA cell
    // and the variant card inside the expansion — use findAllByText.
    expect((await screen.findAllByText("/aw/")).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("/awa/")).toBeTruthy();
    // CLEF config loads async; wait for the dynamic headers to mount.
    await waitFor(() => expect(screen.getByTestId("sim-col-header-ar")).toBeTruthy());
    expect(screen.getByTestId("sim-col-header-fa")).toBeTruthy();
    // Fail01 row carries real values for both columns.
    expect(screen.getByText("0.42")).toBeTruthy();
    expect(screen.getByText("0.81")).toBeTruthy();
    // No row should display the silent-fallback "0.00".
    expect(screen.queryByText("0.00")).toBeNull();
    // Kzn03 row has no similarity entry -- both columns fall back to "—".
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("opens a Speaker Forms variant in Annotate and restores its expanded compare row on return", async () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    configureBigCompareWorkspace();
    const bundlePayload = makeBeShapedBigCompareBundles();
    bundlePayload.bundles[0].candidates.Fail01["53"] = {
      csv_row_id: "53",
      ipa: "gawra",
      ortho: "big",
      start_sec: 1524.743,
      end_sec: 1525.584,
      realization_index: 0,
    };
    mockGetCompareBundles.mockResolvedValue(bundlePayload);

    render(<ParseUI />);

    expect(await screen.findByTestId("speaker-forms-table")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("variant-open-annotate-Fail01-53"));

    await waitFor(() => expect(window.localStorage.getItem("parse.currentMode")).toBe("annotate"));
    const playbackState = usePlaybackStore.getState() as {
      activeSpeaker: string | null;
      pendingSeek: { targetSec: number; nonce: number } | null;
    };
    expect(playbackState.activeSpeaker).toBe("Fail01");
    expect(playbackState.pendingSeek?.targetSec).toBe(1524.743);
    expect(useCompareReturnStore.getState().snapshot).toMatchObject({
      conceptId: 1,
      conceptKey: "53",
      expandedSpeaker: "Fail01",
    });

    await switchToCompareMode();

    await waitFor(() => expect(useCompareReturnStore.getState().snapshot).toBeNull());
    expect(await screen.findByTestId("speaker-expanded-Fail01")).toBeTruthy();
  });

  it("renders dynamic similarity columns based on CLEF primary_contact_languages (not hardcoded Arabic/Persian)", async () => {
    // Success criterion for the dynamic-primary-langs PR: when the user
    // configures English + Spanish (or any other set), the Speaker forms
    // table must render those as the similarity columns instead of the
    // built-in Arabic + Persian pair. The column data binding is driven
    // by the same primaryContactCodes list that the Reference Forms
    // cards iterate over, so there is a single source of truth for the
    // configured languages.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["eng", "spa"],
      languages: [
        { code: "eng", name: "English" },
        { code: "spa", name: "Spanish" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    mockEnrichmentData = {
      similarity: {
        "1": {
          Fail01: {
            eng: { score: 0.37, has_reference_data: true },
            spa: { score: 0.55, has_reference_data: true },
          },
        },
      },
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("sim-col-header-eng")).toBeTruthy());
    expect(screen.getByTestId("sim-col-header-eng").textContent ?? "").toMatch(/english sim\./i);
    expect(screen.getByTestId("sim-col-header-spa").textContent ?? "").toMatch(/spanish sim\./i);
    // Old hardcoded labels are gone -- regression guard so no one
    // accidentally reverts the headers.
    expect(screen.queryByTestId("sim-col-header-ar")).toBeNull();
    expect(screen.queryByTestId("sim-col-header-fa")).toBeNull();
    // Scores render under the new column codes via the dynamic cell testid.
    expect(screen.getByTestId("sim-cell-Fail01-eng").textContent ?? "").toContain("0.37");
    expect(screen.getByTestId("sim-cell-Fail01-spa").textContent ?? "").toContain("0.55");
  });

  it.skip("renders compare speaker forms from annotation data instead of MOCK_FORMS placeholders", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kzn03"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاو", start: 3, end: 4 },
      ]),
      Kzn03: makeRecord("Kzn03", [
        { conceptText: "water", ipa: "awa", ortho: "ئاوا", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    expect(screen.getByText("/aw/")).toBeTruthy();
    expect(screen.getByText("/awa/")).toBeTruthy();
    expect(screen.getByTestId("realization-pill-Fail01-A")).toBeTruthy();
    expect(screen.getByTestId("realization-pill-Fail01-B")).toBeTruthy();
    expect(screen.getByText("1 utterance")).toBeTruthy();
    expect(screen.queryByTestId("realization-pill-Kzn03-A")).toBeNull();
    expect(screen.queryByText("/ramaːd/")).toBeNull();
  });

  it.skip("renders source-item variant pickers with imported A/B labels and persists overrides by source_item", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kalh01"],
      concepts: [
        { id: "concept-a", label: "brother of husband A", source_item: "2.15", source_survey: "KLQ" },
        { id: "concept-b", label: "brother of husband B", source_item: "2.15", source_survey: "KLQ" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "brother of husband A", conceptId: "concept-a", ipa: "bra-a", ortho: "برا ئا", start: 1, end: 2 },
        { conceptText: "brother of husband B", conceptId: "concept-b", ipa: "bra-b", ortho: "برا ب", start: 3, end: 4 },
      ]),
      Kalh01: makeRecord("Kalh01", [
        { conceptText: "brother of husband A", conceptId: "concept-a", ipa: "kalh-a", ortho: "کەڵ ئا", start: 1, end: 2 },
        { conceptText: "brother of husband B", conceptId: "concept-b", ipa: "kalh-b", ortho: "کەڵ ب", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    expect(screen.getByTestId("realization-pill-Fail01-A")).toBeTruthy();
    expect(screen.getByTestId("realization-pill-Fail01-B")).toBeTruthy();
    expect(screen.getByTestId("realization-pill-Kalh01-A")).toBeTruthy();
    expect(screen.getByTestId("realization-pill-Kalh01-B")).toBeTruthy();

    fireEvent.click(screen.getByTestId("lexeme-chevron-Fail01"));
    const detailRow = screen.getByTestId("lexeme-detail-row-Fail01");
    expect(within(detailRow).getByText(/Realizations · pick one as canonical for BEAST2 export/i)).toBeTruthy();
    expect(within(detailRow).queryByText(/Auto-detected realizations/i)).toBeNull();
    expect(within(detailRow).queryByRole("button", { name: /Dismiss auto-detection/i })).toBeNull();

    fireEvent.click(screen.getByTestId("realization-pill-Fail01-B"));
    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { canonical_realizations: { "2.15": { Fail01: 1 } } },
    });
  });

  it.skip("saves canonical realization overrides from compare pills without expanding the row", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاوی", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("realization-pill-Fail01-B"));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { canonical_realizations: { "1": { Fail01: 1 } } },
    });
    expect(screen.queryByTestId("lexeme-detail-row-Fail01")).toBeNull();
  });


  it.skip("preserves existing manual_overrides when saving a canonical realization through enrichment deep merge", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاوی", start: 3, end: 4 },
      ]),
    };
    mockEnrichmentData = {
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        canonical_realizations: { "2.15": { Fail01: 0 } },
        auto_detect_dismissed: { "2": { Fail01: true } },
      },
    };

    mockEnrichmentSaveUsesDeepMerge = true;

    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("realization-pill-Fail01-B"));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        canonical_realizations: { "2.15": { Fail01: 0 }, "1": { Fail01: 1 } },
        auto_detect_dismissed: { "2": { Fail01: true } },
      },
    });
  });

  it.skip("renders the expanded realization picker above lexeme detail", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاوی", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("lexeme-chevron-Fail01"));

    const detailRow = screen.getByTestId("lexeme-detail-row-Fail01");
    expect(within(detailRow).getByText(/Auto-detected realizations · pick one as canonical, or/i)).toBeTruthy();
    expect(within(detailRow).getByRole("button", { name: /Dismiss auto-detection/i })).toBeTruthy();
    const realizationA = within(detailRow).getByTestId("realization-row-Fail01-A");
    expect(realizationA.textContent ?? "").toContain("/aw/");
    expect(realizationA.textContent ?? "").toContain('"ئاو"');
    expect(realizationA.textContent ?? "").toContain("0:01.0–0:02.0");
    expect(within(detailRow).getByTestId("realization-play-Fail01-A")).toBeTruthy();
    expect((within(detailRow).getByLabelText("Canonical") as HTMLInputElement).checked).toBe(true);
    expect((within(detailRow).getByLabelText("Set canonical") as HTMLInputElement).checked).toBe(false);
  });

  it.skip("dismisses per-IPA auto-detection and re-renders the row as utterance count text", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاوی", start: 3, end: 4 },
      ]),
    };
    mockEnrichmentSaveUsesDeepMerge = true;

    const { rerender } = render(<ParseUI />);

    fireEvent.click(screen.getByTestId("lexeme-chevron-Fail01"));
    fireEvent.click(screen.getByRole("button", { name: /Dismiss auto-detection/i }));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { auto_detect_dismissed: { "1": { Fail01: true } } },
    });

    rerender(<ParseUI />);

    expect(screen.queryByTestId("realization-pill-Fail01-A")).toBeNull();
    expect(screen.queryByTestId("realization-pill-Fail01-B")).toBeNull();
    expect(screen.getByText("2 utterances")).toBeTruthy();
  });

  it.skip("marks the canonical realization pill with filled indigo styling", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاوی", start: 3, end: 4 },
      ]),
    };
    mockEnrichmentData = {
      manual_overrides: { canonical_realizations: { "1": { Fail01: 1 } } },
    };

    render(<ParseUI />);

    expect(screen.getByTestId("realization-pill-Fail01-B").className).toContain("bg-indigo-600");
    expect(screen.getByTestId("realization-pill-Fail01-A").className).toContain("ring-slate-200");
    expect(screen.getByText("/aːw/")).toBeTruthy();
  });


  it("renders the Compare bundle table and saves a canonical lexeme through the new endpoint", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", conceptId: "1", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    const bundle = {
      bundle_id: "1",
      label: "water",
      row_ids: ["1"],
      buckets: [{
        bucket_key: "klq\u00001.1",
        survey_id: "klq",
        source_item: "1.1",
        variants: [{ csv_row_id: "1", concept_en: "water", variant_label: "A" }],
      }],
      candidates: { Fail01: { "1": { csv_row_id: "1", ipa: "aw", ortho: "ئاو", start_sec: 1, end_sec: 2, realization_index: 0 } } },
      canonical: { Fail01: null },
    };
    mockGetCompareBundles.mockResolvedValue({ bundles: [bundle] });
    vi.mocked(apiClient.putCanonicalLexeme).mockResolvedValue({
      bundle: {
        ...bundle,
        canonical: { Fail01: { csv_row_id: "1", survey_id: "klq", source_item: "1.1", bucket_key: "klq\u00001.1", source: "manual", selected_at: "" } },
      },
    });

    render(<ParseUI />);

    // SpeakerFormsTable expands the first speaker by default — the canonical
    // radio is rendered inline inside the row's expansion panel and saves
    // immediately on click (no Save button).
    expect(await screen.findByTestId("speaker-forms-table")).toBeTruthy();
    const radioLabel = await screen.findByTestId("canonical-option-Fail01-1");
    const radio = radioLabel.querySelector("input") as HTMLInputElement;
    // Clicking the radio promotes an auto default:single-candidate selection
    // to manual. The radio's onClick handler covers the already-checked case
    // where React would otherwise skip onChange.
    fireEvent.click(radio);

    await waitFor(() => expect(apiClient.putCanonicalLexeme).toHaveBeenCalledWith("1", "Fail01", { csv_row_id: "1", realization_index: 0 }));
    expect(mockPatchCanonicalLexeme).toHaveBeenCalledWith("1", "Fail01", expect.objectContaining({ csv_row_id: "1", source: "manual" }));
  });

  it("fetches all Compare bundles and matches BE-shaped bundle ids by row id", async () => {
    configureBigCompareWorkspace();
    mockGetCompareBundles.mockImplementation((query?: { bundleId?: string }) => {
      if (query?.bundleId && query.bundleId !== "bundle:big") return Promise.resolve({ bundles: [] });
      return Promise.resolve(makeBeShapedBigCompareBundles());
    });

    render(<ParseUI />);

    // SpeakerFormsTable renders by speaker (not by bucket); the table testid
    // is enough to confirm the bundle resolved.
    expect(await screen.findByTestId("speaker-forms-table")).toBeTruthy();
    expect(mockGetCompareBundles).toHaveBeenCalledWith({});
  });

  it("loads Compare bundles once when entering Compare mode and reuses them on concept switches", async () => {
    configureBigCompareWorkspace();
    mockGetCompareBundles.mockResolvedValue(makeBeShapedBigCompareBundles());

    render(<ParseUI />);

    expect(await screen.findByTestId("speaker-forms-table")).toBeTruthy();
    expect(mockGetCompareBundles).toHaveBeenCalledTimes(1);

    fireEvent.click(within(screen.getByTestId("concept-sidebar")).getByRole("button", { name: /small/i }));

    await screen.findByTestId("compare-bundle-no-match");
    expect(mockGetCompareBundles).toHaveBeenCalledTimes(1);
  });

  it("surfaces Compare bundle errors while rendering the fallback bundle for unreachable BE", async () => {
    configureBigCompareWorkspace();
    mockGetCompareBundles.mockRejectedValue(new Error("network down"));

    render(<ParseUI />);

    const error = await screen.findByTestId("compare-bundle-error");
    expect(error.textContent).toContain("network down");
    expect(await screen.findByTestId("speaker-forms-table")).toBeTruthy();
  });

  it("renders a no-match empty state instead of a fallback when BE returns nonmatching bundles", async () => {
    configureBigCompareWorkspace();
    mockGetCompareBundles.mockResolvedValue(makeUnmatchedCompareBundles());

    render(<ParseUI />);

    expect(await screen.findByTestId("compare-bundle-no-match")).toBeTruthy();
    expect(screen.queryByTestId("speaker-forms-table")).toBeNull();
    expect(screen.queryByTestId("compare-bundle-error")).toBeNull();
  });

  const configureHeadMergeWorkspace = () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "247", label: "head (A)" },
        { id: "248", label: "head (B)" },
        { id: "527", label: "head" },
        { id: "600", label: "water" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head (A)", conceptId: "247", ipa: "sær-a", start: 1, end: 2 },
        { conceptText: "head (B)", conceptId: "248", ipa: "sær-b", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "sar", start: 5, end: 6 },
      ]),
    };
    mockEnrichmentData = { manual_overrides: { concept_merges: { "527": ["247", "248"] } } };
  };

  it("keeps saved concept merges out of the annotate sidebar so raw concept ids stay navigable", async () => {
    configureHeadMergeWorkspace();

    render(<ParseUI />);
    await switchToAnnotateMode();

    const sidebar = screen.getByTestId("concept-sidebar");
    const breadcrumb = within(sidebar).getByTestId("concept-scope-breadcrumb");
    expect(breadcrumb.textContent).toContain("3 in Fail01");
    expect(within(sidebar).getByRole("button", { name: /head \(A\).*#1/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /head \(B\).*#2/i })).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /head.*#3/i })).toBeTruthy();
    expect(within(sidebar).queryByText("+2")).toBeNull();
  });

  it("applies saved concept merges in compare mode only", () => {
    configureHeadMergeWorkspace();

    render(<ParseUI />);

    const sidebar = screen.getByTestId("concept-sidebar");
    expect(within(sidebar).getByText("2 concepts")).toBeTruthy();
    expect(within(sidebar).getByRole("button", { name: /head \+2 #1/i })).toBeTruthy();
    expect(within(sidebar).getByText("+2").getAttribute("title")).toContain("head (A)");
    expect(within(sidebar).queryByRole("button", { name: /head \(A\)/i })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /head \(B\)/i })).toBeNull();
  });

  it("maps an annotate raw absorbed concept to its merged primary when switching to compare", async () => {
    configureHeadMergeWorkspace();

    render(<ParseUI />);
    await switchToAnnotateMode();

    let sidebar = screen.getByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /head \(B\).*#2/i }));
    await switchToCompareMode();

    await waitFor(() => {
      sidebar = screen.getByTestId("concept-sidebar");
      expect(within(sidebar).getByRole("button", { name: /head \+2 #1/i }).className).toContain("bg-indigo-50");
    });
  });

  it("maps a compare merged primary to the primary raw concept when switching to annotate", async () => {
    configureHeadMergeWorkspace();

    render(<ParseUI />);
    await switchToAnnotateMode();

    await waitFor(() => {
      const sidebar = screen.getByTestId("concept-sidebar");
      expect(within(sidebar).getByRole("button", { name: /head.*#3/i }).className).toContain("bg-indigo-50");
    });
  });

  it("preserves the active concept id across mode switches when no concept merges are active", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
        { id: "3", label: "earth" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", [{ conceptText: "fire", conceptId: "2", ipa: "agir", start: 1, end: 2 }]) };

    render(<ParseUI />);

    let sidebar = screen.getByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /fire #2/i }));
    await switchToAnnotateMode();

    await waitFor(() => {
      sidebar = screen.getByTestId("concept-sidebar");
      expect(within(sidebar).getByRole("button", { name: /fire #2/i }).className).toContain("bg-indigo-50");
    });

    await switchToCompareMode();
    await waitFor(() => {
      sidebar = screen.getByTestId("concept-sidebar");
      expect(within(sidebar).getByRole("button", { name: /fire #2/i }).className).toContain("bg-indigo-50");
    });
  });

  it("opens the concept merge picker from the sidebar context menu with stem matches preselected", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "247", label: "head (A)" },
        { id: "248", label: "head (B)" },
        { id: "527", label: "head" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", [{ conceptText: "head", conceptId: "527", ipa: "sar", start: 1, end: 2 }]) };

    render(<ParseUI />);

    fireEvent.contextMenu(screen.getByRole("button", { name: /head #3/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /merge with/i }));

    expect(screen.getByRole("dialog", { name: /merge into head/i })).toBeTruthy();
    expect((screen.getAllByLabelText(/head \(A\)/i)[0] as HTMLInputElement).checked).toBe(true);
    expect((screen.getAllByLabelText(/head \(B\)/i)[0] as HTMLInputElement).checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /merge 2 concepts/i }));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { concept_merges: { "527": ["247", "248"] } },
    });
  });

  it("collapses merged concepts in the sidebar and shows an absorbed-count badge", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "247", label: "head (A)" },
        { id: "248", label: "head (B)" },
        { id: "527", label: "head" },
        { id: "600", label: "water" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", [{ conceptText: "head", conceptId: "527", ipa: "sar", start: 1, end: 2 }]) };
    mockEnrichmentData = { manual_overrides: { concept_merges: { "527": ["247", "248"] } } };

    render(<ParseUI />);

    expect(screen.getByText("2 concepts")).toBeTruthy();
    expect(screen.getByText("+2").getAttribute("title")).toContain("head (A)");
    expect(screen.queryByRole("button", { name: /head \(A\)/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /head \(B\)/i })).toBeNull();
  });

  it("unmerges a merged primary from the sidebar context menu", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "247", label: "head (A)" },
        { id: "248", label: "head (B)" },
        { id: "527", label: "head" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", [{ conceptText: "head", conceptId: "527", ipa: "sar", start: 1, end: 2 }]) };
    mockEnrichmentData = { manual_overrides: { concept_merges: { "527": ["247", "248"] } } };

    render(<ParseUI />);

    fireEvent.contextMenu(screen.getByRole("button", { name: /head \+2 #1/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /unmerge/i }));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { concept_merges: { "527": [] } },
    });
  });

  it("preserves sibling manual_overrides when saving concept merge overrides through deep merge", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "247", label: "head (A)" },
        { id: "248", label: "head (B)" },
        { id: "527", label: "head" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", [{ conceptText: "head", conceptId: "527", ipa: "sar", start: 1, end: 2 }]) };
    mockEnrichmentData = {
      manual_overrides: {
        cognate_sets: { "527": { A: ["Fail01"] } },
        speaker_flags: { "527": { Fail01: true } },
        canonical_realizations: { "527": { Fail01: 0 } },
        auto_detect_dismissed: { "527": { Fail01: true } },
      },
    };
    mockEnrichmentSaveUsesDeepMerge = true;

    render(<ParseUI />);

    fireEvent.contextMenu(screen.getByRole("button", { name: /head #3/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /merge with/i }));
    fireEvent.click(screen.getByRole("button", { name: /merge 2 concepts/i }));

    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: {
        cognate_sets: { "527": { A: ["Fail01"] } },
        speaker_flags: { "527": { Fail01: true } },
        canonical_realizations: { "527": { Fail01: 0 } },
        auto_detect_dismissed: { "527": { Fail01: true } },
        concept_merges: { "527": ["247", "248"] },
      },
    });
  });

  it("wires compare Flag and Accept concept buttons to tag actions", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: /^Flag$/i }));
    fireEvent.click(screen.getByRole("button", { name: /Accept concept/i }));

    expect(mockSetConceptTag).toHaveBeenCalledWith("Fail01", "1", "problematic");
    expect(mockSetConceptTag).toHaveBeenCalledWith("Kalh01", "1", "problematic");
    expect(mockSetConceptTag).toHaveBeenCalledWith("Fail01", "1", "confirmed");
    expect(mockSetConceptTag).toHaveBeenCalledWith("Kalh01", "1", "confirmed");
  });

  it("toggles compare Flag and Accept concept off when the tag is already set (MC-449-B)", () => {
    mockRecords = {
      Fail01: { ...makeRecord("Fail01", []), concept_tags: { "1": ["problematic", "confirmed"] } },
      Kalh01: { ...makeRecord("Kalh01", []), concept_tags: { "1": ["problematic", "confirmed"] } },
    };
    mockEnrichmentData = {
      manual_overrides: { speaker_flags: { "1": { Fail01: true } } },
    };

    render(<ParseUI />);

    // Regression (MC-449-B): an already flagged/accepted concept must be
    // reversible from the compare header. Previously the onClick was a no-op
    // when the tag was set, so the buttons could only ever turn ON.
    fireEvent.click(screen.getByRole("button", { name: /^Flag$/i }));
    fireEvent.click(screen.getByRole("button", { name: /Accept concept/i }));

    expect(mockClearConceptTag).toHaveBeenCalledWith("Fail01", "1", "problematic");
    expect(mockClearConceptTag).toHaveBeenCalledWith("Kalh01", "1", "problematic");
    expect(mockClearConceptTag).toHaveBeenCalledWith("Fail01", "1", "confirmed");
    expect(mockClearConceptTag).toHaveBeenCalledWith("Kalh01", "1", "confirmed");
    // Must not re-set the very tag it was asked to clear.
    expect(mockSetConceptTag).not.toHaveBeenCalledWith("Fail01", "1", "problematic");
    expect(mockSetConceptTag).not.toHaveBeenCalledWith("Fail01", "1", "confirmed");
    // Hybrid flag model: clearing the concept flag must not clear per-speaker flags.
    expect(mockSaveEnrichments).not.toHaveBeenCalledWith({
      manual_overrides: { speaker_flags: { "1": { Fail01: false } } },
    });
  });

  it("Flagged sidebar filter and marker include speaker flags without replacing confirmed status", async () => {
    mockRecords = {
      Fail01: { ...makeRecord("Fail01", []), concept_tags: { "1": ["confirmed"] } },
    };
    mockEnrichmentData = {
      manual_overrides: { speaker_flags: { "1": { Fail01: true } } },
    };

    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("tagfilter-flagged"));

    expect(await screen.findByRole("button", { name: /water/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /fire/i })).toBeNull();
    expect(screen.getByTestId("concept-status-dot-1").className).toContain("bg-emerald-500");
    expect(screen.getByTestId("concept-flag-rollup-1").getAttribute("class")).toContain("text-rose-500");
  });

  it("compare table row flag button targets a single speaker via enrichment overrides", async () => {
    render(<ParseUI />);

    fireEvent.click(await screen.findByTestId("speaker-flag-Fail01"));
    expect(mockClearConceptTag).not.toHaveBeenCalled();
    expect(mockSetConceptTag).not.toHaveBeenCalledWith("Fail01", "1", "problematic");
    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { speaker_flags: { "1": { Fail01: true } } },
    });
  });



  it("compare grouped cognate and flag round-trip use the selected variant numeric key", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "1", label: "hair (A)", source_item: "1.1", source_survey: "klq" },
        { id: "599", label: "hair (B)", source_item: "1.1", source_survey: "klq" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "hair (A)", conceptId: "1", ipa: "mu-a", ortho: "مو ئا", start: 1, end: 2 },
        { conceptText: "hair (B)", conceptId: "599", ipa: "mu-b", ortho: "مو ب", start: 3, end: 4 },
      ]),
    };
    mockGetCompareBundles.mockResolvedValue({
      bundles: [{
        bundle_id: "bundle:hair",
        label: "hair",
        row_ids: ["1", "599"],
        buckets: [{
          bucket_key: "klq\u00001.1",
          survey_id: "klq",
          source_item: "1.1",
          variants: [
            { csv_row_id: "1", concept_en: "hair (A)", variant_label: "A" },
            { csv_row_id: "599", concept_en: "hair (B)", variant_label: "B" },
          ],
        }],
        candidates: {
          Fail01: {
            "1": { csv_row_id: "1", ipa: "mu-a", ortho: "مو ئا", start_sec: 1, end_sec: 2, realization_index: 0 },
            "599": { csv_row_id: "599", ipa: "mu-b", ortho: "مو ب", start_sec: 3, end_sec: 4, realization_index: 1 },
          },
        },
        canonical: { Fail01: null },
      }],
    });
    mockEnrichmentData = {
      cognate_sets: {
        "1.1": { Z: ["Fail01"] },
        "1": { A: ["Fail01"] },
      },
      manual_overrides: {
        speaker_flags: {
          "1.1": { Fail01: false },
          "1": { Fail01: true },
        },
      },
    };

    render(<ParseUI />);

    const cognateButton = await screen.findByTestId("cognate-cycle-Fail01");
    expect(cognateButton.textContent).toBe("A");

    fireEvent.click(cognateButton);
    expect(mockSaveEnrichments).toHaveBeenLastCalledWith({
      manual_overrides: { cognate_sets: { "1": { A: [], B: ["Fail01"] } } },
    });
    const lastSaveCall = mockSaveEnrichments.mock.calls[mockSaveEnrichments.mock.calls.length - 1];
    expect(JSON.stringify(lastSaveCall?.[0] ?? {})).not.toContain('"1.1"');

    mockSaveEnrichments.mockClear();
    fireEvent.click(screen.getByTestId("speaker-flag-Fail01"));
    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { speaker_flags: { "1": { Fail01: false } } },
    });
  });

  it("uses one shared decisions import input for the right rail and Actions menu", () => {
    render(<ParseUI />);

    const inputs = Array.from(document.querySelectorAll('input[type="file"][accept=".json"]'));
    expect(inputs).toHaveLength(1);

    const sharedInput = inputs[0] as HTMLInputElement;
    const clickSpy = vi.spyOn(sharedInput, "click");

    fireEvent.click(screen.getByRole("button", { name: "Load decisions" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Load Decisions" }));
    expect(clickSpy).toHaveBeenCalledTimes(2);

    clickSpy.mockRestore();
  });

  it("exports the canonical decisions payload from the Actions menu", async () => {
    mockEnrichmentData = {
      reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        borrowing_flags: { "1": { Fail01: { decision: "borrowed", sourceLang: "ar" } } },
      },
      cognate_decisions: { "1": { decision: "split", ts: 123 } },
    };
    const capture = installBlobDownloadCapture();

    try {
      render(<ParseUI />);

      fireEvent.click(screen.getByRole("button", { name: "Actions" }));
      fireEvent.click(screen.getByRole("button", { name: "Save Decisions" }));

      expect(capture.createObjectURL).toHaveBeenCalledTimes(1);
      expect(capture.anchorClick).toHaveBeenCalledTimes(1);
      expect(capture.blobs).toHaveLength(1);

      const parsed = JSON.parse(await readBlobText(capture.blobs[0]));
      expect(parsed).toEqual({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "1": { decision: "split", ts: 123 } },
          cognate_sets: { "1": { A: ["Fail01"] } },
          speaker_flags: { "1": { Fail01: true } },
          borrowing_flags: { "1": { Fail01: { decision: "borrowed", sourceLang: "ar" } } },
        },
      });
      expect(parsed).not.toHaveProperty("reference_forms");
    } finally {
      capture.restore();
    }
  });

  it("exports the canonical decisions payload from the right-rail decisions panel", async () => {
    mockEnrichmentData = {
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        borrowing_flags: { "1": { Fail01: { decision: "uncertain", sourceLang: null } } },
        cognate_decisions: { "1": { decision: "merge", ts: 456 } },
      },
      notes: { "1": "not part of canonical decisions payload" },
    };
    const capture = installBlobDownloadCapture();

    try {
      render(<ParseUI />);

      fireEvent.click(screen.getByRole("button", { name: "Save decisions" }));

      expect(capture.createObjectURL).toHaveBeenCalledTimes(1);
      expect(capture.anchorClick).toHaveBeenCalledTimes(1);
      expect(capture.blobs).toHaveLength(1);

      const parsed = JSON.parse(await readBlobText(capture.blobs[0]));
      expect(parsed).toEqual({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "1": { decision: "merge", ts: 456 } },
          cognate_sets: { "1": { A: ["Fail01"] } },
          speaker_flags: { "1": { Fail01: true } },
          borrowing_flags: { "1": { Fail01: { decision: "uncertain", sourceLang: null } } },
        },
      });
      expect(parsed).not.toHaveProperty("notes");
    } finally {
      capture.restore();
    }
  });

  it("imports the canonical decisions payload by replacing only decision categories in enrichments", async () => {
    mockEnrichmentData = {
      reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
      manual_overrides: { reviewer_state: { owner: "parse-builder" } },
      cognate_decisions: { "1": { decision: "accepted", ts: 111 } },
    };

    render(<ParseUI />);

    const inputs = Array.from(document.querySelectorAll('input[type="file"][accept=".json"]'));
    expect(inputs).toHaveLength(1);

    const importFile = new File(
      [JSON.stringify({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "2": { decision: "merge", ts: 222 } },
          cognate_sets: { "2": { B: ["Kalh01"] } },
          speaker_flags: { "2": { Kalh01: false } },
          borrowing_flags: { "2": { Kalh01: { decision: "borrowed", sourceLang: "fa" } } },
        },
      })],
      "parse-decisions.json",
      { type: "application/json" },
    );

    const sharedInput = inputs[0] as HTMLInputElement;
    Object.defineProperty(sharedInput, 'files', {
      configurable: true,
      value: [importFile],
    });
    fireEvent.change(sharedInput);

    await waitFor(() => {
      expect(mockReplaceEnrichments).toHaveBeenCalledWith({
        reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
        manual_overrides: {
          reviewer_state: { owner: "parse-builder" },
          cognate_decisions: { "2": { decision: "merge", ts: 222 } },
          cognate_sets: { "2": { B: ["Kalh01"] } },
          speaker_flags: { "2": { Kalh01: false } },
          borrowing_flags: { "2": { Kalh01: { decision: "borrowed", sourceLang: "fa" } } },
        },
      });
    });
  });

  it("opens the speaker import modal from the Actions menu", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Import Speaker Data…" }));

    expect(await screen.findByTestId("speaker-import")).toBeTruthy();
  });

  it("disables Refine Boundaries (BND) when the active speaker has no STT word timestamps", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const button = await screen.findByTestId("phonetic-refine-boundaries");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("title") ?? "").toMatch(/run stt first/i);
  });

  it("enables Refine Boundaries (BND) when the speaker's STT cache has word timestamps", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    useTranscriptionLanesStore.setState({
      sttBySpeaker: {
        Fail01: [
          {
            start: 1.0,
            end: 2.0,
            text: "ئاو",
            words: [{ word: "ئاو", start: 1.05, end: 1.85, prob: 0.92 }],
          },
        ],
      },
      sttStatus: { Fail01: "loaded" },
      sttSourceBySpeaker: {},
      selectedInterval: null,
    });

    render(<ParseUI />);
    await switchToAnnotateMode();

    const button = await screen.findByTestId("phonetic-refine-boundaries");
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(button.getAttribute("title") ?? "").toMatch(/run fast boundary refinement/i);
  });

  it("disables Re-run STT with Boundaries when the active speaker has no ortho_words intervals", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const button = await screen.findByTestId("phonetic-retranscribe-with-boundaries");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("title") ?? "").toMatch(/refine boundaries/i);
  });

  it("enables Re-run STT with Boundaries when the active speaker has ortho_words intervals", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    const base = makeRecord("Fail01", [
      { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
    ]);
    mockRecords = {
      Fail01: {
        ...base,
        tiers: {
          ...base.tiers,
          ortho_words: {
            name: "ortho_words",
            display_order: 4,
            intervals: [{ start: 1.1, end: 1.4, text: "ئاو" }],
          },
        },
      },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const button = await screen.findByTestId("phonetic-retranscribe-with-boundaries");
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(button.getAttribute("title") ?? "").toMatch(/respects your manual boundary corrections/i);
  });

  it("surfaces Refine Boundaries progress in the topbar chip instead of the Phonetic Tools button", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    useTranscriptionLanesStore.setState({
      sttBySpeaker: {
        Fail01: [
          {
            start: 1.0,
            end: 2.0,
            text: "ئاو",
            words: [{ word: "ئاو", start: 1.05, end: 1.85, prob: 0.92 }],
          },
        ],
      },
      sttStatus: { Fail01: "loaded" },
      sttSourceBySpeaker: {},
      selectedInterval: null,
    });

    render(<ParseUI />);
    await switchToAnnotateMode();

    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      { jobId: "boundaries-job-chip", type: "compute:boundaries", status: "running", progress: 0.2 },
    ]);

    const button = await screen.findByTestId("phonetic-refine-boundaries");
    fireEvent.click(button);
    window.dispatchEvent(new Event("parse:active-jobs-refresh"));

    const topbarStatus = await screen.findByTestId("topbar-job-strip");
    expect(await screen.findByTestId("topbar-job-strip-row-boundaries-job-chip")).toBeTruthy();
    expect(within(topbarStatus).getByText("Boundaries")).toBeTruthy();
    expect(within(topbarStatus).getByText("20%")).toBeTruthy();
    expect(button.textContent ?? "").not.toMatch(/\d+%/);
    expect(button.parentElement?.textContent ?? "").not.toMatch(/~\d.*left/);
  });

  it("surfaces Re-run STT with Boundaries progress in the topbar chip instead of the Phonetic Tools button", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    const base = makeRecord("Fail01", [
      { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
    ]);
    mockRecords = {
      Fail01: {
        ...base,
        tiers: {
          ...base.tiers,
          ortho_words: {
            name: "ortho_words",
            display_order: 4,
            intervals: [{ start: 1.1, end: 1.4, text: "ئاو" }],
          },
        },
      },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      { jobId: "bnd-stt-job-chip", type: "compute:retranscribe_with_boundaries", status: "running", progress: 0.3 },
    ]);

    const button = await screen.findByTestId("phonetic-retranscribe-with-boundaries");
    fireEvent.click(button);
    window.dispatchEvent(new Event("parse:active-jobs-refresh"));

    const topbarStatus = await screen.findByTestId("topbar-job-strip");
    expect(await screen.findByTestId("topbar-job-strip-row-bnd-stt-job-chip")).toBeTruthy();
    expect(within(topbarStatus).getByText("BND retranscribe")).toBeTruthy();
    expect(within(topbarStatus).getByText("30%")).toBeTruthy();
    expect(button.textContent ?? "").not.toMatch(/\d+%/);
    expect(button.parentElement?.textContent ?? "").not.toMatch(/~\d.*left/);
  });

  it("multi-select user tag filter narrows concepts by AND across selected tags", async () => {
    mockConfig = {
      ...mockConfig,
      concepts: [
        { id: "c1", label: "water" },
        { id: "c2", label: "fire" },
        { id: "c3", label: "stone" },
        { id: "c4", label: "wind" },
      ],
    } as ProjectConfig;
    mockTags = [
      { id: "t1", label: "Core", color: "#2563eb" },
      { id: "t2", label: "Fieldwork", color: "#16a34a" },
      { id: "t3", label: "Later", color: "#9333ea" },
    ];
    mockRecords = {
      Fail01: { ...makeRecord("Fail01", []), concept_tags: { c1: ["t1", "t2"], c2: ["t1"], c3: ["t2"], c4: ["t3"] } },
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /Core/i }));
    fireEvent.click(within(sidebar).getByRole("button", { name: /Fieldwork/i }));

    expect(within(sidebar).getByRole("button", { name: /water/i })).toBeTruthy();
    expect(within(sidebar).queryByRole("button", { name: /fire/i })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /stone/i })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /wind/i })).toBeNull();
  });

  it("supports renaming an existing tag in Tags mode", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    fireEvent.click(await screen.findByRole("button", { name: /Tags\s*T/i }));

    const reviewButtons = await screen.findAllByRole("button", { name: /Review needed/i });
    fireEvent.click(reviewButtons[0]);
    const editButtons = screen.getAllByRole("button", { name: /Edit tag/i });
    fireEvent.click(editButtons[0]);

    const renameInput = screen.getByDisplayValue("Review needed");
    fireEvent.change(renameInput, { target: { value: "Oxford core" } });
    fireEvent.click(screen.getByRole("button", { name: /Save tag/i }));

    expect(mockUpdateTag).toHaveBeenCalledWith("review-needed", { label: "Oxford core", color: "#f59e0b" });
  });

  it("renames the mode menu label to Tags", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByRole("button", { name: /Tags\s*T/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Manage Tags" })).toBeNull();
  });

  it("shows PARSE as the top-left title", () => {
    render(<ParseUI />);

    expect(screen.getByText("PARSE")).toBeTruthy();
    expect(screen.queryByText("PARSE Compare")).toBeNull();
  });

  it("shows inline arrow hotkeys on annotate prev/next buttons", async () => {
    render(<ParseUI />);
    await switchToAnnotateMode();

    expect(screen.getByRole("button", { name: /←\s*Prev/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Next\s*→/i })).toBeTruthy();
  });

  it("shows mode hotkeys inside the mode dropdown", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByRole("button", { name: /Annotate\s*A/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Compare\s*C/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Tags\s*T/i })).toBeTruthy();
  });

  it("supports app-mode hotkeys a/c/t", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", conceptId: "1", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    fireEvent.keyDown(window, { key: "a" });
    expect(await screen.findByRole("button", { name: /Mark Done/i })).toBeTruthy();

    fireEvent.keyDown(window, { key: "t" });
    expect(await screen.findByText("Linguistic tags")).toBeTruthy();

    fireEvent.keyDown(window, { key: "c" });
    expect(await screen.findByRole("button", { name: /Accept concept/i })).toBeTruthy();
  });


  it("Delete key on elicitation pill calls delete-interval handler with confirmation", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "early", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
      ]),
    };
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(await within(sidebar).findByTestId("concept-elicitation-pill-527-1"));
    fireEvent.keyDown(window, { key: "Delete" });

    expect(confirmSpy).toHaveBeenCalledWith('Delete this interval (B) for "head"? A backup file will be created.');
    await waitFor(() => expect(apiClient.deleteAnnotationInterval).toHaveBeenCalledWith({
      speaker: "Fail01",
      concept_id: "527",
      start: 10,
      end: 11,
    }));
  });

  it("Delete key on variant pill opens delete-variant confirmation and can delete", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "365", label: "new (A)", source_item: "154", source_survey: "JBIL" },
        { id: "618", label: "new (B)", source_item: "154", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(await within(sidebar).findByTestId("concept-variant-pill-618"));
    fireEvent.keyDown(window, { key: "Delete" });

    expect(screen.getByText("Delete new (B)?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("618"));
  });

  it("Delete key on pill-less concept row opens delete-variant confirmation and can delete", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    window.localStorage.setItem("parse.sidebar.scopedToSpeaker.annotate", "false");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "2", label: "hair" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = { Fail01: makeRecord("Fail01", []) };
    vi.mocked(apiClient.deleteConcept).mockResolvedValueOnce({ ok: true, deleted_id: "2" });

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(sidebar.querySelector<HTMLElement>('[data-realization-key="2:0"]') as HTMLElement);
    fireEvent.keyDown(window, { key: "Delete" });

    expect(screen.getByText("Delete hair?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(apiClient.deleteConcept).toHaveBeenCalledWith("2"));
  });

  it("Delete key inside focused IPA input does nothing", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "early", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
      ]),
    };
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(await within(sidebar).findByTestId("concept-elicitation-pill-527-1"));
    const ipaInput = await screen.findByPlaceholderText("Enter IPA…");
    fireEvent.focus(ipaInput);
    fireEvent.keyDown(ipaInput, { key: "Delete" });

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(apiClient.deleteAnnotationInterval).not.toHaveBeenCalled();
    expect(apiClient.deleteConcept).not.toHaveBeenCalled();
  });

  it("Delete key with no selection does nothing", async () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "early", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
      ]),
    };
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ParseUI />);
    await screen.findByTestId("concept-sidebar");
    fireEvent.keyDown(window, { key: "Delete" });

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(apiClient.deleteAnnotationInterval).not.toHaveBeenCalled();
    expect(apiClient.deleteConcept).not.toHaveBeenCalled();
  });

  it("Delete key with user cancel leaves data intact", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "early", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
      ]),
    };
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(await within(sidebar).findByTestId("concept-elicitation-pill-527-1"));
    fireEvent.keyDown(window, { key: "Delete" });

    expect(confirmSpy).toHaveBeenCalledWith('Delete this interval (B) for "head"? A backup file will be created.');
    expect(apiClient.deleteAnnotationInterval).not.toHaveBeenCalled();
    expect(apiClient.deleteConcept).not.toHaveBeenCalled();
  });

  it("uses all arrow keys to cycle sidebar realization pills in DOM order regardless of focused element", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    window.localStorage.setItem("parse.sidebar.scopedToSpeaker.annotate", "false");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "concept-a", label: "brother of husband A", source_item: "2.15", source_survey: "KLQ", custom_order: 1 },
        { id: "concept-b", label: "brother of husband B", source_item: "2.15", source_survey: "KLQ", custom_order: 2 },
        { id: "middle-empty", label: "empty concept", source_item: "9", source_survey: "JBIL", custom_order: 3 },
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL", custom_order: 4 },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "brother of husband", conceptId: "concept-a", ipa: "ba", start: 1, end: 2 },
        { conceptText: "brother of husband", conceptId: "concept-b", ipa: "bb", start: 3, end: 4 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
        { conceptText: "head", conceptId: "527", ipa: "early", start: 5, end: 6 },
      ]),
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    const chips = Array.from(sidebar.querySelectorAll<HTMLElement>("[data-realization-key]"));
    expect(chips.map((chip) => chip.getAttribute("data-realization-key"))).toEqual([
      "concept-a:0",
      "concept-b:0",
      "middle-empty:0",
      "527:0",
      "527:1",
    ]);

    const activeKey = () => Array.from(sidebar.querySelectorAll<HTMLElement>("[data-realization-key]"))
      .find((chip) => chip.className.includes("bg-indigo-50"))
      ?.getAttribute("data-realization-key");

    fireEvent.click(screen.getByTestId("concept-variant-pill-concept-a"));
    expect(activeKey()).toBe("concept-a:0");

    const ipaInput = await screen.findByPlaceholderText("Enter IPA…");
    fireEvent.focus(ipaInput);
    fireEvent.keyDown(ipaInput, { key: "ArrowRight" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowLeft" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("concept-b:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("middle-empty:0"));
    expect(screen.getByRole("heading", { name: "empty concept" })).toBeTruthy();

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("527:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("527:1"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("527:1"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowUp" });
    await waitFor(() => expect(activeKey()).toBe("527:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowUp" });
    await waitFor(() => expect(activeKey()).toBe("middle-empty:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowUp" });
    await waitFor(() => expect(activeKey()).toBe("concept-b:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowUp" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));

    fireEvent.focus(screen.getByPlaceholderText("Enter IPA…"));
    fireEvent.keyDown(screen.getByPlaceholderText("Enter IPA…"), { key: "ArrowUp" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));
  });


  it("uses ArrowDown to cycle Annotate realization pills even when only one concept is navigable", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    window.localStorage.setItem("parse.sidebar.scopedToSpeaker.annotate", "false");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "527", label: "head", source_item: "10", source_survey: "JBIL", custom_order: 1 },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "head", conceptId: "527", ipa: "early", start: 5, end: 6 },
        { conceptText: "head", conceptId: "527", ipa: "late", start: 10, end: 11 },
      ]),
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    const chips = Array.from(sidebar.querySelectorAll<HTMLElement>("[data-realization-key]"));
    expect(chips.map((chip) => chip.getAttribute("data-realization-key"))).toEqual(["527:0", "527:1"]);
    const activeKey = () => Array.from(sidebar.querySelectorAll<HTMLElement>("[data-realization-key]"))
      .find((chip) => chip.className.includes("bg-indigo-50"))
      ?.getAttribute("data-realization-key");

    fireEvent.click(screen.getByTestId("concept-elicitation-pill-527-0"));
    expect(activeKey()).toBe("527:0");

    const ipaInput = await screen.findByPlaceholderText("Enter IPA…");
    fireEvent.focus(ipaInput);
    fireEvent.keyDown(ipaInput, { key: "ArrowDown" });

    await waitFor(() => expect(activeKey()).toBe("527:1"));
  });

  it("horizontal arrows preserve caret in IPA/ORTH inputs but still navigate from button focus", async () => {
    window.localStorage.setItem("parse.currentMode", "annotate");
    window.localStorage.setItem("parse.sidebar.scopedToSpeaker.annotate", "false");
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [
        { id: "concept-a", label: "brother of husband A", source_item: "2.15", source_survey: "KLQ", custom_order: 1 },
        { id: "concept-b", label: "brother of husband B", source_item: "2.15", source_survey: "KLQ", custom_order: 2 },
        { id: "middle-empty", label: "empty concept", source_item: "9", source_survey: "JBIL", custom_order: 3 },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "brother of husband", conceptId: "concept-a", ipa: "ba", ortho: "با", start: 1, end: 2 },
        { conceptText: "brother of husband", conceptId: "concept-b", ipa: "bb", ortho: "بب", start: 3, end: 4 },
      ]),
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    const activeKey = () => Array.from(sidebar.querySelectorAll<HTMLElement>("[data-realization-key]"))
      .find((chip) => chip.className.includes("bg-indigo-50"))
      ?.getAttribute("data-realization-key");

    const firstPill = await screen.findByTestId("concept-variant-pill-concept-a");
    fireEvent.click(firstPill);
    expect(activeKey()).toBe("concept-a:0");

    const ipaInput = await screen.findByPlaceholderText("Enter IPA…");
    fireEvent.focus(ipaInput);
    fireEvent.keyDown(ipaInput, { key: "ArrowRight" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));
    fireEvent.keyDown(ipaInput, { key: "ArrowLeft" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));

    const orthoInput = screen.getByPlaceholderText("Enter orthographic form…");
    fireEvent.focus(orthoInput);
    fireEvent.keyDown(orthoInput, { key: "ArrowRight" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));
    fireEvent.keyDown(orthoInput, { key: "ArrowLeft" });
    await waitFor(() => expect(activeKey()).toBe("concept-a:0"));

    fireEvent.focus(ipaInput);
    fireEvent.keyDown(ipaInput, { key: "ArrowDown" });
    await waitFor(() => expect(activeKey()).toBe("concept-b:0"));

    const secondPill = screen.getByTestId("concept-variant-pill-concept-b");
    fireEvent.click(secondPill);
    secondPill.focus();
    expect(document.activeElement?.tagName).toBe("BUTTON");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => expect(activeKey()).toBe("middle-empty:0"));
  });

  it("arrow keys navigate concepts when focus is on a button (chip click leaves button focused)", async () => {
    render(<ParseUI />);
    await switchToAnnotateMode();

    const sidebar = await screen.findByTestId("concept-sidebar");
    const waterButton = within(sidebar).getByRole("button", { name: /water/i });
    fireEvent.click(waterButton);
    waterButton.focus();
    expect(document.activeElement?.tagName).toBe("BUTTON");
    expect(screen.getByRole("heading", { name: "water" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(await screen.findByRole("heading", { name: "fire" })).toBeTruthy();

    const fireButton = within(sidebar).getByRole("button", { name: /fire/i });
    fireEvent.click(fireButton);
    fireButton.focus();
    expect(document.activeElement?.tagName).toBe("BUTTON");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(await screen.findByRole("heading", { name: "water" })).toBeTruthy();
  });

  it("uses arrow keys to follow the sorted annotate concept list selection path", async () => {
    mockConfig = {
      ...mockConfig!,
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "apple" },
      ],
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("concept-sort-az"));
    fireEvent.click(screen.getByRole("button", { name: /apple/i }));
    expect(await screen.findByRole("heading", { name: "apple" })).toBeTruthy();
    mockSetActiveConcept.mockClear();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByRole("heading", { name: "water" })).toBeTruthy();
    await waitFor(() => expect(mockSetActiveConcept).toHaveBeenCalledWith("1"));

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(await screen.findByRole("heading", { name: "apple" })).toBeTruthy();
  });

  it("preserves vertical caret arrows in the Compare Notes textarea", async () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    mockConfig = {
      ...mockConfig!,
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /hair/i }));
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();

    const notesField = screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i);
    notesField.focus();
    expect(document.activeElement).toBe(notesField);
    mockSetActiveConcept.mockClear();

    expect(fireEvent.keyDown(notesField, { key: "ArrowDown" })).toBe(true);
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();
    expect(mockSetActiveConcept).not.toHaveBeenCalled();

    fireEvent.focus(screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i));
    expect(fireEvent.keyDown(screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i), { key: "ArrowUp" })).toBe(true);
    await waitFor(() => expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy());
    expect(mockSetActiveConcept).not.toHaveBeenCalled();
  });

  it("preserves horizontal caret arrows in Compare text fields", async () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    mockConfig = {
      ...mockConfig!,
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /hair/i }));
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();

    const notesField = screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i);
    notesField.focus();
    expect(document.activeElement).toBe(notesField);
    mockSetActiveConcept.mockClear();

    fireEvent.keyDown(notesField, { key: "ArrowRight" });
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();
    fireEvent.keyDown(notesField, { key: "ArrowLeft" });
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();
    expect(mockSetActiveConcept).not.toHaveBeenCalled();
  });

  it("uses ArrowDown and ArrowUp to navigate concepts in Compare mode", async () => {
    window.localStorage.setItem("parse.currentMode", "compare");
    mockConfig = {
      ...mockConfig!,
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "hair" },
        { id: "3", label: "fire" },
      ],
    };

    render(<ParseUI />);

    const sidebar = await screen.findByTestId("concept-sidebar");
    fireEvent.click(within(sidebar).getByRole("button", { name: /hair/i }));
    expect(screen.getByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();
    mockSetActiveConcept.mockClear();

    // ArrowDown from a non-field target navigates to the next concept (preventDefault → false).
    expect(fireEvent.keyDown(window, { key: "ArrowDown" })).toBe(false);
    expect(await screen.findByPlaceholderText(/Ask PARSE AI about fire/i)).toBeTruthy();
    await waitFor(() => expect(mockSetActiveConcept).toHaveBeenCalledWith("3"));

    // ArrowUp navigates back to the previous concept.
    expect(fireEvent.keyDown(window, { key: "ArrowUp" })).toBe(false);
    expect(await screen.findByPlaceholderText(/Ask PARSE AI about hair/i)).toBeTruthy();
    await waitFor(() => expect(mockSetActiveConcept).toHaveBeenCalledWith("2"));
  });

  it("persists compare notes per concept via localStorage without requiring a blur", () => {
    const { unmount } = render(<ParseUI />);
    const notesField = screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i);

    fireEvent.change(notesField, { target: { value: "Loanword candidate from Arabic." } });
    unmount();

    render(<ParseUI />);
    expect(screen.getByDisplayValue("Loanword candidate from Arabic.")).toBeTruthy();
  });

  it("renders assistant markdown with readable headings, lists, and inline code in the AI chat panel", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: "openai", method: "api_key", flow_active: false });
    mockChatMessages = [
      {
        role: "assistant",
        timestamp: "2026-04-21T12:00:00.000Z",
        content:
          "**Cannot import speakers — read-only MVP constraints.** ### What I checked - `project_context_read`: Current project has 0 speakers. - `read_text_preview`: File not found. ### Recommended next steps 1. Add speaker audio files. 2. Create initial annotation files.",
      },
    ];

    render(<ParseUI />);

    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByRole("heading", { name: "What I checked" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Recommended next steps" })).toBeTruthy();
    expect(screen.getByText("project_context_read").tagName).toBe("CODE");
    expect(screen.getByText(/read-only MVP constraints\./i).closest("strong")).not.toBeNull();
    expect(screen.queryByText(/\*\*Cannot import speakers/i)).toBeNull();
  });

  it("shows a reference placeholder for configured languages with no data", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    render(<ParseUI />);
    const placeholders = await screen.findAllByText("No reference data");
    expect(placeholders.length).toBeGreaterThanOrEqual(1);
  });

  it("hides the Reference Forms section entirely when CLEF is not configured", async () => {
    render(<ParseUI />);
    // Wait one tick for the mount effect's getClefConfig() to resolve,
    // then assert the section's heading and placeholder never appear.
    await screen.findByRole("button", { name: "Run" });
    expect(screen.queryByText("Reference forms")).toBeNull();
    expect(screen.queryByText("No reference data")).toBeNull();
  });

  it("opens CLEF configuration instead of starting contact-lexeme compute when the drawer Run button is unconfigured", async () => {
    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });

    await switchCompareComputeMode('contact-lexemes');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    await waitFor(() => expect(apiClient.getClefCatalog).toHaveBeenCalledTimes(1));
    expect(apiClient.startCompute).not.toHaveBeenCalledWith('contact-lexemes');
    expect(apiClient.getClefProviders).toHaveBeenCalledTimes(1);
  });

  it("auto-chains similarity after a successful configured contact-lexeme populate", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar', 'fa'],
      languages: [
        { code: 'ar', name: 'Arabic' },
        { code: 'fa', name: 'Persian' },
      ],
      config_path: '',
      concepts_csv_exists: true,
      meta: {},
    };
    vi.mocked(apiClient.startCompute).mockImplementation(async (computeType: string) => ({
      job_id: computeType === 'contact-lexemes' ? 'contact-job-1' : 'similarity-job-1',
      jobId: computeType === 'contact-lexemes' ? 'contact-job-1' : 'similarity-job-1',
    }));
    vi.mocked(apiClient.pollCompute).mockImplementation(async (computeType: string) => {
      if (computeType === 'contact-lexemes') {
        return {
          status: 'complete',
          progress: 100,
          result: {
            total_filled: 3,
            filled: { ar: 2, fa: 1 },
          },
        };
      }
      return { status: 'running', progress: 10 };
    });

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    vi.useFakeTimers();

    await switchCompareComputeMode('contact-lexemes');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run' }));
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(apiClient.startCompute).toHaveBeenCalledWith('contact-lexemes');
    expect(apiClient.startCompute).toHaveBeenCalledWith('similarity', { speakers: ['Fail01', 'Kalh01'] });
  });

  it("does not auto-chain similarity when contact-lexeme populate completes with zero filled forms", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar'],
      languages: [{ code: 'ar', name: 'Arabic' }],
      config_path: '',
      concepts_csv_exists: true,
      meta: {},
    };
    vi.mocked(apiClient.startCompute).mockResolvedValue({ job_id: 'contact-job-2', jobId: 'contact-job-2' });
    vi.mocked(apiClient.pollCompute).mockResolvedValue({
      status: 'complete',
      progress: 100,
      result: { total_filled: 0, filled: {} },
    });

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    vi.useFakeTimers();

    await switchCompareComputeMode('contact-lexemes');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run' }));
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(apiClient.startCompute).toHaveBeenCalledTimes(1);
    expect(apiClient.startCompute).toHaveBeenCalledWith('contact-lexemes');
  });

  it("rehydrates in-flight contact-lexeme and similarity jobs from listActiveJobs on mount", async () => {
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      { jobId: 'contact-job-9', type: 'compute:contact-lexemes', status: 'running', progress: 0.25 },
      { jobId: 'similarity-job-9', type: 'compute:similarity', status: 'running', progress: 0.5 },
    ]);
    vi.mocked(apiClient.pollCompute).mockImplementation(async (computeType: string, jobId: string) => ({
      status: 'running',
      progress: jobId === 'contact-job-9' ? 25 : 50,
      message: `${computeType}:${jobId}`,
    }));

    render(<ParseUI />);

    await waitFor(() => expect(apiClient.pollCompute).toHaveBeenCalledWith('contact-lexemes', 'contact-job-9'));
    expect(apiClient.pollCompute).toHaveBeenCalledWith('similarity', 'similarity-job-9');
  });

  it("keeps Refresh as an enrichments reload instead of starting another compute job", async () => {
    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Refresh' });

    mockLoadEnrichments.mockClear();
    vi.mocked(apiClient.startCompute).mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    await waitFor(() => expect(mockLoadEnrichments).toHaveBeenCalledTimes(1));
    expect(apiClient.startCompute).not.toHaveBeenCalled();
  });

  it("runs cognate compute on the selected compare-speaker subset", async () => {
    render(<ParseUI />);

    await screen.findByRole("button", { name: "Run" });

    fireEvent.click(screen.getByRole("button", { name: "Kalh01" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledWith("cognates", { speakers: ["Fail01"] });
    });
  });

  it("runs similarity compute on the selected compare-speaker subset", async () => {
    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const computeModeSelect = within(screen.getByTestId("right-panel")).getAllByRole("combobox")[1];
    fireEvent.change(computeModeSelect, { target: { value: "similarity" } });
    fireEvent.click(screen.getByRole("button", { name: "Kalh01" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledWith("similarity", { speakers: ["Fail01"] });
    });
  });

  it("does not start generic compare compute when no speakers remain selected", async () => {
    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const rightPanel = screen.getByTestId("right-panel");
    fireEvent.click(within(rightPanel).getByRole("button", { name: "Fail01" }));
    fireEvent.click(within(rightPanel).getByRole("button", { name: "Kalh01" }));

    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText(/Selected speakers only:/i)).toBeNull();

    const runButton = screen.getByRole("button", { name: "Run" }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);

    vi.mocked(apiClient.startCompute).mockClear();
    runButton.disabled = false;
    runButton.removeAttribute("disabled");
    fireEvent.click(runButton);

    expect(apiClient.startCompute).not.toHaveBeenCalled();
  });

  it("routes configured contact-lexeme Run through the isolated cross-speaker job path", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar"],
      languages: [{ code: "ar", name: "Arabic" }],
      config_path: "config/sil_contact_languages.json",
      concepts_csv_exists: true,
      meta: {},
    };

    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const rightPanel = screen.getByTestId("right-panel");
    await switchCompareComputeMode('contact-lexemes');
    expect(getCompareComputeModePicker().value).toBe('contact-lexemes');
    expect(screen.getByText(/CLEF configured/i)).toBeTruthy();

    fireEvent.click(within(rightPanel).getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(apiClient.startCompute).mock.calls[0]).toEqual(["contact-lexemes"]);
  });

  it("shows contact-lexemes progress in the header chip instead of the compare drawer", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar'],
      languages: [{ code: 'ar', name: 'Arabic' }],
      config_path: 'config/sil_contact_languages.json',
      concepts_csv_exists: true,
      meta: {},
    };
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      { jobId: 'contact-job-chip', type: 'compute:contact-lexemes', status: 'running', progress: 0.25 },
    ]);
    vi.mocked(apiClient.pollCompute).mockImplementation(async (computeType: string, jobId: string) => ({
      status: 'running',
      progress: computeType === 'contact-lexemes' && jobId === 'contact-job-chip' ? 25 : 0,
      message: `${computeType}:${jobId}`,
    }));

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    await switchCompareComputeMode('contact-lexemes');

    await waitFor(() => expect(apiClient.pollCompute).toHaveBeenCalledWith('contact-lexemes', 'contact-job-chip'));
    const chip = screen.getByTestId('topbar-job-strip');
    expect(screen.getByTestId('topbar-job-strip-row-contact-job-chip')).toBeTruthy();
    expect(chip.textContent).toContain('Contact lexemes');
    expect(chip.textContent).toContain('25%');
    expect(screen.queryByText(/Running… 25%/i)).toBeNull();
  });

  it("opens the decomposed Sources Report modal with academic citations from the CLEF endpoint", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar'],
      languages: [{ code: 'ar', name: 'Arabic' }],
      config_path: 'config/sil_contact_languages.json',
      concepts_csv_exists: true,
      meta: {},
    };

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    await switchCompareComputeMode('contact-lexemes');

    fireEvent.click(screen.getByRole('button', { name: 'Sources Report' }));

    await waitFor(() => expect(apiClient.getClefSourcesReport).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Academic citations')).toBeTruthy();
    expect(screen.getByTestId('sources-report-citation-wikidata')).toBeTruthy();
    expect(screen.getByText(/Vrandečić, D\. & Krötzsch, M\./i)).toBeTruthy();
  });

  it("restores the xAI provider badge after reload when backend reports provider=xai", async () => {
    // Regression: the mount effect used to call setProvider('openai')
    // unconditionally whenever the backend said authenticated=true, so users
    // who saved an xAI key would see the OpenAI badge on reload.
    mockGetAuthStatus.mockResolvedValue({
      authenticated: true,
      provider: "xai",
      method: "api_key",
      flow_active: false,
    });

    render(<ParseUI />);

    // Expand the minimized AI chat so the provider badge renders.
    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByText("Connected to xAI")).toBeTruthy();
    expect(screen.getByText(/grok-4\.2 reasoning/i)).toBeTruthy();
    expect(screen.queryByText("Connected to OpenAI")).toBeNull();
  });

  it("restores the OpenAI provider badge after reload when backend reports provider=openai", async () => {
    mockGetAuthStatus.mockResolvedValue({
      authenticated: true,
      provider: "openai",
      method: "api_key",
      flow_active: false,
    });

    render(<ParseUI />);

    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByText("Connected to OpenAI")).toBeTruthy();
    expect(screen.getByText("gpt-5.4")).toBeTruthy();
    expect(screen.queryByText("Connected to xAI")).toBeNull();
  });
});


describe("Actions menu — transcription run flow", () => {
  // All per-model transcription actions (Normalize, STT, ORTH, IPA, and the
  // combined Full Pipeline) are now routed through a single batch runner
  // modal. The dedicated behaviours (sequential execution, pre-flight
  // preflight, step-level error capture, post-run report with tracebacks)
  // are tested in the TranscriptionRunModal / useBatchPipelineJob /
  // BatchReportModal suites. These tests just cover the entry points from
  // the action menu.

  it("Actions menu shows every transcription entry point and the cross-speaker match", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    expect(screen.getByText("Run Audio Normalization…")).toBeTruthy();
    expect(screen.getByText("Run STT…")).toBeTruthy();
    expect(screen.getByText("Generate ORTH (razhan)…")).toBeTruthy();
    expect(screen.getByText("Run IPA Transcription…")).toBeTruthy();
    expect(screen.getByText("Run Full Pipeline…")).toBeTruthy();
    expect(screen.getByText("Run Cross-Speaker Match")).toBeTruthy();
  });

  it("clicking a transcription action opens the run modal", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByTestId("actions-normalize"));

    // The modal fires getPipelineState per speaker on open; give it a
    // microtask to render.
    await act(async () => { await Promise.resolve(); });

    // The modal renders with the title supplied by the action.
    expect(screen.getByText(/Run Audio Normalization/i)).toBeTruthy();
  });

  it("exports LingPy TSV from the Actions menu through the canonical export helper path", async () => {
    const createObjectURL = vi.fn(() => "blob:lingpy");
    const revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getAllByRole("button", { name: /Export LingPy TSV/i })[0]);

    await waitFor(() => expect(apiClient.getLingPyExport).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:lingpy");
    expect(screen.queryByText("Run Cross-Speaker Match")).toBeNull();

    clickSpy.mockRestore();
  });

  it("shows the concept-appendix export below Export LingPy TSV in the Actions menu and runs it", async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:md"), revokeObjectURL: vi.fn() });

    render(<ParseUI />);
    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    // The appendix entry lives in the Actions menu, directly after Export LingPy TSV.
    const lingpy = screen.getAllByRole("button", { name: /Export LingPy TSV/i })[0];
    const appendix = screen.getByTestId("actions-export-concept-appendix");
    expect(lingpy.compareDocumentPosition(appendix) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(appendix);
    await waitFor(() => expect(apiClient.getConceptAppendixExport).toHaveBeenCalledTimes(1));

    clickSpy.mockRestore();
  });

  it("imports custom tags from the Actions menu and shows the shared summary banner", async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('custom-sk-concept-list');
    vi.mocked(apiClient.importTagCsv).mockResolvedValueOnce({
      ok: true,
      tagId: 'custom-sk-concept-list',
      tagName: 'custom-sk-concept-list',
      color: '#6366f1',
      matchedCount: 12,
      missedCount: 3,
      missedLabels: [],
      totalTagsInFile: 1,
    });

    render(<ParseUI />);
    mockSyncTagsFromServer.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Actions' }));
    fireEvent.click(screen.getByTestId('concept-import-menu'));

    const input = screen.getByTestId('concept-import-input') as HTMLInputElement;
    const file = new File(['concept\nwater\n'], 'custom-sk-concept-list.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(apiClient.importTagCsv).toHaveBeenCalledWith(file, { tagName: 'custom-sk-concept-list' }));
    expect(mockSyncTagsFromServer).toHaveBeenCalledOnce();
    expect(screen.getByTestId('concept-import-summary').textContent).toContain('Tag "custom-sk-concept-list": 12 concepts assigned, 3 unmatched');
    expect(promptSpy).toHaveBeenCalledWith('Tag name for this concept list:', 'custom-sk-concept-list');

    promptSpy.mockRestore();
  });

  it("opens the comments import modal from the compare right panel", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("open-comments-import"));

    expect(screen.getByTestId("comments-import")).toBeTruthy();
    expect(screen.getAllByText(/Import Audition Comments/i).length).toBeGreaterThan(1);
  });

  it("exports LingPy TSV from the compare right panel", async () => {
    const createObjectURL = vi.fn(() => "blob:lingpy");
    const revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: /Export LingPy TSV/i }));

    await waitFor(() => expect(apiClient.getLingPyExport).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:lingpy");

    clickSpy.mockRestore();
  });

  it("captures an offset anchor from annotate mode without marking the lexeme as manually adjusted", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const rightPanel = screen.getByTestId("right-panel");
    const anchorButton = within(rightPanel).getByTestId("annotate-capture-anchor");
    expect(anchorButton.textContent).toContain("00:09.50");

    fireEvent.click(anchorButton);

    expect(mockMarkLexemeManuallyAdjusted).not.toHaveBeenCalled();
    expect((await within(rightPanel).findByTestId("annotate-capture-toast")).textContent).toContain(
      "Anchored water @ 00:09.50 → +1.50s offset.",
    );
  });

  it("anchors against imported_csv_start when a retimed lexeme carries CSV provenance", async () => {
    // Lucas's fail02 scenario: a lexeme that was manually retimed to its
    // real audio position (78.0s) still carries the original Audition CSV
    // start (1.3s). Capturing an anchor must compare current audio to the
    // IMPORTED time, not the edited start — otherwise the offset collapses
    // to ~0 and global apply does nothing. This is the production-path
    // integration test the unit test in useOffsetState.test.ts cannot do
    // because it mocks lookupConceptInterval directly.
    mockCurrentTime = 78.0;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        {
          conceptText: "water",
          ipa: "aw",
          ortho: "ئاو",
          start: 78.0,
          end: 78.5,
          importedCsvStart: 1.3,
          importedCsvEnd: 1.8,
        },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const rightPanel = screen.getByTestId("right-panel");
    fireEvent.click(within(rightPanel).getByTestId("annotate-capture-anchor"));

    expect((await within(rightPanel).findByTestId("annotate-capture-toast")).textContent).toContain(
      "Anchored water @ 01:18.00 → +76.70s offset.",
    );
  });

  it("falls back to start when imported_csv_start is absent (legacy annotations)", async () => {
    // Legacy speakers imported before MC-410-C have no imported_csv_*; the
    // hook must still anchor using `start`, preserving pre-MC-410-C
    // behavior. This locks the `?? interval.start` fallback in place.
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const rightPanel = screen.getByTestId("right-panel");
    fireEvent.click(within(rightPanel).getByTestId("annotate-capture-anchor"));

    expect((await within(rightPanel).findByTestId("annotate-capture-toast")).textContent).toContain(
      "Anchored water @ 00:09.50 → +1.50s offset.",
    );
  });

  it("captures the current lexeme into the manual offset modal and shows the live consensus", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset-manual"));
    expect(await screen.findByTestId("offset-manual")).toBeTruthy();

    fireEvent.click(screen.getByTestId("offset-manual-capture"));

    const anchorList = await screen.findByTestId("offset-manual-anchor-list");
    expect(within(anchorList).getByText("water")).toBeTruthy();
    expect(within(anchorList).getByText("1")).toBeTruthy();
    expect(within(anchorList).getByText("+1.50s")).toBeTruthy();
    expect(screen.getByTestId("offset-manual-consensus").textContent).toContain("+1.500 s");
    expect(mockMarkLexemeManuallyAdjusted).not.toHaveBeenCalled();
  });

  it("shows detecting offset progress only in the generic header strip", async () => {
    vi.mocked(apiClient.detectTimestampOffset).mockResolvedValue({ job_id: "offset-job-1", jobId: "offset-job-1" });
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      {
        jobId: "offset-job-1",
        type: "compute:offset_detect",
        status: "running",
        progress: 0.42,
        message: "Scanning anchors…",
      },
    ]);
    vi.mocked(apiClient.pollOffsetDetectJob).mockImplementation(
      async (_jobId, _jobType, handlers) => {
        handlers?.onProgress?.({ progress: 42, message: "Scanning anchors…" });
        return new Promise(() => {});
      },
    );

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset"));

    const row = await screen.findByTestId("topbar-job-strip-row-offset-job-1");
    expect(row.textContent).toContain("Offset detect");
    expect(row.textContent).toContain("42%");
    expect(row.textContent).toContain("Scanning anchors");
    expect(screen.queryByTestId("offset-modal")).toBeNull();
    expect(screen.queryByTestId("offset-detecting")).toBeNull();
  });

  it("captures the current lexeme into the manual offset modal and shows the live consensus", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset-manual"));
    expect(await screen.findByTestId("offset-manual")).toBeTruthy();

    fireEvent.click(screen.getByTestId("offset-manual-capture"));

    const anchorList = await screen.findByTestId("offset-manual-anchor-list");
    expect(within(anchorList).getByText("water")).toBeTruthy();
    expect(within(anchorList).getByText("1")).toBeTruthy();
    expect(within(anchorList).getByText("+1.50s")).toBeTruthy();
    expect(screen.getByTestId("offset-manual-consensus").textContent).toContain("+1.500 s");
    expect(mockMarkLexemeManuallyAdjusted).not.toHaveBeenCalled();
  });

  it("keeps the modal for detected results, then hides it while applying offset", async () => {
    vi.mocked(apiClient.detectTimestampOffset).mockResolvedValue({ job_id: "offset-job-1", jobId: "offset-job-1" });
    vi.mocked(apiClient.pollOffsetDetectJob).mockResolvedValue({
      speaker: "Fail01",
      offsetSec: 1.5,
      confidence: 0.88,
      nAnchors: 2,
      totalAnchors: 2,
      totalSegments: 12,
      method: "auto",
    });
    vi.mocked(apiClient.applyTimestampOffset).mockImplementation(() => new Promise(() => {}));

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset"));

    expect(await screen.findByTestId("offset-modal")).toBeTruthy();
    expect(screen.getByTestId("offset-value").textContent).toContain("+1.500 s");

    fireEvent.click(screen.getByTestId("offset-apply"));

    await waitFor(() => {
      expect(screen.queryByTestId("offset-modal")).toBeNull();
    });
  });

  it("Reset Project resets the batch runner", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset Project" }));

    // Batch is idle after reset → no topbar batch-status element.
    expect(screen.queryByTestId("topbar-batch-status")).toBeNull();
    expect(confirmSpy).toHaveBeenCalled();
    expect(mockAnnotationSetState).toHaveBeenCalledWith({ records: {}, dirty: {}, loading: {} });

    confirmSpy.mockRestore();
  });

  it("prefills Orthographic from direct ortho when both direct ortho and ortho_words overlap", async () => {
    // Direct tiers.ortho now wins for editor pre-fill when both tiers overlap.
    // This keeps Saha01's refined Arabic-script concept-window text visible
    // even if ortho_words still contains stale import-time English names.
    const COARSE_TEXT = "زور جوان بووین ئاو دەگڕێ";  // monolithic paragraph
    const WORD_TEXT = "ئاو";

    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kalh01"],
      concepts: [{ id: "1", label: "water" }, { id: "2", label: "fire" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    const base = makeRecord("Fail01", [
      { conceptText: "water", ortho: COARSE_TEXT, start: 0.0, end: 5.0 },
    ]);
    mockRecords = {
      Fail01: {
        ...base,
        tiers: {
          ...base.tiers,
          // Word-level tier: single word fully inside the concept anchor
          ortho_words: {
            name: "ortho_words",
            display_order: 4,
            intervals: [
              { start: 1.1, end: 1.4, text: WORD_TEXT },
            ],
          },
        },
      },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    // After mode switch the annotate view renders and the editor prefers the
    // direct ortho interval over the ortho_words helper result.
    await waitFor(() => {
      expect(screen.getByDisplayValue(COARSE_TEXT)).toBeTruthy();
    });
    expect(screen.queryByDisplayValue(WORD_TEXT)).toBeNull();
  });
});
