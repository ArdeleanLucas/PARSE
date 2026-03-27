(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;

  const STYLE_ID = 'parse-chat-panel-style-v1';

  const state = {
    initialized: false,
    options: null,
    snapshot: null,
    rootEl: null,
    launcherBtnEl: null,
    launcherUnreadEl: null,
    panelEl: null,
    historyEl: null,
    composerFormEl: null,
    composerInputEl: null,
    sendBtnEl: null,
    listeners: [],
    transcriptOpenByRun: Object.create(null),
    shouldAutoScroll: true,
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

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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

    if (status === 'pending' || status === 'created') return 'queued';
    if (status === 'in_progress' || status === 'in-progress' || status === 'processing') return 'running';
    if (status === 'complete' || status === 'done' || status === 'success') return 'completed';
    if (status === 'canceled') return 'cancelled';
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

  function statusMeta(status) {
    const moduleApi = adapters();
    if (moduleApi && typeof moduleApi.statusMeta === 'function') {
      return moduleApi.statusMeta(status);
    }

    const normalized = normalizeStatus(status, 'queued');
    if (normalized === 'completed') {
      return { status: normalized, label: 'Completed', tone: 'ok' };
    }
    if (normalized === 'running') {
      return { status: normalized, label: 'Running', tone: 'running' };
    }
    if (normalized === 'cancelled') {
      return { status: normalized, label: 'Cancelled', tone: 'warn' };
    }
    if (normalized === 'error') {
      return { status: normalized, label: 'Failed', tone: 'danger' };
    }
    return { status: normalized, label: 'Queued', tone: 'pending' };
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

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ID;
    styleEl.textContent = '' +
      '.parse-chat-dock{position:fixed;right:16px;bottom:16px;z-index:1600;font-family:system-ui,-apple-system,sans-serif;color:#f8fafc;}' +
      '.parse-chat-launcher{min-width:62px;height:52px;border-radius:16px;border:1px solid rgba(148,163,184,0.45);background:linear-gradient(135deg,#0f172a,#1e293b);color:#e2e8f0;font-size:13px;font-weight:700;padding:0 14px;display:flex;align-items:center;justify-content:center;gap:8px;box-shadow:0 12px 28px rgba(2,6,23,0.45);cursor:pointer;}' +
      '.parse-chat-launcher:hover{border-color:#60a5fa;transform:translateY(-1px);}' +
      '.parse-chat-launcher:focus-visible{outline:2px solid #38bdf8;outline-offset:2px;}' +
      '.parse-chat-launcher-badge{min-width:18px;height:18px;border-radius:999px;padding:0 6px;background:#ef4444;color:#fff;font-size:11px;line-height:18px;text-align:center;font-weight:700;display:none;}' +
      '.parse-chat-launcher-badge.show{display:inline-block;}' +
      '.parse-chat-panel{position:absolute;right:0;bottom:64px;width:min(430px,calc(100vw - 24px));height:min(620px,calc(100vh - 96px));border-radius:16px;border:1px solid rgba(148,163,184,0.35);background:linear-gradient(180deg,#0b1220,#111b2f);box-shadow:0 22px 46px rgba(2,6,23,0.58);overflow:hidden;display:flex;flex-direction:column;opacity:0;pointer-events:none;transform:translateY(8px) scale(0.98);transition:opacity .18s ease,transform .18s ease;}' +
      '.parse-chat-dock.open .parse-chat-panel{opacity:1;pointer-events:auto;transform:translateY(0) scale(1);}' +
      '.parse-chat-header{padding:11px 12px 10px;border-bottom:1px solid rgba(71,85,105,0.45);background:rgba(15,23,42,0.72);display:flex;flex-direction:column;gap:7px;}' +
      '.parse-chat-header-top{display:flex;align-items:center;justify-content:space-between;gap:8px;}' +
      '.parse-chat-title{font-size:13px;font-weight:700;letter-spacing:0.02em;}' +
      '.parse-chat-close{border:1px solid rgba(100,116,139,0.5);background:rgba(15,23,42,0.55);color:#cbd5e1;border-radius:8px;padding:4px 8px;font-size:11px;font-weight:700;cursor:pointer;}' +
      '.parse-chat-close:hover{border-color:#93c5fd;color:#fff;}' +
      '.parse-chat-history{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px;}' +
      '.parse-chat-empty{border:1px dashed rgba(100,116,139,0.5);border-radius:12px;background:rgba(15,23,42,0.42);padding:12px;font-size:12px;line-height:1.45;color:#cbd5e1;}' +
      '.parse-chat-empty strong{color:#f8fafc;display:block;margin-bottom:6px;}' +
      '.parse-chat-run{border:1px solid rgba(100,116,139,0.5);border-radius:12px;background:rgba(15,23,42,0.58);padding:10px;display:flex;flex-direction:column;gap:8px;}' +
      '.parse-chat-run-head{display:flex;align-items:center;gap:8px;}' +
      '.parse-chat-status{padding:2px 8px;border-radius:999px;font-size:10px;font-weight:800;letter-spacing:0.03em;text-transform:uppercase;border:1px solid transparent;}' +
      '.parse-chat-status.pending{background:rgba(148,163,184,0.2);color:#e2e8f0;border-color:rgba(148,163,184,0.45);}' +
      '.parse-chat-status.running{background:rgba(56,189,248,0.2);color:#bae6fd;border-color:rgba(56,189,248,0.45);}' +
      '.parse-chat-status.ok{background:rgba(52,211,153,0.2);color:#bbf7d0;border-color:rgba(52,211,153,0.45);}' +
      '.parse-chat-status.warn{background:rgba(250,204,21,0.18);color:#fde68a;border-color:rgba(250,204,21,0.4);}' +
      '.parse-chat-status.danger{background:rgba(248,113,113,0.2);color:#fecaca;border-color:rgba(248,113,113,0.45);}' +
      '.parse-chat-run-time{font-size:11px;color:#94a3b8;white-space:nowrap;}' +
      '.parse-chat-run-actions{margin-left:auto;display:flex;align-items:center;gap:6px;}' +
      '.parse-chat-run-btn{border:1px solid rgba(100,116,139,0.6);background:rgba(15,23,42,0.46);color:#e2e8f0;border-radius:7px;padding:3px 7px;font-size:11px;font-weight:700;cursor:pointer;}' +
      '.parse-chat-run-btn:hover{border-color:#93c5fd;color:#fff;}' +
      '.parse-chat-line{display:flex;flex-direction:column;gap:3px;}' +
      '.parse-chat-line-label{font-size:10px;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;color:#94a3b8;}' +
      '.parse-chat-line-content{font-size:12px;line-height:1.45;color:#f8fafc;white-space:pre-wrap;word-break:break-word;}' +
      '.parse-chat-line-content.placeholder{color:#93a7c5;font-style:italic;}' +
      '.parse-chat-error{border:1px solid rgba(248,113,113,0.55);background:rgba(127,29,29,0.25);border-radius:8px;padding:7px 8px;color:#fecaca;font-size:11px;line-height:1.4;}' +
      '.parse-chat-transcript-toggle{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;border:1px solid rgba(71,85,105,0.65);background:rgba(30,41,59,0.6);color:#e2e8f0;border-radius:8px;padding:6px 8px;font-size:11px;font-weight:700;cursor:pointer;}' +
      '.parse-chat-transcript-toggle:hover{border-color:#93c5fd;}' +
      '.parse-chat-transcript-list{margin-top:6px;border:1px solid rgba(71,85,105,0.55);border-radius:8px;background:rgba(15,23,42,0.42);padding:6px;display:flex;flex-direction:column;gap:6px;}' +
      '.parse-chat-transcript-item{border:1px solid rgba(71,85,105,0.5);border-radius:7px;padding:6px;background:rgba(15,23,42,0.56);display:flex;flex-direction:column;gap:4px;}' +
      '.parse-chat-transcript-head{display:flex;align-items:center;gap:6px;}' +
      '.parse-chat-transcript-title{font-size:11px;font-weight:700;color:#e2e8f0;}' +
      '.parse-chat-transcript-status{margin-left:auto;font-size:10px;color:#93c5fd;}' +
      '.parse-chat-transcript-status.warn{color:#fde68a;}' +
      '.parse-chat-transcript-status.danger{color:#fecaca;}' +
      '.parse-chat-transcript-detail{font-size:11px;line-height:1.4;color:#cbd5e1;white-space:pre-wrap;word-break:break-word;}' +
      '.parse-chat-composer{border-top:1px solid rgba(71,85,105,0.45);padding:10px;display:flex;flex-direction:column;gap:8px;background:rgba(15,23,42,0.75);}' +
      '.parse-chat-input{width:100%;min-height:70px;max-height:170px;resize:vertical;border:1px solid rgba(100,116,139,0.7);border-radius:10px;background:rgba(15,23,42,0.75);color:#f8fafc;padding:8px 9px;font-size:12px;line-height:1.45;}' +
      '.parse-chat-input:focus{outline:none;border-color:#38bdf8;box-shadow:0 0 0 2px rgba(14,165,233,0.2);}' +
      '.parse-chat-compose-row{display:flex;align-items:center;justify-content:flex-end;gap:10px;}' +
      '.parse-chat-send{border:1px solid rgba(56,189,248,0.8);background:linear-gradient(180deg,#0ea5e9,#0284c7);color:#fff;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:800;cursor:pointer;}' +
      '.parse-chat-send:disabled{opacity:0.5;cursor:not-allowed;}' +
      '.parse-chat-send:not(:disabled):hover{filter:brightness(1.06);}' +
      '@media (max-width: 700px){.parse-chat-dock{right:10px;left:10px;bottom:10px;}.parse-chat-panel{width:100%;right:0;}}' +
      '.parse-chat-auth{padding:24px 16px;display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center;flex:1;justify-content:center;}' +
      '.parse-chat-auth-title{font-size:15px;font-weight:800;color:#f8fafc;}' +
      '.parse-chat-auth-desc{font-size:12px;line-height:1.5;color:#cbd5e1;max-width:300px;}' +
      '.parse-chat-auth-btn{border:1px solid rgba(56,189,248,0.8);background:linear-gradient(180deg,#0ea5e9,#0284c7);color:#fff;border-radius:10px;padding:10px 20px;font-size:13px;font-weight:800;cursor:pointer;transition:filter .15s;}' +
      '.parse-chat-auth-btn:hover{filter:brightness(1.08);}' +
      '.parse-chat-auth-btn:disabled{opacity:0.5;cursor:not-allowed;}' +
      '.parse-chat-auth-code{font-family:monospace;font-size:24px;letter-spacing:0.15em;color:#38bdf8;font-weight:800;padding:8px 16px;border:2px dashed rgba(56,189,248,0.6);border-radius:10px;background:rgba(14,165,233,0.1);}' +
      '.parse-chat-auth-step{font-size:11px;color:#94a3b8;line-height:1.4;}' +
      '.parse-chat-auth-step a{color:#38bdf8;text-decoration:underline;}' +
      '.parse-chat-auth-status{font-size:11px;color:#fde68a;font-weight:700;}' +
      '.parse-chat-auth-error{font-size:11px;color:#fecaca;}' +
      '.parse-chat-logout{border:1px solid rgba(100,116,139,0.6);background:rgba(15,23,42,0.46);color:#e2e8f0;border-radius:7px;padding:3px 7px;font-size:10px;font-weight:700;cursor:pointer;}' +
      '.parse-chat-logout:hover{border-color:#f87171;color:#fecaca;}';

    document.head.appendChild(styleEl);
  }

  function ensureClient() {
    const client = P.modules && P.modules.chatClient ? P.modules.chatClient : null;
    if (!client || typeof client.init !== 'function' || typeof client.getState !== 'function') {
      throw new Error('window.PARSE.modules.chatClient is required before chat-panel init.');
    }

    const clientDefaults = {
      readOnly: true,
      provider: 'openai',
      model: 'gpt54',
      reasoning: 'high',
      intent: 'xhigh',
    };

    client.init(Object.assign({}, clientDefaults, toObject(state.options).clientOptions));
    return client;
  }

  function getCurrentSnapshot() {
    const client = ensureClient();
    return client.getState();
  }

  function inferContext() {
    const context = {};

    if (P.mode) {
      context.mode = P.mode;
    }

    if (P.currentSpeaker) {
      context.speaker = P.currentSpeaker;
    }

    if (P.currentConcept != null) {
      context.conceptId = P.currentConcept;
    }

    if (P.compareState && Array.isArray(P.compareState.selectedSpeakers)) {
      context.selectedSpeakers = P.compareState.selectedSpeakers.slice();
    }

    return context;
  }

  function formatTime(value) {
    const text = toString(value);
    if (!text) {
      return '—';
    }

    const date = new Date(text);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }

    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function transcriptDefaultOpen(run) {
    if (!run) return false;
    return isActiveStatus(run.status) || normalizeStatus(run.status, '') === 'error';
  }

  function transcriptIsOpen(runId, run) {
    const key = toString(runId);
    if (Object.prototype.hasOwnProperty.call(state.transcriptOpenByRun, key)) {
      return !!state.transcriptOpenByRun[key];
    }

    return transcriptDefaultOpen(run);
  }

  function toggleTranscript(runId) {
    const key = toString(runId);
    if (!key) return;

    const run = toObject(state.snapshot && state.snapshot.runsById ? state.snapshot.runsById[key] : null);
    const current = transcriptIsOpen(key, run);
    state.transcriptOpenByRun[key] = !current;
    renderHistory();
  }

  function renderTranscriptItem(entry, index) {
    const moduleApi = adapters();
    const formatted = moduleApi && typeof moduleApi.formatToolEntry === 'function'
      ? moduleApi.formatToolEntry(entry)
      : {
          title: toString(entry.title) || toString(entry.toolName) || 'Tool',
          statusLabel: statusMeta(entry.status).label,
          tone: statusMeta(entry.status).tone,
          detail: toString(entry.detail),
        };

    const detail = toString(formatted.detail) || toString(entry.inputPreview) || toString(entry.outputPreview) || 'No details recorded.';

    return '' +
      '<div class="parse-chat-transcript-item" data-entry-index="' + index + '">' +
        '<div class="parse-chat-transcript-head">' +
          '<span class="parse-chat-transcript-title">' + escapeHtml(formatted.title || 'Tool') + '</span>' +
          '<span class="parse-chat-transcript-status ' + escapeHtml(formatted.tone || 'pending') + '">' + escapeHtml(formatted.statusLabel || 'Queued') + '</span>' +
        '</div>' +
        '<div class="parse-chat-transcript-detail">' + escapeHtml(detail) + '</div>' +
      '</div>';
  }

  function runAssistantText(run) {
    const response = toString(run.assistantText);
    if (response) {
      return response;
    }

    const status = normalizeStatus(run.status, 'queued');
    if (status === 'running') {
      return 'Thinking… waiting for assistant response.';
    }
    if (status === 'queued') {
      return 'Queued and waiting for backend run to start.';
    }
    if (status === 'cancelled') {
      return 'Run was cancelled before completion.';
    }
    if (status === 'error') {
      return 'Run failed before a response could be produced.';
    }

    return 'No text response returned.';
  }

  function runActionButtonHtml(run) {
    const runId = toString(run.id);
    if (!runId) {
      return '';
    }

    if (run.canCancel && isActiveStatus(run.status)) {
      return '<button type="button" class="parse-chat-run-btn" data-action="cancel-run" data-run-id="' + escapeHtml(runId) + '">Cancel</button>';
    }

    if (run.canRetry || isDoneStatus(run.status) && (normalizeStatus(run.status, '') === 'error' || normalizeStatus(run.status, '') === 'cancelled')) {
      return '<button type="button" class="parse-chat-run-btn" data-action="retry-run" data-run-id="' + escapeHtml(runId) + '">Retry</button>';
    }

    return '';
  }

  function renderRunCard(run) {
    const runId = toString(run.id);
    const meta = statusMeta(run.status);
    const transcript = toArray(run.transcript);
    const transcriptOpen = transcriptIsOpen(runId, run);

    const transcriptItems = transcript.length
      ? transcript.map(renderTranscriptItem).join('')
      : '<div class="parse-chat-transcript-item"><div class="parse-chat-transcript-detail">No tool calls recorded for this run.</div></div>';

    const errorHtml = toString(run.error)
      ? '<div class="parse-chat-error">' + escapeHtml(run.error) + '</div>'
      : '';

    const retryInfo = run.retryOf
      ? '<span class="parse-chat-run-time">retry #' + escapeHtml(String(run.attempt || 1)) + '</span>'
      : '';

    return '' +
      '<article class="parse-chat-run" data-run-id="' + escapeHtml(runId) + '">' +
        '<div class="parse-chat-run-head">' +
          '<span class="parse-chat-status ' + escapeHtml(meta.tone || 'pending') + '">' + escapeHtml(meta.label || 'Queued') + '</span>' +
          '<span class="parse-chat-run-time">' + escapeHtml(formatTime(run.updatedAt || run.createdAt)) + '</span>' +
          retryInfo +
          '<div class="parse-chat-run-actions">' + runActionButtonHtml(run) + '</div>' +
        '</div>' +
        '<div class="parse-chat-line">' +
          '<div class="parse-chat-line-label">You</div>' +
          '<div class="parse-chat-line-content">' + escapeHtml(toString(run.userText)) + '</div>' +
        '</div>' +
        '<div class="parse-chat-line">' +
          '<div class="parse-chat-line-label">Assistant</div>' +
          '<div class="parse-chat-line-content' + (toString(run.assistantText) ? '' : ' placeholder') + '">' + escapeHtml(runAssistantText(run)) + '</div>' +
        '</div>' +
        errorHtml +
        '<div class="parse-chat-transcript">' +
          '<button type="button" class="parse-chat-transcript-toggle" data-action="toggle-transcript" data-run-id="' + escapeHtml(runId) + '">' +
            '<span>Tool transcript (' + transcript.length + ')</span>' +
            '<span>' + (transcriptOpen ? 'Hide' : 'Show') + '</span>' +
          '</button>' +
          (transcriptOpen
            ? '<div class="parse-chat-transcript-list">' + transcriptItems + '</div>'
            : '') +
        '</div>' +
      '</article>';
  }

  function renderHistory() {
    if (!state.historyEl) {
      return;
    }

    const snapshot = toObject(state.snapshot);
    const runOrder = toArray(snapshot.runOrder);
    const runsById = toObject(snapshot.runsById);

    const shouldStickToBottom = state.historyEl.scrollHeight - state.historyEl.scrollTop - state.historyEl.clientHeight < 20;

    if (!runOrder.length) {
      state.historyEl.innerHTML = '' +
        '<div class="parse-chat-empty">' +
          '<strong>PARSE Assistant</strong>' +
          'Ask about annotations, compare output, or project context.' +
        '</div>';
    } else {
      const cards = [];
      for (let i = 0; i < runOrder.length; i += 1) {
        const run = runsById[runOrder[i]];
        if (!run) continue;
        cards.push(renderRunCard(run));
      }
      state.historyEl.innerHTML = cards.join('');
    }

    if (state.shouldAutoScroll || shouldStickToBottom) {
      state.historyEl.scrollTop = state.historyEl.scrollHeight;
      state.shouldAutoScroll = false;
    }
  }

  function updateLauncher() {
    if (!state.rootEl || !state.launcherBtnEl || !state.launcherUnreadEl || !state.panelEl) {
      return;
    }

    const snapshot = toObject(state.snapshot);
    const launcher = toObject(snapshot.launcher);
    const isOpen = !!launcher.isOpen;

    state.rootEl.classList.toggle('open', isOpen);
    state.panelEl.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
    state.launcherBtnEl.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

    const unread = Math.max(0, Math.floor(Number(launcher.unread) || 0));
    state.launcherUnreadEl.textContent = unread > 99 ? '99+' : String(unread);
    state.launcherUnreadEl.classList.toggle('show', unread > 0 && !isOpen);
  }

  function updateComposer() {
    if (!state.composerInputEl || !state.sendBtnEl) {
      return;
    }

    const snapshot = toObject(state.snapshot);
    const draft = String(snapshot.draft == null ? '' : snapshot.draft);
    const isFocused = document.activeElement === state.composerInputEl;

    if (!isFocused || draft === '') {
      if (state.composerInputEl.value !== draft) {
        state.composerInputEl.value = draft;
      }
    }

    const hasText = toString(state.composerInputEl.value).length > 0;
    state.sendBtnEl.disabled = !hasText;
  }

  // ── Auth flow state ────────────────────────────────────────────
  var authState = {
    checked: false,
    authenticated: false,
    flowActive: false,
    userCode: '',
    verificationUri: '',
    pollTimer: null,
    error: '',
  };

  function checkAuthStatus() {
    fetch('/api/auth/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        authState.checked = true;
        authState.authenticated = !!data.authenticated;
        authState.flowActive = !!data.flow_active;
        authState.userCode = data.user_code || '';
        authState.verificationUri = data.verification_uri || '';
        render();
      })
      .catch(function () {
        authState.checked = true;
        authState.authenticated = false;
        render();
      });
  }

  function startAuthFlow() {
    authState.error = '';
    fetch('/api/auth/start', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          authState.error = data.error;
          render();
          return;
        }
        authState.flowActive = true;
        authState.userCode = data.user_code || '';
        authState.verificationUri = data.verification_uri || '';
        render();
        startAuthPolling();
      })
      .catch(function (err) {
        authState.error = 'Failed to start auth flow: ' + err.message;
        render();
      });
  }

  function startAuthPolling() {
    if (authState.pollTimer) clearInterval(authState.pollTimer);
    authState.pollTimer = setInterval(function () {
      fetch('/api/auth/poll', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.status === 'complete') {
            clearInterval(authState.pollTimer);
            authState.pollTimer = null;
            authState.authenticated = true;
            authState.flowActive = false;
            render();
          } else if (data.status === 'expired' || data.status === 'error') {
            clearInterval(authState.pollTimer);
            authState.pollTimer = null;
            authState.flowActive = false;
            authState.error = data.error || 'Auth flow expired.';
            render();
          }
        })
        .catch(function () {
          // silently retry on next interval
        });
    }, 5000);
  }

  function doLogout() {
    fetch('/api/auth/logout', { method: 'POST' })
      .then(function () {
        authState.authenticated = false;
        authState.flowActive = false;
        authState.userCode = '';
        authState.error = '';
        render();
      })
      .catch(function () {});
  }

  function renderAuthScreen() {
    if (!state.historyEl) return;

    if (!authState.checked) {
      state.historyEl.innerHTML = '<div class="parse-chat-auth"><div class="parse-chat-auth-status">Checking authentication…</div></div>';
      if (state.composerFormEl) state.composerFormEl.style.display = 'none';
      return;
    }

    if (authState.flowActive && authState.userCode) {
      state.historyEl.innerHTML = '' +
        '<div class="parse-chat-auth">' +
          '<div class="parse-chat-auth-title">Sign in with OpenAI</div>' +
          '<div class="parse-chat-auth-desc">Enter this code on the OpenAI page:</div>' +
          '<div class="parse-chat-auth-code">' + escapeHtml(authState.userCode) + '</div>' +
          '<div class="parse-chat-auth-step"><a href="' + escapeHtml(authState.verificationUri) + '" target="_blank" rel="noopener">Open OpenAI auth page →</a></div>' +
          '<div class="parse-chat-auth-status">Waiting for approval…</div>' +
          (authState.error ? '<div class="parse-chat-auth-error">' + escapeHtml(authState.error) + '</div>' : '') +
        '</div>';
      if (state.composerFormEl) state.composerFormEl.style.display = 'none';
      return;
    }

    // Not authenticated, no active flow
    state.historyEl.innerHTML = '' +
      '<div class="parse-chat-auth">' +
        '<div class="parse-chat-auth-title">Sign in to use PARSE Assistant</div>' +
        '<div class="parse-chat-auth-desc">Sign in with your OpenAI account to enable AI-powered analysis of your linguistic data.</div>' +
        '<button type="button" class="parse-chat-auth-btn" data-action="start-auth">Sign in with OpenAI</button>' +
        (authState.error ? '<div class="parse-chat-auth-error">' + escapeHtml(authState.error) + '</div>' : '') +
      '</div>';
    if (state.composerFormEl) state.composerFormEl.style.display = 'none';
  }

  function render() {
    if (!state.initialized) {
      return;
    }

    updateLauncher();

    if (!authState.checked) {
      checkAuthStatus();
      return;
    }

    if (!authState.authenticated) {
      renderAuthScreen();
      return;
    }

    // Authenticated — show normal chat
    if (state.composerFormEl) state.composerFormEl.style.display = '';
    renderHistory();
    updateComposer();
  }

  function submitComposer() {
    const inputEl = state.composerInputEl;
    if (!inputEl) return;

    const text = toString(inputEl.value);
    if (!text) {
      return;
    }

    dispatch('parse:chat-send', {
      text: text,
      context: inferContext(),
    });

    dispatch('parse:chat-draft', { text: '' });
    state.shouldAutoScroll = true;
  }

  function onRootClick(event) {
    const actionEl = event.target && typeof event.target.closest === 'function'
      ? event.target.closest('[data-action]')
      : null;

    if (!actionEl || !state.rootEl || !state.rootEl.contains(actionEl)) {
      return;
    }

    const action = toString(actionEl.dataset.action);

    if (action === 'toggle-launcher') {
      dispatch('parse:chat-launcher', { toggle: true });
      state.shouldAutoScroll = true;
      return;
    }

    if (action === 'close-panel') {
      dispatch('parse:chat-launcher', { open: false });
      return;
    }

    if (action === 'cancel-run') {
      dispatch('parse:chat-cancel-run', { runId: actionEl.dataset.runId });
      return;
    }

    if (action === 'retry-run') {
      dispatch('parse:chat-retry-run', {
        runId: actionEl.dataset.runId,
        context: inferContext(),
      });
      state.shouldAutoScroll = true;
      return;
    }

    if (action === 'toggle-transcript') {
      toggleTranscript(actionEl.dataset.runId);
      return;
    }

    if (action === 'start-auth') {
      startAuthFlow();
      return;
    }

    if (action === 'logout') {
      doLogout();
      return;
    }
  }

  function onComposerInput(event) {
    if (!state.composerInputEl || event.target !== state.composerInputEl) {
      return;
    }

    dispatch('parse:chat-draft', {
      text: state.composerInputEl.value,
    });

    updateComposer();
  }

  function onComposerKeyDown(event) {
    if (!state.composerInputEl || event.target !== state.composerInputEl) {
      return;
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submitComposer();
    }
  }

  function onComposerSubmit(event) {
    event.preventDefault();
    submitComposer();
  }

  function onChatState(event) {
    const detail = toObject(event && event.detail);
    const snapshot = detail.state;
    if (!snapshot || typeof snapshot !== 'object') {
      return;
    }

    state.snapshot = snapshot;
    render();
  }

  function createShell(mountEl) {
    const root = document.createElement('div');
    root.className = 'parse-chat-dock';
    root.setAttribute('data-parse-chat-dock', '1');
    root.innerHTML = '' +
      '<button type="button" class="parse-chat-launcher" data-action="toggle-launcher" aria-expanded="false" aria-label="Toggle PARSE assistant">' +
        '<span>AI</span>' +
        '<span class="parse-chat-launcher-badge" data-role="launcher-unread">0</span>' +
      '</button>' +
      '<section class="parse-chat-panel" aria-hidden="true">' +
        '<header class="parse-chat-header">' +
          '<div class="parse-chat-header-top">' +
            '<div class="parse-chat-title">PARSE Assistant</div>' +
            '<button type="button" class="parse-chat-logout" data-action="logout" title="Sign out of OpenAI">Sign out</button>' +
            '<button type="button" class="parse-chat-close" data-action="close-panel">Close</button>' +
          '</div>' +
        '</header>' +
        '<div class="parse-chat-history" data-role="history"></div>' +
        '<form class="parse-chat-composer" data-role="composer">' +
          '<textarea class="parse-chat-input" data-role="composer-input" placeholder="Ask about annotations, comparisons, or transcripts…"></textarea>' +
          '<div class="parse-chat-compose-row">' +
            '<button class="parse-chat-send" type="submit" data-role="send-btn">Send</button>' +
          '</div>' +
        '</form>' +
      '</section>';

    mountEl.appendChild(root);

    state.rootEl = root;
    state.launcherBtnEl = root.querySelector('.parse-chat-launcher');
    state.launcherUnreadEl = root.querySelector('[data-role="launcher-unread"]');
    state.panelEl = root.querySelector('.parse-chat-panel');
    state.historyEl = root.querySelector('[data-role="history"]');
    state.composerFormEl = root.querySelector('[data-role="composer"]');
    state.composerInputEl = root.querySelector('[data-role="composer-input"]');
    state.sendBtnEl = root.querySelector('[data-role="send-btn"]');
  }

  function bindEvents() {
    addListener(state.rootEl, 'click', onRootClick);
    addListener(state.composerFormEl, 'submit', onComposerSubmit);
    addListener(state.composerInputEl, 'input', onComposerInput);
    addListener(state.composerInputEl, 'keydown', onComposerKeyDown);
    addListener(document, 'parse:chat-state', onChatState);
  }

  /**
   * Initialize chat panel UI.
   * @param {object=} options Optional mount and client options.
   * @returns {object} Public module API.
   */
  function init(options) {
    if (state.initialized) {
      return P.modules.chatPanel;
    }

    state.options = toObject(options);

    ensureStyles();

    const mountEl = state.options.mountEl && state.options.mountEl.appendChild
      ? state.options.mountEl
      : document.body;

    if (!mountEl) {
      throw new Error('chat-panel init requires a valid mount element.');
    }

    ensureClient();
    createShell(mountEl);
    bindEvents();

    state.snapshot = getCurrentSnapshot();
    state.initialized = true;

    render();
    return P.modules.chatPanel;
  }

  /**
   * Destroy chat panel UI and detach listeners.
   */
  function destroy() {
    if (!state.initialized) {
      return;
    }

    removeListeners();

    if (state.rootEl && state.rootEl.parentNode) {
      state.rootEl.parentNode.removeChild(state.rootEl);
    }

    state.initialized = false;
    state.options = null;
    state.snapshot = null;
    state.rootEl = null;
    state.launcherBtnEl = null;
    state.launcherUnreadEl = null;
    state.panelEl = null;
    state.historyEl = null;
    state.composerFormEl = null;
    state.composerInputEl = null;
    state.sendBtnEl = null;
    state.transcriptOpenByRun = Object.create(null);
    state.shouldAutoScroll = true;
  }

  function open() {
    dispatch('parse:chat-launcher', { open: true });
  }

  function close() {
    dispatch('parse:chat-launcher', { open: false });
  }

  function toggle() {
    dispatch('parse:chat-launcher', { toggle: true });
  }

  function isOpen() {
    const snapshot = toObject(state.snapshot);
    return !!toObject(snapshot.launcher).isOpen;
  }

  P.modules.chatPanel = {
    init: init,
    destroy: destroy,
    open: open,
    close: close,
    toggle: toggle,
    isOpen: isOpen,
    render: render,
  };

  // Also register under the keys that compare.js resolveAssistantModule() looks for.
  P.modules.assistantDock = P.modules.chatPanel;
  P.modules.aiChatDock = P.modules.chatPanel;

  // Auto-init: when compare.js fires the mount-ready event, initialize the chat panel.
  document.addEventListener('parse:assistant-mount-ready', function onMountReady(evt) {
    var detail = evt && evt.detail ? evt.detail : {};
    var mountId = detail.mountId || 'parse-assistant-dock';
    var mountEl = document.getElementById(mountId);
    if (!mountEl) return;

    try {
      if (!P.modules.chatPanel._initialized) {
        P.modules.chatPanel.init({ mountEl: mountEl });
        P.modules.chatPanel._initialized = true;
      }
    } catch (err) {
      console.warn('[chat-panel] auto-init from mount-ready failed:', err);
    }
  });

  // Also fire the module-ready event so compare.js picks it up on retry.
  document.dispatchEvent(new CustomEvent('parse:assistant-ready', { detail: {} }));
}());
