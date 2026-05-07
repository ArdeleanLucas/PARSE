// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AnnotationInterval, AnnotationRecord } from '../../api/types';

const { mockSaveLexemeNoteApi, mockSaveEnrichments, mockLoadEnrichments } = vi.hoisted(() => ({
  mockSaveLexemeNoteApi: vi.fn(),
  mockSaveEnrichments: vi.fn(),
  mockLoadEnrichments: vi.fn(),
}));

let mockRecord: AnnotationRecord | null = null;
let mockEnrichmentData: Record<string, unknown> = {};
let mockSelectedRegion: { start: number; end: number } | null = { start: 1.25, end: 2.5 };
let mockCurrentTime = 0;
let mockDuration = 4;
let mockIsPlaying = false;
let mockTags: Array<{ id: string; label: string; color: string }> = [];

const mockSetConceptTag = vi.fn((speaker: string, conceptId: string, tagId: string) => {
  expect(speaker).toBe('Fail01');
  if (!mockRecord) return;
  const nextTags = new Set(mockRecord.concept_tags?.[conceptId] ?? []);
  nextTags.add(tagId);
  mockRecord = {
    ...mockRecord,
    concept_tags: {
      ...(mockRecord.concept_tags ?? {}),
      [conceptId]: Array.from(nextTags),
    },
  };
});
const mockSetConfirmedAnchor = vi.fn((speaker: string, conceptId: string, anchor: { start: number; end: number; matched_text?: string } | null) => {
  expect(speaker).toBe('Fail01');
  if (!mockRecord) return;
  const nextAnchors = { ...(mockRecord.confirmed_anchors ?? {}) };
  if (anchor) {
    nextAnchors[conceptId] = anchor;
  } else {
    delete nextAnchors[conceptId];
  }
  mockRecord = { ...mockRecord, confirmed_anchors: nextAnchors };
});

const applyIntervalToMockRecord = (tier: string, interval: AnnotationInterval) => {
  if (!mockRecord) {
    throw new Error('mockRecord must be seeded before saving intervals');
  }
  const existingTier = mockRecord.tiers[tier] ?? { name: tier, display_order: 99, intervals: [] };
  const nextIntervals = existingTier.intervals
    .filter((candidate) => !(Math.abs(candidate.start - interval.start) < 0.001 && Math.abs(candidate.end - interval.end) < 0.001))
    .concat(interval)
    .sort((left, right) => left.start - right.start);
  mockRecord = {
    ...mockRecord,
    tiers: {
      ...mockRecord.tiers,
      [tier]: {
        ...existingTier,
        intervals: nextIntervals,
      },
    },
  };
};

const mockSetInterval = vi.fn((speaker: string, tier: string, interval: AnnotationInterval) => {
  expect(speaker).toBe('Fail01');
  applyIntervalToMockRecord(tier, interval);
});
const mockSaveLexemeAnnotation = vi.fn().mockReturnValue({ ok: true, moved: 4 });
const mockMoveIntervalAcrossTiers = vi.fn().mockReturnValue(0);
const mockSaveSpeaker = vi.fn().mockResolvedValue(undefined);
const mockUndo = vi.fn();
const mockRedo = vi.fn();
const mockSeek = vi.fn();
const mockAddRegion = vi.fn();
const mockScrollToTimeAtFraction = vi.fn();
const mockSetZoom = vi.fn();
const mockSetRate = vi.fn();
const mockPlayPause = vi.fn();
const mockPlayRange = vi.fn();
const mockPause = vi.fn();
const mockSkip = vi.fn();
const mockClearQuickRetimeSelection = vi.fn();
let mockWaveSurferOptions: { quickRetimeSelection?: {
  enabled: boolean;
  label: string;
  onContextMenu: (selection: { start: number; end: number }, event: MouseEvent) => void;
} } | null = null;

vi.mock('../../api/client', () => ({
  saveLexemeNote: mockSaveLexemeNoteApi,
}));

vi.mock('../../stores/annotationStore', () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) => selector({
    records: { Fail01: mockRecord },
    setInterval: mockSetInterval,
    saveLexemeAnnotation: mockSaveLexemeAnnotation,
    moveIntervalAcrossTiers: mockMoveIntervalAcrossTiers,
    saveSpeaker: mockSaveSpeaker,
    undo: mockUndo,
    redo: mockRedo,
    setConceptTag: mockSetConceptTag,
    setConfirmedAnchor: mockSetConfirmedAnchor,
    histories: {},
  }),
}));

