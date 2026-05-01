// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  fetchAll: vi.fn(),
  create: vi.fn(),
  deleteTag: vi.fn(),
  attach: vi.fn(),
  detach: vi.fn(),
}));

vi.mock('@/api/tags', () => ({
  tagsApi: {
    fetchAll: mocks.fetchAll,
    create: mocks.create,
    delete: mocks.deleteTag,
    attach: mocks.attach,
    detach: mocks.detach,
  },
}));

import { useConceptTagUsageCounts, useConceptTagsStore, type ConceptTag } from './conceptTags';

const archaic: ConceptTag = { id: 't1', name: 'archaic', color: '#3554B8', createdAt: '2026-05-01T00:00:00.000Z' };
const dialectal: ConceptTag = { id: 't2', name: 'dialectal', color: '#0f766e', createdAt: '2026-05-01T00:00:00.000Z' };

function resetStore() {
  useConceptTagsStore.setState(useConceptTagsStore.getInitialState(), true);
}

beforeEach(() => {
  resetStore();
  mocks.fetchAll.mockReset();
  mocks.create.mockReset();
  mocks.deleteTag.mockReset();
  mocks.attach.mockReset();
  mocks.detach.mockReset();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  resetStore();
});

describe('useConceptTagsStore', () => {
  it('load hydrates tags and attachments from the API', async () => {
    mocks.fetchAll.mockResolvedValue({ tags: [archaic], attachments: { sister: ['t1'] } });

    await act(async () => {
      await useConceptTagsStore.getState().load();
    });

    expect(useConceptTagsStore.getState().tags).toEqual([archaic]);
    expect(useConceptTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t1'] });
    expect(useConceptTagsStore.getState().loaded).toBe(true);
  });

  it('load is idempotent after loaded is true', async () => {
    mocks.fetchAll.mockResolvedValue({ tags: [], attachments: {} });

    await act(async () => {
      await useConceptTagsStore.getState().load();
      await useConceptTagsStore.getState().load();
    });

    expect(mocks.fetchAll).toHaveBeenCalledOnce();
  });

  it('load swallows API errors, marks loaded, and records the warning state', async () => {
    mocks.fetchAll.mockRejectedValue(new Error('404'));

    await act(async () => {
      await useConceptTagsStore.getState().load();
    });

    expect(useConceptTagsStore.getState().loaded).toBe(true);
    expect(useConceptTagsStore.getState().warnedLoadFailure).toBe(true);
    expect(console.warn).toHaveBeenCalledWith('[conceptTags] load failed; backend may be pending', expect.any(Error));
  });

  it('reset clears warnedLoadFailure so the next failed load warns again', async () => {
    mocks.fetchAll.mockRejectedValue(new Error('404'));

    await act(async () => {
      await useConceptTagsStore.getState().load();
    });
    resetStore();
    await act(async () => {
      await useConceptTagsStore.getState().load();
    });

    expect(console.warn).toHaveBeenCalledTimes(2);
  });

  it('attachTag adds without duplicates', async () => {
    mocks.attach.mockResolvedValue(undefined);
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1'] } });

    await act(async () => {
      await useConceptTagsStore.getState().attachTag('sister', 't1');
      await useConceptTagsStore.getState().attachTag('sister', 't2');
    });

    expect(useConceptTagsStore.getState().attachmentsByConcept.sister).toEqual(['t1', 't2']);
  });

  it('attachTag rolls back on API error', async () => {
    mocks.attach.mockRejectedValue(new Error('fail'));
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1'] } });

    await expect(useConceptTagsStore.getState().attachTag('sister', 't2')).rejects.toThrow('fail');

    expect(useConceptTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t1'] });
  });

  it('attachTag rollback does not clobber a concurrent successful attach', async () => {
    let rejectSlow!: (error: Error) => void;
    mocks.attach
      .mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectSlow = reject; }))
      .mockResolvedValueOnce(undefined);

    const slow = useConceptTagsStore.getState().attachTag('sister', 't1');
    await act(async () => {
      await useConceptTagsStore.getState().attachTag('sister', 't2');
    });
    expect(useConceptTagsStore.getState().attachmentsByConcept.sister).toEqual(['t1', 't2']);

    rejectSlow(new Error('boom'));
    await expect(slow).rejects.toThrow('boom');

    expect(useConceptTagsStore.getState().attachmentsByConcept.sister).toEqual(['t2']);
  });

  it('detachTag removes idempotently and prunes empty concept entries', async () => {
    mocks.detach.mockResolvedValue(undefined);
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1', 't2'], water: ['t2'] } });

    await act(async () => {
      await useConceptTagsStore.getState().detachTag('sister', 't1');
      await useConceptTagsStore.getState().detachTag('water', 't1');
      await useConceptTagsStore.getState().detachTag('water', 't2');
    });

    expect(useConceptTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t2'] });
  });

  it('detachTag rollback does not clobber a concurrent successful detach', async () => {
    let rejectSlow!: (error: Error) => void;
    mocks.detach
      .mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectSlow = reject; }))
      .mockResolvedValueOnce(undefined);
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1', 't2'] } });

    const slow = useConceptTagsStore.getState().detachTag('sister', 't1');
    await act(async () => {
      await useConceptTagsStore.getState().detachTag('sister', 't2');
    });
    expect(useConceptTagsStore.getState().attachmentsByConcept).toEqual({});

    rejectSlow(new Error('boom'));
    await expect(slow).rejects.toThrow('boom');

    expect(useConceptTagsStore.getState().attachmentsByConcept.sister).toEqual(['t1']);
  });

  it('createTag appends to tags', async () => {
    mocks.create.mockResolvedValue(archaic);

    await act(async () => {
      await useConceptTagsStore.getState().createTag('archaic', '#3554B8');
    });

    expect(mocks.create).toHaveBeenCalledWith({ name: 'archaic', color: '#3554B8' });
    expect(useConceptTagsStore.getState().tags).toEqual([archaic]);
  });

  it('deleteTag removes the tag and all attachments, pruning empty arrays', async () => {
    mocks.deleteTag.mockResolvedValue(undefined);
    useConceptTagsStore.setState({
      tags: [archaic, dialectal],
      attachmentsByConcept: { sister: ['t1', 't2'], water: ['t1'] },
    });

    await act(async () => {
      await useConceptTagsStore.getState().deleteTag('t1');
    });

    expect(useConceptTagsStore.getState().tags).toEqual([dialectal]);
    expect(useConceptTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t2'] });
  });

  it('useConceptTagUsageCounts returns per-tag totals across concepts', () => {
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1', 't2'], water: ['t1'] } });

    const { result } = renderHook(() => useConceptTagUsageCounts());

    expect(result.current).toEqual({ t1: 2, t2: 1 });
  });

  it('useConceptTagUsageCounts returns the same reference when only unrelated state changes', () => {
    useConceptTagsStore.setState({ attachmentsByConcept: { sister: ['t1'] } });
    const { result, rerender } = renderHook(() => useConceptTagUsageCounts());
    const first = result.current;

    act(() => useConceptTagsStore.setState({ loaded: true }));
    rerender();

    expect(result.current).toBe(first);
  });
});
