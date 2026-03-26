(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;

  const MODULE_TAG = '[video-sync-panel]';
  const CONTAINER_ID = 'parse-video-sync';
  const STYLE_ID = 'parse-video-sync-panel-styles';

  const API_START_URL = '/api/video-sync';
  const API_STATUS_BASE = '/api/video-sync/status/';

  const POLL_INTERVAL_MS = 2000;
  const MAX_POLL_ATTEMPTS = 300;

  const STANDARD_FPS = [24, 25, 29.97, 30, 50, 59.94, 60, 120];

  const FINE_TUNE_MIN_SEC = -30;
  const FINE_TUNE_MAX_SEC = 30;
  const FINE_TUNE_STEP_SEC = 0.1;
  const SLIDER_STEP_SEC = 0.01;

  const state = {
    initialized: false,
    listenersBound: false,

    containerEl: null,
    rootEl: null,

    titleEl: null,
    statusValueEl: null,
    statusHintEl: null,
    messageEl: null,

    chooseVideoBtnEl: null,
    videoFileInputEl: null,
    videoFileNameEl: null,
    fpsSelectEl: null,
    autoSyncBtnEl: null,

    offsetSliderEl: null,
    offsetValueEl: null,
    driftValueEl: null,
    fineMinusBtnEl: null,
    finePlusBtnEl: null,
    lockBtnEl: null,

    currentSpeaker: null,
    currentConceptId: null,
    currentAudioFile: null,

    selectedVideoFile: '',
    selectedFps: 60,

    baseOffsetSec: 0,
    driftRate: 0,
    method: 'fft_auto',
    aiVerified: false,
    confidence: null,
    manualAdjustmentSec: 0,

    hasSyncResult: false,
    isSyncing: false,
    isLocked: false,
    isOpen: false,

    pollToken: 0,
  };

  function logError() {
    const args = Array.prototype.slice.call(arguments);
    args.unshift(MODULE_TAG);
    console.error.apply(console, args);
  }

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function toFiniteNumber(value, fallback) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function almostEqual(left, right, epsilon) {
    const eps = epsilon == null ? 0.0001 : epsilon;
    return Math.abs(left - right) <= eps;
  }

  function isNonEmptyString(value) {
    return typeof value === 'string' && value.trim().length > 0;
  }

  function toLowerString(value) {
    return String(value || '').trim().toLowerCase();
  }

  function toDisplayFps(value) {
    const fps = toFiniteNumber(value, null);
    if (!Number.isFinite(fps)) return '';
    if (almostEqual(fps, Math.round(fps))) {
      return String(Math.round(fps));
    }
    return fps.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  }

  function toStatusHintText() {
    if (state.isSyncing) {
      return 'Auto-sync in progress';
    }
    if (state.isLocked) {
      return 'Sync locked for this speaker';
    }
    if (state.hasSyncResult) {
      return 'Result ready - review and lock';
    }
    return 'Run auto-sync or load a locked sync';
  }

  function formatSeconds(value) {
    const sec = toFiniteNumber(value, 0);
    return sec.toFixed(3) + 's';
  }

  function formatSignedSeconds(value) {
    const sec = toFiniteNumber(value, 0);
    const sign = sec > 0 ? '+' : '';
    return sign + sec.toFixed(1) + 's';
  }

  function formatDrift(value) {
    const drift = toFiniteNumber(value, 0);
    return drift.toFixed(3) + ' s/min';
  }

  function finalOffsetSec() {
    return toFiniteNumber(state.baseOffsetSec, 0) + toFiniteNumber(state.manualAdjustmentSec, 0);
  }

  function nextPollToken() {
    state.pollToken += 1;
    return state.pollToken;
  }

  function isPollTokenActive(token) {
    return token === state.pollToken;
  }

  function cancelPolling() {
    nextPollToken();
    state.isSyncing = false;
  }

  function pause(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.parse-video-sync-panel{margin-top:12px;border:1px solid #d6dee9;border-radius:12px;background:linear-gradient(180deg,#ffffff,#f7fafc);box-shadow:0 6px 18px rgba(15,23,42,0.06);overflow:hidden;}',
      '.parse-video-sync-panel.hidden{display:none !important;}',
      '.parse-video-sync-panel__header{padding:12px 14px;border-bottom:1px solid #e3eaf2;background:rgba(255,255,255,0.9);}',
      '.parse-video-sync-panel__title{margin:0;font-size:15px;line-height:1.3;font-weight:700;color:#0f172a;}',
      '.parse-video-sync-panel__status{margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px;color:#334155;}',
      '.parse-video-sync-panel__status-value{font-weight:700;}',
      '.parse-video-sync-panel__status-hint{font-size:12px;color:#64748b;}',
      '.parse-video-sync-panel__body{padding:12px 14px;display:flex;flex-direction:column;gap:12px;}',
      '.parse-video-sync-panel__row{display:grid;grid-template-columns:90px minmax(0,1fr);gap:10px;align-items:center;}',
      '.parse-video-sync-panel__label{font-size:13px;font-weight:600;color:#334155;}',
      '.parse-video-sync-panel__video-picker{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',
      '.parse-video-sync-panel__filename{font-size:12px;color:#0f172a;overflow-wrap:anywhere;}',
      '.parse-video-sync-panel__input, .parse-video-sync-panel__select{width:100%;min-width:0;padding:8px 10px;border:1px solid #c7d3e2;border-radius:8px;background:#fff;color:#0f172a;font:inherit;}',
      '.parse-video-sync-panel__select:focus, .parse-video-sync-panel__input:focus{outline:none;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,0.2);}',
      '.parse-video-sync-panel__btn{border:1px solid transparent;border-radius:8px;background:#fff;color:#0f172a;padding:8px 12px;font:inherit;cursor:pointer;}',
      '.parse-video-sync-panel__btn:disabled{opacity:0.55;cursor:not-allowed;}',
      '.parse-video-sync-panel__btn--pick{border-color:#c2d0df;background:#ffffff;}',
      '.parse-video-sync-panel__btn--sync{justify-self:flex-start;background:#1f6feb;border-color:#1f6feb;color:#fff;font-weight:600;}',
      '.parse-video-sync-panel__btn--sync:hover:not(:disabled){background:#195fc7;}',
      '.parse-video-sync-panel__btn--lock{justify-self:flex-start;background:#0f766e;border-color:#0f766e;color:#fff;font-weight:600;}',
      '.parse-video-sync-panel__btn--lock:hover:not(:disabled){background:#0b625c;}',
      '.parse-video-sync-panel__slider-wrap{display:flex;align-items:center;gap:10px;}',
      '.parse-video-sync-panel__slider{flex:1 1 auto;}',
      '.parse-video-sync-panel__offset-value{font-variant-numeric:tabular-nums;min-width:76px;text-align:right;color:#0f172a;font-size:13px;}',
      '.parse-video-sync-panel__drift{font-variant-numeric:tabular-nums;font-size:13px;color:#334155;}',
      '.parse-video-sync-panel__fine{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',
      '.parse-video-sync-panel__fine-btn{border-color:#c7d3e2;background:#fff;}',
      '.parse-video-sync-panel__message{min-height:1.2em;font-size:12px;color:#64748b;}',
      '.parse-video-sync-panel__message.is-error{color:#b42318;}',
      '.parse-video-sync-panel__message.is-success{color:#166534;}',
      '@media (max-width: 760px){',
      '  .parse-video-sync-panel__row{grid-template-columns:1fr;gap:6px;}',
      '  .parse-video-sync-panel__slider-wrap{align-items:stretch;flex-direction:column;}',
      '  .parse-video-sync-panel__offset-value{text-align:left;}',
      '}'
    ].join('');

    document.head.appendChild(style);
  }

  function resolveContainer(containerEl) {
    if (containerEl && containerEl.nodeType === 1) {
      if (containerEl.id === CONTAINER_ID) {
        return containerEl;
      }

      const nested = containerEl.querySelector('#' + CONTAINER_ID);
      if (nested) {
        return nested;
      }
    }

    const existing = document.getElementById(CONTAINER_ID);
    if (existing) {
      return existing;
    }

    const created = document.createElement('div');
    created.id = CONTAINER_ID;
    created.className = 'parse-video-sync hidden';

    const panelEl = document.getElementById('parse-panel') || document.body;
    panelEl.appendChild(created);

    return created;
  }

  function setMessage(text, kind) {
    if (!state.messageEl) return;

    state.messageEl.classList.remove('is-error', 'is-success');
    if (kind === 'error') {
      state.messageEl.classList.add('is-error');
    } else if (kind === 'success') {
      state.messageEl.classList.add('is-success');
    }
    state.messageEl.textContent = text || '';
  }

  function clearMessage() {
    setMessage('', null);
  }

  function setPanelVisible(visible) {
    if (!state.rootEl || !state.containerEl) return;

    state.isOpen = !!visible;
    state.rootEl.classList.toggle('hidden', !visible);
    state.rootEl.setAttribute('aria-hidden', visible ? 'false' : 'true');
    state.containerEl.classList.toggle('hidden', !visible);
  }

  function currentStatusLabel() {
    if (state.isSyncing) {
      return '🟡 Syncing...';
    }
    if (state.isLocked) {
      return '🟢 Synced';
    }
    return '🔴 Not synced';
  }

  function updateFpsOptions(selectedFps) {
    if (!state.fpsSelectEl) return;

    const requested = toFiniteNumber(selectedFps, null);
    const values = STANDARD_FPS.slice();

    if (Number.isFinite(requested)) {
      const exists = values.some(function (fps) {
        return almostEqual(fps, requested, 0.0005);
      });
      if (!exists) {
        values.push(requested);
      }
    }

    values.sort(function (left, right) {
      return left - right;
    });

    state.fpsSelectEl.innerHTML = '';
    values.forEach(function (fps) {
      const option = document.createElement('option');
      option.value = toDisplayFps(fps);
      option.textContent = toDisplayFps(fps);
      state.fpsSelectEl.appendChild(option);
    });

    const fallback = Number.isFinite(requested) ? requested : 60;
    state.selectedFps = fallback;
    state.fpsSelectEl.value = toDisplayFps(fallback);
  }

  function updateTitle() {
    if (!state.titleEl) return;

    const speakerText = state.currentSpeaker ? String(state.currentSpeaker) : '—';
    state.titleEl.textContent = '🎬 Video Sync - ' + speakerText;
  }

  function updateVideoFileDisplay() {
    if (!state.videoFileNameEl) return;

    state.videoFileNameEl.textContent = state.selectedVideoFile
      ? state.selectedVideoFile
      : 'No video selected';
  }

  function updateSyncValuesDisplay() {
    if (state.offsetSliderEl) {
      state.offsetSliderEl.value = String(clamp(state.manualAdjustmentSec, FINE_TUNE_MIN_SEC, FINE_TUNE_MAX_SEC));
    }

    if (state.offsetValueEl) {
      state.offsetValueEl.textContent = formatSeconds(finalOffsetSec());
    }

    if (state.driftValueEl) {
      state.driftValueEl.textContent = formatDrift(state.driftRate);
    }
  }

  function updateStatusDisplay() {
    if (state.statusValueEl) {
      state.statusValueEl.textContent = currentStatusLabel();
    }
    if (state.statusHintEl) {
      state.statusHintEl.textContent = toStatusHintText();
    }
  }

  function updateControlAvailability() {
    const hasVideoFile = isNonEmptyString(state.selectedVideoFile);
    const hasAudioFile = isNonEmptyString(state.currentAudioFile);
    const canAdjust = state.hasSyncResult && !state.isSyncing;

    if (state.chooseVideoBtnEl) {
      state.chooseVideoBtnEl.disabled = state.isSyncing;
    }
    if (state.fpsSelectEl) {
      state.fpsSelectEl.disabled = state.isSyncing;
    }
    if (state.autoSyncBtnEl) {
      state.autoSyncBtnEl.disabled = !(hasVideoFile && hasAudioFile) || state.isSyncing;
    }
    if (state.offsetSliderEl) {
      state.offsetSliderEl.disabled = !canAdjust;
    }
    if (state.fineMinusBtnEl) {
      state.fineMinusBtnEl.disabled = !canAdjust;
    }
    if (state.finePlusBtnEl) {
      state.finePlusBtnEl.disabled = !canAdjust;
    }
    if (state.lockBtnEl) {
      state.lockBtnEl.disabled = !hasVideoFile || !state.hasSyncResult || state.isSyncing;
    }
  }

  function render() {
    updateTitle();
    updateStatusDisplay();
    updateVideoFileDisplay();
    updateSyncValuesDisplay();
    updateControlAvailability();
  }

  function resetComputedSync() {
    state.baseOffsetSec = 0;
    state.driftRate = 0;
    state.method = 'fft_auto';
    state.aiVerified = false;
    state.confidence = null;
    state.manualAdjustmentSec = 0;
    state.hasSyncResult = false;
    state.isLocked = false;
  }

  function getSpeakerProjectEntry(speaker) {
    if (!P.project || typeof P.project !== 'object') {
      return null;
    }
    const speakers = P.project.speakers;
    if (!speakers || typeof speakers !== 'object') {
      return null;
    }
    const entry = speakers[speaker];
    return entry && typeof entry === 'object' ? entry : null;
  }

  function getSpeakerVideoEntries(speakerEntry) {
    if (!speakerEntry || !Array.isArray(speakerEntry.video_files)) {
      return [];
    }
    return speakerEntry.video_files.filter(function (item) {
      return item && typeof item === 'object';
    });
  }

  function isVideoEntrySynced(videoEntry) {
    if (!videoEntry || typeof videoEntry !== 'object') {
      return false;
    }

    const status = toLowerString(videoEntry.sync_status);
    if (status === 'synced') {
      return true;
    }

    const sync = videoEntry.sync;
    return !!(sync && typeof sync === 'object' && toLowerString(sync.status) === 'synced');
  }

  function choosePreferredVideoEntry(videoEntries) {
    if (!Array.isArray(videoEntries) || !videoEntries.length) {
      return null;
    }

    const synced = videoEntries.find(function (entry) {
      return isVideoEntrySynced(entry);
    });
    return synced || videoEntries[0] || null;
  }

  function resolvePrimaryAudioFile(speaker, preferredSourceWav) {
    if (isNonEmptyString(preferredSourceWav)) {
      return String(preferredSourceWav);
    }

    const speakerEntry = getSpeakerProjectEntry(speaker);
    if (speakerEntry && Array.isArray(speakerEntry.source_files) && speakerEntry.source_files.length) {
      const primary = speakerEntry.source_files.find(function (item) {
        return item && item.is_primary;
      }) || speakerEntry.source_files[0];

      if (primary && isNonEmptyString(primary.filename)) {
        return String(primary.filename);
      }
    }

    const srcIndexSpeaker =
      P.sourceIndex &&
      P.sourceIndex.speakers &&
      typeof P.sourceIndex.speakers === 'object'
        ? P.sourceIndex.speakers[speaker]
        : null;

    if (srcIndexSpeaker && Array.isArray(srcIndexSpeaker.source_wavs) && srcIndexSpeaker.source_wavs.length) {
      const wavEntry = srcIndexSpeaker.source_wavs.find(function (item) {
        return item && item.is_primary;
      }) || srcIndexSpeaker.source_wavs[0];

      if (wavEntry && isNonEmptyString(wavEntry.filename)) {
        return String(wavEntry.filename);
      }
    }

    return null;
  }

  function applySyncDataFromProject(videoEntry) {
    if (!videoEntry || typeof videoEntry !== 'object') {
      resetComputedSync();
      return;
    }

    const sync = videoEntry.sync && typeof videoEntry.sync === 'object' ? videoEntry.sync : {};
    const synced = isVideoEntrySynced(videoEntry);

    state.baseOffsetSec = toFiniteNumber(sync.offset_sec != null ? sync.offset_sec : sync.offsetSec, 0);
    state.driftRate = toFiniteNumber(sync.drift_rate != null ? sync.drift_rate : sync.driftRate, 0);
    state.method = isNonEmptyString(sync.method) ? String(sync.method) : 'fft_auto';
    state.aiVerified = !!(sync.ai_verified != null ? sync.ai_verified : sync.aiVerified);
    state.confidence = toFiniteNumber(sync.confidence, null);
    state.manualAdjustmentSec = clamp(
      toFiniteNumber(sync.manual_adjustment_sec != null ? sync.manual_adjustment_sec : sync.manualAdjustmentSec, 0),
      FINE_TUNE_MIN_SEC,
      FINE_TUNE_MAX_SEC
    );

    state.hasSyncResult = synced;
    state.isLocked = synced;

    if (!synced) {
      state.baseOffsetSec = 0;
      state.driftRate = 0;
      state.manualAdjustmentSec = 0;
      state.method = 'fft_auto';
      state.aiVerified = false;
      state.confidence = null;
    }
  }

  function resetForSpeaker(detail) {
    cancelPolling();
    clearMessage();

    const speaker = detail && isNonEmptyString(detail.speaker) ? String(detail.speaker) : null;
    state.currentSpeaker = speaker;
    state.currentConceptId = detail && detail.conceptId != null ? String(detail.conceptId) : null;
    state.currentAudioFile = resolvePrimaryAudioFile(speaker, detail && detail.sourceWav);

    const speakerEntry = speaker ? getSpeakerProjectEntry(speaker) : null;
    const videoEntries = getSpeakerVideoEntries(speakerEntry);
    const preferredVideo = choosePreferredVideoEntry(videoEntries);

    state.selectedVideoFile = preferredVideo && isNonEmptyString(preferredVideo.filename)
      ? String(preferredVideo.filename)
      : '';

    const preferredFps = preferredVideo ? toFiniteNumber(preferredVideo.fps, 60) : 60;
    updateFpsOptions(preferredFps);

    applySyncDataFromProject(preferredVideo);
    state.isSyncing = false;

    if (!state.currentAudioFile && speaker) {
      setMessage('No source audio found for this speaker. Auto-sync is disabled.', 'error');
    }

    if (state.isLocked) {
      setMessage('Loaded locked sync from project.json.', 'success');
    }

    setPanelVisible(!!speaker);
    render();
  }

  function clearPanel() {
    cancelPolling();
    state.currentSpeaker = null;
    state.currentConceptId = null;
    state.currentAudioFile = null;
    state.selectedVideoFile = '';
    state.selectedFps = 60;

    resetComputedSync();
    clearMessage();
    setPanelVisible(false);
    render();
  }

  function normalizeSyncResult(payload, fallbackSpeaker) {
    if (!payload || typeof payload !== 'object') {
      return null;
    }

    const offsetSec = toFiniteNumber(
      payload.offsetSec != null ? payload.offsetSec : payload.offset_sec,
      null
    );
    if (!Number.isFinite(offsetSec)) {
      return null;
    }

    const driftRate = toFiniteNumber(
      payload.driftRate != null ? payload.driftRate : payload.drift_rate,
      0
    );

    const confidence = toFiniteNumber(payload.confidence, null);

    return {
      speaker: isNonEmptyString(payload.speaker)
        ? String(payload.speaker)
        : (isNonEmptyString(fallbackSpeaker) ? String(fallbackSpeaker) : null),
      offsetSec: offsetSec,
      driftRate: driftRate,
      method: isNonEmptyString(payload.method) ? String(payload.method) : 'fft_auto',
      aiVerified: !!(payload.aiVerified != null ? payload.aiVerified : payload.ai_verified),
      confidence: confidence,
    };
  }

  function normalizeStatusPayload(payload, speaker) {
    const body = payload && typeof payload === 'object' ? payload : {};
    const status = toLowerString(body.status || body.state || body.phase);

    const progress = toFiniteNumber(
      body.progress != null
        ? body.progress
        : body.percent != null
          ? body.percent
          : body.percent_complete,
      null
    );

    const step = isNonEmptyString(body.step)
      ? String(body.step)
      : isNonEmptyString(body.phase)
        ? String(body.phase)
        : isNonEmptyString(body.stage)
          ? String(body.stage)
          : 'syncing';

    const errorMessage =
      isNonEmptyString(body.error)
        ? String(body.error)
        : isNonEmptyString(body.message) && (status === 'error' || status === 'failed')
          ? String(body.message)
          : '';

    const nestedResult =
      (body.result && typeof body.result === 'object' && body.result) ||
      (body.sync && typeof body.sync === 'object' && body.sync) ||
      (body.data && typeof body.data === 'object' && body.data) ||
      null;

    const result =
      normalizeSyncResult(nestedResult, speaker) ||
      normalizeSyncResult(body, speaker);

    const isError =
      status === 'error' ||
      status === 'failed' ||
      status === 'failure' ||
      body.success === false ||
      !!errorMessage;

    const isDone =
      !!result ||
      body.done === true ||
      body.completed === true ||
      status === 'done' ||
      status === 'completed' ||
      status === 'success';

    return {
      step: step,
      progress: progress,
      errorMessage: errorMessage,
      isError: isError,
      isDone: isDone,
      result: result,
    };
  }

  async function readJsonResponse(response) {
    const text = await response.text();
    if (!text) {
      return {};
    }

    try {
      return JSON.parse(text);
    } catch (_) {
      return { message: text };
    }
  }

  function emitProgress(step, progress) {
    const safeProgress = clamp(toFiniteNumber(progress, 0), 0, 100);
    dispatch('parse:video-sync-progress', {
      speaker: state.currentSpeaker,
      step: step || 'syncing',
      progress: safeProgress,
    });

    setMessage('Syncing: ' + (step || 'processing') + ' (' + safeProgress.toFixed(0) + '%)', null);
  }

  function applyResultAndNotify(resultDetail) {
    const detail = Object.assign({}, resultDetail);
    if (!detail.speaker) {
      detail.speaker = state.currentSpeaker;
    }
    dispatch('parse:video-sync-result', detail);
  }

  async function pollUntilDone(speaker, token) {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
      if (!isPollTokenActive(token)) {
        return;
      }

      await pause(POLL_INTERVAL_MS);
      if (!isPollTokenActive(token)) {
        return;
      }

      const statusUrl = API_STATUS_BASE + encodeURIComponent(String(speaker || ''));
      let response;
      try {
        response = await fetch(statusUrl, {
          method: 'GET',
          cache: 'no-store',
          headers: {
            Accept: 'application/json'
          }
        });
      } catch (error) {
        throw new Error('Network error while polling sync status: ' + ((error && error.message) || String(error)));
      }

      const payload = await readJsonResponse(response);

      if (!response.ok) {
        const msg = isNonEmptyString(payload.message)
          ? payload.message
          : 'HTTP ' + response.status;
        throw new Error('Status polling failed: ' + msg);
      }

      const status = normalizeStatusPayload(payload, speaker);

      if (status.isError) {
        throw new Error(status.errorMessage || 'Auto-sync failed on server.');
      }

      if (Number.isFinite(status.progress)) {
        emitProgress(status.step, status.progress);
      }

      if (status.result) {
        applyResultAndNotify(status.result);
        return;
      }

      if (status.isDone) {
        throw new Error('Auto-sync completed without a valid result payload.');
      }
    }

    throw new Error('Auto-sync status polling timed out.');
  }

  async function runAutoSync(token, payload) {
    let response;
    try {
      response = await fetch(API_START_URL, {
        method: 'POST',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json'
        },
        body: JSON.stringify(payload)
      });
    } catch (error) {
      throw new Error('Network error while starting video sync: ' + ((error && error.message) || String(error)));
    }

    const startPayload = await readJsonResponse(response);
    if (!response.ok) {
      const msg = isNonEmptyString(startPayload.message)
        ? startPayload.message
        : 'HTTP ' + response.status;
      throw new Error('Failed to start auto-sync: ' + msg);
    }

    const startStatus = normalizeStatusPayload(startPayload, payload.speaker);
    if (startStatus.isError) {
      throw new Error(startStatus.errorMessage || 'Server failed to start auto-sync.');
    }

    if (Number.isFinite(startStatus.progress)) {
      emitProgress(startStatus.step, startStatus.progress);
    }

    if (startStatus.result) {
      applyResultAndNotify(startStatus.result);
      return;
    }

    await pollUntilDone(payload.speaker, token);
  }

  function setManualAdjustment(nextValue, userInitiated) {
    const clamped = clamp(
      toFiniteNumber(nextValue, 0),
      FINE_TUNE_MIN_SEC,
      FINE_TUNE_MAX_SEC
    );
    state.manualAdjustmentSec = clamped;

    if (userInitiated && state.isLocked) {
      state.isLocked = false;
      setMessage('Adjustment changed. Lock sync to save the new values.', null);
    }

    render();
  }

  function onChooseVideoClick() {
    if (!state.videoFileInputEl || state.isSyncing) {
      return;
    }
    state.videoFileInputEl.click();
  }

  function onVideoFileInputChange(event) {
    const input = event && event.target;
    if (!input || !input.files || !input.files.length) {
      return;
    }

    const file = input.files[0];
    const name = file && isNonEmptyString(file.name) ? String(file.name) : '';
    if (!name) {
      return;
    }

    const changed = state.selectedVideoFile !== name;
    state.selectedVideoFile = name;

    if (changed) {
      resetComputedSync();
      setMessage('Video file changed. Run auto-sync to compute offset.', null);
    }

    render();
  }

  function onFpsChange(event) {
    const value = event && event.target ? event.target.value : null;
    const fps = toFiniteNumber(value, null);
    if (!Number.isFinite(fps) || fps <= 0) {
      return;
    }
    state.selectedFps = fps;
  }

  async function onAutoSyncClick() {
    if (!state.currentSpeaker || state.isSyncing) {
      return;
    }

    if (!isNonEmptyString(state.selectedVideoFile)) {
      setMessage('Select a video file before running auto-sync.', 'error');
      render();
      return;
    }

    if (!isNonEmptyString(state.currentAudioFile)) {
      setMessage('No source audio available for this speaker.', 'error');
      render();
      return;
    }

    const fps = toFiniteNumber(state.fpsSelectEl && state.fpsSelectEl.value, state.selectedFps);
    state.selectedFps = Number.isFinite(fps) && fps > 0 ? fps : 60;

    state.isSyncing = true;
    state.isLocked = false;
    state.hasSyncResult = false;
    state.manualAdjustmentSec = 0;
    clearMessage();
    render();

    const payload = {
      speaker: state.currentSpeaker,
      videoFile: state.selectedVideoFile,
      audioFile: state.currentAudioFile,
      fps: state.selectedFps,
    };

    dispatch('parse:video-sync-start', payload);

    const token = nextPollToken();
    state.isSyncing = true;

    try {
      await runAutoSync(token, payload);
    } catch (error) {
      if (!isPollTokenActive(token)) {
        return;
      }
      state.isSyncing = false;
      state.isLocked = false;
      state.hasSyncResult = false;
      setMessage((error && error.message) || 'Auto-sync failed.', 'error');
      render();
      return;
    }

    if (!isPollTokenActive(token)) {
      return;
    }

    state.isSyncing = false;
    render();
  }

  function onOffsetSliderInput(event) {
    const value = event && event.target ? event.target.value : 0;
    setManualAdjustment(value, true);
  }

  function onFineTuneMinusClick() {
    setManualAdjustment(state.manualAdjustmentSec - FINE_TUNE_STEP_SEC, true);
  }

  function onFineTunePlusClick() {
    setManualAdjustment(state.manualAdjustmentSec + FINE_TUNE_STEP_SEC, true);
  }

  function onLockSyncClick() {
    if (!state.currentSpeaker || !state.hasSyncResult || !isNonEmptyString(state.selectedVideoFile)) {
      return;
    }

    const lockDetail = {
      speaker: state.currentSpeaker,
      videoFile: state.selectedVideoFile,
      offsetSec: toFiniteNumber(state.baseOffsetSec, 0),
      driftRate: toFiniteNumber(state.driftRate, 0),
      manualAdjustmentSec: clamp(
        toFiniteNumber(state.manualAdjustmentSec, 0),
        FINE_TUNE_MIN_SEC,
        FINE_TUNE_MAX_SEC
      ),
      fps: toFiniteNumber(state.fpsSelectEl && state.fpsSelectEl.value, state.selectedFps),
    };

    dispatch('parse:video-sync-locked', lockDetail);
    state.isLocked = true;
    state.isSyncing = false;
    setMessage('Sync locked. Saving to project config...', 'success');
    render();
  }

  function onPanelOpen(event) {
    const detail = (event && event.detail) || {};
    resetForSpeaker(detail);
  }

  function onPanelClose(event) {
    const detail = (event && event.detail) || {};
    if (detail.speaker && state.currentSpeaker && String(detail.speaker) !== String(state.currentSpeaker)) {
      return;
    }
    clearPanel();
  }

  function onVideoSyncResult(event) {
    const detail = (event && event.detail) || {};
    const normalized = normalizeSyncResult(detail, state.currentSpeaker);
    if (!normalized) {
      return;
    }

    if (state.currentSpeaker && normalized.speaker && normalized.speaker !== state.currentSpeaker) {
      return;
    }

    state.baseOffsetSec = normalized.offsetSec;
    state.driftRate = normalized.driftRate;
    state.method = normalized.method;
    state.aiVerified = normalized.aiVerified;
    state.confidence = normalized.confidence;
    state.manualAdjustmentSec = 0;
    state.hasSyncResult = true;
    state.isSyncing = false;
    state.isLocked = false;

    const confidenceText = Number.isFinite(state.confidence)
      ? state.confidence.toFixed(2)
      : 'n/a';
    const verificationText = state.aiVerified ? 'AI verified' : 'AI not verified';

    setMessage(
      'Auto-sync complete (' + state.method + ', ' + verificationText + ', confidence ' + confidenceText + '). Review and lock.',
      'success'
    );
    render();
  }

  function onIoComplete(event) {
    const detail = (event && event.detail) || {};
    if (toLowerString(detail.operation) !== 'export') {
      return;
    }

    const format = toLowerString(detail.format);
    if (format.indexOf('segment') === -1) {
      return;
    }

    if (detail.success) {
      setMessage(detail.message || 'Segment export completed.', 'success');
    } else {
      setMessage(detail.message || 'Segment export failed.', 'error');
    }
  }

  function buildUiShell() {
    if (!state.containerEl) {
      return;
    }

    state.containerEl.innerHTML = '';

    const root = document.createElement('section');
    root.className = 'parse-video-sync-panel hidden';
    root.setAttribute('aria-hidden', 'true');

    const headerEl = document.createElement('div');
    headerEl.className = 'parse-video-sync-panel__header';

    const titleEl = document.createElement('h3');
    titleEl.className = 'parse-video-sync-panel__title';
    titleEl.textContent = '🎬 Video Sync - —';

    const statusLineEl = document.createElement('div');
    statusLineEl.className = 'parse-video-sync-panel__status';

    const statusValueEl = document.createElement('span');
    statusValueEl.className = 'parse-video-sync-panel__status-value';
    statusValueEl.textContent = '🔴 Not synced';

    const statusHintEl = document.createElement('span');
    statusHintEl.className = 'parse-video-sync-panel__status-hint';
    statusHintEl.textContent = '';

    statusLineEl.appendChild(statusValueEl);
    statusLineEl.appendChild(statusHintEl);
    headerEl.appendChild(titleEl);
    headerEl.appendChild(statusLineEl);

    const bodyEl = document.createElement('div');
    bodyEl.className = 'parse-video-sync-panel__body';

    const videoRowEl = document.createElement('div');
    videoRowEl.className = 'parse-video-sync-panel__row';

    const videoLabelEl = document.createElement('div');
    videoLabelEl.className = 'parse-video-sync-panel__label';
    videoLabelEl.textContent = 'Video file:';

    const videoPickerEl = document.createElement('div');
    videoPickerEl.className = 'parse-video-sync-panel__video-picker';

    const chooseVideoBtnEl = document.createElement('button');
    chooseVideoBtnEl.type = 'button';
    chooseVideoBtnEl.className = 'parse-video-sync-panel__btn parse-video-sync-panel__btn--pick';
    chooseVideoBtnEl.textContent = 'Choose file';

    const videoFileNameEl = document.createElement('span');
    videoFileNameEl.className = 'parse-video-sync-panel__filename';
    videoFileNameEl.textContent = 'No video selected';

    const videoFileInputEl = document.createElement('input');
    videoFileInputEl.type = 'file';
    videoFileInputEl.accept = 'video/*';
    videoFileInputEl.hidden = true;

    videoPickerEl.appendChild(chooseVideoBtnEl);
    videoPickerEl.appendChild(videoFileNameEl);
    videoPickerEl.appendChild(videoFileInputEl);

    videoRowEl.appendChild(videoLabelEl);
    videoRowEl.appendChild(videoPickerEl);

    const fpsRowEl = document.createElement('div');
    fpsRowEl.className = 'parse-video-sync-panel__row';

    const fpsLabelEl = document.createElement('div');
    fpsLabelEl.className = 'parse-video-sync-panel__label';
    fpsLabelEl.textContent = 'FPS:';

    const fpsSelectEl = document.createElement('select');
    fpsSelectEl.className = 'parse-video-sync-panel__select';
    fpsSelectEl.setAttribute('aria-label', 'Video FPS');

    fpsRowEl.appendChild(fpsLabelEl);
    fpsRowEl.appendChild(fpsSelectEl);

    const autoSyncRowEl = document.createElement('div');
    autoSyncRowEl.className = 'parse-video-sync-panel__row';

    const autoSyncSpacerEl = document.createElement('div');
    autoSyncSpacerEl.className = 'parse-video-sync-panel__label';
    autoSyncSpacerEl.textContent = '';

    const autoSyncBtnEl = document.createElement('button');
    autoSyncBtnEl.type = 'button';
    autoSyncBtnEl.className = 'parse-video-sync-panel__btn parse-video-sync-panel__btn--sync';
    autoSyncBtnEl.textContent = '🔍 Auto-Sync';

    autoSyncRowEl.appendChild(autoSyncSpacerEl);
    autoSyncRowEl.appendChild(autoSyncBtnEl);

    const offsetRowEl = document.createElement('div');
    offsetRowEl.className = 'parse-video-sync-panel__row';

    const offsetLabelEl = document.createElement('div');
    offsetLabelEl.className = 'parse-video-sync-panel__label';
    offsetLabelEl.textContent = 'Offset:';

    const offsetWrapEl = document.createElement('div');
    offsetWrapEl.className = 'parse-video-sync-panel__slider-wrap';

    const offsetSliderEl = document.createElement('input');
    offsetSliderEl.className = 'parse-video-sync-panel__slider';
    offsetSliderEl.type = 'range';
    offsetSliderEl.min = String(FINE_TUNE_MIN_SEC);
    offsetSliderEl.max = String(FINE_TUNE_MAX_SEC);
    offsetSliderEl.step = String(SLIDER_STEP_SEC);
    offsetSliderEl.value = '0';
    offsetSliderEl.setAttribute('aria-label', 'Offset fine tune slider');

    const offsetValueEl = document.createElement('div');
    offsetValueEl.className = 'parse-video-sync-panel__offset-value';
    offsetValueEl.textContent = formatSeconds(0);

    offsetWrapEl.appendChild(offsetSliderEl);
    offsetWrapEl.appendChild(offsetValueEl);
    offsetRowEl.appendChild(offsetLabelEl);
    offsetRowEl.appendChild(offsetWrapEl);

    const driftRowEl = document.createElement('div');
    driftRowEl.className = 'parse-video-sync-panel__row';

    const driftLabelEl = document.createElement('div');
    driftLabelEl.className = 'parse-video-sync-panel__label';
    driftLabelEl.textContent = 'Drift:';

    const driftValueEl = document.createElement('div');
    driftValueEl.className = 'parse-video-sync-panel__drift';
    driftValueEl.textContent = formatDrift(0);

    driftRowEl.appendChild(driftLabelEl);
    driftRowEl.appendChild(driftValueEl);

    const fineRowEl = document.createElement('div');
    fineRowEl.className = 'parse-video-sync-panel__row';

    const fineLabelEl = document.createElement('div');
    fineLabelEl.className = 'parse-video-sync-panel__label';
    fineLabelEl.textContent = 'Fine-tune:';

    const fineWrapEl = document.createElement('div');
    fineWrapEl.className = 'parse-video-sync-panel__fine';

    const fineMinusBtnEl = document.createElement('button');
    fineMinusBtnEl.type = 'button';
    fineMinusBtnEl.className = 'parse-video-sync-panel__btn parse-video-sync-panel__fine-btn';
    fineMinusBtnEl.textContent = '◄ ' + formatSignedSeconds(-FINE_TUNE_STEP_SEC);

    const finePlusBtnEl = document.createElement('button');
    finePlusBtnEl.type = 'button';
    finePlusBtnEl.className = 'parse-video-sync-panel__btn parse-video-sync-panel__fine-btn';
    finePlusBtnEl.textContent = '► ' + formatSignedSeconds(FINE_TUNE_STEP_SEC);

    fineWrapEl.appendChild(fineMinusBtnEl);
    fineWrapEl.appendChild(finePlusBtnEl);

    fineRowEl.appendChild(fineLabelEl);
    fineRowEl.appendChild(fineWrapEl);

    const lockRowEl = document.createElement('div');
    lockRowEl.className = 'parse-video-sync-panel__row';

    const lockSpacerEl = document.createElement('div');
    lockSpacerEl.className = 'parse-video-sync-panel__label';
    lockSpacerEl.textContent = '';

    const lockBtnEl = document.createElement('button');
    lockBtnEl.type = 'button';
    lockBtnEl.className = 'parse-video-sync-panel__btn parse-video-sync-panel__btn--lock';
    lockBtnEl.textContent = '🔒 Lock Sync';

    lockRowEl.appendChild(lockSpacerEl);
    lockRowEl.appendChild(lockBtnEl);

    const messageEl = document.createElement('div');
    messageEl.className = 'parse-video-sync-panel__message';
    messageEl.setAttribute('aria-live', 'polite');

    bodyEl.appendChild(videoRowEl);
    bodyEl.appendChild(fpsRowEl);
    bodyEl.appendChild(autoSyncRowEl);
    bodyEl.appendChild(offsetRowEl);
    bodyEl.appendChild(driftRowEl);
    bodyEl.appendChild(fineRowEl);
    bodyEl.appendChild(lockRowEl);
    bodyEl.appendChild(messageEl);

    root.appendChild(headerEl);
    root.appendChild(bodyEl);
    state.containerEl.appendChild(root);

    state.rootEl = root;

    state.titleEl = titleEl;
    state.statusValueEl = statusValueEl;
    state.statusHintEl = statusHintEl;
    state.messageEl = messageEl;

    state.chooseVideoBtnEl = chooseVideoBtnEl;
    state.videoFileInputEl = videoFileInputEl;
    state.videoFileNameEl = videoFileNameEl;
    state.fpsSelectEl = fpsSelectEl;
    state.autoSyncBtnEl = autoSyncBtnEl;

    state.offsetSliderEl = offsetSliderEl;
    state.offsetValueEl = offsetValueEl;
    state.driftValueEl = driftValueEl;
    state.fineMinusBtnEl = fineMinusBtnEl;
    state.finePlusBtnEl = finePlusBtnEl;
    state.lockBtnEl = lockBtnEl;

    chooseVideoBtnEl.addEventListener('click', onChooseVideoClick);
    videoFileInputEl.addEventListener('change', onVideoFileInputChange);
    fpsSelectEl.addEventListener('change', onFpsChange);
    autoSyncBtnEl.addEventListener('click', onAutoSyncClick);
    offsetSliderEl.addEventListener('input', onOffsetSliderInput);
    fineMinusBtnEl.addEventListener('click', onFineTuneMinusClick);
    finePlusBtnEl.addEventListener('click', onFineTunePlusClick);
    lockBtnEl.addEventListener('click', onLockSyncClick);

    updateFpsOptions(60);
    render();
  }

  function bindGlobalListeners() {
    if (state.listenersBound) {
      return;
    }

    document.addEventListener('parse:panel-open', onPanelOpen);
    document.addEventListener('parse:panel-close', onPanelClose);
    document.addEventListener('parse:video-sync-result', onVideoSyncResult);
    document.addEventListener('parse:io-complete', onIoComplete);

    state.listenersBound = true;
  }

  function unbindGlobalListeners() {
    if (!state.listenersBound) {
      return;
    }

    document.removeEventListener('parse:panel-open', onPanelOpen);
    document.removeEventListener('parse:panel-close', onPanelClose);
    document.removeEventListener('parse:video-sync-result', onVideoSyncResult);
    document.removeEventListener('parse:io-complete', onIoComplete);

    state.listenersBound = false;
  }

  /**
   * Initialize the video-sync panel module.
   * @param {HTMLElement} containerEl optional mount root
   * @returns {object} module public API
   */
  function init(containerEl) {
    if (state.initialized) {
      return P.modules.videoSync;
    }

    ensureStyles();

    state.containerEl = resolveContainer(containerEl);
    buildUiShell();
    bindGlobalListeners();

    state.initialized = true;
    setPanelVisible(false);
    render();

    return P.modules.videoSync;
  }

  /**
   * Destroy module state and listeners.
   */
  function destroy() {
    cancelPolling();
    unbindGlobalListeners();

    if (state.chooseVideoBtnEl) {
      state.chooseVideoBtnEl.removeEventListener('click', onChooseVideoClick);
    }
    if (state.videoFileInputEl) {
      state.videoFileInputEl.removeEventListener('change', onVideoFileInputChange);
    }
    if (state.fpsSelectEl) {
      state.fpsSelectEl.removeEventListener('change', onFpsChange);
    }
    if (state.autoSyncBtnEl) {
      state.autoSyncBtnEl.removeEventListener('click', onAutoSyncClick);
    }
    if (state.offsetSliderEl) {
      state.offsetSliderEl.removeEventListener('input', onOffsetSliderInput);
    }
    if (state.fineMinusBtnEl) {
      state.fineMinusBtnEl.removeEventListener('click', onFineTuneMinusClick);
    }
    if (state.finePlusBtnEl) {
      state.finePlusBtnEl.removeEventListener('click', onFineTunePlusClick);
    }
    if (state.lockBtnEl) {
      state.lockBtnEl.removeEventListener('click', onLockSyncClick);
    }

    if (state.rootEl && state.rootEl.parentNode) {
      state.rootEl.parentNode.removeChild(state.rootEl);
    }

    state.initialized = false;
    state.containerEl = null;
    state.rootEl = null;

    state.titleEl = null;
    state.statusValueEl = null;
    state.statusHintEl = null;
    state.messageEl = null;

    state.chooseVideoBtnEl = null;
    state.videoFileInputEl = null;
    state.videoFileNameEl = null;
    state.fpsSelectEl = null;
    state.autoSyncBtnEl = null;

    state.offsetSliderEl = null;
    state.offsetValueEl = null;
    state.driftValueEl = null;
    state.fineMinusBtnEl = null;
    state.finePlusBtnEl = null;
    state.lockBtnEl = null;

    state.currentSpeaker = null;
    state.currentConceptId = null;
    state.currentAudioFile = null;

    state.selectedVideoFile = '';
    state.selectedFps = 60;

    resetComputedSync();
    state.isSyncing = false;
    state.isLocked = false;
    state.isOpen = false;
  }

  function getState() {
    return {
      speaker: state.currentSpeaker,
      conceptId: state.currentConceptId,
      audioFile: state.currentAudioFile,
      videoFile: state.selectedVideoFile,
      fps: state.selectedFps,
      isOpen: state.isOpen,
      isSyncing: state.isSyncing,
      isLocked: state.isLocked,
      hasSyncResult: state.hasSyncResult,
      offsetSec: state.baseOffsetSec,
      driftRate: state.driftRate,
      manualAdjustmentSec: state.manualAdjustmentSec,
      method: state.method,
      aiVerified: state.aiVerified,
      confidence: state.confidence,
    };
  }

  P.modules.videoSync = {
    init: init,
    destroy: destroy,
    getState: getState,
  };
}());