vi.mock('../../stores/enrichmentStore', () => ({
  useEnrichmentStore: (selector: (state: unknown) => unknown) => selector({
    data: mockEnrichmentData,
    save: mockSaveEnrichments,
    load: mockLoadEnrichments,
    loading: false,
    replace: vi.fn(),
  }),
}));

vi.mock('../../stores/playbackStore', () => {
  const usePlaybackStore = (selector: (state: unknown) => unknown) => selector({
    isPlaying: mockIsPlaying,
    currentTime: mockCurrentTime,
    duration: mockDuration,
    selectedRegion: mockSelectedRegion,
  });
  (usePlaybackStore as unknown as { setState: (...args: unknown[]) => void }).setState = vi.fn();
  return { usePlaybackStore };
});

vi.mock('../../stores/tagStore', () => ({
  useTagStore: (selector: (state: unknown) => unknown) => selector({
    tags: mockTags,
  }),
}));

vi.mock('../../hooks/useSpectrogram', () => ({
  useSpectrogram: vi.fn(),
}));

vi.mock('../../hooks/useWaveSurfer', () => ({
  useWaveSurfer: (options: typeof mockWaveSurferOptions) => {
    mockWaveSurferOptions = options;
    return {
      playPause: mockPlayPause,
      playRange: mockPlayRange,
      pause: mockPause,
      seek: mockSeek,
      scrollToTimeAtFraction: mockScrollToTimeAtFraction,
      skip: mockSkip,
      addRegion: mockAddRegion,
      clearQuickRetimeSelection: mockClearQuickRetimeSelection,
      setZoom: mockSetZoom,
      setRate: mockSetRate,
      wsRef: { current: null },
    };
  },
}));

vi.mock('./TranscriptionLanes', () => ({
  LABEL_COL_PX: 148,
  TranscriptionLanes: () => <div data-testid="transcription-lanes">lanes</div>,
}));

import { AnnotateView } from './AnnotateView';

function makeRecord(concepts: Array<{ conceptText: string; conceptId?: string; ipa?: string; ortho?: string; orthoWords?: string; start: number; end: number }>): AnnotationRecord {
  const tier = (intervals: AnnotationInterval[]) => ({
    name: 'tier',
    display_order: 1,
    intervals,
  });
  return {
    speaker: 'Fail01',
    source_wav: 'Fail01.wav',
    source_audio: 'Fail01.wav',
    tiers: {
      concept: tier(concepts.map((item) => ({ start: item.start, end: item.end, text: item.conceptText, concept_id: item.conceptId ?? item.conceptText }))),
      ipa: tier(concepts.filter((item) => item.ipa).map((item) => ({ start: item.start, end: item.end, text: item.ipa ?? '' }))),
      ortho: tier(concepts.filter((item) => item.ortho !== undefined).map((item) => ({ start: item.start, end: item.end, text: item.ortho ?? '' }))),
      ortho_words: tier(concepts.filter((item) => item.orthoWords !== undefined).map((item) => ({ start: item.start, end: item.end, text: item.orthoWords ?? '', concept_id: item.conceptId ?? item.conceptText }))),
    },
  } as AnnotationRecord;
}

