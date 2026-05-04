// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTagStore } from './tagStore';

const mockPutTags = vi.fn();

vi.mock('../api/client', () => ({
  putTags: (...args: unknown[]) => mockPutTags(...args),
  getTags: vi.fn().mockResolvedValue({ tags: [] }),
}));

describe('useTagStore server write-through', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    window.localStorage.clear();
    useTagStore.setState(useTagStore.getInitialState(), true);
  });

  afterEach(() => {
    vi.useRealTimers();
    window.localStorage.clear();
    useTagStore.setState(useTagStore.getInitialState(), true);
  });

  it('persist schedules a debounced server PUT with current tags', async () => {
    mockPutTags.mockResolvedValue(undefined);
    useTagStore.setState({
      tags: [{ id: 't1', label: 'Archaic', color: '#3554B8' }],
    });

    useTagStore.getState().persist();
    vi.advanceTimersByTime(499);
    expect(mockPutTags).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);

    expect(mockPutTags).toHaveBeenCalledTimes(1);
    expect(mockPutTags).toHaveBeenCalledWith([
      { id: 't1', label: 'Archaic', color: '#3554B8' },
    ]);
  });

  it('coalesces rapid persisted changes into one server PUT', async () => {
    mockPutTags.mockResolvedValue(undefined);
    useTagStore.getState().addTag('Archaic', '#3554B8');
    useTagStore.getState().addTag('Dialectal', '#0f766e');

    await vi.advanceTimersByTimeAsync(500);

    expect(mockPutTags).toHaveBeenCalledTimes(1);
    expect(mockPutTags.mock.calls[0][0]).toHaveLength(2);
  });

  it('server write failure does not roll back localStorage', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    mockPutTags.mockRejectedValue(new Error('offline'));

    const tag = useTagStore.getState().addTag('Archaic', '#3554B8');
    await vi.advanceTimersByTimeAsync(500);

    const stored = JSON.parse(window.localStorage.getItem('parse-tags-v2') ?? '[]');
    expect(stored).toEqual([tag]);
    expect(useTagStore.getState().tags).toEqual([tag]);
    expect(warn).toHaveBeenCalledWith('[tagStore] server write failed; localStorage retains', expect.any(Error));
  });

  it('rejects duplicate tag labels case-insensitively', () => {
    useTagStore.getState().addTag('Archaic', '#3554B8');

    expect(() => useTagStore.getState().addTag(' archaic ', '#0f766e')).toThrow('409: tag name already exists');
    expect(useTagStore.getState().tags).toHaveLength(1);
  });
});
