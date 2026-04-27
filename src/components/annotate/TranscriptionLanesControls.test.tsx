// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockToggleLane = vi.fn();
const mockSetLaneColor = vi.fn();

const mockLanes = {
  ipa_phone: { visible: true, color: '#111111' },
  ipa: { visible: true, color: '#222222' },
  stt: { visible: true, color: '#333333' },
  ortho: { visible: true, color: '#444444' },
  stt_words: { visible: false, color: '#555555' },
  boundaries: { visible: false, color: '#666666' },
};

vi.mock('../../stores/transcriptionLanesStore', () => ({
  useTranscriptionLanesStore: (selector: (state: unknown) => unknown) => selector({
    lanes: mockLanes,
    toggleLane: mockToggleLane,
    setLaneColor: mockSetLaneColor,
  }),
}));

vi.mock('./LaneColorPicker', () => ({
  LaneColorPicker: ({ ariaLabel, onChange }: { ariaLabel: string; onChange: (color: string) => void }) => (
    <button type="button" aria-label={ariaLabel} onClick={() => onChange('#abcdef')}>
      color
    </button>
  ),
}));

import { TranscriptionLanesControls } from './TranscriptionLanesControls';

describe('TranscriptionLanesControls', () => {
  beforeEach(() => {
    mockToggleLane.mockReset();
    mockSetLaneColor.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the oracle lane split with Words directly above Boundaries', () => {
    render(<TranscriptionLanesControls />);
    expect(screen.getByText('Transcription lanes')).toBeTruthy();
    expect(screen.getByText('Phones tier')).toBeTruthy();
    expect(screen.getByText('IPA tier')).toBeTruthy();
    expect(screen.getByText('STT segments')).toBeTruthy();
    expect(screen.getByText('Words (Tier 1)')).toBeTruthy();
    expect(screen.getByText('Boundaries (Tier 2)')).toBeTruthy();
    expect(screen.getByText('Raw faster-whisper word boundaries')).toBeTruthy();
    expect(screen.getByText('Forced-aligned edges; colored by Tier 1 ↔ Tier 2 shift')).toBeTruthy();

    const labels = Array.from(document.querySelectorAll('label')).map((el) =>
      el.textContent?.replace(/\s+/g, ' ').trim(),
    );
    expect(labels).toEqual([
      'Phones tierPhone-level IPA',
      'IPA tierWord/lexeme IPA',
      'STT segmentsCoarse transcript',
      'Ortho tierOrthographic',
      'Words (Tier 1)Raw faster-whisper word boundaries',
      'Boundaries (Tier 2)Forced-aligned edges; colored by Tier 1 ↔ Tier 2 shift',
    ]);
  });

  it('toggles a lane visibility checkbox', () => {
    render(<TranscriptionLanesControls />);
    fireEvent.click(screen.getAllByLabelText(/phones tier/i)[0]);
    expect(mockToggleLane).toHaveBeenCalledWith('ipa_phone');
  });

  it('updates a lane color through the color control', () => {
    render(<TranscriptionLanesControls />);
    fireEvent.click(screen.getByLabelText('Color for IPA tier'));
    expect(mockSetLaneColor).toHaveBeenCalledWith('ipa', '#abcdef');
  });
});
