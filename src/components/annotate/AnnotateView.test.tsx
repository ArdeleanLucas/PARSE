// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AnnotationInterval, AnnotationRecord } from '../../api/types';

const { mockSaveLexemeNoteApi } = vi.hoisted(() => ({
  mockSaveLexemeNoteApi: vi.fn(),
}));

let mockRecord: AnnotationRecord | null = null;
let mockSelectedRegion: { start: number; end: number } | null = { start: 1.25, end: 2.5 };
let mockCurrentTime = 0;
let mockDuration = 4;
let mockIsPlaying = false;

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
const mockTagConcept = vi.fn();
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
    histories: {},
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
    tagConcept: mockTagConcept,
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

function makeRecord(concepts: Array<{ conceptText: string; ipa?: string; ortho?: string; start: number; end: number }>): AnnotationRecord {
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
      concept: tier(concepts.map((item) => ({ start: item.start, end: item.end, text: item.conceptText }))),
      ipa: tier(concepts.filter((item) => item.ipa).map((item) => ({ start: item.start, end: item.end, text: item.ipa ?? '' }))),
      ortho: tier(concepts.filter((item) => item.ortho).map((item) => ({ start: item.start, end: item.end, text: item.ortho ?? '' }))),
      ortho_words: tier([]),
    },
  } as AnnotationRecord;
}

describe('AnnotateView', () => {
  beforeEach(() => {
    mockRecord = null;
    mockSelectedRegion = { start: 1.25, end: 2.5 };
    mockCurrentTime = 0;
    mockDuration = 4;
    mockIsPlaying = false;
    mockSetInterval.mockClear();
    mockSaveLexemeAnnotation.mockReset();
    mockSaveLexemeAnnotation.mockReturnValue({ ok: true, moved: 4 });
    mockMoveIntervalAcrossTiers.mockClear();
    mockSaveSpeaker.mockClear();
    mockUndo.mockClear();
    mockRedo.mockClear();
    mockTagConcept.mockClear();
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
    mockWaveSurferOptions = null;
  });

  afterEach(() => {
    cleanup();
  });

  it('renders stored annotate fields, speaker notes, and annotated badge', () => {
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

    expect(screen.getByDisplayValue('aw')).toBeTruthy();
    expect(screen.getByDisplayValue('ئاو')).toBeTruthy();
    expect(screen.getByText('Orthographic')).toBeTruthy();
    expect(screen.queryByText('Orthographic (Kurdish)')).toBeNull();
    expect(screen.getByTestId('lexeme-user-note-Fail01-water')).toBeTruthy();
    expect(screen.getByText('Annotated')).toBeTruthy();
    expect(screen.getByTestId('transcription-lanes')).toBeTruthy();
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
    expect(mockTagConcept).toHaveBeenCalledWith('confirmed', 'water');
  });
});
