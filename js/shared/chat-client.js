(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;

  const STORAGE_VERSION = 1;
  const DEFAULT_STORAGE_KEY = 'parse.chat.session.v1';
  const DEFAULT_MAX_RUNS = 96;
  const DEFAULT_MAX_TRANSCRIPT_ITEMS = 260;
  const DEFAULT_POLL_INTERVAL_MS = 2200;

  const EVENT_SEND = 'parse:chat-send';
  const EVENT_CANCEL = 'parse:chat-cancel-run';
  const EVENT_RETRY = 'parse:chat-retry-run';
  const EVENT_LAUNCHER = 'parse:chat-launcher';
  const EVENT_DRAFT = 'parse:chat-draft';
  const EVENT_CLEAR = 'parse:chat-clear-history';

  const state = {
    initialized: false,
    options: null,
    snapshot: null,
    storage: null,
    pollers: new Map(),
    listeners: [],
    idCounter: 0,
  };

  function toObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function toArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function toString(value) {
    return String(value == null ? '' : value).trim();
  }

  function asPositiveInt(value, fallback) {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) {
      return fallback;
    }
    return Math.max(1, Math.floor(num));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function clone(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function adapters() {
    return P.modules && P.modules.chatToolAdapters ? P.modules.chatToolAdapters : null;
  }

  function normalizeStatus(rawStatus, fallback) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.normalizeStatus === 'function') {
      return moduleApi.normalizeStatus(rawStatus, fallback || 'queued');
    }

    const status = toString(rawStatus).toLowerCase();
    if (!status) {
      return toString(fallback).toLowerCase() || 'queued';
    }

    if (status === 'pending' || status === 'created' || status === 'submitted') {
      return 'queued';
    }

    if (status === 'in_progress' || status === 'in-progress' || status === 'processing') {
      return 'running';
    }

    if (status === 'complete' || status === 'completed' || status === 'done' || status === 'success') {
      return 'completed';
    }

    if (status === 'canceled') {
      return 'cancelled';
    }

    return status;
  }

  function isDoneStatus(status) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.isDoneStatus === 'function') {
      return !!moduleApi.isDoneStatus(status);
    }

    const normalized = normalizeStatus(status, 'queued');
    return normalized === 'completed' || normalized === 'error' || normalized === 'cancelled';
  }

  function isActiveStatus(status) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.isActiveStatus === 'function') {
      return !!moduleApi.isActiveStatus(status);
    }

    const normalized = normalizeStatus(status, 'queued');
    return normalized === 'queued' || normalized === 'running';
  }

  function isErrorStatus(status) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.isErrorStatus === 'function') {
      return !!moduleApi.isErrorStatus(status);
    }

    const normalized = normalizeStatus(status, 'queued');
    return normalized === 'error' || normalized === 'cancelled';
  }

  function makeId(prefix) {
    state.idCounter += 1;
    return [
      toString(prefix) || 'id',
      Date.now(),
      Math.random().toString(36).slice(2, 8),
      state.idCounter,
    ].join('-');
  }

  function defaultOptions(overrides) {
    const provided = toObject(overrides);

    return {
      storageScope: toString(provided.storageScope || provided.storage || 'session').toLowerCase(),
      storageKey: toString(provided.storageKey) || DEFAULT_STORAGE_KEY,
      maxRuns: asPositiveInt(provided.maxRuns, DEFAULT_MAX_RUNS),
      maxTranscriptItems: asPositiveInt(provided.maxTranscriptItems, DEFAULT_MAX_TRANSCRIPT_ITEMS),
      pollIntervalMs: asPositiveInt(provided.pollIntervalMs, DEFAULT_POLL_INTERVAL_MS),
      readOnly: provided.readOnly !== false,
      provider: toString(provided.provider) || 'openai',
      model: toString(provided.model) || 'gpt54',
      reasoning: toString(provided.reasoning) || 'high',
      intent: toString(provided.intent) || 'xhigh',
    };
  }

  function createEmptySnapshot() {
    const opts = state.options || defaultOptions({});
    const createdAt = nowIso();

    return {
      version: STORAGE_VERSION,
      sessionId: makeId('chat-session'),
      createdAt: createdAt,
      updatedAt: createdAt,
      readOnly: opts.readOnly !== false,
      provider: opts.provider,
      model: opts.model,
      reasoning: opts.reasoning,
      intent: opts.intent,
      launcher: {
        isOpen: false,
        unread: 0,
      },
      draft: '',
      runOrder: [],
      runsById: {},
      lastError: null,
    };
  }

  function normalizeTranscriptEntry(entry, index, runId) {
    const item = toObject(entry);
    const id = toString(item.id) || [runId || 'run', 'entry', index].join(':');

    return {
      id: id,
      type: toString(item.type) || 'tool',
      source: toString(item.source) || 'unknown',
      title: toString(item.title) || toString(item.toolName) || 'Tool',
      toolName: toString(item.toolName || item.title) || 'tool',
      status: normalizeStatus(item.status, 'queued'),
      detail: toString(item.detail),
      mutating: !!item.mutating,
      inputPreview: toString(item.inputPreview),
      outputPreview: toString(item.outputPreview),
      startedAt: toString(item.startedAt) || null,
      endedAt: toString(item.endedAt) || null,
      order: Number.isFinite(Number(item.order)) ? Number(item.order) : index,
    };
  }

  function normalizeRun(runLike, runIdHint) {
    const raw = toObject(runLike);
    const id = toString(raw.id || runIdHint || makeId('run'));
    const createdAt = toString(raw.createdAt) || nowIso();
    const updatedAt = toString(raw.updatedAt) || createdAt;

    const normalized = {
      id: id,
      serverRunId: toString(raw.serverRunId || raw.runId || raw.jobId) || null,
      status: normalizeStatus(raw.status, 'queued'),
      createdAt: createdAt,
      updatedAt: updatedAt,
      userText: toString(raw.userText || raw.prompt),
      assistantText: toString(raw.assistantText || raw.answer),
      message: toString(raw.message),
      error: toString(raw.error),
      model: toString(raw.model),
      reasoning: toString(raw.reasoning),
      intent: toString(raw.intent),
      provider: toString(raw.provider),
      canCancel: raw.canCancel == null ? false : !!raw.canCancel,
      canRetry: raw.canRetry == null ? false : !!raw.canRetry,
      progress: Number.isFinite(Number(raw.progress)) ? Number(raw.progress) : null,
      attempt: Math.max(1, asPositiveInt(raw.attempt, 1)),
      retryOf: toString(raw.retryOf) || null,
      origin: toObject(raw.origin),
      transcript: [],
    };

    const transcript = toArray(raw.transcript);
    for (let i = 0; i < transcript.length; i += 1) {
      normalized.transcript.push(normalizeTranscriptEntry(transcript[i], i, normalized.id));
    }

    if (!normalized.model) {
      normalized.model = state.options ? state.options.model : 'gpt54';
    }
    if (!normalized.reasoning) {
      normalized.reasoning = state.options ? state.options.reasoning : 'high';
    }
    if (!normalized.intent) {
      normalized.intent = state.options ? state.options.intent : 'xhigh';
    }
    if (!normalized.provider) {
      normalized.provider = state.options ? state.options.provider : 'openai';
    }

    if (isDoneStatus(normalized.status)) {
      normalized.canCancel = false;
      if (raw.canRetry == null) {
        normalized.canRetry = isErrorStatus(normalized.status) || !!normalized.error;
      }
    } else if (raw.canCancel == null) {
      normalized.canCancel = true;
    }

    return normalized;
  }

  function normalizeSnapshot(rawSnapshot) {
    const raw = toObject(rawSnapshot);
    const base = createEmptySnapshot();

    base.sessionId = toString(raw.sessionId) || base.sessionId;
    base.createdAt = toString(raw.createdAt) || base.createdAt;
    base.updatedAt = toString(raw.updatedAt) || base.updatedAt;
    base.readOnly = raw.readOnly !== false;
    base.provider = toString(raw.provider) || base.provider;
    base.model = toString(raw.model) || base.model;
    base.reasoning = toString(raw.reasoning) || base.reasoning;
    base.intent = toString(raw.intent) || base.intent;

    const launcher = toObject(raw.launcher);
    base.launcher.isOpen = !!launcher.isOpen;
    base.launcher.unread = Math.max(0, Math.floor(Number(launcher.unread) || 0));

    base.draft = toString(raw.draft);

    const runsById = toObject(raw.runsById);
    const orderIn = toArray(raw.runOrder);

    const orderOut = [];
    const normalizedRuns = {};

    for (let i = 0; i < orderIn.length; i += 1) {
      const runId = toString(orderIn[i]);
      if (!runId) {
        continue;
      }

      const normalized = normalizeRun(runsById[runId], runId);
      normalizedRuns[normalized.id] = normalized;
      orderOut.push(normalized.id);
    }

    const runKeys = Object.keys(runsById);
    for (let i = 0; i < runKeys.length; i += 1) {
      const runId = toString(runKeys[i]);
      if (!runId || normalizedRuns[runId]) {
        continue;
      }

      const normalized = normalizeRun(runsById[runId], runId);
      normalizedRuns[normalized.id] = normalized;
      orderOut.push(normalized.id);
    }

    base.runsById = normalizedRuns;
    base.runOrder = orderOut;

    const lastError = toObject(raw.lastError);
    const message = toString(lastError.message);
    if (message) {
      base.lastError = {
        message: message,
        at: toString(lastError.at) || base.updatedAt,
        action: toString(lastError.action) || null,
      };
    }

    return base;
  }

  function storageAvailable(storage) {
    if (!storage) {
      return false;
    }

    const probeKey = '__parse-chat-probe__';
    try {
      storage.setItem(probeKey, '1');
      storage.removeItem(probeKey);
      return true;
    } catch (_) {
      return false;
    }
  }

  function resolveStorage() {
    if (!state.options || state.options.storageScope === 'none') {
      return null;
    }

    const scope = state.options.storageScope;

    if (scope === 'local') {
      if (storageAvailable(window.localStorage)) {
        return window.localStorage;
      }
      return null;
    }

    if (scope === 'session') {
      if (storageAvailable(window.sessionStorage)) {
        return window.sessionStorage;
      }
      if (storageAvailable(window.localStorage)) {
        return window.localStorage;
      }
      return null;
    }

    if (storageAvailable(window.sessionStorage)) {
      return window.sessionStorage;
    }

    if (storageAvailable(window.localStorage)) {
      return window.localStorage;
    }

    return null;
  }

  function mergeTranscript(existing, incoming) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.mergeTranscriptEntries === 'function') {
      return moduleApi.mergeTranscriptEntries(existing, incoming);
    }

    const current = toArray(existing);
    const next = toArray(incoming);

    const byId = Object.create(null);
    const order = [];

    function upsert(entry, index) {
      const normalized = normalizeTranscriptEntry(entry, index, null);
      if (!byId[normalized.id]) {
        byId[normalized.id] = normalized;
        order.push(normalized.id);
        return;
      }

      byId[normalized.id] = Object.assign({}, byId[normalized.id], normalized);
    }

    for (let i = 0; i < current.length; i += 1) {
      upsert(current[i], i);
    }

    for (let i = 0; i < next.length; i += 1) {
      upsert(next[i], current.length + i);
    }

    return order.map(function (id) {
      return byId[id];
    });
  }

  function pruneHistory() {
    const maxRuns = state.options.maxRuns;
    const runOrder = state.snapshot.runOrder;

    while (runOrder.length > maxRuns) {
      const droppedRunId = runOrder.shift();
      delete state.snapshot.runsById[droppedRunId];
      stopPolling(droppedRunId);
    }

    for (let i = 0; i < runOrder.length; i += 1) {
      const runId = runOrder[i];
      const run = state.snapshot.runsById[runId];
      if (!run) continue;

      if (run.transcript.length > state.options.maxTranscriptItems) {
        run.transcript = run.transcript.slice(-state.options.maxTranscriptItems);
      }
    }
  }

  function persistSnapshot() {
    if (!state.storage || !state.options || !state.options.storageKey) {
      return;
    }

    pruneHistory();

    function buildPayload() {
      return {
        version: STORAGE_VERSION,
        sessionId: state.snapshot.sessionId,
        createdAt: state.snapshot.createdAt,
        updatedAt: state.snapshot.updatedAt,
        readOnly: state.snapshot.readOnly,
        provider: state.snapshot.provider,
        model: state.snapshot.model,
        reasoning: state.snapshot.reasoning,
        intent: state.snapshot.intent,
        launcher: {
          isOpen: !!state.snapshot.launcher.isOpen,
          unread: Math.max(0, Math.floor(Number(state.snapshot.launcher.unread) || 0)),
        },
        draft: state.snapshot.draft,
        runOrder: state.snapshot.runOrder.slice(),
        runsById: state.snapshot.runsById,
        lastError: state.snapshot.lastError,
      };
    }

    try {
      state.storage.setItem(state.options.storageKey, JSON.stringify(buildPayload()));
    } catch (_) {
      // If storage is full, aggressively trim and retry once.
      while (state.snapshot.runOrder.length > 16) {
        const dropped = state.snapshot.runOrder.shift();
        delete state.snapshot.runsById[dropped];
      }

      try {
        state.storage.setItem(state.options.storageKey, JSON.stringify(buildPayload()));
      } catch (_) {
        // If still failing, skip persistence for this update.
      }
    }
  }

  function touch() {
    state.snapshot.updatedAt = nowIso();
  }

  function emitState(reason, extra) {
    const detail = Object.assign(
      {
        reason: toString(reason) || 'update',
        state: clone(state.snapshot),
      },
      toObject(extra)
    );

    dispatch('parse:chat-state', detail);
  }

  function addListener(target, name, handler) {
    if (!target || typeof target.addEventListener !== 'function') {
      return;
    }

    target.addEventListener(name, handler);
    state.listeners.push({ target: target, name: name, handler: handler });
  }

  function removeListeners() {
    for (let i = 0; i < state.listeners.length; i += 1) {
      const item = state.listeners[i];
      item.target.removeEventListener(item.name, item.handler);
    }
    state.listeners = [];
  }

  function ensureInitialized() {
    if (!state.initialized) {
      throw new Error('chatClient.init() must be called before using chatClient methods.');
    }
  }

  function getAiClient() {
    const aiClient = P.modules && P.modules.aiClient ? P.modules.aiClient : null;
    if (!aiClient) {
      throw new Error('window.PARSE.modules.aiClient is required for chat-client.');
    }

    if (typeof aiClient.init === 'function') {
      aiClient.init();
    }

    if (typeof aiClient.startChatRun !== 'function' || typeof aiClient.pollChatRunStatus !== 'function') {
      throw new Error('ai-client chat helpers are not available (startChatRun/pollChatRunStatus).');
    }

    return aiClient;
  }

  function findLocalRunId(runRef) {
    const wanted = toString(runRef);
    if (!wanted) {
      return null;
    }

    if (state.snapshot.runsById[wanted]) {
      return wanted;
    }

    const runOrder = state.snapshot.runOrder;
    for (let i = 0; i < runOrder.length; i += 1) {
      const runId = runOrder[i];
      const run = state.snapshot.runsById[runId];
      if (!run) continue;
      if (toString(run.serverRunId) === wanted) {
        return runId;
      }
    }

    return null;
  }

  function getRun(runRef) {
    const localRunId = findLocalRunId(runRef);
    if (!localRunId) {
      return null;
    }

    return state.snapshot.runsById[localRunId] || null;
  }

  function createReadOnlyPolicyTranscript(runId) {
    const ts = nowIso();
    return {
      id: 'policy:' + runId,
      type: 'policy',
      source: 'client-policy',
      title: 'Read-only policy',
      toolName: 'policy',
      status: 'completed',
      detail: 'Assistant is read-only in MVP. It can inspect and analyze but must not overwrite annotations or project data.',
      mutating: false,
      inputPreview: '',
      outputPreview: '',
      startedAt: ts,
      endedAt: ts,
      order: -1,
    };
  }

  function buildOriginContext(rawContext) {
    const context = Object.assign({}, toObject(rawContext));

    if (!context.mode && P.mode) {
      context.mode = P.mode;
    }

    if (!context.speaker && P.currentSpeaker) {
      context.speaker = P.currentSpeaker;
    }

    if (!context.conceptId && P.currentConcept != null) {
      context.conceptId = P.currentConcept;
    }

    if (!context.selectedSpeakers && P.compareState && Array.isArray(P.compareState.selectedSpeakers)) {
      context.selectedSpeakers = P.compareState.selectedSpeakers.slice();
    }

    return context;
  }

  function createRun(userText, opts) {
    const options = toObject(opts);
    const ts = nowIso();

    const run = {
      id: makeId('run'),
      serverRunId: null,
      status: 'queued',
      createdAt: ts,
      updatedAt: ts,
      userText: toString(userText),
      assistantText: '',
      message: 'Queued',
      error: '',
      model: toString(options.model) || state.snapshot.model,
      reasoning: toString(options.reasoning) || state.snapshot.reasoning,
      intent: toString(options.intent) || state.snapshot.intent,
      provider: toString(options.provider) || state.snapshot.provider,
      canCancel: true,
      canRetry: false,
      progress: 0,
      attempt: Math.max(1, asPositiveInt(options.attempt, 1)),
      retryOf: toString(options.retryOf) || null,
      origin: buildOriginContext(options.context),
      transcript: [],
    };

    run.transcript = [createReadOnlyPolicyTranscript(run.id)];

    return run;
  }

  function addRun(run) {
    const normalized = normalizeRun(run, run && run.id);

    state.snapshot.runsById[normalized.id] = normalized;
    state.snapshot.runOrder.push(normalized.id);

    touch();
    pruneHistory();
    persistSnapshot();

    dispatch('parse:chat-run-created', {
      runId: normalized.id,
      run: clone(normalized),
    });

    emitState('run-created', { runId: normalized.id });

    return normalized.id;
  }

  function applyRunUpdate(localRunId, patch, reason) {
    const run = state.snapshot.runsById[localRunId];
    if (!run) {
      return null;
    }

    const prevStatus = run.status;
    const prevDone = isDoneStatus(prevStatus);

    const update = toObject(patch);

    if (update.runId) {
      run.serverRunId = toString(update.runId);
    }

    if (update.status) {
      run.status = normalizeStatus(update.status, run.status);
    }

    if (update.message) {
      run.message = toString(update.message);
    }

    if (update.assistantText) {
      run.assistantText = toString(update.assistantText);
    }

    if (update.error) {
      run.error = toString(update.error);
    }

    if (update.model) {
      run.model = toString(update.model);
    }

    if (update.reasoning) {
      run.reasoning = toString(update.reasoning);
    }

    if (update.intent) {
      run.intent = toString(update.intent);
    }

    if (update.progress != null && Number.isFinite(Number(update.progress))) {
      run.progress = Math.max(0, Math.min(100, Number(update.progress)));
    }

    if (update.canCancel != null) {
      run.canCancel = !!update.canCancel;
    }

    if (update.canRetry != null) {
      run.canRetry = !!update.canRetry;
    }

    if (Array.isArray(update.transcript) && update.transcript.length) {
      run.transcript = mergeTranscript(run.transcript, update.transcript);
      if (run.transcript.length > state.options.maxTranscriptItems) {
        run.transcript = run.transcript.slice(-state.options.maxTranscriptItems);
      }
    }

    if (isDoneStatus(run.status)) {
      run.canCancel = false;
      if (update.canRetry == null) {
        run.canRetry = isErrorStatus(run.status) || !!run.error;
      }
      stopPolling(localRunId);
    }

    run.updatedAt = nowIso();

    const nowDone = isDoneStatus(run.status);
    if (!prevDone && nowDone && !state.snapshot.launcher.isOpen) {
      state.snapshot.launcher.unread = Math.min(99, state.snapshot.launcher.unread + 1);
    }

    touch();
    persistSnapshot();

    dispatch('parse:chat-run-updated', {
      runId: localRunId,
      reason: toString(reason) || 'update',
      run: clone(run),
    });

    if (!prevDone && nowDone) {
      dispatch('parse:chat-run-finished', {
        runId: localRunId,
        status: run.status,
        success: run.status === 'completed' && !run.error,
        run: clone(run),
      });
    }

    emitState(toString(reason) || 'run-updated', { runId: localRunId });

    return run;
  }

  function normalizeServerPayload(payload, run) {
    const moduleApi = adapters();

    if (moduleApi && typeof moduleApi.normalizeRunPayload === 'function') {
      return moduleApi.normalizeRunPayload(payload, run, {
        runId: run && (run.serverRunId || run.id),
      });
    }

    const body = toObject(payload);

    const extractedRunId =
      toString(body.runId) ||
      toString(body.run_id) ||
      toString(body.jobId) ||
      toString(body.job_id) ||
      toString(body.id) ||
      null;

    const status = normalizeStatus(body.status || body.state || body.phase, run ? run.status : 'queued');

    const assistantText =
      toString(body.assistantText) ||
      toString(body.assistant_text) ||
      toString(body.answer) ||
      toString(toObject(body.result).text) ||
      toString(toObject(body.response).text);

    const error = toString(body.error) || toString(toObject(body.error).message);

    return {
      runId: extractedRunId,
      status: status,
      message: toString(body.message || body.detail),
      assistantText: assistantText,
      error: error,
      progress: Number.isFinite(Number(body.progress)) ? Number(body.progress) : null,
      transcript: toArray(body.transcript),
      canCancel: body.canCancel,
      canRetry: body.canRetry,
      model: toString(body.model),
      reasoning: toString(body.reasoning),
      intent: toString(body.intent),
    };
  }

  function buildConversationHistory(limit, excludeRunId) {
    const max = Math.max(1, asPositiveInt(limit, 24));
    const rows = [];

    for (let i = 0; i < state.snapshot.runOrder.length; i += 1) {
      const runId = state.snapshot.runOrder[i];
      if (excludeRunId && runId === excludeRunId) {
        continue;
      }

      const run = state.snapshot.runsById[runId];
      if (!run) {
        continue;
      }

      if (run.userText) {
        rows.push({ role: 'user', content: run.userText });
      }

      if (run.assistantText) {
        rows.push({ role: 'assistant', content: run.assistantText });
      }
    }

    if (rows.length <= max) {
      return rows;
    }

    return rows.slice(rows.length - max);
  }

  function buildRequestPayload(run) {
    return {
      sessionId: state.snapshot.sessionId,
      message: run.userText,
      history: buildConversationHistory(32, run.id),
      readOnly: state.snapshot.readOnly !== false,
      mode: state.snapshot.readOnly !== false ? 'read-only' : 'default',
      provider: run.provider,
      model: run.model,
      reasoning: run.reasoning,
      intent: run.intent,
      context: clone(run.origin),
      retryOf: run.retryOf || undefined,
    };
  }

  function stopPolling(localRunId) {
    const poller = state.pollers.get(localRunId);
    if (!poller) {
      return;
    }

    if (poller.timerId) {
      window.clearInterval(poller.timerId);
    }

    poller.stopped = true;
    state.pollers.delete(localRunId);
  }

  function stopAllPolling() {
    const ids = Array.from(state.pollers.keys());
    for (let i = 0; i < ids.length; i += 1) {
      stopPolling(ids[i]);
    }
  }

  function startPolling(localRunId) {
    const run = state.snapshot.runsById[localRunId];
    if (!run) {
      return;
    }

    if (isDoneStatus(run.status)) {
      return;
    }

    const runToken = toString(run.serverRunId || run.id);
    if (!runToken || runToken.indexOf('run-') !== 0 && runToken.indexOf('chat-') !== 0 && runToken.indexOf('job-') !== 0 && runToken.indexOf('local-') === 0) {
      // If we only have a local temporary id, backend polling is impossible.
      return;
    }

    stopPolling(localRunId);

    const poller = {
      runId: localRunId,
      timerId: null,
      inFlight: false,
      stopped: false,
      failures: 0,
    };

    async function tick() {
      if (poller.stopped || poller.inFlight) {
        return;
      }

      const currentRun = state.snapshot.runsById[localRunId];
      if (!currentRun || isDoneStatus(currentRun.status)) {
        stopPolling(localRunId);
        return;
      }

      poller.inFlight = true;
      try {
        const aiClient = getAiClient();
        const payload = await aiClient.pollChatRunStatus(
          toString(currentRun.serverRunId || currentRun.id),
          { sessionId: state.snapshot.sessionId }
        );

        poller.failures = 0;

        const normalized = normalizeServerPayload(payload, currentRun);
        applyRunUpdate(localRunId, normalized, 'poll');
      } catch (error) {
        poller.failures += 1;

        if (poller.failures >= 4) {
          applyRunUpdate(
            localRunId,
            {
              status: 'error',
              error: toString(error && error.message) || 'Polling failed.',
              canCancel: false,
              canRetry: true,
              transcript: [
                {
                  id: 'poll-error:' + makeId('entry'),
                  type: 'tool',
                  source: 'client-poll',
                  title: 'Polling error',
                  toolName: 'poll',
                  status: 'error',
                  detail: toString(error && error.message) || 'Unable to poll chat run status.',
                  mutating: false,
                  startedAt: nowIso(),
                  endedAt: nowIso(),
                  order: Number.MAX_SAFE_INTEGER,
                },
              ],
            },
            'poll-failed'
          );
        }
      } finally {
        poller.inFlight = false;
      }
    }

    poller.timerId = window.setInterval(tick, state.options.pollIntervalMs);
    state.pollers.set(localRunId, poller);
    tick();
  }

  function resumePolling() {
    const runOrder = state.snapshot.runOrder;
    for (let i = 0; i < runOrder.length; i += 1) {
      const runId = runOrder[i];
      const run = state.snapshot.runsById[runId];
      if (!run) continue;
      if (!isActiveStatus(run.status)) continue;
      if (!toString(run.serverRunId)) continue;

      startPolling(runId);
    }
  }

  function setLastError(message, action) {
    const msg = toString(message);
    if (!msg) {
      state.snapshot.lastError = null;
      return;
    }

    state.snapshot.lastError = {
      message: msg,
      action: toString(action) || null,
      at: nowIso(),
    };
  }

  /**
   * Send a new chat message and start a backend run.
   * @param {string} text User input text.
   * @param {object=} opts Optional run metadata.
   * @returns {Promise<string>} Local run id.
   */
  async function sendMessage(text, opts) {
    ensureInitialized();

    const messageText = toString(text);
    if (!messageText) {
      throw new Error('Message text is required.');
    }

    const run = createRun(messageText, opts);
    const localRunId = addRun(run);

    state.snapshot.draft = '';
    setLastError('', null);
    touch();
    persistSnapshot();
    emitState('draft-cleared', { runId: localRunId });

    applyRunUpdate(localRunId, {
      status: 'running',
      message: 'Submitting request…',
      canCancel: true,
      canRetry: false,
      progress: 2,
    }, 'start-request');

    try {
      const aiClient = getAiClient();
      const response = await aiClient.startChatRun(buildRequestPayload(run));
      const normalized = normalizeServerPayload(response, getRun(localRunId));

      const responseRunId =
        normalized.runId ||
        (typeof aiClient.extractChatRunId === 'function' ? aiClient.extractChatRunId(response) : null);

      if (responseRunId) {
        normalized.runId = responseRunId;
      }

      const updatedRun = applyRunUpdate(localRunId, normalized, 'start-response');

      if (updatedRun && !isDoneStatus(updatedRun.status)) {
        if (toString(updatedRun.serverRunId)) {
          startPolling(localRunId);
        } else {
          applyRunUpdate(
            localRunId,
            {
              status: 'error',
              error: 'Chat run started without a run ID; cannot poll status.',
              canCancel: false,
              canRetry: true,
              transcript: [
                {
                  id: 'start-missing-run-id:' + makeId('entry'),
                  type: 'tool',
                  source: 'client-start',
                  title: 'Run ID missing',
                  toolName: 'chat',
                  status: 'error',
                  detail: 'Backend response did not include runId/jobId.',
                  mutating: false,
                  startedAt: nowIso(),
                  endedAt: nowIso(),
                  order: Number.MAX_SAFE_INTEGER,
                },
              ],
            },
            'start-missing-run-id'
          );
        }
      }

      return localRunId;
    } catch (error) {
      const errorMessage = toString(error && error.message) || 'Failed to start chat run.';

      applyRunUpdate(
        localRunId,
        {
          status: 'error',
          error: errorMessage,
          canCancel: false,
          canRetry: true,
          transcript: [
            {
              id: 'start-error:' + makeId('entry'),
              type: 'tool',
              source: 'client-start',
              title: 'Start failed',
              toolName: 'chat',
              status: 'error',
              detail: errorMessage,
              mutating: false,
              startedAt: nowIso(),
              endedAt: nowIso(),
              order: Number.MAX_SAFE_INTEGER,
            },
          ],
        },
        'start-error'
      );

      setLastError(errorMessage, 'send');
      touch();
      persistSnapshot();
      emitState('error', { runId: localRunId });

      throw error;
    }
  }

  /**
   * Cancel an in-flight run.
   * @param {string} runRef Local run id or backend run id.
   * @returns {Promise<boolean>} True if cancellation was applied.
   */
  async function cancelRun(runRef) {
    ensureInitialized();

    const localRunId = findLocalRunId(runRef);
    if (!localRunId) {
      return false;
    }

    const run = getRun(localRunId);
    if (!run || isDoneStatus(run.status)) {
      return false;
    }

    const runToken = toString(run.serverRunId || run.id);

    try {
      const aiClient = getAiClient();
      const payload = await aiClient.cancelChatRun(runToken, {
        sessionId: state.snapshot.sessionId,
      });

      const normalized = normalizeServerPayload(payload, run);
      normalized.status = normalizeStatus(normalized.status || 'cancelled', 'cancelled');
      normalized.canCancel = false;
      normalized.canRetry = true;

      applyRunUpdate(localRunId, normalized, 'cancel-response');
      return true;
    } catch (error) {
      const statusCode = Number(error && error.status);
      if (statusCode === 404 || statusCode === 405) {
        applyRunUpdate(
          localRunId,
          {
            status: 'cancelled',
            message: 'Cancelled locally (backend cancel endpoint unavailable).',
            canCancel: false,
            canRetry: true,
            transcript: [
              {
                id: 'cancel-local:' + makeId('entry'),
                type: 'tool',
                source: 'client-cancel',
                title: 'Cancelled locally',
                toolName: 'chat',
                status: 'cancelled',
                detail: 'Backend cancel endpoint not available; polling stopped in client.',
                mutating: false,
                startedAt: nowIso(),
                endedAt: nowIso(),
                order: Number.MAX_SAFE_INTEGER,
              },
            ],
          },
          'cancel-local'
        );

        stopPolling(localRunId);
        return true;
      }

      const message = toString(error && error.message) || 'Cancel request failed.';
      setLastError(message, 'cancel');

      applyRunUpdate(
        localRunId,
        {
          transcript: [
            {
              id: 'cancel-error:' + makeId('entry'),
              type: 'tool',
              source: 'client-cancel',
              title: 'Cancel failed',
              toolName: 'chat',
              status: 'error',
              detail: message,
              mutating: false,
              startedAt: nowIso(),
              endedAt: nowIso(),
              order: Number.MAX_SAFE_INTEGER,
            },
          ],
        },
        'cancel-error'
      );

      throw error;
    }
  }

  /**
   * Retry a previous run by resubmitting its original user prompt.
   * @param {string} runRef Local run id or backend run id.
   * @param {object=} opts Optional retry overrides.
   * @returns {Promise<string>} New local run id.
   */
  async function retryRun(runRef, opts) {
    ensureInitialized();

    const original = getRun(runRef);
    if (!original) {
      throw new Error('Run not found.');
    }

    const retryOpts = Object.assign({}, toObject(opts), {
      retryOf: original.id,
      attempt: Math.max(1, Number(original.attempt || 1) + 1),
      context: Object.assign({}, toObject(original.origin), toObject(opts).context),
      model: toString(toObject(opts).model) || original.model,
      reasoning: toString(toObject(opts).reasoning) || original.reasoning,
      intent: toString(toObject(opts).intent) || original.intent,
      provider: toString(toObject(opts).provider) || original.provider,
    });

    return sendMessage(original.userText, retryOpts);
  }

  function setLauncherOpen(isOpen) {
    ensureInitialized();

    const open = !!isOpen;
    state.snapshot.launcher.isOpen = open;
    if (open) {
      state.snapshot.launcher.unread = 0;
    }

    touch();
    persistSnapshot();
    emitState('launcher', { open: open });
  }

  function toggleLauncher() {
    ensureInitialized();
    const next = !state.snapshot.launcher.isOpen;
    setLauncherOpen(next);
    return next;
  }

  function setDraft(text) {
    ensureInitialized();

    const draftText = String(text == null ? '' : text);
    if (state.snapshot.draft === draftText) {
      return;
    }

    state.snapshot.draft = draftText;
    touch();
    persistSnapshot();
    emitState('draft');
  }

  function clearHistory() {
    ensureInitialized();

    stopAllPolling();

    state.snapshot.runOrder = [];
    state.snapshot.runsById = {};
    state.snapshot.launcher.unread = 0;
    state.snapshot.draft = '';
    state.snapshot.lastError = null;

    touch();
    persistSnapshot();

    dispatch('parse:chat-history-cleared', {});
    emitState('clear-history');
  }

  function getState() {
    ensureInitialized();
    return clone(state.snapshot);
  }

  function onSendEvent(event) {
    const detail = toObject(event && event.detail);

    sendMessage(detail.text, detail).catch(function (error) {
      dispatch('parse:chat-error', {
        action: 'send',
        message: toString(error && error.message) || 'Failed to send chat message.',
      });
    });
  }

  function onCancelEvent(event) {
    const detail = toObject(event && event.detail);

    cancelRun(detail.runId || detail.id).catch(function (error) {
      dispatch('parse:chat-error', {
        action: 'cancel',
        runId: detail.runId || detail.id || null,
        message: toString(error && error.message) || 'Failed to cancel run.',
      });
    });
  }

  function onRetryEvent(event) {
    const detail = toObject(event && event.detail);

    retryRun(detail.runId || detail.id, detail).catch(function (error) {
      dispatch('parse:chat-error', {
        action: 'retry',
        runId: detail.runId || detail.id || null,
        message: toString(error && error.message) || 'Failed to retry run.',
      });
    });
  }

  function onLauncherEvent(event) {
    const detail = toObject(event && event.detail);

    if (detail.toggle) {
      toggleLauncher();
      return;
    }

    if (typeof detail.open === 'boolean') {
      setLauncherOpen(detail.open);
    }
  }

  function onDraftEvent(event) {
    const detail = toObject(event && event.detail);
    setDraft(detail.text);
  }

  function onClearEvent() {
    clearHistory();
  }

  function bindActionEvents() {
    addListener(document, EVENT_SEND, onSendEvent);
    addListener(document, EVENT_CANCEL, onCancelEvent);
    addListener(document, EVENT_RETRY, onRetryEvent);
    addListener(document, EVENT_LAUNCHER, onLauncherEvent);
    addListener(document, EVENT_DRAFT, onDraftEvent);
    addListener(document, EVENT_CLEAR, onClearEvent);
  }

  /**
   * Initialize chat-client state, storage, and action listeners.
   * @param {object=} options Optional initialization overrides.
   * @returns {object} Public module API.
   */
  function init(options) {
    if (state.initialized) {
      return P.modules.chatClient;
    }

    state.options = defaultOptions(options);
    state.storage = resolveStorage();

    if (state.storage && state.options.storageKey) {
      try {
        const raw = state.storage.getItem(state.options.storageKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          state.snapshot = normalizeSnapshot(parsed);
        }
      } catch (_) {
        state.snapshot = null;
      }
    }

    if (!state.snapshot) {
      state.snapshot = createEmptySnapshot();
    }

    state.snapshot.readOnly = state.options.readOnly !== false;
    state.snapshot.provider = state.options.provider;
    state.snapshot.model = state.options.model;
    state.snapshot.reasoning = state.options.reasoning;
    state.snapshot.intent = state.options.intent;

    state.initialized = true;

    bindActionEvents();
    resumePolling();

    touch();
    persistSnapshot();
    emitState('init');

    return P.modules.chatClient;
  }

  /**
   * Destroy the chat client module and stop active pollers.
   */
  function destroy() {
    if (!state.initialized) {
      return;
    }

    stopAllPolling();
    removeListeners();

    state.initialized = false;
    state.options = null;
    state.snapshot = null;
    state.storage = null;
  }

  P.modules.chatClient = {
    init: init,
    destroy: destroy,
    getState: getState,
    sendMessage: sendMessage,
    cancelRun: cancelRun,
    retryRun: retryRun,
    setLauncherOpen: setLauncherOpen,
    toggleLauncher: toggleLauncher,
    setDraft: setDraft,
    clearHistory: clearHistory,
  };
}());
