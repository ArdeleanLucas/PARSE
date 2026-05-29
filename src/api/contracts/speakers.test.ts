// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deleteSpeaker } from './speakers';
import { ApiError } from './shared';

const fetchSpy = vi.spyOn(globalThis, 'fetch');

beforeEach(() => {
  fetchSpy.mockReset();
});
afterEach(() => {
  fetchSpy.mockReset();
});

describe('deleteSpeaker', () => {
  it('DELETEs /api/speakers/{speaker} and returns the parsed body', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ok: true, speaker: 'Saha01', trashDir: '.trash/Saha01-x', movedFiles: [], prunedRegistry: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const res = await deleteSpeaker('Saha01');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/speakers/Saha01');
    expect(init).toMatchObject({ method: 'DELETE' });
    expect(res.ok).toBe(true);
    expect(res.speaker).toBe('Saha01');
  });

  it('URL-encodes the speaker id', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, speaker: 'a b', trashDir: '', movedFiles: [], prunedRegistry: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await deleteSpeaker('a b');

    expect(fetchSpy.mock.calls[0][0]).toBe('/api/speakers/a%20b');
  });

  it('throws an ApiError with the holder body on 409', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'busy', holder: { jobId: 'job-1' } }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    try {
      await deleteSpeaker('Saha01');
      throw new Error('expected deleteSpeaker to reject');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(409);
      expect((error as ApiError).body).toEqual({ error: 'busy', holder: { jobId: 'job-1' } });
    }
  });
});
