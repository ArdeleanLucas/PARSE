// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  deleteModel,
  getModel,
  getModelBinding,
  installModelFromHf,
  installModelPack,
  listModels,
  setModelBinding,
  type ModelRecord,
} from './models';
import { ApiError } from './shared';

const fetchSpy = vi.spyOn(globalThis, 'fetch');

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const SAMPLE: ModelRecord = {
  id: 'stt-faster-whisper-large-v3',
  name: 'Faster-Whisper large-v3',
  stage: 'stt',
  format: 'faster-whisper-ct2',
  engine: 'faster-whisper',
  languages: ['mul'],
  source: { type: 'bundled', ref: 'bundled/stt' },
  size_bytes: 1_500_000_000,
  removable: false,
  root: 'bundled',
};

beforeEach(() => {
  fetchSpy.mockReset();
});
afterEach(() => {
  fetchSpy.mockReset();
});

describe('listModels', () => {
  it('GETs /api/models and unwraps the models array', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ models: [SAMPLE] }));

    const models = await listModels();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/models');
    expect(init?.method ?? 'GET').toBe('GET');
    expect(models).toEqual([SAMPLE]);
  });

  it('returns an empty array when the wrapper is missing', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));
    expect(await listModels()).toEqual([]);
  });
});

describe('getModel', () => {
  it('GETs /api/models/{id} with the id encoded', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(SAMPLE));

    const model = await getModel('stt/large v3');

    expect(fetchSpy.mock.calls[0][0]).toBe('/api/models/stt%2Flarge%20v3');
    expect(model).toEqual(SAMPLE);
  });

  it('throws ApiError on 404', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ error: 'not found' }, 404));
    await expect(getModel('missing')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('installModelPack', () => {
  it('POSTs multipart form-data to /api/models/install and returns the jobId', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ jobId: 'job-123' }, 202));
    const file = new File(['zip-bytes'], 'model.parsemodel', { type: 'application/zip' });

    const result = await installModelPack(file, { overwrite: true });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/models/install');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(form.get('pack')).toBe(file);
    expect(form.get('overwrite')).toBe('true');
    expect(result).toEqual({ jobId: 'job-123' });
  });

  it('omits the overwrite field by default', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ job_id: 'job-9' }, 202));
    const file = new File(['x'], 'm.zip');

    const result = await installModelPack(file);

    const form = fetchSpy.mock.calls[0][1]?.body as FormData;
    expect(form.get('overwrite')).toBeNull();
    // resolveJobId also accepts the snake_case job_id shape.
    expect(result).toEqual({ jobId: 'job-9' });
  });

  it('throws a descriptive error on a non-ok response', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ error: 'bad pack' }, 400));
    await expect(installModelPack(new File(['x'], 'm.zip'))).rejects.toThrow(/400/);
  });
});

describe('installModelFromHf', () => {
  it('POSTs the JSON body to /api/models/install and returns the jobId', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ jobId: 'job-hf' }, 202));

    const result = await installModelFromHf({
      hfRepoId: 'razhan/whisper-base-sdh',
      stage: 'ortho',
      format: 'hf-transformers',
      name: 'Razhan ORTH',
    });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/models/install');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      hfRepoId: 'razhan/whisper-base-sdh',
      stage: 'ortho',
      format: 'hf-transformers',
      name: 'Razhan ORTH',
    });
    expect(result).toEqual({ jobId: 'job-hf' });
  });
});

describe('deleteModel', () => {
  it('DELETEs /api/models/{id}', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true, id: 'user-x' }));

    const result = await deleteModel('user-x');

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/models/user-x');
    expect(init?.method).toBe('DELETE');
    expect(result).toEqual({ ok: true, id: 'user-x' });
  });
});

describe('getModelBinding', () => {
  it('GETs /api/models/binding and normalizes missing stages to null', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ stt: 'model-a' }));

    const binding = await getModelBinding();

    expect(fetchSpy.mock.calls[0][0]).toBe('/api/models/binding');
    expect(binding).toEqual({ stt: 'model-a', ipa: null, ortho: null });
  });
});

describe('setModelBinding', () => {
  it('POSTs {stage, modelId} and returns the updated binding', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ stt: 'model-a', ipa: null, ortho: null }),
    );

    const binding = await setModelBinding('stt', 'model-a');

    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/models/binding');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ stage: 'stt', modelId: 'model-a' });
    expect(binding).toEqual({ stt: 'model-a', ipa: null, ortho: null });
  });

  it('sends modelId: null to clear a binding', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ stt: null, ipa: null, ortho: null }));

    await setModelBinding('ipa', null);

    expect(JSON.parse(fetchSpy.mock.calls[0][1]?.body as string)).toEqual({
      stage: 'ipa',
      modelId: null,
    });
  });
});
