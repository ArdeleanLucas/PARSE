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

import { useTagUsageCounts, useTagsStore, type Tag } from './tags';

const archaic: Tag = { id: 't1', name: 'archaic', color: '#3554B8', createdAt: '2026-05-01T00:00:00.000Z' };
const dialectal: Tag = { id: 't2', name: 'dialectal', color: '#0f766e', createdAt: '2026-05-01T00:00:00.000Z' };

function resetStore() {
  useTagsStore.setState(useTagsStore.getInitialState(), true);
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

describe('useTagsStore', () => {
  it('load hydrates tags and attachments from the API', async () => {
    mocks.fetchAll.mockResolvedValue({ tags: [archaic], attachments: { sister: ['t1'] } });

    await act(async () => {
      await useTagsStore.getState().load();
    });

    expect(useTagsStore.getState().tags).toEqual([archaic]);
    expect(useTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t1'] });
    expect(useTagsStore.getState().loaded).toBe(true);
  });

  it('load is idempotent after loaded is true', async () => {
    mocks.fetchAll.mockResolvedValue({ tags: [], attachments: {} });

    await act(async () => {
      await useTagsStore.getState().load();
      await useTagsStore.getState().load();
    });

    expect(mocks.fetchAll).toHaveBeenCalledOnce();
  });

  it('load swallows API errors and marks loaded', async () => {
    mocks.fetchAll.mockRejectedValue(new Error('404'));

    await act(async () => {
      await useTagsStore.getState().load();
    });

    expect(useTagsStore.getState().loaded).toBe(true);
    expect(console.warn).toHaveBeenCalledWith('[tags] load failed; backend may be pending', expect.any(Error));
  });

  it('attachTag adds without duplicates', async () => {
    mocks.attach.mockResolvedValue(undefined);
    useTagsStore.setState({ attachmentsByConcept: { sister: ['t1'] } });

    await act(async () => {
      await useTagsStore.getState().attachTag('sister', 't1');
      await useTagsStore.getState().attachTag('sister', 't2');
    });

    expect(useTagsStore.getState().attachmentsByConcept.sister).toEqual(['t1', 't2']);
  });

  it('attachTag rolls back on API error', async () => {
    mocks.attach.mockRejectedValue(new Error('fail'));
    useTagsStore.setState({ attachmentsByConcept: { sister: ['t1'] } });

    await expect(useTagsStore.getState().attachTag('sister', 't2')).rejects.toThrow('fail');

    expect(useTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t1'] });
  });

  it('detachTag removes idempotently and prunes empty concept entries', async () => {
    mocks.detach.mockResolvedValue(undefined);
    useTagsStore.setState({ attachmentsByConcept: { sister: ['t1', 't2'], water: ['t2'] } });

    await act(async () => {
      await useTagsStore.getState().detachTag('sister', 't1');
      await useTagsStore.getState().detachTag('water', 't1');
      await useTagsStore.getState().detachTag('water', 't2');
    });

    expect(useTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t2'] });
  });

  it('createTag appends to tags', async () => {
    mocks.create.mockResolvedValue(archaic);

    await act(async () => {
      await useTagsStore.getState().createTag('archaic', '#3554B8');
    });

    expect(mocks.create).toHaveBeenCalledWith({ name: 'archaic', color: '#3554B8' });
    expect(useTagsStore.getState().tags).toEqual([archaic]);
  });

  it('deleteTag removes the tag and all attachments, pruning empty arrays', async () => {
    mocks.deleteTag.mockResolvedValue(undefined);
    useTagsStore.setState({
      tags: [archaic, dialectal],
      attachmentsByConcept: { sister: ['t1', 't2'], water: ['t1'] },
    });

    await act(async () => {
      await useTagsStore.getState().deleteTag('t1');
    });

    expect(useTagsStore.getState().tags).toEqual([dialectal]);
    expect(useTagsStore.getState().attachmentsByConcept).toEqual({ sister: ['t2'] });
  });

  it('useTagUsageCounts returns per-tag totals across concepts', () => {
    useTagsStore.setState({ attachmentsByConcept: { sister: ['t1', 't2'], water: ['t1'] } });

    const { result } = renderHook(() => useTagUsageCounts());

    expect(result.current).toEqual({ t1: 2, t2: 1 });
  });
});
