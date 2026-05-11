// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { duplicateConcept, deleteConcept } from './concepts';
import { ApiError } from './shared';

const fetchSpy = vi.spyOn(globalThis, 'fetch');

beforeEach(() => {
  fetchSpy.mockReset();
});
afterEach(() => {
  fetchSpy.mockReset();
});

describe('duplicateConcept', () => {
  it('POSTs to /api/concepts/{id}/duplicate and returns the parsed body', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          primary: { id: '322', label: 'leaf (A)', source_item: '102', source_survey: 'JBIL' },
          sibling: { id: '618', label: 'leaf (B)', source_item: '102', source_survey: 'JBIL' },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const res = await duplicateConcept('322');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/concepts/322/duplicate');
    expect(init).toMatchObject({ method: 'POST' });
    expect(res.primary.label).toBe('leaf (A)');
    expect(res.sibling.label).toBe('leaf (B)');
  });

  it('encodes the conceptId path component', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ primary: {}, sibling: {} }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );

    await duplicateConcept('a/b').catch(() => {});

    const [url] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/concepts/a%2Fb/duplicate');
  });

  it('throws with status code on 409 already-A/B response', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response('concept already part of an A/B pair', { status: 409 }),
    );

    await expect(duplicateConcept('322')).rejects.toThrow(/409/);
  });

  it('throws with status code on 404 unknown-concept response', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('not found', { status: 404 }));

    await expect(duplicateConcept('9999')).rejects.toThrow(/404/);
  });
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
