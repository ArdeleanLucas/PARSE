// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockSearchLexeme = vi.fn();
const mockRequestSeek = vi.fn();

vi.mock('../../api/client', () => ({
  searchLexeme: (...args: unknown[]) => mockSearchLexeme(...args),
}));

vi.mock('../../stores/playbackStore', () => ({
  usePlaybackStore: (selector: (state: unknown) => unknown) => selector({
    requestSeek: mockRequestSeek,
  }),
}));

import { LexemeSearchBlock } from './LexemeSearchBlock';

describe('LexemeSearchBlock', () => {
  beforeEach(() => {
    mockSearchLexeme.mockReset();
    mockRequestSeek.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('submits a debounced lexeme search and renders results', async () => {
    mockSearchLexeme.mockResolvedValue({
      candidates: [
        { matched_text: 'aw', matched_variant: 'aw', start: 1.5, score: 0.92, tier: 'ipa' },
      ],
    });

    render(<LexemeSearchBlock speaker="Fail01" conceptId={1} />);
    fireEvent.change(screen.getByLabelText(/search lexeme variants/i), { target: { value: 'aw' } });

    await new Promise((resolve) => setTimeout(resolve, 350));
    await waitFor(() => expect(mockSearchLexeme).toHaveBeenCalledWith('Fail01', ['aw'], { conceptId: '1' }));
    expect(await screen.findByText('aw')).toBeTruthy();
    fireEvent.click(screen.getByRole('option'));
    expect(mockRequestSeek).toHaveBeenCalledWith(1.5);
  });

  it('renders the empty state when no matches are returned', async () => {
    mockSearchLexeme.mockResolvedValue({ candidates: [] });

    render(<LexemeSearchBlock speaker="Fail01" conceptId={2} />);
    fireEvent.change(screen.getByLabelText(/search lexeme variants/i), { target: { value: 'zzz' } });

    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(await screen.findByText('No matches')).toBeTruthy();
  });

  it('renders an error state when search fails', async () => {
    mockSearchLexeme.mockRejectedValue(new Error('bad search'));

    render(<LexemeSearchBlock speaker="Fail01" conceptId={3} />);
    fireEvent.change(screen.getByLabelText(/search lexeme variants/i), { target: { value: 'err' } });

    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(await screen.findByText('bad search')).toBeTruthy();
  });
});
