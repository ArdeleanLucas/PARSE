// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConceptNotesBox, conceptNoteFromEnrichments } from './ConceptNotesBox';

const mocks = vi.hoisted(() => ({
  save: vi.fn().mockResolvedValue(undefined),
  storeData: {} as Record<string, unknown>,
}));

vi.mock('../../stores/enrichmentStore', () => ({
  useEnrichmentStore: Object.assign(
    (selector: (state: { data: Record<string, unknown> }) => unknown) => selector({ data: mocks.storeData }),
    {
      getState: () => ({ data: mocks.storeData, save: mocks.save }),
    },
  ),
}));

const STORAGE_KEY = 'parseui-compare-notes-v1';

beforeEach(() => {
  mocks.save.mockClear();
  mocks.storeData = {};
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe('conceptNoteFromEnrichments', () => {
  it('reads the server-backed note for a concept', () => {
    const data = { concept_notes: { '356': { note: 'native hangwīn', updated_at: 'x' } } };
    expect(conceptNoteFromEnrichments(data, '356')).toBe('native hangwīn');
  });

  it('returns empty string when absent or malformed', () => {
    expect(conceptNoteFromEnrichments(null, '356')).toBe('');
    expect(conceptNoteFromEnrichments({}, '356')).toBe('');
    expect(conceptNoteFromEnrichments({ concept_notes: { '356': {} } }, '356')).toBe('');
  });
});

describe('ConceptNotesBox', () => {
  it('shows the server-backed note from the enrichment store', () => {
    mocks.storeData = { concept_notes: { '356': { note: 'HONEY — rep=B' } } };
    render(<ConceptNotesBox conceptId={356} />);
    expect((screen.getByTestId('concept-note-356') as HTMLTextAreaElement).value).toBe('HONEY — rep=B');
  });

  it('falls back to the legacy localStorage cache when the server has no note', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ '356': 'legacy local note' }));
    render(<ConceptNotesBox conceptId={356} />);
    expect((screen.getByTestId('concept-note-356') as HTMLTextAreaElement).value).toBe('legacy local note');
  });

  it('persists edits to parse-enrichments.json via the merge-safe store.save and caches locally', async () => {
    render(<ConceptNotesBox conceptId={356} />);
    const textarea = screen.getByTestId('concept-note-356');
    fireEvent.focus(textarea);
    fireEvent.change(textarea, { target: { value: 'etymon *masya-' } });
    fireEvent.blur(textarea);

    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1));
    const patch = mocks.save.mock.calls[0][0] as { concept_notes: Record<string, { note: string }> };
    expect(patch.concept_notes['356'].note).toBe('etymon *masya-');
    // localStorage write-through cache
    const cached = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}');
    expect(cached['356']).toBe('etymon *masya-');
  });

  it('does not save when the value is unchanged', () => {
    mocks.storeData = { concept_notes: { '356': { note: 'unchanged' } } };
    render(<ConceptNotesBox conceptId={356} />);
    const textarea = screen.getByTestId('concept-note-356');
    fireEvent.focus(textarea);
    fireEvent.blur(textarea);
    expect(mocks.save).not.toHaveBeenCalled();
  });
});
