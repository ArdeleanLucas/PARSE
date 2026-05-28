// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deleteConcept } from './concepts';
import { ApiError } from './shared';

const fetchSpy = vi.spyOn(globalThis, 'fetch');

beforeEach(() => {
  fetchSpy.mockReset();
});
afterEach(() => {
  fetchSpy.mockReset();
});

describe('deleteConcept', () => {
  it('DELETEs /api/concepts/{id} and returns the parsed body', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, deleted_id: '322' }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );

    const res = await deleteConcept('322');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/concepts/322');
    expect(init).toMatchObject({ method: 'DELETE' });
    expect(res).toEqual({ ok: true, deleted_id: '322' });
  });

  it('throws an ApiError with the parsed conflict body on 409', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'blocked', blocking_speakers: ['Qasr01'] }), { status: 409, headers: { 'Content-Type': 'application/json' } }),
    );

    try {
      await deleteConcept('322');
      throw new Error('expected deleteConcept to reject');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).message).toContain('409');
      expect((error as ApiError).body).toEqual({ error: 'blocked', blocking_speakers: ['Qasr01'] });
    }
  });
});
