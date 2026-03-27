(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const QUICK_TIMEOUT_MS = 30000;

  const state = {
    initialized: false,
    baseUrl: window.location.origin,
    pollers: new Map(),
    jobMeta: Object.create(null),
  };

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function trimTrailingSlash(url) {
    const text = String(url || '').trim();
    if (!text) {
      return window.location.origin;
    }
    return text.replace(/\/+$/, '');
  }

  function buildUrl(pathname) {
    const path = String(pathname || '').trim();
    if (!path) {
      return state.baseUrl;
    }

    if (/^https?:\/\//i.test(path)) {
      return path;
    }

    if (path.charAt(0) === '/') {
      return state.baseUrl + path;
    }

    return state.baseUrl + '/' + path;
  }

  function extractErrorMessage(payload, fallbackText) {
    if (payload && typeof payload === 'object') {
      if (typeof payload.error === 'string' && payload.error.trim()) {
        return payload.error.trim();
      }
      if (typeof payload.message === 'string' && payload.message.trim()) {
        return payload.message.trim();
      }
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        return payload.detail.trim();
      }
    }

    const text = String(fallbackText || '').trim();
    return text || 'Request failed.';
  }

  async function parseResponseBody(response) {
    const text = await response.text();
    if (!text) {
      return { payload: null, text: '' };
    }

    try {
      return {
        payload: JSON.parse(text),
        text: text,
      };
    } catch (_) {
      return {
        payload: null,
        text: text,
      };
    }
  }

  async function request(pathname, options) {
    const requestOptions = options || {};
    const method = String(requestOptions.method || 'GET').toUpperCase();
    const timeoutMs = Number.isFinite(Number(requestOptions.timeoutMs))
      ? Number(requestOptions.timeoutMs)
      : null;

    const headers = Object.assign(
      {
        Accept: 'application/json',
      },
      requestOptions.headers || {}
    );

    const fetchOptions = {
      method: method,
      headers: headers,
    };

    if (requestOptions.body !== undefined) {
      fetchOptions.body = JSON.stringify(requestOptions.body);
      if (!Object.prototype.hasOwnProperty.call(headers, 'Content-Type')) {
        headers['Content-Type'] = 'application/json';
      }
    }

    let timeoutId = null;
    let controller = null;

    if (timeoutMs != null && timeoutMs > 0) {
      controller = new AbortController();
      fetchOptions.signal = controller.signal;
      timeoutId = setTimeout(function () {
        controller.abort();
      }, timeoutMs);
    }

    let response;
    try {
      response = await fetch(buildUrl(pathname), fetchOptions);
    } catch (error) {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }

      if (error && error.name === 'AbortError') {
        throw new Error(method + ' ' + pathname + ' timed out after ' + timeoutMs + 'ms');
      }

      throw new Error(method + ' ' + pathname + ' failed: ' + (error && error.message ? error.message : String(error)));
    }

    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    const body = await parseResponseBody(response);

    if (!response.ok) {
      const message = extractErrorMessage(body.payload, body.text);
      const error = new Error(method + ' ' + pathname + ' failed (' + response.status + '): ' + message);
      error.status = response.status;
      error.payload = body.payload;
      throw error;
    }

    if (body.payload != null) {
      return body.payload;
    }

    return {};
  }

  function normalizeJobId(value) {
    if (value == null) return null;
    const text = String(value).trim();
    return text || null;
  }

  function extractJobId(payload) {
    const jobId = normalizeJobId(
      payload && (payload.jobId != null ? payload.jobId : payload.job_id)
    );

    if (!jobId) {
      throw new Error('Server response did not include a jobId.');
    }

    return jobId;
  }

  function asNumber(value, fallback) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function statusIsDone(rawStatus, payload) {
    const status = String(rawStatus || '').toLowerCase();

    if (payload && payload.done === true) {
      return true;
    }

    return status === 'done' ||
      status === 'completed' ||
      status === 'success' ||
      status === 'succeeded' ||
      status === 'failed' ||
      status === 'error' ||
      status === 'cancelled' ||
      status === 'canceled';
  }

  function statusIsSuccess(rawStatus, payload) {
    if (payload && payload.success != null) {
      return payload.success !== false;
    }

    const status = String(rawStatus || '').toLowerCase();
    return status === 'done' ||
      status === 'completed' ||
      status === 'success' ||
      status === 'succeeded';
  }

  function normalizeComputeType(type) {
    const text = String(type || '').trim().toLowerCase();
    if (!text) {
      throw new Error('Compute type is required.');
    }
    return text;
  }

  function pollerKey(kind, type, jobId) {
    return kind + ':' + (type || '-') + ':' + jobId;
  }

  function stopPollerByKey(key) {
    const poller = state.pollers.get(key);
    if (!poller) return;

    poller.stopped = true;
    if (poller.timerId) {
      clearInterval(poller.timerId);
    }

    state.pollers.delete(key);
  }

  function stopAllPollers() {
    const keys = Array.from(state.pollers.keys());
    for (let i = 0; i < keys.length; i += 1) {
      stopPollerByKey(keys[i]);
    }
  }

  function parsePollingType(type, jobId) {
    const raw = String(type || '').trim();
    if (!raw) {
      throw new Error('Polling type is required.');
    }

    const lower = raw.toLowerCase();
    if (lower === 'stt') {
      return {
        kind: 'stt',
        computeType: null,
      };
    }

    if (lower.indexOf('compute:') === 0) {
      return {
        kind: 'compute',
        computeType: normalizeComputeType(raw.slice(8)),
      };
    }

    if (lower === 'compute') {
      const meta = state.jobMeta[jobId];
      return {
        kind: 'compute',
        computeType: meta && meta.kind === 'compute' && meta.type ? meta.type : 'compute',
      };
    }

    return {
      kind: 'compute',
      computeType: normalizeComputeType(raw),
    };
  }

  async function pollComputeStatus(jobId, computeType) {
    const body = { jobId: jobId };
    const endpoints = [
      '/api/compute/' + encodeURIComponent(computeType) + '/status',
      '/api/' + encodeURIComponent(computeType) + '/status',
      '/api/compute/status',
    ];

    let lastError = null;

    for (let i = 0; i < endpoints.length; i += 1) {
      const endpoint = endpoints[i];

      try {
        const payload = await request(endpoint, {
          method: 'POST',
          body: i === 2 ? { jobId: jobId, type: computeType } : body,
          timeoutMs: QUICK_TIMEOUT_MS,
        });
        return payload;
      } catch (error) {
        lastError = error;
        if (error && error.status === 404) {
          continue;
        }
        throw error;
      }
    }

    if (lastError) {
      throw lastError;
    }

    throw new Error('Unable to poll compute job status.');
  }

  function extractChatRunId(payload) {
    if (!payload || typeof payload !== 'object') {
      return null;
    }

    return normalizeJobId(
      payload.runId != null ? payload.runId :
      payload.run_id != null ? payload.run_id :
      payload.jobId != null ? payload.jobId :
      payload.job_id != null ? payload.job_id :
      payload.id
    );
  }

  async function requestFirstAvailable(candidates, fallbackMessage) {
    const list = Array.isArray(candidates) ? candidates : [];
    let lastError = null;

    for (let i = 0; i < list.length; i += 1) {
      const candidate = list[i] || {};
      const pathname = String(candidate.pathname || '').trim();
      if (!pathname) {
        continue;
      }

      const options = Object.assign({}, candidate.options || {});
      try {
        return await request(pathname, options);
      } catch (error) {
        lastError = error;
        if (error && (error.status === 404 || error.status === 405)) {
          continue;
        }
        throw error;
      }
    }

    if (lastError) {
      throw lastError;
    }

    throw new Error(fallbackMessage || 'No compatible API endpoint responded.');
  }

  /**
   * Start a backend chat run.
   *
   * The request body is intentionally pass-through to keep this helper compatible
   * with incremental backend API evolution.
   *
   * @param {object=} payload Chat request payload.
   * @returns {Promise<object>} Server response payload.
   */
  function startChatRun(payload) {
    const body = payload && typeof payload === 'object' ? payload : {};

    return requestFirstAvailable(
      [
        {
          pathname: '/api/chat',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
        {
          pathname: '/api/chat/run',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
        {
          pathname: '/api/chat/start',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
      ],
      'Unable to start chat run.'
    );
  }

  /**
   * Poll chat run status.
   * @param {string} runId Backend run identifier.
   * @param {object=} opts Optional polling options merged into request body.
   * @returns {Promise<object>} Status payload.
   */
  function pollChatRunStatus(runId, opts) {
    const normalizedRunId = normalizeJobId(runId);
    if (!normalizedRunId) {
      return Promise.reject(new Error('runId is required.'));
    }

    const body = Object.assign({}, opts || {}, {
      runId: normalizedRunId,
    });

    const encodedRunId = encodeURIComponent(normalizedRunId);

    return requestFirstAvailable(
      [
        {
          pathname: '/api/chat/status',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/run/status',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/' + encodedRunId + '/status',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/status?runId=' + encodedRunId,
          options: { method: 'GET', timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/' + encodedRunId,
          options: { method: 'GET', timeoutMs: QUICK_TIMEOUT_MS },
        },
      ],
      'Unable to poll chat run status.'
    );
  }

  /**
   * Request cancellation for a chat run.
   * @param {string} runId Backend run identifier.
   * @param {object=} opts Optional cancellation options merged into request body.
   * @returns {Promise<object>} Cancellation response payload.
   */
  function cancelChatRun(runId, opts) {
    const normalizedRunId = normalizeJobId(runId);
    if (!normalizedRunId) {
      return Promise.reject(new Error('runId is required.'));
    }

    const body = Object.assign({}, opts || {}, {
      runId: normalizedRunId,
    });

    const encodedRunId = encodeURIComponent(normalizedRunId);

    return requestFirstAvailable(
      [
        {
          pathname: '/api/chat/cancel',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/run/cancel',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
        {
          pathname: '/api/chat/' + encodedRunId + '/cancel',
          options: { method: 'POST', body: body, timeoutMs: QUICK_TIMEOUT_MS },
        },
      ],
      'Unable to cancel chat run.'
    );
  }

  /**
   * Retry a previous chat run.
   * @param {string} runId Backend run identifier.
   * @param {object=} opts Optional retry options merged into request body.
   * @returns {Promise<object>} Retry response payload.
   */
  function retryChatRun(runId, opts) {
    const normalizedRunId = normalizeJobId(runId);
    if (!normalizedRunId) {
      return Promise.reject(new Error('runId is required.'));
    }

    const body = Object.assign({}, opts || {}, {
      runId: normalizedRunId,
    });

    const encodedRunId = encodeURIComponent(normalizedRunId);

    return requestFirstAvailable(
      [
        {
          pathname: '/api/chat/retry',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
        {
          pathname: '/api/chat/run/retry',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
        {
          pathname: '/api/chat/' + encodedRunId + '/retry',
          options: { method: 'POST', body: body, timeoutMs: null },
        },
      ],
      'Unable to retry chat run.'
    );
  }

  /**
   * Initialize the AI client module.
   * @param {{baseUrl?: string}=} options Optional initialization options.
   * @returns {object} Public AI client API.
   */
  function init(options) {
    if (options && typeof options === 'object' && options.baseUrl) {
      state.baseUrl = trimTrailingSlash(options.baseUrl);
    }

    if (state.initialized) {
      return P.modules.aiClient;
    }

    state.initialized = true;
    return P.modules.aiClient;
  }

  /**
   * Destroy the AI client module and stop all polling loops.
   */
  function destroy() {
    stopAllPollers();
    state.initialized = false;
  }

  /**
   * Update the AI API base URL.
   * @param {string} baseUrl Base URL for API requests.
   */
  function setBaseUrl(baseUrl) {
    state.baseUrl = trimTrailingSlash(baseUrl);
  }

  /**
   * Request a full-file STT job.
   * @param {string} speaker Speaker identifier.
   * @param {string} sourceWav Source WAV path.
   * @param {object=} opts Additional STT options.
   * @returns {Promise<string>} Resolves with created job ID.
   */
  async function requestSTT(speaker, sourceWav, opts) {
    dispatch('parse:stt-request', {
      speaker: speaker,
      sourceWav: sourceWav,
      options: opts,
    });

    const payload = await request('/api/stt', {
      method: 'POST',
      body: Object.assign({}, opts || {}, {
        speaker: speaker,
        sourceWav: sourceWav,
      }),
      timeoutMs: null,
    });

    const jobId = extractJobId(payload);
    const safeSpeaker = String(speaker || '').trim() || (payload && payload.speaker) || undefined;

    state.jobMeta[jobId] = {
      kind: 'stt',
      speaker: safeSpeaker,
    };

    dispatch('parse:stt-started', {
      jobId: jobId,
      speaker: safeSpeaker,
      estimatedDuration: payload && (payload.estimatedDuration != null ? payload.estimatedDuration : payload.estimated_duration),
    });

    return jobId;
  }

  /**
   * Poll the status of an STT job.
   * @param {string} jobId STT job ID.
   * @returns {Promise<object>} Resolves with server status payload.
   */
  function pollSTTStatus(jobId) {
    const normalizedJobId = normalizeJobId(jobId);
    if (!normalizedJobId) {
      return Promise.reject(new Error('jobId is required.'));
    }

    return request('/api/stt/status', {
      method: 'POST',
      body: { jobId: normalizedJobId },
      timeoutMs: QUICK_TIMEOUT_MS,
    });
  }

  /**
   * Request IPA transcription.
   * @param {string} text Input orthographic text.
   * @param {string} language Language code.
   * @returns {Promise<string>} Resolves with IPA string.
   */
  async function requestIPA(text, language) {
    const payload = await request('/api/ipa', {
      method: 'POST',
      body: {
        text: text,
        language: language,
      },
      timeoutMs: QUICK_TIMEOUT_MS,
    });

    if (payload && typeof payload.ipa === 'string') {
      return payload.ipa;
    }

    throw new Error('IPA response did not contain an ipa string.');
  }

  /**
   * Request AI concept suggestions.
   * @param {string} speaker Speaker identifier.
   * @param {object=} opts Additional suggestion options.
   * @returns {Promise<Array|object>} Suggestion payload from the server.
   */
  async function requestSuggestions(speaker, opts) {
    const payload = await request('/api/suggest', {
      method: 'POST',
      body: Object.assign({}, opts || {}, {
        speaker: speaker,
      }),
      timeoutMs: QUICK_TIMEOUT_MS,
    });

    if (payload && Object.prototype.hasOwnProperty.call(payload, 'suggestions')) {
      return payload.suggestions;
    }

    return payload;
  }

  /**
   * Request a compute job.
   * @param {string} type Compute type (e.g. cognates, offset, spectrograms).
   * @param {Array<string>} speakers Speaker IDs included in computation.
   * @param {Array<number>} conceptIds Concept IDs included in computation.
   * @param {object=} opts Additional compute options.
   * @returns {Promise<string>} Resolves with created job ID.
   */
  async function requestCompute(type, speakers, conceptIds, opts) {
    const computeType = normalizeComputeType(type);

    const payload = await request('/api/compute/' + encodeURIComponent(computeType), {
      method: 'POST',
      body: Object.assign({}, opts || {}, {
        type: computeType,
        speakers: Array.isArray(speakers) ? speakers : [],
        conceptIds: Array.isArray(conceptIds) ? conceptIds : [],
      }),
      timeoutMs: null,
    });

    const jobId = extractJobId(payload);

    state.jobMeta[jobId] = {
      kind: 'compute',
      type: computeType,
    };

    dispatch('parse:compute-started', {
      jobId: jobId,
      type: computeType,
      estimatedDuration: payload && (payload.estimatedDuration != null ? payload.estimatedDuration : payload.estimated_duration),
    });

    return jobId;
  }

  /**
   * Fetch enrichments data.
   * @returns {Promise<object>} Resolves with enrichments payload.
   */
  async function getEnrichments() {
    const payload = await request('/api/enrichments', {
      method: 'GET',
      timeoutMs: QUICK_TIMEOUT_MS,
    });

    if (payload && Object.prototype.hasOwnProperty.call(payload, 'enrichments')) {
      return payload.enrichments;
    }

    return payload;
  }

  /**
   * Save enrichments data.
   * @param {object} data Enrichments payload to save.
   * @returns {Promise<object>} Resolves with server response payload.
   */
  function saveEnrichments(data) {
    return request('/api/enrichments', {
      method: 'POST',
      body: data,
      timeoutMs: QUICK_TIMEOUT_MS,
    });
  }

  /**
   * Fetch server configuration.
   * @returns {Promise<object>} Resolves with config payload.
   */
  async function getConfig() {
    const payload = await request('/api/config', {
      method: 'GET',
      timeoutMs: QUICK_TIMEOUT_MS,
    });

    if (payload && Object.prototype.hasOwnProperty.call(payload, 'config')) {
      return payload.config;
    }

    return payload;
  }

  /**
   * Update server configuration.
   * @param {object} patch Partial config update payload.
   * @returns {Promise<object>} Resolves with server response payload.
   */
  function updateConfig(patch) {
    return request('/api/config', {
      method: 'PUT',
      body: patch,
      timeoutMs: QUICK_TIMEOUT_MS,
    });
  }

  /**
   * Start polling a job and emit lifecycle progress/completion events.
   * @param {string} jobId Job identifier.
   * @param {string} type Polling type: stt, compute:<type>, compute, or <computeType>.
   * @param {number=} intervalMs Polling interval in milliseconds.
   * @returns {{stop: function(): void, key: string}} Poller control handle.
   */
  function startPolling(jobId, type, intervalMs) {
    const normalizedJobId = normalizeJobId(jobId);
    if (!normalizedJobId) {
      throw new Error('jobId is required.');
    }

    const parsedType = parsePollingType(type, normalizedJobId);
    const pollInterval = Math.max(250, asNumber(intervalMs, 2000));

    const key = pollerKey(parsedType.kind, parsedType.computeType, normalizedJobId);
    stopPollerByKey(key);

    const poller = {
      key: key,
      jobId: normalizedJobId,
      kind: parsedType.kind,
      computeType: parsedType.computeType,
      intervalMs: pollInterval,
      timerId: null,
      stopped: false,
      inFlight: false,
    };

    async function tick() {
      if (poller.stopped || poller.inFlight) {
        return;
      }

      poller.inFlight = true;
      try {
        let payload;
        if (poller.kind === 'stt') {
          payload = await pollSTTStatus(poller.jobId);
        } else {
          payload = await pollComputeStatus(poller.jobId, poller.computeType);
        }

        if (poller.stopped) {
          return;
        }

        if (poller.kind === 'stt') {
          const meta = state.jobMeta[poller.jobId] || {};
          const speaker = meta.speaker || payload.speaker;
          const progress = asNumber(payload.progress, 0);
          const segmentsProcessed = asNumber(
            payload.segmentsProcessed != null ? payload.segmentsProcessed : payload.segments,
            0
          );

          dispatch('parse:stt-progress', {
            jobId: poller.jobId,
            speaker: speaker,
            progress: progress,
            segmentsProcessed: segmentsProcessed,
          });

          const status = payload.status;
          if (statusIsDone(status, payload)) {
            const success = statusIsSuccess(status, payload);
            dispatch('parse:stt-done', {
              jobId: poller.jobId,
              speaker: speaker,
              success: success,
              totalSegments: asNumber(payload.totalSegments != null ? payload.totalSegments : payload.segments, undefined),
              error: success ? undefined : extractErrorMessage(payload, ''),
            });
            stopPollerByKey(poller.key);
          }
        } else {
          const progress = asNumber(payload.progress, 0);
          dispatch('parse:compute-progress', {
            jobId: poller.jobId,
            type: poller.computeType,
            progress: progress,
            message: payload.message,
          });

          const status = payload.status;
          if (statusIsDone(status, payload)) {
            const success = statusIsSuccess(status, payload);
            dispatch('parse:compute-done', {
              jobId: poller.jobId,
              type: poller.computeType,
              success: success,
              error: success ? undefined : extractErrorMessage(payload, ''),
            });
            stopPollerByKey(poller.key);
          }
        }
      } catch (error) {
        if (!poller.stopped) {
          if (poller.kind === 'stt') {
            const meta = state.jobMeta[poller.jobId] || {};
            dispatch('parse:stt-done', {
              jobId: poller.jobId,
              speaker: meta.speaker,
              success: false,
              error: error && error.message ? error.message : String(error),
            });
          } else {
            dispatch('parse:compute-done', {
              jobId: poller.jobId,
              type: poller.computeType,
              success: false,
              error: error && error.message ? error.message : String(error),
            });
          }
          stopPollerByKey(poller.key);
        }
      } finally {
        poller.inFlight = false;
      }
    }

    poller.timerId = setInterval(function () {
      tick();
    }, pollInterval);

    state.pollers.set(key, poller);
    tick();

    return {
      key: key,
      stop: function () {
        stopPollerByKey(key);
      },
    };
  }

  /**
   * Stop a running poller.
   * @param {string} jobId Job ID.
   * @param {string} type Polling type used when starting the poller.
   */
  function stopPolling(jobId, type) {
    const normalizedJobId = normalizeJobId(jobId);
    if (!normalizedJobId) return;

    const parsedType = parsePollingType(type, normalizedJobId);
    const key = pollerKey(parsedType.kind, parsedType.computeType, normalizedJobId);
    stopPollerByKey(key);
  }

  P.modules.aiClient = {
    init: init,
    destroy: destroy,
    setBaseUrl: setBaseUrl,
    requestSTT: requestSTT,
    pollSTTStatus: pollSTTStatus,
    requestIPA: requestIPA,
    requestSuggestions: requestSuggestions,
    requestCompute: requestCompute,
    startChatRun: startChatRun,
    pollChatRunStatus: pollChatRunStatus,
    cancelChatRun: cancelChatRun,
    retryChatRun: retryChatRun,
    extractChatRunId: extractChatRunId,
    getEnrichments: getEnrichments,
    saveEnrichments: saveEnrichments,
    getConfig: getConfig,
    updateConfig: updateConfig,
    startPolling: startPolling,
    stopPolling: stopPolling,
  };
}());
