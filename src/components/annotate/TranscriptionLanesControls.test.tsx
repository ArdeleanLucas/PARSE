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

  it('renders lane labels and hints', () => {
    render(<TranscriptionLanesControls />);
    expect(screen.getByText('Transcription lanes')).toBeTruthy();
    expect(screen.getByText('Phones tier')).toBeTruthy();
    expect(screen.getByText('IPA tier')).toBeTruthy();
    expect(screen.getByText('Coarse transcript')).toBeTruthy();
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