describe('AnnotateView', () => {
  beforeEach(() => {
    mockRecord = null;
    mockEnrichmentData = {};
    mockSelectedRegion = { start: 1.25, end: 2.5 };
    mockCurrentTime = 0;
    mockDuration = 4;
    mockIsPlaying = false;
    mockTags = [
      { id: 'review-needed', label: 'Review needed', color: '#f59e0b' },
      { id: 'confirmed', label: 'Confirmed', color: '#16a34a' },
      { id: 'problematic', label: 'Problematic', color: '#ef4444' },
    ];
    mockSetInterval.mockClear();
    mockSaveLexemeAnnotation.mockReset();
    mockSaveLexemeAnnotation.mockReturnValue({ ok: true, moved: 4 });
    mockSetConceptTag.mockClear();
    mockSetConfirmedAnchor.mockClear();
    mockMoveIntervalAcrossTiers.mockClear();
    mockSaveSpeaker.mockClear();
    mockUndo.mockClear();
    mockRedo.mockClear();
    mockSeek.mockClear();
    mockAddRegion.mockClear();
    mockScrollToTimeAtFraction.mockClear();
    mockSetZoom.mockClear();
    mockSetRate.mockClear();
    mockPlayPause.mockClear();
    mockPlayRange.mockClear();
    mockPause.mockClear();
    mockSkip.mockClear();
    mockClearQuickRetimeSelection.mockClear();
    mockSaveLexemeNoteApi.mockReset();
    mockSaveLexemeNoteApi.mockResolvedValue({ success: true });
    mockSaveEnrichments.mockReset();
    mockSaveEnrichments.mockResolvedValue(undefined);
    mockLoadEnrichments.mockReset();
    mockWaveSurferOptions = null;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  function renderWaterAnnotateView() {
    return render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );
  }

  function getOrthographicInput() {
    return screen.getByPlaceholderText('Enter orthographic form…') as HTMLInputElement;
  }

  it('renders stored annotate fields, speaker notes, and complete badge', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    expect(screen.getByDisplayValue('aw')).toBeTruthy();
    expect(screen.getByDisplayValue('ئاو')).toBeTruthy();
    expect(screen.getByText('Orthographic')).toBeTruthy();
    expect(screen.queryByText('Orthographic (Kurdish)')).toBeNull();
    expect(screen.getByTestId('lexeme-user-note-Fail01-water')).toBeTruthy();
    expect(screen.getByText('Complete')).toBeTruthy();
    expect(screen.queryByText('Annotated')).toBeNull();
    expect(screen.queryByText('Missing')).toBeNull();
    expect(screen.getByTestId('transcription-lanes')).toBeTruthy();
  });

  it('pre-fills ORTHOGRAPHIC editor from tiers.ortho when both ortho and ortho_words have entries for the concept window', () => {
    mockRecord = makeRecord([{ conceptText: 'one', conceptId: 'water', ipa: 'jɛk', ortho: 'یەک', orthoWords: 'one', start: 18.5, end: 19.5 }]);

    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('یەک');
    expect(getOrthographicInput().value).not.toBe('one');
    expect(screen.getByDisplayValue('jɛk')).toBeTruthy();
  });

  it('falls back to ortho_words pre-fill when tiers.ortho has no overlapping interval', () => {
    mockRecord = makeRecord([{ conceptText: 'one', conceptId: 'water', orthoWords: 'refined-word', start: 18.5, end: 19.5 }]);

    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('refined-word');
  });

  it('does not save unedited ortho_words fallback text as a direct ORTH annotation', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', orthoWords: 'god', start: 1.25, end: 2.5 }]);

    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('god');
    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'xwa' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith(expect.objectContaining({
      ipaText: 'xwa',
      orthoText: undefined,
    })));
  });

  it('keeps a cleared ortho_words fallback empty after save and reload', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', orthoWords: 'god', start: 1.25, end: 2.5 }]);
    mockSaveLexemeAnnotation.mockImplementation(({ newStart, newEnd, orthoText }) => {
      mockRecord = makeRecord([{ conceptText: 'water', ortho: orthoText, orthoWords: 'god', start: newStart, end: newEnd }]);
      return { ok: true, moved: 3 };
    });

    const { unmount } = renderWaterAnnotateView();

    const orthographic = getOrthographicInput();
    expect(orthographic.value).toBe('god');
    fireEvent.change(orthographic, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith(expect.objectContaining({
      orthoText: '',
    })));

    unmount();
    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('');
  });

  it('keeps a cleared pre-existing direct ORTH interval empty after save and reload', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ortho: 'God', orthoWords: 'god', start: 1.25, end: 2.5 }]);
    mockSaveLexemeAnnotation.mockImplementation(({ newStart, newEnd, orthoText }) => {
      mockRecord = makeRecord([{ conceptText: 'water', ortho: orthoText, orthoWords: 'god', start: newStart, end: newEnd }]);
      return { ok: true, moved: 4 };
    });

    const { unmount } = renderWaterAnnotateView();

    const orthographic = getOrthographicInput();
    expect(orthographic.value).toBe('God');
    fireEvent.change(orthographic, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith(expect.objectContaining({
      orthoText: '',
    })));

    unmount();
    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('');
  });

  it('saves an edited ortho_words fallback as a direct ORTH annotation', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', orthoWords: 'god', start: 1.25, end: 2.5 }]);

    renderWaterAnnotateView();

    fireEvent.change(getOrthographicInput(), { target: { value: 'خودا' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith(expect.objectContaining({
      orthoText: 'خودا',
    })));
  });

  it('treats an overlapping empty tiers.ortho interval as an explicit clear instead of falling back to ortho_words', () => {
    mockRecord = makeRecord([{ conceptText: 'one', ortho: '', orthoWords: 'fallback-word', start: 18.5, end: 19.5 }]);

    renderWaterAnnotateView();

    expect(getOrthographicInput().value).toBe('');
  });

  it('renders no badge for a boundary-only concept', () => {
    mockRecord = makeRecord([{ conceptText: 'water', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    expect(screen.queryByText('Annotated')).toBeNull();
    expect(screen.queryByText('Complete')).toBeNull();
    expect(screen.queryByText('Missing')).toBeNull();
  });

  it('flips Mark Done to confirmed, emits a transient toast, and ignores repeat clicks', async () => {
    vi.useFakeTimers();
    mockRecord = makeRecord([{ conceptText: 'water', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    const markDone = screen.getByRole('button', { name: /Mark Done/i });
    expect(markDone.getAttribute('aria-pressed')).toBe('false');
    expect(markDone.className).toContain('bg-white');

    fireEvent.click(markDone);

    expect(mockSetConceptTag).toHaveBeenCalledWith('Fail01', 'water', 'confirmed');
    expect(mockSetConfirmedAnchor).toHaveBeenCalledWith('Fail01', 'water', expect.objectContaining({
      start: 1,
      end: 2,
      matched_text: 'water',
    }));
    expect(screen.getByTestId('annotate-mark-done-toast').textContent).toBe('Marked done.');

    expect(mockSetConceptTag).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(1700);
    });
    expect(screen.queryByTestId('annotate-mark-done-toast')).toBeNull();
  });

  it('clears the Marked done toast when navigating to a different concept', () => {
    mockRecord = makeRecord([{ conceptText: 'water', start: 1, end: 2 }]);

    const { rerender } = renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /Mark Done/i }));
    expect(screen.getByTestId('annotate-mark-done-toast').textContent).toBe('Marked done.');

    rerender(
      <AnnotateView
        concept={{ id: 2, key: 'fire', name: 'fire' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    expect(screen.queryByTestId('annotate-mark-done-toast')).toBeNull();
    const markDone = screen.getByRole('button', { name: /Mark Done/i });
    expect(markDone.getAttribute('aria-pressed')).toBe('false');
    expect(markDone.className).toContain('bg-white');
  });

  it('renders no badge when only auto-imported ortho_words exists for the concept', () => {
    mockRecord = makeRecord([{ conceptText: 'water', orthoWords: 'water', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    expect(screen.getByDisplayValue('water')).toBeTruthy();
    expect(screen.queryByText('Annotated')).toBeNull();
    expect(screen.queryByText('Complete')).toBeNull();
    expect(screen.queryByText('Missing')).toBeNull();
  });

  it('renders Annotated for a boundary plus ortho-only concept', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ortho: 'ئاو', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    expect(screen.getByText('Annotated')).toBeTruthy();
    expect(screen.queryByText('Complete')).toBeNull();
    expect(screen.queryByText('Missing')).toBeNull();
  });

  it('renders Annotated for a boundary plus ipa-only concept', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', start: 1, end: 2 }]);

    renderWaterAnnotateView();

    expect(screen.getByText('Annotated')).toBeTruthy();
    expect(screen.queryByText('Complete')).toBeNull();
    expect(screen.queryByText('Missing')).toBeNull();
  });

  it('saves speaker notes for the active speaker and concept on blur', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    const notes = screen.getByTestId('lexeme-user-note-Fail01-water');
    fireEvent.change(notes, { target: { value: 'Check vowel length.' } });
    fireEvent.blur(notes);

    await waitFor(() => expect(mockSaveLexemeNoteApi).toHaveBeenCalledWith({
      speaker: 'Fail01',
      concept_id: 'water',
      user_note: 'Check vowel length.',
    }));
  });

  it('loads persisted speaker note for the active speaker and concept on mount', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 }]);
    mockEnrichmentData = {
      lexeme_notes: {
        Fail01: {
          water: { user_note: 'Existing note', updated_at: '2026-05-07T00:00:00Z' },
        },
      },
    };

    renderWaterAnnotateView();

    expect((screen.getByTestId('lexeme-user-note-Fail01-water') as HTMLTextAreaElement).value).toBe('Existing note');
  });

  it('saving a speaker note also updates the in-memory enrichment store', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 }]);
    mockEnrichmentData = { lexeme_notes: {} };

    renderWaterAnnotateView();

    const notes = screen.getByTestId('lexeme-user-note-Fail01-water');
    fireEvent.change(notes, { target: { value: 'Vowel length unclear.' } });
    fireEvent.blur(notes);

    await waitFor(() => expect(mockSaveLexemeNoteApi).toHaveBeenCalledWith({
      speaker: 'Fail01',
      concept_id: 'water',
      user_note: 'Vowel length unclear.',
    }));
    await waitFor(() => expect(mockSaveEnrichments).toHaveBeenCalledWith({
      lexeme_notes: {
        Fail01: {
          water: expect.objectContaining({
            user_note: 'Vowel length unclear.',
            updated_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
          }),
        },
      },
    }));
  });

  it('clears userNote when navigating to a concept with no saved note even if the previous concept had unblurred edits', () => {
    mockRecord = makeRecord([
      { conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 },
      { conceptText: 'fire', ipa: 'fr', ortho: 'ئاگر', start: 3, end: 4 },
    ]);
    mockEnrichmentData = { lexeme_notes: {} };

    const { rerender } = render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    const waterTextarea = screen.getByTestId('lexeme-user-note-Fail01-water') as HTMLTextAreaElement;
    fireEvent.change(waterTextarea, { target: { value: 'unblurred edit' } });

    rerender(
      <AnnotateView
        concept={{ id: 2, key: 'fire', name: 'fire' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    const fireTextarea = screen.getByTestId('lexeme-user-note-Fail01-fire') as HTMLTextAreaElement;
    expect(fireTextarea.value).toBe('');
  });

  it('renders a live waveform playhead chip from playback state with two-decimal precision', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 1, end: 2 }]);
    mockCurrentTime = 5.125;

    const view = (
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />
    );

    const { rerender } = render(view);
    expect(screen.getByLabelText('Waveform playhead time').textContent).toBe('0:05.13');

    mockCurrentTime = 65.1;
    rerender(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );
    expect(screen.getByLabelText('Waveform playhead time').textContent).toBe('1:05.10');
  });

  it('saves annotation tiers for the selected region with one atomic store action', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', start: 1.25, end: 2.5 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.change(screen.getByTestId('lexeme-start'), { target: { value: '1.75' } });
    fireEvent.change(screen.getByTestId('lexeme-end'), { target: { value: '2.75' } });
    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'aβ' } });
    fireEvent.change(screen.getByPlaceholderText('Enter orthographic form…'), { target: { value: 'ئاو' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith({
      speaker: 'Fail01',
      oldStart: 1.25,
      oldEnd: 2.5,
      newStart: 1.75,
      newEnd: 2.75,
      ipaText: 'aβ',
      orthoText: 'ئاو',
      orthoEdited: true,
      conceptName: 'water',
    }));
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith('Fail01', expect.anything()));
    expect(mockSetInterval).not.toHaveBeenCalled();
  });

  it('updates the saved lexeme bounds used by later waveform region commits after Save Annotation', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', start: 1.25, end: 2.5 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.change(screen.getByTestId('lexeme-start'), { target: { value: '1.750' } });
    fireEvent.change(screen.getByTestId('lexeme-end'), { target: { value: '2.750' } });
    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'aβ' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith('Fail01', expect.anything()));
    expect(mockAddRegion).toHaveBeenCalledWith(1.75, 2.75);
    expect((screen.getByTestId('lexeme-start') as HTMLInputElement).value).toBe('1.750');
    expect((screen.getByTestId('lexeme-end') as HTMLInputElement).value).toBe('2.750');

    (mockWaveSurferOptions as unknown as { onRegionCommit: (start: number, end: number) => void }).onRegionCommit(1.8, 2.8);

    expect(mockMoveIntervalAcrossTiers).toHaveBeenLastCalledWith(
      'Fail01',
      1.75,
      2.75,
      1.8,
      2.8,
      ['concept', 'ipa', 'ortho', 'ortho_words'],
    );
  });

  it('commits a dragged waveform quick-retime selection from the dynamic context menu', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'old-ipa', ortho: 'old-ortho', start: 1.25, end: 2.5 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'edited-ipa' } });
    fireEvent.change(screen.getByPlaceholderText('Enter orthographic form…'), { target: { value: 'edited-ortho' } });

    expect(mockWaveSurferOptions?.quickRetimeSelection?.enabled).toBe(true);
    expect(mockWaveSurferOptions?.quickRetimeSelection?.label).toBe('Update water timestamp');

    const contextEvent = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 96, clientY: 48 });
    mockWaveSurferOptions!.quickRetimeSelection!.onContextMenu({ start: 1.75, end: 2.75 }, contextEvent);

    const commit = await screen.findByRole('menuitem', { name: 'Update water timestamp' });
    fireEvent.click(commit);

    await waitFor(() => expect(mockSaveLexemeAnnotation).toHaveBeenCalledWith({
      speaker: 'Fail01',
      oldStart: 1.25,
      oldEnd: 2.5,
      newStart: 1.75,
      newEnd: 2.75,
      ipaText: 'edited-ipa',
      orthoText: 'edited-ortho',
      orthoEdited: true,
      conceptName: 'water',
    }));
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith('Fail01', expect.anything()));
    expect(mockClearQuickRetimeSelection).toHaveBeenCalledTimes(1);
    expect(mockAddRegion).toHaveBeenCalledWith(1.75, 2.75);
    expect(mockSeek).toHaveBeenCalledWith(1.75);
  });


  it('cancels a quick-retime menu selection without saving', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'old-ipa', ortho: 'old-ortho', start: 1.25, end: 2.5 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    const contextEvent = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 96, clientY: 48 });
    mockWaveSurferOptions!.quickRetimeSelection!.onContextMenu({ start: 1.75, end: 2.75 }, contextEvent);

    const cancel = await screen.findByRole('menuitem', { name: 'Cancel selection' });
    fireEvent.click(cancel);

    expect(mockClearQuickRetimeSelection).toHaveBeenCalledTimes(1);
    expect(mockSaveLexemeAnnotation).not.toHaveBeenCalled();
    expect(screen.queryByRole('menu', { name: 'Waveform quick retime menu' })).toBeNull();
  });

  it('dismisses a quick-retime menu selection with Escape without saving', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'old-ipa', ortho: 'old-ortho', start: 1.25, end: 2.5 }]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    const contextEvent = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 96, clientY: 48 });
    mockWaveSurferOptions!.quickRetimeSelection!.onContextMenu({ start: 1.75, end: 2.75 }, contextEvent);
    await screen.findByRole('menuitem', { name: 'Update water timestamp' });

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(mockClearQuickRetimeSelection).toHaveBeenCalledTimes(1);
    expect(mockSaveLexemeAnnotation).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('menu', { name: 'Waveform quick retime menu' })).toBeNull());
  });

  it('reloads the saved ipa and orthography after saving onto a new selected region', async () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'old-ipa', ortho: 'old-ortho', start: 0.2, end: 0.8 }]);
    mockSelectedRegion = { start: 1.25, end: 2.5 };
    mockSaveLexemeAnnotation.mockImplementation(({ newStart, newEnd, ipaText, orthoText, conceptName }) => {
      mockRecord = makeRecord([{ conceptText: conceptName, ipa: ipaText, ortho: orthoText, start: newStart, end: newEnd }]);
      return { ok: true, moved: 4 };
    });

    const view = (
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />
    );

    const { unmount } = render(view);
    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'new-ipa' } });
    fireEvent.change(screen.getByPlaceholderText('Enter orthographic form…'), { target: { value: 'new-ortho' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith('Fail01', expect.anything()));

    unmount();
    render(view);

    expect(screen.getByDisplayValue('new-ipa')).toBeTruthy();
    expect(screen.getByDisplayValue('new-ortho')).toBeTruthy();
  });


  it('uses the server-normalized annotation to report changed tiers and refresh saved bounds', async () => {
    const before = makeRecord([{ conceptText: 'water', ipa: 'old-ipa', ortho: 'old-ortho', start: 1.25, end: 2.5 }]);
    const after = makeRecord([{ conceptText: 'water', ipa: 'new-ipa', ortho: 'new-ortho', start: 1.76, end: 2.76 }]);
    after.tiers.ortho_words = {
      name: 'ortho_words',
      display_order: 4,
      intervals: [{ start: 1.76, end: 2.11, text: 'new', manuallyAdjusted: true }],
    };
    mockRecord = before;
    mockSaveLexemeAnnotation.mockReturnValue({ ok: true, moved: 1 });
    mockSaveSpeaker.mockResolvedValueOnce({
      record: after,
      changedTiers: ['concept', 'ipa', 'ortho', 'ortho_words'],
    });

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.change(screen.getByTestId('lexeme-start'), { target: { value: '1.750' } });
    fireEvent.change(screen.getByTestId('lexeme-end'), { target: { value: '2.750' } });
    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'new-ipa' } });
    fireEvent.change(screen.getByPlaceholderText('Enter orthographic form…'), { target: { value: 'new-ortho' } });
    fireEvent.click(screen.getByTestId('save-lexeme-annotation'));

    await waitFor(() => expect(screen.getByTestId('lexeme-timestamp-msg').textContent).toBe('Saved (4 tiers updated).'));
    expect((screen.getByTestId('lexeme-start') as HTMLInputElement).value).toBe('1.760');
    expect((screen.getByTestId('lexeme-end') as HTMLInputElement).value).toBe('2.760');
    expect(mockAddRegion).toHaveBeenCalledWith(1.76, 2.76);
  });

  it('does not render Save timestamp, Reset, or Chat placeholder buttons', () => {
    mockRecord = makeRecord([]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    expect(screen.queryByTestId('lexeme-timestamp-save')).toBeNull();
    expect(screen.queryByTestId('lexeme-timestamp-reset')).toBeNull();
    expect(screen.queryByText(/^Chat$/)).toBeNull();
  });

  it('marks the current concept done', () => {
    mockRecord = makeRecord([]);

    render(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /mark done/i }));
    expect(mockSetConceptTag).toHaveBeenCalledWith('Fail01', 'water', 'confirmed');
  });

  it('left-click on the Spectrogram button shows the spectrogram row beneath the waveform', () => {
    mockRecord = makeRecord([]);
    renderWaterAnnotateView();

    expect(screen.queryByTestId('spectrogram-row')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    expect(screen.getByTestId('spectrogram-row')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    expect(screen.queryByTestId('spectrogram-row')).toBeNull();
  });

  it('right-click on the Spectrogram button opens the settings popover', () => {
    mockRecord = makeRecord([]);
    renderWaterAnnotateView();

    expect(screen.queryByTestId('spectrogram-settings')).toBeNull();

    fireEvent.contextMenu(screen.getByRole('button', { name: /spectrogram/i }));
    expect(screen.getByTestId('spectrogram-settings')).toBeTruthy();
  });

  it('renders a spectrogram playhead positioned within the rendered slice (no concept => first 30 s)', () => {
    mockRecord = makeRecord([]);
    mockCurrentTime = 1.5;
    mockDuration = 4;
    renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    const playhead = screen.getByTestId('spectrogram-playhead') as HTMLElement;
    // No concept interval → effective slice = [0, min(duration, 30)] = [0, 4].
    // 1.5 / 4 = 37.5%.
    expect(playhead.style.left).toBe('37.5%');
  });

  it('positions the playhead relative to the concept slice on a long recording', () => {
    // Long audio (e.g. 8500 s) with a concept at 1530.0–1531.0. The pre-slice
    // playhead bug computed currentTime/duration on the full file and was
    // visually static; the fix maps currentTime into [start-0.5, end+0.5].
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'a', start: 1530, end: 1531 }]);
    mockCurrentTime = 1530.5;
    mockDuration = 8500;
    renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    const playhead = screen.getByTestId('spectrogram-playhead') as HTMLElement;
    // Slice = [1529.5, 1531.5]; (1530.5 − 1529.5) / 2.0 = 50%.
    expect(playhead.style.left).toBe('50%');
  });

  it('hides the spectrogram playhead when currentTime is outside the slice', () => {
    mockRecord = makeRecord([{ conceptText: 'water', ipa: 'a', start: 1530, end: 1531 }]);
    mockCurrentTime = 1600; // far past the [1529.5, 1531.5] slice
    mockDuration = 8500;
    renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    expect(screen.queryByTestId('spectrogram-playhead')).toBeNull();
  });

  it('hides the spectrogram playhead when duration is zero', () => {
    mockRecord = makeRecord([]);
    mockCurrentTime = 0;
    mockDuration = 0;
    renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /spectrogram/i }));
    expect(screen.queryByTestId('spectrogram-playhead')).toBeNull();
  });

  it('marks done without a time anchor when no concept boundary exists', () => {
    vi.useFakeTimers();
    mockRecord = makeRecord([]);

    renderWaterAnnotateView();

    fireEvent.click(screen.getByRole('button', { name: /Mark Done/i }));

    expect(mockSetConceptTag).toHaveBeenCalledWith('Fail01', 'water', 'confirmed');
    expect(mockSetConfirmedAnchor).not.toHaveBeenCalled();
    expect(screen.getByTestId('annotate-mark-done-toast').textContent).toBe('Marked done. Time anchor skipped: no boundary.');
  });

  it('disables Confirm time when no concept boundary exists', () => {
    mockRecord = makeRecord([]);

    renderWaterAnnotateView();

    expect((screen.getByTestId('confirm-time') as HTMLButtonElement).disabled).toBe(true);
  });

  it('toggles Confirm time anchor without tagging or matched text', () => {
    mockRecord = makeRecord([{ conceptText: 'water', start: 1, end: 2 }]);

    const { rerender } = renderWaterAnnotateView();

    fireEvent.click(screen.getByTestId('confirm-time'));

    expect(mockSetConfirmedAnchor).toHaveBeenCalledWith('Fail01', 'water', expect.objectContaining({
      start: 1,
      end: 2,
      source: 'user+boundary_only',
      confirmed_at: expect.any(String),
    }));
    expect(mockSetConfirmedAnchor.mock.calls[0][2]).not.toHaveProperty('matched_text');
    expect(mockSetConceptTag).not.toHaveBeenCalled();

    mockRecord = {
      ...mockRecord!,
      confirmed_anchors: {
        ...(mockRecord!.confirmed_anchors ?? {}),
        water: { start: 1, end: 2, source: 'user+boundary_only', confirmed_at: '2026-05-04T00:00:00.000Z' },
      },
    };
    rerender(
      <AnnotateView
        concept={{ id: 1, key: 'water', name: 'water' }}
        speaker="Fail01"
        totalConcepts={2}
        onPrev={() => {}}
        onNext={() => {}}
        audioUrl="/Fail01.wav"
      />,
    );

    fireEvent.click(screen.getByTestId('confirm-time'));
    expect(mockSetConfirmedAnchor).toHaveBeenLastCalledWith('Fail01', 'water', null);
  });

  describe('past-end-of-audio handling (Khan01 manifest case)', () => {
    function withDuration(record: AnnotationRecord, durationSec: number): AnnotationRecord {
      return { ...record, source_audio_duration_sec: durationSec } as AnnotationRecord;
    }

    it('shows no banner and leaves play enabled when all intervals fit inside the working WAV', () => {
      mockRecord = withDuration(
        makeRecord([{ conceptText: 'water', ipa: 'aw', start: 1, end: 2 }]),
        4,
      );
      renderWaterAnnotateView();
      expect(screen.queryByTestId('past-eoa-banner')).toBeNull();
      const play = screen.getByTestId('annotate-play') as HTMLButtonElement;
      expect(play.getAttribute('aria-disabled')).toBeNull();
    });

    it('shows the banner when at least one concept interval is past source_audio_duration_sec', () => {
      mockRecord = withDuration(
        makeRecord([
          { conceptText: 'water', ipa: 'aw', start: 1, end: 2 },
          { conceptText: 'water', ipa: 'aw', start: 12000, end: 12001 },
        ]),
        8590,
      );
      renderWaterAnnotateView();
      const banner = screen.getByTestId('past-eoa-banner');
      expect(banner).toBeTruthy();
      expect(banner.textContent).toContain('1');
      expect(banner.textContent).toContain('2');
      expect(banner.textContent?.toLowerCase()).toContain('past the end of the source audio');
      expect(banner.textContent).toContain('143m');
      expect(banner.textContent?.toLowerCase()).toContain('editing text fields is still permitted');
    });

    it('disables the play button and routes the click to a toast when the active concept is past EOA', () => {
      vi.useFakeTimers();
      mockRecord = withDuration(
        makeRecord([{ conceptText: 'water', ipa: 'aw', start: 12000, end: 12001 }]),
        8590,
      );
      renderWaterAnnotateView();
      const play = screen.getByTestId('annotate-play') as HTMLButtonElement;
      expect(play.getAttribute('aria-disabled')).toBe('true');
      expect(play.getAttribute('title')?.toLowerCase()).toContain('past the end of the source audio');

      fireEvent.click(play);
      expect(mockPlayPause).not.toHaveBeenCalled();
      expect(mockPlayRange).not.toHaveBeenCalled();
      expect(screen.getByTestId('past-eoa-toast').textContent?.toLowerCase()).toContain('cannot seek past end');

      act(() => { vi.advanceTimersByTime(2300); });
      expect(screen.queryByTestId('past-eoa-toast')).toBeNull();
    });

    it('keeps editing text fields enabled even when the concept is past EOA', () => {
      mockRecord = withDuration(
        makeRecord([{ conceptText: 'water', ipa: 'aw', ortho: 'ئاو', start: 12000, end: 12001 }]),
        8590,
      );
      renderWaterAnnotateView();
      const orthoInput = screen.getByPlaceholderText('Enter orthographic form…') as HTMLInputElement;
      expect(orthoInput.disabled).toBe(false);
      expect(orthoInput.value).toBe('ئاو');
    });
  });

});
