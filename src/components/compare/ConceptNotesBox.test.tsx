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
  it('keys by the stable csv-id key — not the volatile sequential Concept.id', () => {
    // Regression for the off-by-N bug: concept_notes is keyed by csv id (heart=281),
    // so a heart box must look up '281', never the grouped-list position.
    mocks.storeData = {
      concept_notes: { '281': { note: 'HEART note' }, '259': { note: 'NECK note' } },
    };
    render(<ConceptNotesBox conceptKeys={['281']} />);
    expect((screen.getByTestId('concept-note-281') as HTMLTextAreaElement).value).toBe('HEART note');
  });

  it('shows the server-backed note from the enrichment store', () => {
    mocks.storeData = { concept_notes: { '356': { note: 'HONEY — rep=B' } } };
    render(<ConceptNotesBox conceptKeys={['356']} />);
    expect((screen.getByTestId('concept-note-356') as HTMLTextAreaElement).value).toBe('HONEY — rep=B');
  });

  it('resolves the uid-keyed note when keys lead with the uid (MC-458-K)', () => {
    // Post MC-458-E concept_notes is uid-keyed (c-328). noteKeysForConcept now
    // leads with the uid, so the box must read c-328 (not the member id 328,
    // which would miss and fall back to a stale cached note).
    mocks.storeData = { concept_notes: { 'c-328': { note: 'CLOUD — single state A hawr' } } };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ '328': 'STALE cold note' }));
    render(<ConceptNotesBox conceptKeys={['c-328', '328']} />);
    expect((screen.getByTestId('concept-note-c-328') as HTMLTextAreaElement).value).toBe('CLOUD — single state A hawr');
  });

  it('falls back to the legacy localStorage cache when the server has no note', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ '356': 'legacy local note' }));
    render(<ConceptNotesBox conceptKeys={['356']} />);
    expect((screen.getByTestId('concept-note-356') as HTMLTextAreaElement).value).toBe('legacy local note');
  });

  it('persists edits to parse-enrichments.json via the merge-safe store.save and caches locally', async () => {
    render(<ConceptNotesBox conceptKeys={['356']} />);
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

  it('reads from any member and saves to every member for a merged concept', async () => {
    // Note seeded under one member id; box should surface it and, on save,
    // write the new text to all member ids so they stay in sync.
    mocks.storeData = { concept_notes: { '599': { note: 'HAIR note' } } };
    render(<ConceptNotesBox conceptKeys={['1', '249', '250', '599']} />);
    const textarea = screen.getByTestId('concept-note-1');
    expect((textarea as HTMLTextAreaElement).value).toBe('HAIR note');

    fireEvent.focus(textarea);
    fireEvent.change(textarea, { target: { value: 'HAIR edited' } });
    fireEvent.blur(textarea);
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1));
    const patch = mocks.save.mock.calls[0][0] as { concept_notes: Record<string, { note: string }> };
    expect(Object.keys(patch.concept_notes).sort()).toEqual(['1', '249', '250', '599']);
    expect(patch.concept_notes['1'].note).toBe('HAIR edited');
    expect(patch.concept_notes['599'].note).toBe('HAIR edited');
  });

  it('does not save when the value is unchanged', () => {
    mocks.storeData = { concept_notes: { '356': { note: 'unchanged' } } };
    render(<ConceptNotesBox conceptKeys={['356']} />);
    const textarea = screen.getByTestId('concept-note-356');
    fireEvent.focus(textarea);
    fireEvent.blur(textarea);
    expect(mocks.save).not.toHaveBeenCalled();
  });

  it('stays dirty and retries on the next blur when the server save fails', async () => {
    mocks.save.mockRejectedValueOnce(new Error('network down'));
    render(<ConceptNotesBox conceptKeys={['356']} />);
    const textarea = screen.getByTestId('concept-note-356');

    fireEvent.focus(textarea);
    fireEvent.change(textarea, { target: { value: 'etymon *masya-' } });
    fireEvent.blur(textarea);

    // First attempt failed — surfaced as an error, not "saved".
    await waitFor(() => expect(screen.getByText('network down')).toBeTruthy());
    expect(screen.queryByText('Saved')).toBeNull();

    // The edit is still considered unsaved, so a second blur retries it.
    mocks.save.mockResolvedValueOnce(undefined);
    fireEvent.focus(textarea);
    fireEvent.blur(textarea);
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2));
    const retry = mocks.save.mock.calls[1][0] as { concept_notes: Record<string, { note: string }> };
    expect(retry.concept_notes['356'].note).toBe('etymon *masya-');
  });

  it('clears a stale status pill when switching concepts', async () => {
    const { rerender } = render(<ConceptNotesBox conceptKeys={['356']} />);
    const textarea = screen.getByTestId('concept-note-356');
    fireEvent.focus(textarea);
    fireEvent.change(textarea, { target: { value: 'note A' } });
    fireEvent.blur(textarea);
    await waitFor(() => expect(screen.getByText('Saved')).toBeTruthy());

    rerender(<ConceptNotesBox conceptKeys={['357']} />);
    expect(screen.queryByText('Saved')).toBeNull();
  });
});
