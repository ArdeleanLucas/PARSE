(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const MODULE_TAG = '[project-config]';
  const PROJECT_URL = '/project.json';
  const REQUIRED_PATH_KEYS = [
    'audio_original',
    'audio_working',
    'annotations',
    'exports',
    'peaks',
    'transcripts'
  ];
  const SAVE_ENDPOINTS = [
    { method: 'PUT', url: '/api/project' },
    { method: 'POST', url: '/api/project' },
    { method: 'PUT', url: '/project.json' },
    { method: 'POST', url: '/project.json' }
  ];

  let listenersBound = false;
  let saveQueue = Promise.resolve();

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function emitProjectLoaded(config) {
    emit('parse:project-loaded', {
      projectId: config.project_id,
      projectName: config.project_name,
      speakers: Object.keys(config.speakers || {}),
      language: {
        code: config.language.code,
        name: config.language.name
      }
    });
  }

  function emitProjectError(message, showOnboarding) {
    emit('parse:project-error', {
      error: message,
      showOnboarding: !!showOnboarding
    });
  }

  function makeTaggedError(kind, message, cause) {
    const err = new Error(message);
    err.kind = kind;
    if (cause) {
      err.cause = cause;
    }
    return err;
  }

  function isNonEmptyString(value) {
    return typeof value === 'string' && value.trim().length > 0;
  }

  function isPlainObject(value) {
    return value != null && typeof value === 'object' && !Array.isArray(value);
  }

  function cloneJsonValue(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function validateProjectConfig(config) {
    if (!isPlainObject(config)) {
      throw makeTaggedError('schema', 'project.json must contain a top-level object.');
    }

    if (typeof config.parse_version !== 'string') {
      throw makeTaggedError('schema', 'Missing required field: parse_version (string).');
    }

    if (!isNonEmptyString(config.project_id)) {
      throw makeTaggedError('schema', 'Missing required field: project_id (non-empty string).');
    }

    if (!isNonEmptyString(config.project_name)) {
      throw makeTaggedError('schema', 'Missing required field: project_name (non-empty string).');
    }

    if (!isPlainObject(config.language) || !isNonEmptyString(config.language.code)) {
      throw makeTaggedError('schema', 'Missing required field: language.code (non-empty string).');
    }

    if (!isNonEmptyString(config.language.name)) {
      throw makeTaggedError('schema', 'Missing required field: language.name (non-empty string).');
    }

    if (!isPlainObject(config.paths)) {
      throw makeTaggedError('schema', 'Missing required field: paths (object).');
    }

    for (let i = 0; i < REQUIRED_PATH_KEYS.length; i += 1) {
      const key = REQUIRED_PATH_KEYS[i];
      if (!Object.prototype.hasOwnProperty.call(config.paths, key)) {
        throw makeTaggedError('schema', 'Missing required field: paths.' + key + '.');
      }
      if (!isNonEmptyString(config.paths[key])) {
        throw makeTaggedError('schema', 'Invalid required field: paths.' + key + ' must be a non-empty string.');
      }
    }

    if (!isPlainObject(config.speakers)) {
      throw makeTaggedError('schema', 'Missing required field: speakers must be an object.');
    }

    if (Object.keys(config.speakers).length === 0) {
      throw makeTaggedError('schema', 'Missing required field: speakers must be a non-empty object.');
    }
  }

  async function fetchProjectConfig() {
    let response;

    try {
      response = await fetch(PROJECT_URL, {
        method: 'GET',
        cache: 'no-store',
        headers: {
          Accept: 'application/json'
        }
      });
    } catch (err) {
      throw makeTaggedError(
        'network',
        'Network error while loading /project.json: ' + ((err && err.message) || String(err)),
        err
      );
    }

    if (response.status === 404) {
      throw makeTaggedError('not_found', 'project.json not found (HTTP 404).');
    }

    if (!response.ok) {
      throw makeTaggedError(
        'http',
        'Failed to load project.json (HTTP ' + response.status + ').'
      );
    }

    const bodyText = await response.text();
    let parsed;

    try {
      parsed = JSON.parse(bodyText);
    } catch (err) {
      throw makeTaggedError(
        'malformed_json',
        'Malformed JSON in project.json: ' + ((err && err.message) || String(err)),
        err
      );
    }

    validateProjectConfig(parsed);
    return parsed;
  }

  function classifyLoadError(err) {
    if (!err || !err.kind) {
      return {
        message: 'Unknown error while loading project.json.',
        showOnboarding: false
      };
    }

    if (err.kind === 'not_found') {
      return {
        message: err.message,
        showOnboarding: true
      };
    }

    return {
      message: err.message,
      showOnboarding: false
    };
  }

  async function loadProject() {
    try {
      const config = await fetchProjectConfig();
      P.project = config;
      emitProjectLoaded(config);
      return config;
    } catch (err) {
      const classified = classifyLoadError(err);
      P.project = null;

      if (err && (err.kind === 'network' || err.kind === 'http' || err.kind === 'malformed_json')) {
        console.error(MODULE_TAG, err);
      }

      emitProjectError(classified.message, classified.showOnboarding);
      return null;
    }
  }

  function ensureVideoSyncListener() {
    if (listenersBound) {
      return;
    }

    document.addEventListener('parse:video-sync-locked', onVideoSyncLocked);
    listenersBound = true;
  }

  function createSyncPayload(detail) {
    const manualAdjustmentSec = Number(detail.manualAdjustmentSec);
    const offsetSec = Number(detail.offsetSec);
    const driftRate = Number(detail.driftRate);

    return {
      status: 'synced',
      offset_sec: Number.isFinite(offsetSec) ? offsetSec : 0,
      drift_rate: Number.isFinite(driftRate) ? driftRate : 0,
      method: Number.isFinite(manualAdjustmentSec) && Math.abs(manualAdjustmentSec) > 0 ? 'manual' : 'fft_auto',
      ai_verified: false,
      locked_at: new Date().toISOString(),
      manual_adjustment_sec: Number.isFinite(manualAdjustmentSec) ? manualAdjustmentSec : 0
    };
  }

  async function trySaveProjectAtEndpoint(config, endpoint) {
    const response = await fetch(endpoint.url, {
      method: endpoint.method,
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/plain, */*'
      },
      body: JSON.stringify(config, null, 2)
    });

    if (response.ok) {
      return;
    }

    let responseMessage = '';
    try {
      responseMessage = (await response.text()).trim();
    } catch (_) {
      responseMessage = '';
    }

    const suffix = responseMessage ? ' ' + responseMessage : '';
    throw makeTaggedError(
      'save_http',
      'Save failed at ' + endpoint.method + ' ' + endpoint.url + ' (HTTP ' + response.status + ').' + suffix
    );
  }

  async function saveProjectConfig(config) {
    let lastError = null;

    for (let i = 0; i < SAVE_ENDPOINTS.length; i += 1) {
      const endpoint = SAVE_ENDPOINTS[i];

      try {
        await trySaveProjectAtEndpoint(config, endpoint);
        return;
      } catch (err) {
        lastError = err;
        console.warn(MODULE_TAG, err.message);
      }
    }

    if (lastError) {
      throw lastError;
    }

    throw makeTaggedError('save', 'Unable to save project config: no save endpoint succeeded.');
  }

  async function applyVideoSyncLock(detail) {
    if (!isPlainObject(P.project)) {
      throw makeTaggedError('project', 'Cannot save video sync: project config is not loaded.');
    }

    const speaker = typeof detail.speaker === 'string' ? detail.speaker : '';
    const videoFile = typeof detail.videoFile === 'string' ? detail.videoFile : '';

    if (!speaker) {
      throw makeTaggedError('sync', 'Cannot save video sync: missing speaker ID.');
    }
    if (!videoFile) {
      throw makeTaggedError('sync', 'Cannot save video sync: missing video file name.');
    }

    const nextConfig = cloneJsonValue(P.project);
    const speakerConfig = nextConfig.speakers && nextConfig.speakers[speaker];

    if (!speakerConfig) {
      throw makeTaggedError('sync', 'Cannot save video sync: speaker "' + speaker + '" not found in project config.');
    }

    if (!Array.isArray(speakerConfig.video_files)) {
      throw makeTaggedError('sync', 'Cannot save video sync: speaker "' + speaker + '" has no video_files array.');
    }

    const videoEntry = speakerConfig.video_files.find(function (entry) {
      return entry && entry.filename === videoFile;
    });

    if (!videoEntry) {
      throw makeTaggedError(
        'sync',
        'Cannot save video sync: video file "' + videoFile + '" not found for speaker "' + speaker + '".'
      );
    }

    const fps = Number(detail.fps);

    videoEntry.sync_status = 'synced';
    if (Number.isFinite(fps) && fps > 0) {
      videoEntry.fps = fps;
    }
    videoEntry.sync = createSyncPayload(detail);

    await saveProjectConfig(nextConfig);
    P.project = nextConfig;
  }

  function onVideoSyncLocked(event) {
    const detail = (event && event.detail) || {};

    saveQueue = saveQueue
      .then(function () {
        return applyVideoSyncLock(detail);
      })
      .catch(function (err) {
        console.error(MODULE_TAG, err);
        emitProjectError(err.message || 'Failed to save video sync data.', false);
      });
  }

  /**
   * Initialize the project config module.
   * Fetches and validates /project.json, then emits lifecycle events.
   * @returns {Promise<object|null>}
   */
  function init() {
    ensureVideoSyncListener();
    return loadProject();
  }

  /**
   * Reload project.json after onboarding or external edits.
   * @returns {Promise<object|null>}
   */
  function reload() {
    ensureVideoSyncListener();
    return loadProject();
  }

  P.modules.config = {
    init: init,
    reload: reload
  };
}());
