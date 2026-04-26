// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AnnotationInterval, AnnotationRecord } from '../../api/types';

let mockRecord: AnnotationRecord | null = null;
let mockSelectedRegion: { start: number; end: number } | null = { start: 1.25, end: 2.5 };
let mockCurrentTime = 0;
let mockDuration = 4;
let mockIsPlaying = false;

const mockSetInterval = vi.fn();
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

vi.mock('../../stores/annotationStore', () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) => selector({
    records: { Fail01: mockRecord },
    setInterval: mockSetInterval,
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
  useWaveSurfer: () => ({
    playPause: mockPlayPause,
    playRange: mockPlayRange,
    pause: mockPause,
    seek: mockSeek,
    scrollToTimeAtFraction: mockScrollToTimeAtFraction,
    skip: mockSkip,
    addRegion: mockAddRegion,
    setZoom: mockSetZoom,
    setRate: mockSetRate,
    wsRef: { current: null },
  }),
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
  });

  afterEach(() => {
    cleanup();
  });

  it('renders stored annotate fields and annotated badge', () => {
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
    expect(screen.getByText('Annotated')).toBeTruthy();
    expect(screen.getByTestId('transcription-lanes')).toBeTruthy();
  });

  it('saves annotation tiers for the selected region', async () => {
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

    fireEvent.change(screen.getByPlaceholderText('Enter IPA…'), { target: { value: 'aβ' } });
    fireEvent.change(screen.getByPlaceholderText('Enter orthographic form…'), { target: { value: 'ئاو' } });
    fireEvent.click(screen.getByRole('button', { name: /save annotation/i }));

    expect(mockSetInterval).toHaveBeenCalledWith('Fail01', 'ipa', { start: 1.25, end: 2.5, text: 'aβ' });
    expect(mockSetInterval).toHaveBeenCalledWith('Fail01', 'ortho', { start: 1.25, end: 2.5, text: 'ئاو' });
    expect(mockSetInterval).toHaveBeenCalledWith('Fail01', 'concept', { start: 1.25, end: 2.5, text: 'water' });
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith('Fail01'));
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
