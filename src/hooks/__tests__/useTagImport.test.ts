// @vitest-environment jsdom
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useTagImport } from '../useTagImport';

const mockImportTagCsv = vi.fn();
const mockSyncFromServer = vi.fn();

vi.mock('../../api/client', () => ({
  importTagCsv: (...args: unknown[]) => mockImportTagCsv(...args),
}));

vi.mock('../../stores/tagStore', () => ({
  useTagStore: (selector: (state: { syncFromServer: () => Promise<void> }) => unknown) =>
    selector({ syncFromServer: mockSyncFromServer }),
}));

describe('useTagImport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSyncFromServer.mockResolvedValue(undefined);
  });

  it('imports a custom tag CSV with a prompted tag name and exposes a success summary', async () => {
    mockImportTagCsv.mockResolvedValue({
      ok: true,
      tagId: 'custom-sk-concept-list',
      tagName: 'custom-sk-concept-list',
      color: '#6366f1',
      matchedCount: 12,
      missedCount: 3,
      missedLabels: [],
      totalTagsInFile: 1,
    });
    const promptForTagName = vi.fn().mockReturnValue('custom-sk-concept-list');
    const file = new File(['concept\nwater\n'], 'custom-sk-concept-list.csv', { type: 'text/csv' });

    const { result } = renderHook(() => useTagImport({ promptForTagName }));

    await act(async () => {
      await result.current.importFile(file);
    });

    expect(promptForTagName).toHaveBeenCalledWith('custom-sk-concept-list');
    expect(mockImportTagCsv).toHaveBeenCalledWith(file, { tagName: 'custom-sk-concept-list' });
    expect(mockSyncFromServer).toHaveBeenCalledOnce();
    expect(result.current.summary).toBe('Tag "custom-sk-concept-list": 12 concepts assigned, 3 unmatched');
    expect(result.current.error).toBeNull();
  });

  it('does nothing when the tag-name prompt is cancelled', async () => {
    const promptForTagName = vi.fn().mockReturnValue(null);
    const file = new File(['concept\nwater\n'], 'custom-sk-concept-list.csv', { type: 'text/csv' });

    const { result } = renderHook(() => useTagImport({ promptForTagName }));

    await act(async () => {
      await result.current.importFile(file);
    });

    expect(mockImportTagCsv).not.toHaveBeenCalled();
    expect(mockSyncFromServer).not.toHaveBeenCalled();
    expect(result.current.summary).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('surfaces import failures as an error banner state', async () => {
    mockImportTagCsv.mockRejectedValue(new Error('bad csv'));
    const promptForTagName = vi.fn().mockReturnValue('custom-sk-concept-list');
    const file = new File(['concept\nwater\n'], 'custom-sk-concept-list.csv', { type: 'text/csv' });

    const { result } = renderHook(() => useTagImport({ promptForTagName }));

    await act(async () => {
      await result.current.importFile(file);
    });

    expect(result.current.summary).toBeNull();
    expect(result.current.error).toBe('bad csv');
  });

  it('includes rows skipped because tag names already existed in the import summary', async () => {
    mockImportTagCsv.mockResolvedValue({
      ok: true,
      tagId: 'custom-sk-concept-list',
      tagName: 'custom-sk-concept-list',
      color: '#6366f1',
      matchedCount: 4,
      missedCount: 0,
      missedLabels: [],
      totalTagsInFile: 3,
      skippedExistingCount: 2,
    });
    const promptForTagName = vi.fn().mockReturnValue('custom-sk-concept-list');
    const file = new File(['tag,concept\nReview,water\nreview,fire\nCore,stone\n'], 'custom-sk-concept-list.csv', { type: 'text/csv' });

    const { result } = renderHook(() => useTagImport({ promptForTagName }));

    await act(async () => {
      await result.current.importFile(file);
    });

    expect(result.current.summary).toBe('Tag "custom-sk-concept-list": 4 concepts assigned, skipped: 2 tags already existed');
    expect(result.current.error).toBeNull();
  });
});
