(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const COMPUTE_TYPE_ORDER = ['cognates', 'offset', 'spectrograms'];
  const COMPUTE_START_ENDPOINTS = {
    cognates: '/api/compute/cognates',
    offset: '/api/compute/offset',
    spectrograms: '/api/compute/spectrograms',
  };
  const CONCEPT_SELECTED_EVENT = 'parse:compare-concept-selected';
  const CONCEPT_SELECT_COMPAT_EVENT = CONCEPT_SELECTED_EVENT.replace(/selected$/, 'select');
  const TAG_PSEUDO_ALL = '__all__';
  const TAG_PSEUDO_UNTAGGED = '__untagged__';
  const TAG_DEFAULT_COLOR = '#6b7280';
  const REVIEW_FILTER_ORDER = ['all', 'unreviewed', 'flagged', 'borrowing'];
  const SIDEBAR_SORT_ORDER = ['alpha', 'id'];
  const SHELL_DRAFT_STORAGE_KEY = 'parse.compare.shell-draft.v1';
  const SHELL_DRAFT_EXPORT_VERSION = 1;
  const NOTE_SAVE_DELAY_MS = 220;
  const ENTRY_MATCH_EPSILON = 0.01;
  const COGNATE_GROUP_COLORS = {
    A: '#4a90d9',
    B: '#27ae60',
    C: '#e67e22',
    D: '#8e44ad',
    E: '#e74c3c',
  };

  const ASSISTANT_MOUNT_ID = 'parse-assistant-dock';
  const ASSISTANT_HISTORY_KEY = 'parse-ai-chat-history-v1';
  const ASSISTANT_CONTEXT_EVENT = 'parse:assistant-context';
  const ASSISTANT_MOUNT_READY_EVENT = 'parse:assistant-mount-ready';
  const ASSISTANT_MODULE_READY_EVENTS = ['parse:assistant-ready', 'parse:toolbox-ready'];
  const ASSISTANT_MODULE_KEYS = [
    'assistantDock',
    'aiAssistantDock',
    'aiChatDock',
    'aiToolbox',
    'assistantToolbox',
    'assistant',
    'chatToolbox',
  ];
  const ASSISTANT_RETRY_DELAY_MS = 900;
  const ASSISTANT_RETRY_MAX = 10;

  const state = {
    initialized: false,
    containerEl: null,
    headerEl: null,
    tableEl: null,
    cognatePanelEl: null,
    borrowingPanelEl: null,
    spectrogramPanelEl: null,
    computeStatusEl: null,
    computeTextEl: null,
    computeProgressEl: null,
    sidebarSearchEl: null,
    sidebarConceptListEl: null,
    sidebarSortButtons: [],
    sidebarFilterButtons: [],
    conceptTitleEl: null,
    navPositionEl: null,
    shellStateEl: null,
    shellStateTitleEl: null,
    shellStateMessageEl: null,
    shellStateMetaEl: null,
    navPrevButtons: [],
    navNextButtons: [],
    acceptButtons: [],
    flagButtons: [],
    notesFieldEl: null,
    progressBadgeEl: null,
    progressBarEl: null,
    refArabicFormEl: null,
    refArabicIpaEl: null,
    refPersianFormEl: null,
    refPersianIpaEl: null,
    formsTbodyEl: null,
    loadButtonEl: null,
    saveButtonEl: null,
    toastEl: null,
    shellFileInputEl: null,
    legacyFileInputEl: null,
    legacyCompatGlobals: null,
    listeners: [],
    availableSpeakers: [],
    selectedSpeakers: [],
    concepts: [],
    filteredConcepts: [],
    selectedConceptId: '',
    reviewFilter: 'all',
    sortMode: 'alpha',
    sidebarQuery: '',
    notesPersistTimer: 0,
    tagFilter: {
      activeTagIds: [],
      includeUntagged: false,
    },
    computeType: 'cognates',
    computeToken: 0,
    conceptDispatchToken: 0,
    isBootstrapping: false,
    bootstrapErrorMessage: '',
    bootstrapSummary: {
      projectLoaded: false,
      sourceIndexLoaded: false,
      discoveredSpeakers: 0,
      loadedAnnotationSpeakers: 0,
      annotationConcepts: 0,
      csvConceptRows: 0,
      enrichmentConcepts: 0,
    },
    shellDecisions: {},
    toastTimer: 0,
    assistantMountEl: null,
    assistantModule: null,
    assistantApi: null,
    assistantReady: false,
    assistantRetryTimer: 0,
    assistantRetryCount: 0,
    assistantContextSignature: '',
  };

  function dispatchEvent(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function toObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function toString(value) {
    return String(value == null ? '' : value).trim();
  }

  function toFiniteNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function normalizeConceptId(value) {
    let text = toString(value);
    if (!text) return '';

    if (text.charAt(0) === '#') {
      text = text.slice(1).trim();
    }

    const colonIndex = text.indexOf(':');
    if (colonIndex !== -1) {
      text = text.slice(0, colonIndex).trim();
    }

    return text;
  }

  function splitConceptText(value) {
    const text = toString(value);
    if (!text) {
      return { conceptId: '', conceptLabel: '' };
    }

    const colonIndex = text.indexOf(':');
    if (colonIndex === -1) {
      const conceptId = normalizeConceptId(text);
      if (conceptId && conceptId === text) {
        return { conceptId: conceptId, conceptLabel: '' };
      }
      return { conceptId: conceptId, conceptLabel: text };
    }

    return {
      conceptId: normalizeConceptId(text.slice(0, colonIndex)),
      conceptLabel: text.slice(colonIndex + 1).trim(),
    };
  }

  function conceptIdKeyCandidates(conceptId) {
    const normalized = normalizeConceptId(conceptId);
    if (!normalized) return [];

    const out = [normalized];
    const numeric = Number(normalized);
    if (Number.isFinite(numeric)) {
      const numericKey = String(numeric);
      if (out.indexOf(numericKey) === -1) {
        out.push(numericKey);
      }
    }

    return out;
  }

  function valueForConceptId(record, conceptId) {
    const map = toObject(record);
    const candidates = conceptIdKeyCandidates(conceptId);

    for (let i = 0; i < candidates.length; i += 1) {
      const key = candidates[i];
      if (Object.prototype.hasOwnProperty.call(map, key)) {
        return map[key];
      }
    }

    return undefined;
  }

  function approxEqual(left, right, epsilon) {
    const a = Number(left);
    const b = Number(right);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
    return Math.abs(a - b) <= epsilon;
  }

  function intervalsFromTier(record, tierName) {
    const tiers = toObject(record && record.tiers);
    const tier = toObject(tiers[tierName]);
    return Array.isArray(tier.intervals) ? tier.intervals : [];
  }

  function findIntervalTextByBounds(intervals, startSec, endSec) {
    const list = Array.isArray(intervals) ? intervals : [];

    for (let i = 0; i < list.length; i += 1) {
      const interval = toObject(list[i]);
      if (
        approxEqual(interval.start, startSec, ENTRY_MATCH_EPSILON) &&
        approxEqual(interval.end, endSec, ENTRY_MATCH_EPSILON)
      ) {
        return toString(interval.text);
      }
    }

    return '';
  }

  function formatSecondsToClock(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return '--:--';

    const total = Math.floor(value);
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;

    if (hrs > 0) {
      return String(hrs) + ':' + String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
    }

    return String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
  }

  function normalizeGroupLetter(value) {
    const raw = toString(value).toUpperCase();
    if (!raw) return '';

    if (Object.prototype.hasOwnProperty.call(COGNATE_GROUP_COLORS, raw)) {
      return raw;
    }

    const code = raw.charCodeAt(0) - 65;
    if (Number.isFinite(code) && code >= 0) {
      const letters = Object.keys(COGNATE_GROUP_COLORS);
      return letters[code % letters.length] || '';
    }

    return '';
  }

  function colorForGroup(groupLetter) {
    const normalized = normalizeGroupLetter(groupLetter);
    return COGNATE_GROUP_COLORS[normalized] || '#94a3b8';
  }

  function numericOrTextConceptId(conceptId) {
    const num = Number(conceptId);
    return Number.isFinite(num) ? num : conceptId;
  }

  function deepClone(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
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

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function assistantContextSignature(context) {
    return JSON.stringify({
      speakers: context.speakers,
      conceptId: context.conceptId,
      conceptLabel: context.conceptLabel,
      visibleConceptIds: context.visibleConceptIds,
      reviewFilter: context.reviewFilter,
      tagFilter: context.tagFilter,
    });
  }

  function resolveAssistantModule() {
    const modules = toObject(P.modules);

    for (let i = 0; i < ASSISTANT_MODULE_KEYS.length; i += 1) {
      const key = ASSISTANT_MODULE_KEYS[i];
      const candidate = modules[key];
      if (candidate && (typeof candidate === 'object' || typeof candidate === 'function')) {
        return candidate;
      }
    }

    const globals = [
      window.PARSEAssistantDock,
      window.PARSEAiAssistantDock,
      window.PARSEToolbox,
      window.PARSEAssistant,
    ];

    for (let i = 0; i < globals.length; i += 1) {
      const candidate = globals[i];
      if (candidate && (typeof candidate === 'object' || typeof candidate === 'function')) {
        return candidate;
      }
    }

    return null;
  }

  function ensureAssistantMount() {
    if (state.assistantMountEl && document.body.contains(state.assistantMountEl)) {
      return state.assistantMountEl;
    }

    let mountEl = firstById([ASSISTANT_MOUNT_ID, 'parse-ai-dock', 'parse-chat-dock', 'parse-toolbox-dock']);
    if (!mountEl) {
      mountEl = document.createElement('div');
      mountEl.id = ASSISTANT_MOUNT_ID;
      mountEl.style.position = 'fixed';
      mountEl.style.right = '20px';
      mountEl.style.bottom = '20px';
      mountEl.style.zIndex = '1400';
      mountEl.style.pointerEvents = 'none';
      document.body.appendChild(mountEl);
    }

    mountEl.dataset.assistantPage = 'compare';
    mountEl.dataset.assistantMounted = state.assistantReady ? 'true' : 'false';

    state.assistantMountEl = mountEl;
    return mountEl;
  }

  function currentAssistantContext(reason) {
    const selectedConcept = findConceptById(state.selectedConceptId);

    return {
      mode: 'compare',
      page: 'compare',
      source: 'js/compare/compare.js',
      reason: reason || 'sync',
      readOnly: true,
      allowAttachments: false,
      allowWrite: false,
      allowEdits: false,
      historyKey: ASSISTANT_HISTORY_KEY,
      speakers: state.selectedSpeakers.slice(),
      selectedSpeakers: state.selectedSpeakers.slice(),
      conceptId: state.selectedConceptId || null,
      selectedConceptId: state.selectedConceptId || null,
      conceptLabel: selectedConcept ? conceptDisplayLabel(selectedConcept) : '',
      selectedConceptLabel: selectedConcept ? conceptDisplayLabel(selectedConcept) : '',
      visibleConceptIds: visibleConceptIds(),
      reviewFilter: state.reviewFilter,
      tagFilter: deepClone(state.tagFilter),
      timestamp: new Date().toISOString(),
    };
  }

  function dispatchAssistantContext(context) {
    dispatchEvent(ASSISTANT_CONTEXT_EVENT, context);
  }

  function applyAssistantContext(reason, force) {
    const context = currentAssistantContext(reason);
    const signature = assistantContextSignature(context);

    if (!force && signature === state.assistantContextSignature) {
      return;
    }

    state.assistantContextSignature = signature;
    dispatchAssistantContext(context);

    const api = state.assistantApi;
    if (!api) {
      return;
    }

    try {
      if (typeof api === 'function') {
        api(context);
        return;
      }

      if (typeof api.setContext === 'function') {
        api.setContext(context);
        return;
      }
      if (typeof api.updateContext === 'function') {
        api.updateContext(context);
        return;
      }
      if (typeof api.setPageContext === 'function') {
        api.setPageContext(context);
        return;
      }
      if (typeof api.updatePageContext === 'function') {
        api.updatePageContext(context);
      }
    } catch (error) {
      console.warn('[compare] assistant context update skipped:', error);
    }
  }

  function clearAssistantRetryTimer() {
    if (state.assistantRetryTimer) {
      window.clearTimeout(state.assistantRetryTimer);
      state.assistantRetryTimer = 0;
    }
  }

  function scheduleAssistantRetry() {
    if (state.assistantReady) return;
    if (state.assistantRetryTimer) return;
    if (state.assistantRetryCount >= ASSISTANT_RETRY_MAX) return;

    state.assistantRetryTimer = window.setTimeout(function () {
      state.assistantRetryTimer = 0;
      state.assistantRetryCount += 1;
      initAssistantDock(false);
    }, ASSISTANT_RETRY_DELAY_MS);
  }

  function initializeAssistantApi(moduleRef, mountEl, context) {
    let api = moduleRef;

    try {
      if (moduleRef && typeof moduleRef.init === 'function') {
        try {
          const maybeApi = moduleRef.init(Object.assign({}, context, {
            mountEl: mountEl,
            mount: mountEl,
            containerEl: mountEl,
            launcherPosition: 'bottom-right',
            dockPosition: 'bottom-right',
            historyKey: ASSISTANT_HISTORY_KEY,
            readOnly: true,
            allowAttachments: false,
            allowWrite: false,
            allowEdits: false,
          }));
          if (maybeApi && (typeof maybeApi === 'object' || typeof maybeApi === 'function')) {
            api = maybeApi;
          }
        } catch (_) {
          const fallbackApi = moduleRef.init(mountEl, Object.assign({}, context, {
            mountEl: mountEl,
            mount: mountEl,
            containerEl: mountEl,
          }));
          if (fallbackApi && (typeof fallbackApi === 'object' || typeof fallbackApi === 'function')) {
            api = fallbackApi;
          }
        }
      } else if (moduleRef && typeof moduleRef.mount === 'function') {
        const maybeApi = moduleRef.mount(Object.assign({}, context, {
          mountEl: mountEl,
          mount: mountEl,
          containerEl: mountEl,
        }));
        if (maybeApi && (typeof maybeApi === 'object' || typeof maybeApi === 'function')) {
          api = maybeApi;
        }
      }
    } catch (error) {
      console.warn('[compare] assistant init failed:', error);
      return false;
    }

    state.assistantModule = moduleRef;
    state.assistantApi = api;
    state.assistantReady = true;
    state.assistantRetryCount = 0;
    if (mountEl) {
      mountEl.dataset.assistantMounted = 'true';
    }
    return true;
  }

  function initAssistantDock(force) {
    const mountEl = ensureAssistantMount();
    const context = currentAssistantContext('mount');

    dispatchEvent(ASSISTANT_MOUNT_READY_EVENT, {
      mountId: mountEl.id,
      mode: 'compare',
      page: 'compare',
      historyKey: ASSISTANT_HISTORY_KEY,
      readOnly: true,
      allowAttachments: false,
    });

    const moduleRef = resolveAssistantModule();
    if (!moduleRef) {
      state.assistantReady = false;
      state.assistantApi = null;
      if (mountEl) {
        mountEl.dataset.assistantMounted = 'false';
      }
      dispatchAssistantContext(context);
      scheduleAssistantRetry();
      return false;
    }

    clearAssistantRetryTimer();

    const needsInit = force || !state.assistantReady || state.assistantModule !== moduleRef;
    if (needsInit) {
      const mounted = initializeAssistantApi(moduleRef, mountEl, context);
      if (!mounted) {
        state.assistantReady = false;
        state.assistantApi = null;
        if (mountEl) {
          mountEl.dataset.assistantMounted = 'false';
        }
        scheduleAssistantRetry();
        return false;
      }
    }

    applyAssistantContext('mount', true);
    return true;
  }

  function destroyAssistantDock() {
    clearAssistantRetryTimer();

    const teardownTargets = uniqueElements([state.assistantApi, state.assistantModule]);
    for (let i = 0; i < teardownTargets.length; i += 1) {
      const target = teardownTargets[i];
      if (!target || typeof target === 'function') {
        continue;
      }

      try {
        if (typeof target.destroy === 'function') {
          target.destroy();
          continue;
        }
        if (typeof target.unmount === 'function') {
          target.unmount();
        }
      } catch (error) {
        console.warn('[compare] assistant destroy skipped:', error);
      }
    }

    if (state.assistantMountEl) {
      state.assistantMountEl.dataset.assistantMounted = 'false';
    }

    state.assistantModule = null;
    state.assistantApi = null;
    state.assistantReady = false;
    state.assistantContextSignature = '';
  }

  function onAssistantModuleReady() {
    initAssistantDock(false);
  }

  function firstById(candidates) {
    const list = Array.isArray(candidates) ? candidates : [candidates];
    for (let i = 0; i < list.length; i += 1) {
      const id = toString(list[i]);
      if (!id) continue;
      const el = document.getElementById(id);
      if (el) return el;
    }
    return null;
  }

  function firstBySelector(candidates, root) {
    const base = root && typeof root.querySelector === 'function' ? root : document;
    const list = Array.isArray(candidates) ? candidates : [candidates];
    for (let i = 0; i < list.length; i += 1) {
      const selector = toString(list[i]);
      if (!selector) continue;
      const el = base.querySelector(selector);
      if (el) return el;
    }
    return null;
  }

  function findTopbarButtonByText(candidates) {
    const list = Array.isArray(candidates) ? candidates : [candidates];
    const needles = list
      .map(function (item) { return toString(item).toLowerCase(); })
      .filter(Boolean);

    if (!needles.length) return null;

    const buttons = Array.prototype.slice.call(document.querySelectorAll('#topbar .topbar-btn, #topbar button'));
    for (let i = 0; i < buttons.length; i += 1) {
      const text = toString(buttons[i].textContent).toLowerCase();
      if (!text) continue;

      for (let j = 0; j < needles.length; j += 1) {
        if (text.indexOf(needles[j]) !== -1) {
          return buttons[i];
        }
      }
    }

    return null;
  }

  function clickedElementMatches(target, element) {
    if (!target || !element || typeof target.closest !== 'function') {
      return false;
    }

    if (target === element || element.contains(target)) {
      return true;
    }

    if (element.id) {
      const byId = target.closest('#' + element.id);
      if (byId === element) {
        return true;
      }
    }

    const clickable = target.closest('button, a, [role="button"]');
    return clickable === element;
  }

  function uniqueElements(values) {
    const list = Array.isArray(values) ? values : [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < list.length; i += 1) {
      const el = list[i];
      if (!el || seen.has(el)) continue;
      seen.add(el);
      out.push(el);
    }

    return out;
  }

  async function parseJsonBody(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (_) {
      return { raw: text };
    }
  }

  function showToast(message) {
    if (!state.toastEl) return;

    if (state.toastTimer) {
      window.clearTimeout(state.toastTimer);
      state.toastTimer = 0;
    }

    state.toastEl.textContent = toString(message);
    state.toastEl.classList.add('show');
    state.toastTimer = window.setTimeout(function () {
      if (!state.toastEl) return;
      state.toastEl.classList.remove('show');
      state.toastTimer = 0;
    }, 2600);
  }

  function shellMetaChipHtml(label, tone) {
    const safeTone = toString(tone);
    const toneClass = safeTone && ['ok', 'warn', 'error'].indexOf(safeTone) !== -1
      ? (' ' + safeTone)
      : '';
    return '<span class="shell-meta-chip' + toneClass + '">' + escapeHtml(label) + '</span>';
  }

  function renderShellStateMeta() {
    if (!state.shellStateMetaEl) return;

    const summary = toObject(state.bootstrapSummary);
    const chips = [];

    chips.push(
      shellMetaChipHtml(
        summary.projectLoaded ? 'project.json loaded' : 'project.json missing',
        summary.projectLoaded ? 'ok' : 'warn'
      )
    );

    chips.push(
      shellMetaChipHtml(
        Number(summary.loadedAnnotationSpeakers || 0) + ' annotation speakers',
        Number(summary.loadedAnnotationSpeakers || 0) > 0 ? 'ok' : 'warn'
      )
    );

    chips.push(
      shellMetaChipHtml(
        state.concepts.length + ' concepts',
        state.concepts.length > 0 ? 'ok' : 'warn'
      )
    );

    chips.push(
      shellMetaChipHtml(
        state.selectedSpeakers.length + ' selected speakers',
        state.selectedSpeakers.length > 0 ? 'ok' : 'warn'
      )
    );

    chips.push(
      shellMetaChipHtml(
        state.filteredConcepts.length + ' visible concepts',
        state.filteredConcepts.length > 0 ? 'ok' : 'warn'
      )
    );

    if (state.bootstrapErrorMessage) {
      chips.push(shellMetaChipHtml('bootstrap error', 'error'));
    }

    state.shellStateMetaEl.innerHTML = chips.join('');
  }

  function setShellState(kind, title, message) {
    if (!state.shellStateEl) {
      return;
    }

    const stateKind = toString(kind) || 'loading';
    const stateTitle = toString(title) || 'Compare workspace';
    const stateMessage = toString(message);

    state.shellStateEl.setAttribute('data-state', stateKind);
    state.shellStateEl.style.borderLeftColor = '';
    state.shellStateEl.style.background = '';

    if (stateKind === 'no-data') {
      state.shellStateEl.style.borderLeftColor = '#f59e0b';
      state.shellStateEl.style.background = 'linear-gradient(135deg, #fffaf0 0%, #fff5e1 100%)';
    }

    if (stateKind === 'error') {
      state.shellStateEl.style.borderLeftColor = '#ef4444';
      state.shellStateEl.style.background = 'linear-gradient(135deg, #fff5f5 0%, #ffe4e6 100%)';
    }

    if (state.shellStateTitleEl) {
      state.shellStateTitleEl.textContent = stateTitle;
    }

    if (state.shellStateMessageEl) {
      state.shellStateMessageEl.textContent = stateMessage;
    }

    renderShellStateMeta();
  }

  function resetBootstrapSummary() {
    state.bootstrapSummary = {
      projectLoaded: false,
      sourceIndexLoaded: false,
      discoveredSpeakers: 0,
      loadedAnnotationSpeakers: 0,
      annotationConcepts: 0,
      csvConceptRows: 0,
      enrichmentConcepts: 0,
    };
  }

  function hasBootstrapDataSignals() {
    const summary = toObject(state.bootstrapSummary);
    const signals = [
      Number(summary.discoveredSpeakers),
      Number(summary.loadedAnnotationSpeakers),
      Number(summary.annotationConcepts),
      Number(summary.csvConceptRows),
      Number(summary.enrichmentConcepts),
    ];

    for (let i = 0; i < signals.length; i += 1) {
      if (Number.isFinite(signals[i]) && signals[i] > 0) {
        return true;
      }
    }

    return false;
  }

  function isNoDataState() {
    return !state.concepts.length && !hasBootstrapDataSignals();
  }

  function refreshShellStateFromData() {
    if (state.isBootstrapping) {
      setShellState(
        'loading',
        'Loading compare workspace…',
        'Building concept queue and pulling annotations/enrichments.'
      );
      return;
    }

    if (state.bootstrapErrorMessage) {
      setShellState(
        'error',
        'Compare workspace hit an error.',
        state.bootstrapErrorMessage + ' The concept-first shell is still available; refresh after fixing data paths/services.'
      );
      return;
    }

    if (isNoDataState()) {
      setShellState(
        'no-data',
        'No compare data detected yet.',
        'No speakers or concepts were found from project CSV, annotations, or enrichments. The compare shell is loaded and ready once data wiring is available.'
      );
      return;
    }

    if (!state.concepts.length) {
      setShellState(
        'empty',
        'Concept queue is empty.',
        'Compare loaded, but there are no concept records to review yet. Check concept CSV columns and annotation concept labels.'
      );
      return;
    }

    if (!state.filteredConcepts.length) {
      setShellState(
        'filtered-empty',
        'No concepts match the current filters.',
        'Try clearing search/filter/tag selection to restore the concept queue.'
      );
      return;
    }

    if (!state.selectedSpeakers.length) {
      setShellState(
        'attention',
        'Concept queue loaded. No speakers selected.',
        'Use the speaker control above to add one or more speakers, then review each concept top-to-bottom.'
      );
      return;
    }

    setShellState(
      'ready',
      'Ready for concept-by-concept review.',
      'Sidebar queue, concept cards, and decision draft persistence are active.'
    );
  }

  function conceptDisplayLabel(concept) {
    if (!concept) return '';
    return toString(concept.label) || ('Concept ' + concept.id);
  }

  function findConceptById(conceptId) {
    const wanted = normalizeConceptId(conceptId);
    if (!wanted) return null;

    for (let i = 0; i < state.concepts.length; i += 1) {
      if (state.concepts[i].id === wanted) {
        return state.concepts[i];
      }
    }

    return null;
  }

  function currentConcept() {
    return findConceptById(state.selectedConceptId);
  }

  function normalizeShellDecision(raw) {
    const decision = toObject(raw);
    const status = toString(decision.status).toLowerCase();
    return {
      status: REVIEW_FILTER_ORDER.indexOf(status) !== -1 ? status : (status === 'reviewed' || status === 'flagged' ? status : 'unreviewed'),
      notes: toString(decision.notes),
    };
  }

  function shellDecisionForConcept(conceptId) {
    const key = normalizeConceptId(conceptId);
    if (!key) {
      return { status: 'unreviewed', notes: '' };
    }

    if (!state.shellDecisions[key]) {
      state.shellDecisions[key] = { status: 'unreviewed', notes: '' };
    }

    state.shellDecisions[key] = normalizeShellDecision(state.shellDecisions[key]);
    return state.shellDecisions[key];
  }

  function persistShellDraft() {
    try {
      window.localStorage.setItem(SHELL_DRAFT_STORAGE_KEY, JSON.stringify({
        version: SHELL_DRAFT_EXPORT_VERSION,
        savedAt: new Date().toISOString(),
        decisions: state.shellDecisions,
      }));
    } catch (_) {
    }
  }

  function loadShellDraft() {
    try {
      const raw = window.localStorage.getItem(SHELL_DRAFT_STORAGE_KEY);
      if (!raw) {
        state.shellDecisions = {};
        return;
      }

      const parsed = JSON.parse(raw);
      const source = toObject(parsed.decisions || parsed);
      const out = {};
      const keys = Object.keys(source);
      for (let i = 0; i < keys.length; i += 1) {
        const conceptId = normalizeConceptId(keys[i]);
        if (!conceptId) continue;
        out[conceptId] = normalizeShellDecision(source[keys[i]]);
      }
      state.shellDecisions = out;
    } catch (_) {
      state.shellDecisions = {};
    }
  }

  function borrowingRecordForConcept(conceptId) {
    const key = normalizeConceptId(conceptId);
    if (!key) return {};

    const enrichments = toObject(P.enrichments);
    const manualFlags = toObject(toObject(toObject(enrichments).manual_overrides).borrowing_flags);
    const baseFlags = toObject(enrichments.borrowing_flags);

    return Object.assign(
      {},
      toObject(valueForConceptId(baseFlags, key)),
      toObject(valueForConceptId(manualFlags, key))
    );
  }

  function conceptHasBorrowingFlag(conceptId) {
    const record = borrowingRecordForConcept(conceptId);
    const keys = Object.keys(record);
    for (let i = 0; i < keys.length; i += 1) {
      const value = record[keys[i]];
      const entry = toObject(value);
      const decision = toString(entry.decision || entry.status || value).toLowerCase();
      if (decision === 'borrowed' || decision === 'confirmed' || decision === 'borrowing') {
        return true;
      }
    }
    return false;
  }

  function conceptStatusClass(conceptId) {
    const decision = shellDecisionForConcept(conceptId);
    if (decision.status === 'reviewed') return 'reviewed';
    if (decision.status === 'flagged') return 'flagged';
    if (conceptHasBorrowingFlag(conceptId)) return 'borrowing';
    return 'unreviewed';
  }

  function matchesReviewFilter(concept) {
    const decision = shellDecisionForConcept(concept.id);

    if (state.reviewFilter === 'unreviewed') {
      return decision.status !== 'reviewed';
    }

    if (state.reviewFilter === 'flagged') {
      return decision.status === 'flagged';
    }

    if (state.reviewFilter === 'borrowing') {
      return conceptHasBorrowingFlag(concept.id);
    }

    return true;
  }

  function matchesSidebarQuery(concept) {
    const query = toString(state.sidebarQuery).toLowerCase();
    if (!query) return true;

    const label = conceptDisplayLabel(concept).toLowerCase();
    const id = toString(concept.id).toLowerCase();
    return label.indexOf(query) !== -1 || id.indexOf(query) !== -1;
  }

  function buildVisibleConcepts() {
    const visible = applyTagFilter(state.concepts).filter(function (concept) {
      return matchesReviewFilter(concept) && matchesSidebarQuery(concept);
    });

    visible.sort(function (left, right) {
      if (state.sortMode === 'id') {
        return conceptSort(left, right);
      }
      return conceptDisplayLabel(left).localeCompare(conceptDisplayLabel(right));
    });

    return visible;
  }

  function selectedConceptIndex() {
    for (let i = 0; i < state.filteredConcepts.length; i += 1) {
      if (state.filteredConcepts[i].id === state.selectedConceptId) {
        return i;
      }
    }
    return -1;
  }

  function setReferencePlaceholderValue(target, text) {
    if (!target) return;
    target.textContent = toString(text) || '—';
  }

  function renderSidebar() {
    if (!state.sidebarConceptListEl) return;

    if (!state.filteredConcepts.length) {
      if (state.isBootstrapping) {
        state.sidebarConceptListEl.innerHTML = '<div class="sidebar-empty panel-placeholder">Loading concept queue…</div>';
      } else if (!state.concepts.length) {
        if (isNoDataState()) {
          state.sidebarConceptListEl.innerHTML = '<div class="sidebar-empty panel-placeholder">No compare data detected yet. Add speaker annotations or concept CSV data, then refresh Compare.</div>';
        } else {
          state.sidebarConceptListEl.innerHTML = '<div class="sidebar-empty panel-placeholder">Concept queue is empty. Check concept IDs/labels in project CSV or annotation concept tiers.</div>';
        }
      } else {
        state.sidebarConceptListEl.innerHTML = '<div class="sidebar-empty panel-placeholder">No concepts match current search/filter settings.</div>';
      }
      return;
    }

    const rows = [];
    for (let i = 0; i < state.filteredConcepts.length; i += 1) {
      const concept = state.filteredConcepts[i];
      rows.push(
        '<div class="concept-item' + (concept.id === state.selectedConceptId ? ' active' : '') + '" data-action="select-concept" data-concept-id="' + escapeHtml(concept.id) + '">' +
          '<span class="status-dot ' + conceptStatusClass(concept.id) + '"></span>' +
          '<span class="ci-name">' + escapeHtml(conceptDisplayLabel(concept)) + '</span>' +
          '<span class="ci-id">#' + escapeHtml(concept.id) + '</span>' +
        '</div>'
      );
    }

    state.sidebarConceptListEl.innerHTML = rows.join('');
  }

  function scrollSidebarSelectionIntoView() {
    if (!state.sidebarConceptListEl) return;
    const active = state.sidebarConceptListEl.querySelector('.concept-item.active');
    if (active && typeof active.scrollIntoView === 'function') {
      active.scrollIntoView({ block: 'nearest' });
    }
  }

  function updateProgressUi() {
    if (!state.progressBadgeEl || !state.progressBarEl) return;

    const total = state.concepts.length;
    let reviewed = 0;
    for (let i = 0; i < state.concepts.length; i += 1) {
      if (shellDecisionForConcept(state.concepts[i].id).status === 'reviewed') {
        reviewed += 1;
      }
    }

    if (!total) {
      state.progressBadgeEl.textContent = state.isBootstrapping ? 'Loading concepts…' : '0 / 0 reviewed';
      state.progressBarEl.style.width = '0%';
      return;
    }

    state.progressBadgeEl.textContent = reviewed + ' / ' + total + ' reviewed';
    state.progressBarEl.style.width = String((reviewed / total) * 100) + '%';
  }

  function valueForSpeakerId(record, speakerId) {
    const map = toObject(record);
    const wanted = toString(speakerId);
    if (!wanted) return undefined;

    if (Object.prototype.hasOwnProperty.call(map, wanted)) {
      return map[wanted];
    }

    const wantedLower = wanted.toLowerCase();
    const keys = Object.keys(map);
    for (let i = 0; i < keys.length; i += 1) {
      if (toString(keys[i]).toLowerCase() === wantedLower) {
        return map[keys[i]];
      }
    }

    return undefined;
  }

  function valueByAliases(source, aliases) {
    const map = toObject(source);
    const inAliases = Array.isArray(aliases) ? aliases : [aliases];
    const wanted = [];

    for (let i = 0; i < inAliases.length; i += 1) {
      const alias = toString(inAliases[i]).toLowerCase();
      if (!alias) continue;
      if (wanted.indexOf(alias) === -1) {
        wanted.push(alias);
      }
    }

    if (!wanted.length) {
      return undefined;
    }

    for (let i = 0; i < wanted.length; i += 1) {
      if (Object.prototype.hasOwnProperty.call(map, wanted[i])) {
        return map[wanted[i]];
      }
    }

    const keys = Object.keys(map);
    for (let i = 0; i < keys.length; i += 1) {
      const key = toString(keys[i]).toLowerCase();
      if (wanted.indexOf(key) !== -1) {
        return map[keys[i]];
      }
    }

    return undefined;
  }

  function normalizedSimilarityScore(value) {
    let score = toFiniteNumber(value);
    if (!Number.isFinite(score)) return null;

    if (score > 1 && score <= 100) {
      score = score / 100;
    }

    if (score < 0) score = 0;
    if (score > 1) score = 1;
    return score;
  }

  function readScoreFromSimilarityValue(value) {
    const direct = normalizedSimilarityScore(value);
    if (Number.isFinite(direct)) {
      return direct;
    }

    const node = toObject(value);
    const scoreKeys = ['score', 'similarity', 'value', 'similarity_score', 'similarityScore'];
    for (let i = 0; i < scoreKeys.length; i += 1) {
      const score = normalizedSimilarityScore(node[scoreKeys[i]]);
      if (Number.isFinite(score)) {
        return score;
      }
    }

    return null;
  }

  function collectReferenceForms(value, out, depth) {
    const target = Array.isArray(out) ? out : [];
    const level = Number.isFinite(Number(depth)) ? Number(depth) : 0;

    if (target.length >= 8 || level > 4 || value == null) {
      return target;
    }

    if (typeof value === 'string' || typeof value === 'number') {
      const text = toString(value);
      if (text && target.indexOf(text) === -1) {
        target.push(text);
      }
      return target;
    }

    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i += 1) {
        collectReferenceForms(value[i], target, level + 1);
        if (target.length >= 8) break;
      }
      return target;
    }

    const node = toObject(value);
    const keys = ['reference_forms', 'referenceForms', 'references', 'forms', 'form', 'ipa', 'orthography', 'ortho', 'transcription'];
    for (let i = 0; i < keys.length; i += 1) {
      if (!Object.prototype.hasOwnProperty.call(node, keys[i])) continue;
      collectReferenceForms(node[keys[i]], target, level + 1);
      if (target.length >= 8) break;
    }

    return target;
  }

  function similarityInfoForSpeaker(conceptId, speakerId, aliases) {
    const info = {
      score: null,
      references: [],
    };

    const similarity = toObject(toObject(P.enrichments).similarity);
    const conceptNode = valueForConceptId(similarity, conceptId);
    const conceptMap = toObject(conceptNode);
    if (!Object.keys(conceptMap).length) {
      return info;
    }

    const candidates = [];

    function pushCandidate(value) {
      if (typeof value !== 'undefined' && value !== null) {
        candidates.push(value);
      }
    }

    const speakerNodes = [
      valueForSpeakerId(conceptMap, speakerId),
      valueForSpeakerId(toObject(conceptMap.speakers), speakerId),
    ];

    for (let i = 0; i < speakerNodes.length; i += 1) {
      const speakerNode = toObject(speakerNodes[i]);
      pushCandidate(valueByAliases(speakerNode, aliases));
      pushCandidate(valueByAliases(toObject(speakerNode.languages), aliases));
      pushCandidate(valueByAliases(toObject(speakerNode.scores), aliases));
      pushCandidate(valueByAliases(toObject(speakerNode.similarity), aliases));
    }

    const languageNodes = [
      valueByAliases(conceptMap, aliases),
      valueByAliases(toObject(conceptMap.languages), aliases),
    ];

    for (let i = 0; i < languageNodes.length; i += 1) {
      const languageNode = languageNodes[i];
      pushCandidate(languageNode);

      const languageMap = toObject(languageNode);
      pushCandidate(valueForSpeakerId(languageMap, speakerId));
      pushCandidate(valueForSpeakerId(toObject(languageMap.speakers), speakerId));
      pushCandidate(valueForSpeakerId(toObject(languageMap.values), speakerId));
      pushCandidate(valueForSpeakerId(toObject(languageMap.scores), speakerId));
    }

    for (let i = 0; i < candidates.length; i += 1) {
      const candidate = candidates[i];
      if (!Number.isFinite(info.score)) {
        const score = readScoreFromSimilarityValue(candidate);
        if (Number.isFinite(score)) {
          info.score = score;
        }
      }
      collectReferenceForms(candidate, info.references, 0);
    }

    return info;
  }

  function referenceFormsForConceptLanguage(conceptId, aliases) {
    const refs = [];

    const speakers = state.selectedSpeakers.length
      ? state.selectedSpeakers
      : state.availableSpeakers;

    for (let i = 0; i < speakers.length; i += 1) {
      const info = similarityInfoForSpeaker(conceptId, speakers[i], aliases);
      collectReferenceForms(info.references, refs, 0);
      if (refs.length >= 8) break;
    }

    const similarity = toObject(toObject(P.enrichments).similarity);
    const conceptNode = toObject(valueForConceptId(similarity, conceptId));
    collectReferenceForms(valueByAliases(conceptNode, aliases), refs, 0);
    collectReferenceForms(valueByAliases(toObject(conceptNode.languages), aliases), refs, 0);

    return refs.slice(0, 4);
  }

  function renderReferenceCards(concept) {
    if (!concept) {
      setReferencePlaceholderValue(state.refArabicFormEl, '—');
      setReferencePlaceholderValue(state.refArabicIpaEl, '—');
      setReferencePlaceholderValue(state.refPersianFormEl, '—');
      setReferencePlaceholderValue(state.refPersianIpaEl, '—');
      return;
    }

    function applyReferenceValues(formEl, ipaEl, refs, languageLabel) {
      if (!formEl || !ipaEl) return;

      if (!refs.length) {
        formEl.textContent = 'No data';
        ipaEl.textContent = 'No ' + languageLabel + ' reference form available for this concept yet.';
        return;
      }

      formEl.textContent = refs[0];
      if (refs.length > 1) {
        ipaEl.textContent = refs.slice(1).join(' · ');
      } else {
        ipaEl.textContent = 'Reference form available from enrichments.';
      }
    }

    applyReferenceValues(
      state.refArabicFormEl,
      state.refArabicIpaEl,
      referenceFormsForConceptLanguage(concept.id, ['ar', 'arabic']),
      'Arabic'
    );

    applyReferenceValues(
      state.refPersianFormEl,
      state.refPersianIpaEl,
      referenceFormsForConceptLanguage(concept.id, ['fa', 'persian']),
      'Persian'
    );
  }

  function annotationEntryForSpeakerConcept(speaker, conceptId) {
    const speakerId = toString(speaker);
    const conceptKey = normalizeConceptId(conceptId);
    if (!speakerId || !conceptKey) {
      return null;
    }

    const conceptTable = toObject(P.modules).conceptTable;
    if (conceptTable && typeof conceptTable.getEntryForSpeakerConcept === 'function') {
      const fromTable = conceptTable.getEntryForSpeakerConcept(speakerId, conceptKey);
      if (fromTable && typeof fromTable === 'object') {
        const startSec = toFiniteNumber(fromTable.startSec != null ? fromTable.startSec : fromTable.start);
        const endSec = toFiniteNumber(fromTable.endSec != null ? fromTable.endSec : fromTable.end);
        return {
          sourceWav: toString(fromTable.sourceWav || fromTable.source_wav),
          startSec: Number.isFinite(startSec) ? startSec : null,
          endSec: Number.isFinite(endSec) ? endSec : null,
          ipa: toString(fromTable.ipa),
          ortho: toString(fromTable.ortho),
        };
      }
    }

    const record = toObject(toObject(P.annotations)[speakerId]);
    const conceptIntervals = intervalsFromTier(record, 'concept');

    for (let i = 0; i < conceptIntervals.length; i += 1) {
      const interval = toObject(conceptIntervals[i]);
      if (normalizeConceptId(interval.text) !== conceptKey) {
        continue;
      }

      const startSec = toFiniteNumber(interval.start);
      const endSec = toFiniteNumber(interval.end);
      if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec) {
        continue;
      }

      return {
        sourceWav: toString(record.source_audio),
        startSec: startSec,
        endSec: endSec,
        ipa: findIntervalTextByBounds(intervalsFromTier(record, 'ipa'), startSec, endSec),
        ortho: findIntervalTextByBounds(intervalsFromTier(record, 'ortho'), startSec, endSec),
      };
    }

    return null;
  }

  function groupsForConcept(conceptId) {
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return {};

    const enrichmentsIO = toObject(P.modules).enrichmentsIO;
    if (enrichmentsIO && typeof enrichmentsIO.getCognateGroupsForConcept === 'function') {
      return toObject(enrichmentsIO.getCognateGroupsForConcept(conceptKey));
    }

    const enrichments = toObject(P.enrichments);
    const manual = toObject(toObject(enrichments.manual_overrides).cognate_sets);
    const manualGroups = valueForConceptId(manual, conceptKey);
    if (manualGroups) {
      return toObject(manualGroups);
    }

    return toObject(valueForConceptId(toObject(enrichments.cognate_sets), conceptKey));
  }

  function cognateGroupForSpeaker(conceptId, speakerId) {
    const conceptKey = normalizeConceptId(conceptId);
    const speakerKey = toString(speakerId);
    if (!conceptKey || !speakerKey) return '';

    const enrichmentsIO = toObject(P.modules).enrichmentsIO;
    if (enrichmentsIO && typeof enrichmentsIO.getGroupForSpeaker === 'function') {
      return normalizeGroupLetter(enrichmentsIO.getGroupForSpeaker(conceptKey, speakerKey));
    }

    const groups = groupsForConcept(conceptKey);
    const keys = Object.keys(groups);
    for (let i = 0; i < keys.length; i += 1) {
      const group = normalizeGroupLetter(keys[i]);
      if (!group) continue;
      const members = Array.isArray(groups[keys[i]]) ? groups[keys[i]] : [];
      for (let j = 0; j < members.length; j += 1) {
        if (toString(members[j]) === speakerKey) {
          return group;
        }
      }
    }

    return '';
  }

  function normalizeBorrowingBadgeDecision(value) {
    const raw = toString(value).toLowerCase();
    if (!raw) return '';

    if (
      raw === 'borrowed' ||
      raw === 'confirmed' ||
      raw === 'borrowing' ||
      raw === 'loan'
    ) {
      return 'borrowed';
    }

    if (
      raw === 'native' ||
      raw === 'not_borrowing' ||
      raw === 'not-borrowing' ||
      raw === 'not borrowing'
    ) {
      return 'native';
    }

    if (raw === 'uncertain' || raw === 'undecided' || raw === 'unknown') {
      return 'uncertain';
    }

    return '';
  }

  function borrowingBadgeForSpeaker(conceptId, speakerId) {
    const records = borrowingRecordForConcept(conceptId);
    const entry = valueForSpeakerId(records, speakerId);
    const decision = normalizeBorrowingBadgeDecision(toObject(entry).decision || toObject(entry).status || entry);

    if (decision === 'borrowed') {
      return { className: 'borrowed', label: 'Borrowed' };
    }

    if (decision === 'native') {
      return { className: 'native', label: 'Native' };
    }

    if (decision === 'uncertain') {
      return { className: 'uncertain', label: 'Uncertain' };
    }

    return { className: 'none', label: '—' };
  }

  function similarityCellHtml(info) {
    if (!info || !Number.isFinite(info.score)) {
      return '<span class="forms-sim empty">No data</span>';
    }

    const refs = Array.isArray(info.references) ? info.references : [];
    const title = refs.length
      ? ' title="' + escapeHtml('Refs: ' + refs.join(', ')) + '"'
      : '';

    return '<span class="forms-sim"' + title + '>' + info.score.toFixed(2) + '</span>';
  }

  function renderSpeakerFormsPlaceholder(concept) {
    const tbody = state.formsTbodyEl || document.getElementById('forms-tbody');
    if (!tbody) return;

    state.formsTbodyEl = tbody;

    if (!concept) {
      tbody.innerHTML = '<tr class="forms-empty-row"><td colspan="6" class="empty-msg">Select a concept from the sidebar to begin speaker-by-speaker review.</td></tr>';
      return;
    }

    if (!state.selectedSpeakers.length) {
      tbody.innerHTML = '<tr class="forms-empty-row"><td colspan="6" class="empty-msg">No speakers selected. Use the speaker controls above to add speakers for this concept.</td></tr>';
      return;
    }

    const rows = [];
    for (let i = 0; i < state.selectedSpeakers.length; i += 1) {
      const speaker = state.selectedSpeakers[i];
      const entry = annotationEntryForSpeakerConcept(speaker, concept.id);
      const hasEntry = !!entry;
      const hasPlayableClip = !!(
        hasEntry &&
        entry.sourceWav &&
        Number.isFinite(entry.startSec) &&
        Number.isFinite(entry.endSec) &&
        entry.endSec > entry.startSec
      );

      const arInfo = similarityInfoForSpeaker(concept.id, speaker, ['ar', 'arabic']);
      const faInfo = similarityInfoForSpeaker(concept.id, speaker, ['fa', 'persian']);

      const group = cognateGroupForSpeaker(concept.id, speaker);
      const badgeColor = colorForGroup(group);
      const borrowing = borrowingBadgeForSpeaker(concept.id, speaker);

      const formCell = hasEntry
        ? (
          '<div class="forms-entry">' +
            (hasPlayableClip
              ? ('<button type="button" class="play-btn" data-action="play-speaker-form" data-source-wav="' + escapeHtml(entry.sourceWav) + '" data-start-sec="' + escapeHtml(entry.startSec) + '" data-end-sec="' + escapeHtml(entry.endSec) + '" data-speaker="' + escapeHtml(speaker) + '" data-concept-id="' + escapeHtml(concept.id) + '" title="Play annotated clip">▶</button>')
              : '<button type="button" class="play-btn" disabled title="Audio clip unavailable for this entry">▶</button>') +
            '<div class="forms-entry-lines">' +
              '<div class="forms-entry-ipa">' + escapeHtml(entry.ipa || '—') + '</div>' +
              '<div class="forms-entry-ortho">' + escapeHtml(entry.ortho || '—') + '</div>' +
              '<div class="forms-entry-time">' +
                (Number.isFinite(entry.startSec) && Number.isFinite(entry.endSec)
                  ? (escapeHtml(formatSecondsToClock(entry.startSec)) + '–' + escapeHtml(formatSecondsToClock(entry.endSec)))
                  : 'No timestamp') +
              '</div>' +
            '</div>' +
          '</div>'
        )
        : '<span class="empty-msg">No annotated form available for this concept yet.</span>';

      const cognateCell = group
        ? '<span class="forms-cognate-chip" style="border-color:' + badgeColor + ';color:' + badgeColor + ';background:' + hexToRgba(badgeColor, 0.15) + '" title="Cognate group ' + escapeHtml(group) + '">' + escapeHtml(group) + '</span>'
        : '<span class="forms-cognate-chip empty">—</span>';

      rows.push(
        '<tr' + (borrowing.className === 'borrowed' ? ' class="borrowing-row"' : '') + '>' +
          '<td class="forms-speaker">' + escapeHtml(speaker) + '</td>' +
          '<td>' + formCell + '</td>' +
          '<td>' + similarityCellHtml(arInfo) + '</td>' +
          '<td>' + similarityCellHtml(faInfo) + '</td>' +
          '<td>' + cognateCell + '</td>' +
          '<td><span class="forms-flag-chip ' + borrowing.className + '">' + escapeHtml(borrowing.label) + '</span></td>' +
        '</tr>'
      );
    }

    tbody.innerHTML = rows.join('');
  }

  function setActionButtonState(button, active, disabled) {
    if (!button) return;
    button.classList.toggle('active', !!active);
    button.disabled = !!disabled;
  }

  function renderShellContent() {
    const concept = currentConcept();
    const decision = concept ? shellDecisionForConcept(concept.id) : { status: 'unreviewed', notes: '' };
    const index = selectedConceptIndex();
    const hasConcept = !!concept;

    if (state.conceptTitleEl) {
      state.conceptTitleEl.innerHTML = hasConcept
        ? escapeHtml(conceptDisplayLabel(concept)) + ' <span>(#' + escapeHtml(concept.id) + ')</span>'
        : 'Compare review shell <span>(sidebar-first workflow)</span>';
    }

    renderReferenceCards(concept);
    renderSpeakerFormsPlaceholder(concept);
    renderShellStateMeta();

    if (state.notesFieldEl) {
      state.notesFieldEl.disabled = !hasConcept;
      state.notesFieldEl.value = hasConcept ? decision.notes : '';
      state.notesFieldEl.placeholder = hasConcept
        ? 'Draft concept note (saved in local shell decisions).'
        : 'Select a concept to add notes.';
    }

    if (state.navPositionEl) {
      if (!state.filteredConcepts.length) {
        if (state.isBootstrapping) {
          state.navPositionEl.textContent = 'Loading concept queue…';
        } else if (state.bootstrapErrorMessage) {
          state.navPositionEl.textContent = 'Compare boot error. Check status above.';
        } else if (!state.concepts.length) {
          state.navPositionEl.textContent = isNoDataState()
            ? 'No compare data detected yet.'
            : 'Concept queue is empty.';
        } else {
          state.navPositionEl.textContent = 'No concepts match current filters.';
        }
      } else if (index === -1) {
        state.navPositionEl.textContent = 'Select a concept from the sidebar to continue.';
      } else {
        state.navPositionEl.textContent = 'Concept ' + (index + 1) + ' of ' + state.filteredConcepts.length;
      }
    }

    const atStart = index <= 0;
    const atEnd = index === -1 || index >= state.filteredConcepts.length - 1;
    for (let i = 0; i < state.navPrevButtons.length; i += 1) {
      state.navPrevButtons[i].disabled = !hasConcept || atStart;
    }
    for (let i = 0; i < state.navNextButtons.length; i += 1) {
      state.navNextButtons[i].disabled = !hasConcept || atEnd;
    }

    for (let i = 0; i < state.acceptButtons.length; i += 1) {
      setActionButtonState(state.acceptButtons[i], hasConcept && decision.status === 'reviewed', !hasConcept);
    }
    for (let i = 0; i < state.flagButtons.length; i += 1) {
      setActionButtonState(state.flagButtons[i], hasConcept && decision.status === 'flagged', !hasConcept);
    }

    if (state.sidebarSearchEl && state.sidebarSearchEl.value !== state.sidebarQuery) {
      state.sidebarSearchEl.value = state.sidebarQuery;
    }
    for (let i = 0; i < state.sidebarFilterButtons.length; i += 1) {
      const button = state.sidebarFilterButtons[i];
      button.classList.toggle('active', toString(button.dataset.filter) === state.reviewFilter);
    }
    for (let i = 0; i < state.sidebarSortButtons.length; i += 1) {
      const button = state.sidebarSortButtons[i];
      button.classList.toggle('active', toString(button.dataset.sort) === state.sortMode);
    }

    updateProgressUi();
    renderSidebar();
    scrollSidebarSelectionIntoView();
  }

  function setSelectedConcept(conceptId, options) {
    const opts = toObject(options);
    const normalized = normalizeConceptId(conceptId);
    if (!normalized) {
      state.selectedConceptId = '';
      P.currentConcept = null;
      updateCompareStateSnapshot();
      renderShellContent();
      applyAssistantContext('concept-cleared', true);
      return;
    }

    state.selectedConceptId = normalized;
    P.currentConcept = normalized;
    updateCompareStateSnapshot();
    renderShellContent();
    applyAssistantContext('concept-selected', true);

    if (opts.dispatch !== false) {
      scheduleConceptSelectionDispatch();
    }
  }

  function navigateShell(delta) {
    const currentIndex = selectedConceptIndex();
    if (currentIndex === -1) return;
    const nextIndex = Math.max(0, Math.min(state.filteredConcepts.length - 1, currentIndex + delta));
    if (nextIndex === currentIndex) return;
    setSelectedConcept(state.filteredConcepts[nextIndex].id);
  }

  function toggleShellStatus(nextStatus) {
    const concept = currentConcept();
    if (!concept) return;

    const decision = shellDecisionForConcept(concept.id);
    const normalized = nextStatus === decision.status ? 'unreviewed' : nextStatus;
    decision.status = normalized;
    persistShellDraft();
    syncViews();
  }

  function downloadShellDraft() {
    const payload = {
      version: SHELL_DRAFT_EXPORT_VERSION,
      mode: 'compare-shell-draft',
      savedAt: new Date().toISOString(),
      decisions: state.shellDecisions,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'compare-shell-draft.json';
    link.click();
    URL.revokeObjectURL(url);
    showToast('Shell draft exported.');
  }

  function importShellDraftObject(parsed) {
    const source = toObject(parsed && (parsed.decisions || parsed));
    const next = {};
    const keys = Object.keys(source);
    for (let i = 0; i < keys.length; i += 1) {
      const conceptId = normalizeConceptId(keys[i]);
      if (!conceptId) continue;
      next[conceptId] = normalizeShellDecision(source[keys[i]]);
    }

    state.shellDecisions = next;
    persistShellDraft();
    syncViews();
  }

  function importShellDraftFile(file, resetInput) {
    const selectedFile = file || null;
    if (!selectedFile) return;

    const reader = new FileReader();
    reader.onload = function (loadEvent) {
      try {
        const parsed = JSON.parse(String(loadEvent.target && loadEvent.target.result ? loadEvent.target.result : '{}'));
        importShellDraftObject(parsed);
        showToast('Shell draft loaded.');
      } catch (error) {
        showToast('Could not load shell draft JSON.');
        console.warn('[compare] shell draft import failed:', error);
      } finally {
        if (typeof resetInput === 'function') {
          resetInput();
        }
      }
    };
    reader.readAsText(selectedFile);
  }

  function ensureShellFileInput() {
    if (state.shellFileInputEl) return state.shellFileInputEl;

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.className = 'hidden';
    document.body.appendChild(input);
    state.shellFileInputEl = input;
    addListener(input, 'change', function (event) {
      const target = event.target;
      const file = target && target.files ? target.files[0] : null;
      importShellDraftFile(file, function () {
        input.value = '';
      });
    });
    return input;
  }

  function applyReviewFilter(mode) {
    const next = toString(mode).toLowerCase();
    if (REVIEW_FILTER_ORDER.indexOf(next) === -1) {
      return;
    }

    state.reviewFilter = next;
    state.selectedConceptId = '';
    syncViews();
  }

  function applySortMode(mode) {
    const next = toString(mode).toLowerCase();
    if (SIDEBAR_SORT_ORDER.indexOf(next) === -1) {
      return;
    }

    state.sortMode = next;
    state.selectedConceptId = '';
    syncViews();
  }

  function applySidebarQuery(query) {
    state.sidebarQuery = String(query == null ? '' : query);
    state.selectedConceptId = '';
    syncViews();
  }

  function setShellNoteText(text) {
    const concept = currentConcept();
    if (!concept) return;

    const decision = shellDecisionForConcept(concept.id);
    decision.notes = String(text == null ? '' : text);

    if (state.notesPersistTimer) {
      window.clearTimeout(state.notesPersistTimer);
    }
    state.notesPersistTimer = window.setTimeout(function () {
      persistShellDraft();
      state.notesPersistTimer = 0;
    }, NOTE_SAVE_DELAY_MS);
  }

  function selectConceptByIndex(indexLike) {
    if (!state.filteredConcepts.length) {
      return;
    }

    const numeric = Number(indexLike);
    if (!Number.isFinite(numeric)) {
      return;
    }

    const index = Math.max(0, Math.min(state.filteredConcepts.length - 1, Math.round(numeric)));
    const concept = state.filteredConcepts[index];
    if (!concept) return;

    setSelectedConcept(concept.id);
  }

  function triggerShellDraftLoadPicker() {
    if (state.legacyFileInputEl) {
      state.legacyFileInputEl.click();
      return;
    }

    ensureShellFileInput().click();
  }

  function onLegacyDecisionInput(event) {
    const target = event && event.target;
    const file = target && target.files ? target.files[0] : null;
    importShellDraftFile(file, function () {
      if (target) {
        target.value = '';
      }
    });
  }

  function bindLegacyShellCompatGlobals() {
    if (state.legacyCompatGlobals) {
      return;
    }

    const compat = {
      setFilter: function (mode) {
        if (!state.initialized) return;
        applyReviewFilter(mode);
      },
      setSort: function (mode) {
        if (!state.initialized) return;
        applySortMode(mode);
      },
      filterSidebar: function (query) {
        if (!state.initialized) return;
        applySidebarQuery(query);
      },
      navigate: function (delta) {
        if (!state.initialized) return;
        navigateShell(Number(delta) < 0 ? -1 : 1);
      },
      toggleAccept: function () {
        if (!state.initialized) return;
        toggleShellStatus('reviewed');
      },
      toggleFlag: function () {
        if (!state.initialized) return;
        toggleShellStatus('flagged');
      },
      saveNotes: function (value) {
        if (!state.initialized) return;
        setShellNoteText(value);
      },
      triggerLoadDecisions: function () {
        if (!state.initialized) return;
        triggerShellDraftLoadPicker();
      },
      saveDecisions: function () {
        if (!state.initialized) return;
        downloadShellDraft();
      },
      renderConcept: function (index) {
        if (!state.initialized) return;
        selectConceptByIndex(index);
      },
      renderCurrentConcept: function () {
        if (!state.initialized) return;
        renderShellContent();
      },
      handleDecisionLoad: function (event) {
        if (!state.initialized) return;
        onLegacyDecisionInput(event);
      },
    };

    state.legacyCompatGlobals = {};
    const names = Object.keys(compat);
    for (let i = 0; i < names.length; i += 1) {
      const name = names[i];
      state.legacyCompatGlobals[name] = window[name];
      window[name] = compat[name];
    }
  }

  function unbindLegacyShellCompatGlobals() {
    const previous = state.legacyCompatGlobals;
    if (!previous) {
      return;
    }

    const names = Object.keys(previous);
    for (let i = 0; i < names.length; i += 1) {
      const name = names[i];
      const value = previous[name];
      if (typeof value === 'undefined') {
        delete window[name];
      } else {
        window[name] = value;
      }
    }

    state.legacyCompatGlobals = null;
  }

  function onSidebarInput(event) {
    const target = event && event.target;
    if (!target) return;

    if (target === state.sidebarSearchEl) {
      applySidebarQuery(target.value);
    }

    if (target === state.notesFieldEl) {
      setShellNoteText(target.value);
    }
  }

  function onSidebarClick(event) {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;

    const conceptItem = target.closest('[data-action="select-concept"]');
    if (conceptItem) {
      setSelectedConcept(conceptItem.dataset.conceptId);
      return;
    }

    const filterButton = target.closest('.filter-btn[data-filter]');
    if (filterButton && state.sidebarFilterButtons.indexOf(filterButton) !== -1) {
      applyReviewFilter(filterButton.dataset.filter);
      return;
    }

    const sortButton = target.closest('.sort-btn[data-sort]');
    if (sortButton && state.sidebarSortButtons.indexOf(sortButton) !== -1) {
      applySortMode(sortButton.dataset.sort);
      return;
    }

    if (state.navPrevButtons.indexOf(target.closest('.nav-btn')) !== -1) {
      navigateShell(-1);
      return;
    }

    if (state.navNextButtons.indexOf(target.closest('.nav-btn')) !== -1) {
      navigateShell(1);
      return;
    }

    if (state.acceptButtons.indexOf(target.closest('.action-btn.accept')) !== -1) {
      toggleShellStatus('reviewed');
      return;
    }

    if (state.flagButtons.indexOf(target.closest('.action-btn.flag')) !== -1) {
      toggleShellStatus('flagged');
      return;
    }

    if (clickedElementMatches(target, state.loadButtonEl)) {
      triggerShellDraftLoadPicker();
      return;
    }

    if (clickedElementMatches(target, state.saveButtonEl)) {
      downloadShellDraft();
    }
  }

  function onFormsTableClick(event) {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;

    const playButton = target.closest('[data-action="play-speaker-form"]');
    if (!playButton) {
      return;
    }

    const sourceWav = toString(playButton.dataset.sourceWav);
    const startSec = toFiniteNumber(playButton.dataset.startSec);
    const endSec = toFiniteNumber(playButton.dataset.endSec);
    if (!sourceWav || !Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec) {
      showToast('Audio clip unavailable for this row.');
      return;
    }

    dispatchEvent('parse:audio-play', {
      sourceWav: sourceWav,
      startSec: startSec,
      endSec: endSec,
      speaker: toString(playButton.dataset.speaker),
      conceptId: numericOrTextConceptId(playButton.dataset.conceptId),
    });
  }

  function onShellKeydown(event) {
    if (!state.initialized) return;
    const target = event.target;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].indexOf(target.tagName) !== -1) {
      return;
    }

    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault();
      navigateShell(1);
      return;
    }

    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault();
      navigateShell(-1);
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      toggleShellStatus('reviewed');
      return;
    }

    if (event.key === 'b' || event.key === 'B' || event.key === 'f' || event.key === 'F') {
      event.preventDefault();
      toggleShellStatus('flagged');
    }
  }

  async function loadProjectConfig() {
    const configModule = toObject(P.modules).config;
    if (configModule && typeof configModule.init === 'function') {
      const loaded = await configModule.init();
      if (loaded) {
        return loaded;
      }
    }

    try {
      const response = await fetch('/project.json', {
        method: 'GET',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        throw new Error('HTTP ' + response.status + ' while loading /project.json');
      }

      const project = await response.json();
      P.project = project;
      return project;
    } catch (error) {
      console.warn('[compare] project config unavailable:', error);
      P.project = P.project || null;
      return P.project;
    }
  }

  async function loadSourceIndex() {
    const candidates = ['/source_index.json', 'source_index.json'];

    for (let i = 0; i < candidates.length; i += 1) {
      try {
        const response = await fetch(candidates[i], {
          method: 'GET',
          cache: 'no-store',
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) continue;
        const sourceIndex = await response.json();
        if (sourceIndex && typeof sourceIndex === 'object') {
          P.sourceIndex = sourceIndex;
          return sourceIndex;
        }
      } catch (_) {
      }
    }

    return P.sourceIndex || null;
  }

  function collectSpeakerIds() {
    const result = [];
    const seen = new Set();

    function pushSpeaker(value) {
      const speaker = toString(value);
      if (!speaker || seen.has(speaker)) return;
      seen.add(speaker);
      result.push(speaker);
    }

    const projectSpeakers = toObject(toObject(P.project).speakers);
    const projectKeys = Object.keys(projectSpeakers);
    for (let i = 0; i < projectKeys.length; i += 1) {
      pushSpeaker(projectKeys[i]);
    }

    const sourceIndexSpeakers = toObject(toObject(P.sourceIndex).speakers);
    const sourceIndexKeys = Object.keys(sourceIndexSpeakers);
    for (let i = 0; i < sourceIndexKeys.length; i += 1) {
      pushSpeaker(sourceIndexKeys[i]);
    }

    const annotationKeys = Object.keys(toObject(P.annotations));
    for (let i = 0; i < annotationKeys.length; i += 1) {
      pushSpeaker(annotationKeys[i]);
    }

    return result;
  }

  async function ensureAnnotationStore() {
    const annotationStore = toObject(P.modules).annotationStore;
    if (!annotationStore) return;
    if (typeof annotationStore.init === 'function') {
      annotationStore.init();
    }
  }

  async function loadAnnotationsForSpeakers(speakers) {
    const list = Array.isArray(speakers) ? speakers : [];
    const annotationStore = toObject(P.modules).annotationStore;

    if (annotationStore && typeof annotationStore.loadSpeaker === 'function') {
      const jobs = [];
      for (let i = 0; i < list.length; i += 1) {
        jobs.push(annotationStore.loadSpeaker(list[i]));
      }
      await Promise.all(jobs);
      return;
    }

    const jobs = [];
    for (let i = 0; i < list.length; i += 1) {
      const speaker = list[i];
      jobs.push((async function () {
        try {
          const response = await fetch('/api/annotations/' + encodeURIComponent(speaker), {
            method: 'GET',
            headers: { Accept: 'application/json' },
          });
          if (!response.ok) return;
          const record = await response.json();
          P.annotations = toObject(P.annotations);
          P.annotations[speaker] = record;
        } catch (_) {
        }
      })());
    }

    await Promise.all(jobs);
  }

  function extractAnnotationConceptLabels() {
    const labels = {};
    const annotations = toObject(P.annotations);
    const speakers = Object.keys(annotations);

    for (let i = 0; i < speakers.length; i += 1) {
      const record = annotations[speakers[i]];
      const tiers = toObject(record && record.tiers);
      const conceptIntervals = Array.isArray(toObject(tiers.concept).intervals)
        ? tiers.concept.intervals
        : [];

      for (let j = 0; j < conceptIntervals.length; j += 1) {
        const interval = conceptIntervals[j];
        const split = splitConceptText(interval && interval.text);
        const id = split.conceptId;
        if (!id) continue;
        if (!labels[id] && split.conceptLabel) {
          labels[id] = split.conceptLabel;
        }
      }
    }

    return labels;
  }

  function detectDelimiter(headerLine) {
    const text = toString(headerLine);
    const commaCount = (text.match(/,/g) || []).length;
    const tabCount = (text.match(/\t/g) || []).length;
    const semicolonCount = (text.match(/;/g) || []).length;

    if (tabCount >= commaCount && tabCount >= semicolonCount) return '\t';
    if (semicolonCount > commaCount) return ';';
    return ',';
  }

  function parseDelimitedLine(line, delimiter) {
    const cells = [];
    let current = '';
    let inQuote = false;

    for (let i = 0; i < line.length; i += 1) {
      const char = line.charAt(i);

      if (char === '"') {
        if (inQuote && line.charAt(i + 1) === '"') {
          current += '"';
          i += 1;
        } else {
          inQuote = !inQuote;
        }
      } else if (char === delimiter && !inQuote) {
        cells.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }

    cells.push(current.trim());
    return cells;
  }

  function normalizeHeader(value) {
    return toString(value).toLowerCase().replace(/[^a-z0-9]+/g, '');
  }

  function headerIndex(headers, preferredName) {
    const normalizedTarget = normalizeHeader(preferredName);
    for (let i = 0; i < headers.length; i += 1) {
      if (normalizeHeader(headers[i]) === normalizedTarget) {
        return i;
      }
    }

    for (let i = 0; i < headers.length; i += 1) {
      if (normalizeHeader(headers[i]).indexOf(normalizedTarget) !== -1) {
        return i;
      }
    }

    return -1;
  }

  function parseConceptCsv(text, idColumn, labelColumn) {
    const lines = String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .split('\n')
      .filter(function (line) {
        return toString(line) !== '';
      });

    if (!lines.length) return [];

    const delimiter = detectDelimiter(lines[0]);
    const headers = parseDelimitedLine(lines[0], delimiter);
    const idIndex = headerIndex(headers, idColumn || 'concept_id');
    const labelIndex = headerIndex(headers, labelColumn || 'english');

    if (idIndex < 0) {
      return [];
    }

    const rows = [];
    for (let i = 1; i < lines.length; i += 1) {
      const cols = parseDelimitedLine(lines[i], delimiter);
      if (!cols.length) continue;

      const id = normalizeConceptId(cols[idIndex]);
      if (!id) continue;

      const label = labelIndex >= 0 ? toString(cols[labelIndex]) : '';
      rows.push({ id: id, label: label });
    }

    return rows;
  }

  async function loadConceptRowsFromProject() {
    const project = toObject(P.project);
    const conceptConfig = toObject(project.concepts);
    const source = toString(conceptConfig.source);
    if (!source) {
      return [];
    }

    const paths = [];
    if (source.charAt(0) === '/') {
      paths.push(source);
    } else {
      paths.push('/' + source);
      paths.push(source);
    }

    for (let i = 0; i < paths.length; i += 1) {
      try {
        const response = await fetch(paths[i], {
          method: 'GET',
          cache: 'no-store',
          headers: { Accept: 'text/plain, text/csv, */*' },
        });
        if (!response.ok) continue;
        const text = await response.text();
        const rows = parseConceptCsv(text, conceptConfig.id_column, conceptConfig.label_column);
        if (rows.length) {
          return rows;
        }
      } catch (_) {
      }
    }

    return [];
  }

  function conceptSort(left, right) {
    const leftNum = Number(left.id);
    const rightNum = Number(right.id);

    if (Number.isFinite(leftNum) && Number.isFinite(rightNum)) {
      return leftNum - rightNum;
    }

    return String(left.id).localeCompare(String(right.id));
  }

  function buildConceptList(csvConceptRows, annotationLabels, enrichmentsConceptList) {
    const csvRows = Array.isArray(csvConceptRows) ? csvConceptRows : [];
    const labelsFromAnnotations = toObject(annotationLabels);
    const enrichmentsIds = Array.isArray(enrichmentsConceptList) ? enrichmentsConceptList : [];

    const csvLabelMap = {};
    const orderedIds = [];
    const seenIds = new Set();

    function rememberConceptId(value) {
      const conceptId = normalizeConceptId(value);
      if (!conceptId || seenIds.has(conceptId)) return;
      seenIds.add(conceptId);
      orderedIds.push(conceptId);
    }

    for (let i = 0; i < csvRows.length; i += 1) {
      const row = csvRows[i];
      const id = normalizeConceptId(row && row.id);
      if (!id) continue;
      const label = toString(row && row.label);
      if (label) {
        csvLabelMap[id] = label;
      }
      rememberConceptId(id);
    }

    const annotationKeys = Object.keys(labelsFromAnnotations);
    for (let i = 0; i < annotationKeys.length; i += 1) {
      rememberConceptId(annotationKeys[i]);
    }

    for (let i = 0; i < enrichmentsIds.length; i += 1) {
      rememberConceptId(enrichmentsIds[i]);
    }

    const concepts = [];
    for (let i = 0; i < orderedIds.length; i += 1) {
      const id = orderedIds[i];
      concepts.push({
        id: id,
        label: csvLabelMap[id] || labelsFromAnnotations[id] || ('Concept ' + id),
      });
    }

    concepts.sort(conceptSort);
    return concepts;
  }

  function uniqueStringList(values) {
    const list = Array.isArray(values) ? values : [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < list.length; i += 1) {
      const text = toString(list[i]);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      out.push(text);
    }

    return out;
  }

  function enrichmentsConceptIds(enrichments) {
    const data = toObject(enrichments);
    const ids = [];
    const seen = new Set();

    const sources = [
      toObject(data.cognate_sets),
      toObject(toObject(data.manual_overrides).cognate_sets),
      toObject(data.borrowing_flags),
      toObject(toObject(data.manual_overrides).borrowing_flags),
      toObject(toObject(data.manual_overrides).accepted_concepts),
    ];

    for (let s = 0; s < sources.length; s += 1) {
      const keys = Object.keys(sources[s]);
      for (let i = 0; i < keys.length; i += 1) {
        const conceptId = normalizeConceptId(keys[i]);
        if (!conceptId || seen.has(conceptId)) continue;
        seen.add(conceptId);
        const numeric = Number(conceptId);
        ids.push(Number.isFinite(numeric) ? numeric : conceptId);
      }
    }

    return ids;
  }

  function enrichmentsSpeakers(enrichments) {
    const data = toObject(enrichments);
    const out = [];
    const seen = new Set();

    const configured = uniqueStringList(toObject(data.config).speakers_included);
    for (let i = 0; i < configured.length; i += 1) {
      seen.add(configured[i]);
      out.push(configured[i]);
    }

    const setSources = [
      toObject(data.cognate_sets),
      toObject(toObject(data.manual_overrides).cognate_sets),
    ];

    for (let s = 0; s < setSources.length; s += 1) {
      const conceptKeys = Object.keys(setSources[s]);
      for (let i = 0; i < conceptKeys.length; i += 1) {
        const groups = toObject(setSources[s][conceptKeys[i]]);
        const groupKeys = Object.keys(groups);
        for (let j = 0; j < groupKeys.length; j += 1) {
          const speakers = uniqueStringList(groups[groupKeys[j]]);
          for (let k = 0; k < speakers.length; k += 1) {
            const speaker = speakers[k];
            if (seen.has(speaker)) continue;
            seen.add(speaker);
            out.push(speaker);
          }
        }
      }
    }

    const borrowingSources = [
      toObject(data.borrowing_flags),
      toObject(toObject(data.manual_overrides).borrowing_flags),
    ];

    for (let b = 0; b < borrowingSources.length; b += 1) {
      const conceptKeys = Object.keys(borrowingSources[b]);
      for (let i = 0; i < conceptKeys.length; i += 1) {
        const speakerEntries = toObject(borrowingSources[b][conceptKeys[i]]);
        const speakerKeys = Object.keys(speakerEntries);
        for (let j = 0; j < speakerKeys.length; j += 1) {
          const speaker = toString(speakerKeys[j]);
          if (!speaker || seen.has(speaker)) continue;
          seen.add(speaker);
          out.push(speaker);
        }
      }
    }

    return out;
  }

  function dispatchEnrichmentsUpdatedFromMemory() {
    const enrichments = toObject(P.enrichments);
    if (!Object.keys(enrichments).length) {
      return;
    }

    dispatchEvent('parse:enrichments-updated', {
      computedAt: toString(enrichments.computed_at) || null,
      speakers: enrichmentsSpeakers(enrichments),
      concepts: enrichmentsConceptIds(enrichments),
    });
  }

  async function ensureEnrichments() {
    const moduleApi = toObject(P.modules).enrichmentsIO;
    if (moduleApi && typeof moduleApi.init === 'function') {
      await moduleApi.init();
      return;
    }

    if (moduleApi && typeof moduleApi.read === 'function') {
      await moduleApi.read();
      return;
    }

    dispatchEnrichmentsUpdatedFromMemory();
  }

  async function ensureTagsModule() {
    const tagsModule = toObject(P.modules).tags;
    if (tagsModule && typeof tagsModule.init === 'function') {
      try {
        tagsModule.init();
      } catch (_) {
      }
    }
  }

  function normalizeTagColor(value) {
    const text = toString(value);
    if (!text) return TAG_DEFAULT_COLOR;

    if (/^#[0-9a-fA-F]{3}$/.test(text)) {
      return '#' +
        text.charAt(1) + text.charAt(1) +
        text.charAt(2) + text.charAt(2) +
        text.charAt(3) + text.charAt(3);
    }

    if (/^#[0-9a-fA-F]{6}$/.test(text)) {
      return text;
    }

    return TAG_DEFAULT_COLOR;
  }

  function looksNumericConceptId(value) {
    const conceptId = normalizeConceptId(value);
    return /^[0-9]+$/.test(conceptId);
  }

  function hexToRgba(hex, alpha) {
    const normalized = normalizeTagColor(hex).replace('#', '');
    const r = parseInt(normalized.slice(0, 2), 16);
    const g = parseInt(normalized.slice(2, 4), 16);
    const b = parseInt(normalized.slice(4, 6), 16);
    if (!Number.isFinite(r) || !Number.isFinite(g) || !Number.isFinite(b)) {
      return 'rgba(107, 114, 128, ' + String(alpha) + ')';
    }
    return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + String(alpha) + ')';
  }

  function tagEntriesFromState() {
    const seen = new Set();
    const tagsOut = [];
    const tagsModule = toObject(P.modules).tags;

    if (tagsModule && typeof tagsModule.getTags === 'function') {
      try {
        const fromModule = tagsModule.getTags();
        const list = Array.isArray(fromModule) ? fromModule : [];
        for (let i = 0; i < list.length; i += 1) {
          const item = list[i];
          if (!item || typeof item !== 'object') continue;
          const id = toString(item.id || item.tagId);
          if (!id || seen.has(id)) continue;
          seen.add(id);
          tagsOut.push({
            id: id,
            name: toString(item.name || item.label || id),
            color: normalizeTagColor(item.color),
          });
        }
      } catch (_) {
      }
    }

    if (tagsModule && typeof tagsModule.getAllTags === 'function') {
      try {
        const fromModule = tagsModule.getAllTags();
        const list = Array.isArray(fromModule) ? fromModule : [];
        for (let i = 0; i < list.length; i += 1) {
          const item = list[i];
          if (!item || typeof item !== 'object') continue;
          const id = toString(item.id || item.tagId);
          if (!id || seen.has(id)) continue;
          seen.add(id);
          tagsOut.push({
            id: id,
            name: toString(item.name || item.label || id),
            color: normalizeTagColor(item.color),
          });
        }
      } catch (_) {
      }
    }

    if (tagsOut.length) {
      return tagsOut;
    }

    const tags = toObject(P.tags);
    const definitions = Array.isArray(tags.tags) ? tags.tags : [];
    const byConcept = toObject(tags.byConcept);
    const assignments = toObject(tags.assignments);

    for (let i = 0; i < definitions.length; i += 1) {
      const item = definitions[i];
      if (!item || typeof item !== 'object') continue;
      const id = toString(item.id || item.tagId);
      if (!id || seen.has(id)) continue;
      seen.add(id);
      tagsOut.push({
        id: id,
        name: toString(item.name || item.label || id),
        color: normalizeTagColor(item.color),
      });
    }

    const defs = [];

    if (Array.isArray(tags.definitions)) {
      for (let i = 0; i < tags.definitions.length; i += 1) {
        const item = tags.definitions[i];
        if (!item || typeof item !== 'object') continue;
        const id = toString(item.id || item.tagId);
        if (!id) continue;
        defs.push({ id: id, name: toString(item.name || id), color: normalizeTagColor(item.color) });
      }
    } else {
      const defObj = toObject(tags.definitions);
      const keys = Object.keys(defObj);
      for (let i = 0; i < keys.length; i += 1) {
        const id = toString(keys[i]);
        if (!id) continue;
        const value = defObj[keys[i]];
        const name = value && typeof value === 'object' ? toString(value.name || id) : id;
        const color = value && typeof value === 'object'
          ? normalizeTagColor(value.color)
          : TAG_DEFAULT_COLOR;
        defs.push({ id: id, name: name, color: color });
      }
    }

    for (let i = 0; i < defs.length; i += 1) {
      const tag = defs[i];
      if (!tag || !tag.id || seen.has(tag.id)) continue;
      seen.add(tag.id);
      tagsOut.push({ id: tag.id, name: tag.name, color: normalizeTagColor(tag.color) });
    }

    if (tagsOut.length) {
      return tagsOut;
    }

    const byConceptKeys = Object.keys(byConcept);
    for (let i = 0; i < byConceptKeys.length; i += 1) {
      const tagList = Array.isArray(byConcept[byConceptKeys[i]]) ? byConcept[byConceptKeys[i]] : [];
      for (let j = 0; j < tagList.length; j += 1) {
        const tagId = toString(tagList[j]);
        if (!tagId || seen.has(tagId)) continue;
        seen.add(tagId);
        tagsOut.push({ id: tagId, name: tagId, color: TAG_DEFAULT_COLOR });
      }
    }

    const assignmentKeys = Object.keys(assignments);
    for (let i = 0; i < assignmentKeys.length; i += 1) {
      const tagId = toString(assignmentKeys[i]);
      if (!tagId || seen.has(tagId)) continue;

      if (looksNumericConceptId(tagId)) {
        continue;
      }

      const assigned = assignments[assignmentKeys[i]];
      if (Array.isArray(assigned)) {
        const looksLikeConceptList = assigned.some(function (value) {
          return looksNumericConceptId(value);
        });
        if (looksLikeConceptList) {
          seen.add(tagId);
          tagsOut.push({ id: tagId, name: tagId, color: TAG_DEFAULT_COLOR });
        }
      }
    }

    return tagsOut;
  }

  function normalizeTagIdList(values) {
    const inList = Array.isArray(values) ? values : [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < inList.length; i += 1) {
      const tagId = toString(inList[i]);
      if (!tagId || seen.has(tagId)) continue;
      if (tagId === TAG_PSEUDO_ALL || tagId === TAG_PSEUDO_UNTAGGED) continue;
      seen.add(tagId);
      out.push(tagId);
    }

    return out;
  }

  function normalizeTagFilter(filterLike) {
    const payload = toObject(filterLike);
    let includeUntagged = !!payload.includeUntagged;

    if (typeof payload.showUntagged === 'boolean') {
      includeUntagged = payload.showUntagged;
    }

    let candidates = [];
    if (Array.isArray(payload.activeTagIds)) {
      candidates = candidates.concat(payload.activeTagIds);
    }
    if (Array.isArray(payload.activeTags)) {
      candidates = candidates.concat(payload.activeTags);
    }

    if (!candidates.length && payload.tagId != null && toString(payload.tagId) !== '') {
      candidates.push(payload.tagId);
    }

    const normalized = [];
    for (let i = 0; i < candidates.length; i += 1) {
      const value = toString(candidates[i]);
      if (!value) continue;

      const lower = value.toLowerCase();
      if (value === TAG_PSEUDO_UNTAGGED || lower === 'untagged') {
        includeUntagged = true;
        continue;
      }

      if (value === TAG_PSEUDO_ALL || lower === 'all') {
        continue;
      }

      normalized.push(value);
    }

    return {
      activeTagIds: normalizeTagIdList(normalized),
      includeUntagged: !!includeUntagged,
    };
  }

  function sameStringArray(left, right) {
    const a = Array.isArray(left) ? left : [];
    const b = Array.isArray(right) ? right : [];
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  function activeTagsForEvent() {
    const active = state.tagFilter.activeTagIds.slice();
    if (state.tagFilter.includeUntagged) {
      active.push('untagged');
    }
    return active;
  }

  function dispatchTagFilterChanged() {
    dispatchEvent('parse:tag-filter-changed', {
      activeTags: activeTagsForEvent(),
    });
  }

  function hasKnownTagId(tagId) {
    const wanted = toString(tagId);
    if (!wanted) return false;
    const entries = tagEntriesFromState();
    for (let i = 0; i < entries.length; i += 1) {
      if (toString(entries[i].id) === wanted) {
        return true;
      }
    }
    return false;
  }

  function pruneMissingActiveTags() {
    const nextActive = [];
    const seen = new Set();

    for (let i = 0; i < state.tagFilter.activeTagIds.length; i += 1) {
      const tagId = toString(state.tagFilter.activeTagIds[i]);
      if (!tagId || seen.has(tagId)) continue;
      if (!hasKnownTagId(tagId)) continue;
      seen.add(tagId);
      nextActive.push(tagId);
    }

    const changed = !sameStringArray(nextActive, state.tagFilter.activeTagIds);
    if (changed) {
      state.tagFilter.activeTagIds = nextActive;
    }
    return changed;
  }

  function setTagFilter(nextFilter, options) {
    const opts = toObject(options);
    const normalized = normalizeTagFilter(nextFilter);
    const previous = {
      activeTagIds: state.tagFilter.activeTagIds.slice(),
      includeUntagged: !!state.tagFilter.includeUntagged,
    };

    state.tagFilter.activeTagIds = normalized.activeTagIds;
    state.tagFilter.includeUntagged = normalized.includeUntagged;
    pruneMissingActiveTags();

    const changed = !sameStringArray(previous.activeTagIds, state.tagFilter.activeTagIds) ||
      previous.includeUntagged !== state.tagFilter.includeUntagged;

    if (!changed && !opts.force) {
      return false;
    }

    renderHeader();
    syncViews();
    emitCompareOpen();

    if (opts.dispatch !== false) {
      dispatchTagFilterChanged();
    }

    return true;
  }

  function toggleTagFilterTag(rawTagId) {
    const tagId = toString(rawTagId);
    if (!tagId) return;

    if (tagId === TAG_PSEUDO_ALL) {
      setTagFilter({ activeTagIds: [], includeUntagged: false });
      return;
    }

    if (tagId === TAG_PSEUDO_UNTAGGED) {
      setTagFilter({
        activeTagIds: state.tagFilter.activeTagIds,
        includeUntagged: !state.tagFilter.includeUntagged,
      });
      return;
    }

    if (!hasKnownTagId(tagId)) {
      return;
    }

    const nextActive = state.tagFilter.activeTagIds.slice();
    const index = nextActive.indexOf(tagId);
    if (index === -1) {
      nextActive.push(tagId);
    } else {
      nextActive.splice(index, 1);
    }

    setTagFilter({
      activeTagIds: nextActive,
      includeUntagged: state.tagFilter.includeUntagged,
    });
  }

  function tagPillHtml(tagId, label, color, active) {
    const pillColor = normalizeTagColor(color);
    const isActive = !!active;
    const background = isActive ? pillColor : hexToRgba(pillColor, 0.16);
    const textColor = isActive ? '#07101b' : pillColor;

    return '<button type="button" class="compare-btn compare-tag-pill" data-action="toggle-tag-pill" data-tag-id="' + escapeHtml(tagId) + '" aria-pressed="' + (isActive ? 'true' : 'false') + '" style="border-color:' + pillColor + ';background:' + background + ';color:' + textColor + ';font-weight:' + (isActive ? '700' : '600') + ';">' +
      escapeHtml(label) +
      '</button>';
  }

  function tagFilterBarHtml() {
    const entries = tagEntriesFromState();
    const allActive = !state.tagFilter.activeTagIds.length && !state.tagFilter.includeUntagged;
    const untaggedActive = !!state.tagFilter.includeUntagged;
    const pills = [];

    pills.push(tagPillHtml(TAG_PSEUDO_ALL, 'All', '#4cc2ff', allActive));
    pills.push(tagPillHtml(TAG_PSEUDO_UNTAGGED, 'Untagged', '#9db0d0', untaggedActive));

    for (let i = 0; i < entries.length; i += 1) {
      const tag = entries[i];
      const isActive = state.tagFilter.activeTagIds.indexOf(tag.id) !== -1;
      pills.push(tagPillHtml(tag.id, tag.name || tag.id, tag.color, isActive));
    }

    return '<div class="compare-tag-filter-bar" id="compare-tag-filter-bar" style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;">' +
      '<span style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;font-weight:700;margin-right:2px;">Tags</span>' +
      pills.join('') +
      '</div>';
  }

  function tagsForConcept(conceptId) {
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return [];

    const tagsModule = toObject(P.modules).tags;
    if (tagsModule && typeof tagsModule.getTagsForConcept === 'function') {
      try {
        const list = tagsModule.getTagsForConcept(numericOrTextConceptId(conceptKey));
        if (Array.isArray(list)) {
          return list.map(function (value) {
            return toString(value && typeof value === 'object' ? (value.id || value.tagId) : value);
          }).filter(Boolean);
        }
      } catch (_) {
      }
    }

    const tags = toObject(P.tags);
    const tagAssignments = toObject(tags.assignments);
    const byConcept = toObject(tags.byConcept);
    const result = [];
    const seen = new Set();

    const directAssignments = Array.isArray(tagAssignments[conceptKey])
      ? tagAssignments[conceptKey]
      : (Array.isArray(tagAssignments[String(Number(conceptKey))]) ? tagAssignments[String(Number(conceptKey))] : []);

    for (let i = 0; i < directAssignments.length; i += 1) {
      const tagId = toString(directAssignments[i]);
      if (!tagId || seen.has(tagId)) continue;
      seen.add(tagId);
      result.push(tagId);
    }

    const fromByConcept = Array.isArray(byConcept[conceptKey])
      ? byConcept[conceptKey]
      : (Array.isArray(byConcept[String(Number(conceptKey))]) ? byConcept[String(Number(conceptKey))] : []);

    for (let i = 0; i < fromByConcept.length; i += 1) {
      const tagId = toString(fromByConcept[i]);
      if (!tagId || seen.has(tagId)) continue;
      seen.add(tagId);
      result.push(tagId);
    }

    const assignmentKeys = Object.keys(tagAssignments);
    for (let i = 0; i < assignmentKeys.length; i += 1) {
      const tagId = assignmentKeys[i];
      const concepts = Array.isArray(tagAssignments[tagId]) ? tagAssignments[tagId] : [];
      for (let j = 0; j < concepts.length; j += 1) {
        const candidateId = normalizeConceptId(concepts[j]);
        if (candidateId === conceptKey) {
          const cleanTag = toString(tagId);
          if (cleanTag && !seen.has(cleanTag)) {
            seen.add(cleanTag);
            result.push(cleanTag);
          }
          break;
        }
      }
    }

    return result;
  }

  function applyTagFilter(concepts) {
    const list = Array.isArray(concepts) ? concepts : [];
    const activeTagIds = normalizeTagIdList(state.tagFilter.activeTagIds);
    const includeUntagged = !!state.tagFilter.includeUntagged;

    if (!activeTagIds.length && !includeUntagged) {
      return list.slice();
    }

    return list.filter(function (concept) {
      const conceptTags = tagsForConcept(concept.id);
      if (!conceptTags.length) {
        return includeUntagged;
      }

      for (let i = 0; i < activeTagIds.length; i += 1) {
        if (conceptTags.indexOf(activeTagIds[i]) !== -1) {
          return true;
        }
      }

      return false;
    });
  }

  function ensureComputeStatusUI() {
    if (!state.computeStatusEl) return;

    if (state.computeTextEl && state.computeProgressEl) {
      return;
    }

    state.computeStatusEl.innerHTML =
      '<div class="compute-status-text" id="compare-compute-status-text">Idle.</div>' +
      '<div class="compute-progress-wrap"><div class="compute-progress-bar" id="compare-compute-status-bar"></div></div>';

    state.computeTextEl = state.computeStatusEl.querySelector('#compare-compute-status-text');
    state.computeProgressEl = state.computeStatusEl.querySelector('#compare-compute-status-bar');
  }

  function setComputeStatus(text, progress) {
    ensureComputeStatusUI();
    if (!state.computeTextEl || !state.computeProgressEl) return;

    state.computeTextEl.textContent = toString(text) || 'Idle.';

    const boundedProgress = Math.max(0, Math.min(100, Number.isFinite(Number(progress)) ? Number(progress) : 0));
    state.computeProgressEl.style.width = boundedProgress.toFixed(1) + '%';
  }

  function visibleConceptIds() {
    return state.filteredConcepts.map(function (concept) {
      return numericOrTextConceptId(concept.id);
    });
  }

  function updateCompareStateSnapshot() {
    P.compareState = toObject(P.compareState);
    P.compareState.availableSpeakers = state.availableSpeakers.slice();
    P.compareState.selectedSpeakers = state.selectedSpeakers.slice();
    P.compareState.concepts = state.concepts.slice();
    P.compareState.filteredConcepts = state.filteredConcepts.slice();
    P.compareState.selectedConceptId = state.selectedConceptId;
    P.compareState.tagFilter = deepClone(state.tagFilter);
  }

  function emitCompareOpen() {
    dispatchEvent('parse:compare-open', {
      speakers: state.selectedSpeakers.slice(),
      conceptIds: visibleConceptIds(),
    });
  }

  function emitSpeakersChanged() {
    dispatchEvent('parse:compare-speakers-changed', {
      speakers: state.selectedSpeakers.slice(),
    });
  }

  function currentConceptSelectionDetail() {
    const selectedConcept = findConceptById(state.selectedConceptId);

    return {
      conceptId: state.selectedConceptId || null,
      conceptLabel: selectedConcept ? selectedConcept.label : '',
      speakers: state.selectedSpeakers.slice(),
    };
  }

  function dispatchCurrentConceptSelection() {
    const detail = currentConceptSelectionDetail();

    dispatchEvent(CONCEPT_SELECTED_EVENT, {
      conceptId: detail.conceptId,
      conceptLabel: detail.conceptLabel,
      speakers: detail.speakers.slice(),
    });

    dispatchEvent(CONCEPT_SELECT_COMPAT_EVENT, {
      conceptId: detail.conceptId,
      conceptLabel: detail.conceptLabel,
      speakers: detail.speakers.slice(),
    });
  }

  function scheduleConceptSelectionDispatch() {
    const token = state.conceptDispatchToken + 1;
    state.conceptDispatchToken = token;

    Promise.resolve().then(function () {
      if (!state.initialized) return;
      if (token !== state.conceptDispatchToken) return;
      dispatchCurrentConceptSelection();
    });
  }

  function renderMatrixPlaceholder() {
    if (!state.tableEl) return;

    state.tableEl.classList.add('hidden');
    state.tableEl.setAttribute('aria-hidden', 'true');

    state.tableEl.innerHTML =
      '<div class="panel-title">Concept Matrix</div>' +
      '<div class="panel-placeholder">Matrix view is available as a secondary surface. Concept-first review remains the default workflow.</div>';
  }

  function renderCognatePanelPlaceholder() {
    if (!state.cognatePanelEl) return;

    state.cognatePanelEl.innerHTML =
      '<div class="panel-title">Cognate Decision</div>' +
      '<div class="panel-placeholder">No cognate grouping data available for this concept yet.</div>';
  }

  function renderBorrowingPanel() {
    if (!state.borrowingPanelEl) return;

    state.borrowingPanelEl.innerHTML =
      '<div class="panel-title">Borrowing adjudication</div>' +
      '<div class="panel-placeholder">No borrowing candidates available for this concept yet.</div>';
  }

  function renderSpectrogramPanel() {
    if (!state.spectrogramPanelEl) return;

    state.spectrogramPanelEl.classList.add('hidden');
    state.spectrogramPanelEl.setAttribute('aria-hidden', 'true');

    state.spectrogramPanelEl.innerHTML =
      '<div class="panel-title">Spectrogram</div>' +
      '<div class="panel-placeholder">On-demand spectrogram previews are shown here after selection.</div>';
  }

  function speakerSelectOptionsHtml() {
    const options = [];
    for (let i = 0; i < state.availableSpeakers.length; i += 1) {
      const speaker = state.availableSpeakers[i];
      if (state.selectedSpeakers.indexOf(speaker) !== -1) {
        continue;
      }
      options.push('<option value="' + escapeHtml(speaker) + '">' + escapeHtml(speaker) + '</option>');
    }

    if (!options.length) {
      options.push('<option value="">No remaining speakers</option>');
    }

    return options.join('');
  }

  function selectedSpeakersHtml() {
    if (!state.selectedSpeakers.length) {
      return '<span class="panel-placeholder">No speakers selected.</span>';
    }

    const chips = [];
    for (let i = 0; i < state.selectedSpeakers.length; i += 1) {
      const speaker = state.selectedSpeakers[i];
      chips.push(
        '<span class="compare-chip">' +
          escapeHtml(speaker) +
          '<button type="button" data-action="remove-speaker" data-speaker="' + escapeHtml(speaker) + '" aria-label="Remove speaker">x</button>' +
        '</span>'
      );
    }

    return chips.join('');
  }

  function computeTypeOptionsHtml() {
    const options = [];
    for (let i = 0; i < COMPUTE_TYPE_ORDER.length; i += 1) {
      const type = COMPUTE_TYPE_ORDER[i];
      const selected = state.computeType === type ? ' selected' : '';
      options.push('<option value="' + type + '"' + selected + '>' + type + '</option>');
    }
    return options.join('');
  }

  function renderHeader() {
    if (!state.headerEl) return;

    state.headerEl.innerHTML =
      '<div class="compare-toolbar">' +
        '<span class="compare-brand">PARSE Compare</span>' +
        '<a class="compare-mode-link" href="parse.html" data-action="go-annotate">Annotate mode</a>' +

        '<div class="compare-control-group">' +
          '<label for="compare-speaker-select">Speaker</label>' +
          '<select id="compare-speaker-select" class="compare-select">' + speakerSelectOptionsHtml() + '</select>' +
          '<button type="button" class="compare-btn" data-action="add-speaker">Add</button>' +
        '</div>' +

        '<div class="compare-control-group">' +
          '<label for="compare-compute-type">Compute</label>' +
          '<select id="compare-compute-type" class="compare-select">' + computeTypeOptionsHtml() + '</select>' +
          '<button type="button" class="compare-btn primary" data-action="run-compute">Run</button>' +
          '<button type="button" class="compare-btn" data-action="refresh-enrichments">Refresh</button>' +
        '</div>' +
      '</div>' +
      tagFilterBarHtml() +
      '<div class="compare-speaker-chips">' + selectedSpeakersHtml() + '</div>';
  }

  function ensureSubmodules() {
    const modules = toObject(P.modules);

    if (state.tableEl && modules.conceptTable && typeof modules.conceptTable.init === 'function') {
      try {
        modules.conceptTable.init(state.tableEl);
      } catch (error) {
        console.warn('[compare] conceptTable init skipped:', error);
        renderMatrixPlaceholder();
      }
    } else {
      renderMatrixPlaceholder();
    }

    if (state.cognatePanelEl && modules.cognateControls && typeof modules.cognateControls.init === 'function') {
      try {
        modules.cognateControls.init(state.cognatePanelEl);
      } catch (error) {
        console.warn('[compare] cognateControls init skipped:', error);
        renderCognatePanelPlaceholder();
      }
    } else {
      renderCognatePanelPlaceholder();
    }

    // Wave 12 L5 - module not yet built, guard for graceful degradation
    if (state.borrowingPanelEl && modules.borrowingPanel && typeof modules.borrowingPanel.init === 'function') {
      try {
        modules.borrowingPanel.init(state.borrowingPanelEl);
      } catch (error) {
        console.warn('[compare] borrowingPanel init skipped:', error);
        renderBorrowingPanel();
      }
    } else {
      renderBorrowingPanel();
    }

    const speakerImportMount = firstById(['compare-speaker-import', 'speaker-import-modal']);
    if (modules.speakerImport && typeof modules.speakerImport.init === 'function' && speakerImportMount) {
      try {
        modules.speakerImport.init(speakerImportMount);
      } catch (error) {
        console.warn('[compare] speakerImport init skipped:', error);
      }
    }
  }

  function syncViews() {
    state.filteredConcepts = buildVisibleConcepts();

    if (state.selectedConceptId) {
      const stillVisible = state.filteredConcepts.some(function (concept) {
        return concept.id === state.selectedConceptId;
      });
      if (!stillVisible) {
        state.selectedConceptId = '';
      }
    }

    if (!state.selectedConceptId && state.filteredConcepts.length) {
      state.selectedConceptId = state.filteredConcepts[0].id;
    }

    updateCompareStateSnapshot();
    renderShellContent();
    refreshShellStateFromData();

    const conceptTable = toObject(P.modules).conceptTable;
    if (conceptTable && typeof conceptTable.setSpeakers === 'function') {
      conceptTable.setSpeakers(state.selectedSpeakers);
    }

    if (conceptTable && typeof conceptTable.setConcepts === 'function') {
      conceptTable.setConcepts(state.filteredConcepts);
    }

    applyAssistantContext('sync');
    scheduleConceptSelectionDispatch();
  }

  function normalizeSpeakerList(list) {
    const inList = Array.isArray(list) ? list : [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < inList.length; i += 1) {
      const speaker = toString(inList[i]);
      if (!speaker || seen.has(speaker)) continue;
      seen.add(speaker);
      out.push(speaker);
    }

    return out;
  }

  function addSpeaker(speaker, importMode) {
    const speakerId = toString(speaker);
    if (!speakerId) return;
    if (state.selectedSpeakers.indexOf(speakerId) !== -1) return;

    state.selectedSpeakers.push(speakerId);
    state.selectedSpeakers = normalizeSpeakerList(state.selectedSpeakers);

    dispatchEvent('parse:compare-speaker-add', {
      speaker: speakerId,
      importMode: importMode || 'existing',
    });

    renderHeader();
    syncViews();
    emitSpeakersChanged();
    emitCompareOpen();
  }

  function removeSpeaker(speaker) {
    const speakerId = toString(speaker);
    if (!speakerId) return;

    const next = [];
    for (let i = 0; i < state.selectedSpeakers.length; i += 1) {
      if (state.selectedSpeakers[i] !== speakerId) {
        next.push(state.selectedSpeakers[i]);
      }
    }

    state.selectedSpeakers = next;

    dispatchEvent('parse:compare-speaker-remove', {
      speaker: speakerId,
    });

    renderHeader();
    syncViews();
    emitSpeakersChanged();
    emitCompareOpen();
  }

  function onHeaderClick(event) {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') {
      return;
    }

    const actionEl = target.closest('[data-action]');
    if (!actionEl || !state.headerEl || !state.headerEl.contains(actionEl)) {
      return;
    }

    const action = toString(actionEl.dataset.action);

    if (action === 'toggle-tag-pill') {
      toggleTagFilterTag(actionEl.dataset.tagId);
      return;
    }

    if (action === 'go-annotate') {
      dispatchEvent('parse:compare-close', {});
      return;
    }

    if (action === 'add-speaker') {
      const selectEl = state.headerEl.querySelector('#compare-speaker-select');
      addSpeaker(selectEl ? selectEl.value : '', 'existing');
      return;
    }

    if (action === 'remove-speaker') {
      removeSpeaker(actionEl.dataset.speaker);
      return;
    }

    if (action === 'run-compute') {
      dispatchEvent('parse:compute-request', {
        type: state.computeType,
        speakers: state.selectedSpeakers.slice(),
        conceptIds: visibleConceptIds(),
      });
      return;
    }

    if (action === 'refresh-enrichments') {
      const enrichmentsModule = toObject(P.modules).enrichmentsIO;
      if (enrichmentsModule && typeof enrichmentsModule.read === 'function') {
        enrichmentsModule.read().catch(function (error) {
          console.warn('[compare] enrichments refresh failed:', error);
        });
      }
    }
  }

  function onHeaderChange(event) {
    const target = event.target;
    if (!target || !state.headerEl || !state.headerEl.contains(target)) {
      return;
    }

    if (target.id === 'compare-compute-type') {
      const type = toString(target.value);
      if (COMPUTE_TYPE_ORDER.indexOf(type) !== -1) {
        state.computeType = type;
      }
    }
  }

  function onTagFilter(event) {
    const detail = toObject(event && event.detail);
    setTagFilter(detail, { dispatch: true });
  }

  function onTagDefinitionsChanged() {
    const activeChanged = pruneMissingActiveTags();
    renderHeader();
    syncViews();
    emitCompareOpen();

    if (activeChanged) {
      dispatchTagFilterChanged();
    }
  }

  function onItemsTagged() {
    syncViews();
    emitCompareOpen();
  }

  function ensureEnrichmentsWritable() {
    const current = toObject(P.enrichments);
    P.enrichments = Object.assign({}, current);
    P.enrichments.manual_overrides = toObject(P.enrichments.manual_overrides);
    P.enrichments.manual_overrides.borrowing_flags = toObject(P.enrichments.manual_overrides.borrowing_flags);
    P.enrichments.manual_overrides.accepted_concepts = toObject(P.enrichments.manual_overrides.accepted_concepts);
    return P.enrichments;
  }

  function normalizeBorrowingDecision(value) {
    const raw = toString(value).toLowerCase();
    if (!raw) return '';

    if (
      raw === 'native' ||
      raw === 'not_borrowing' ||
      raw === 'not-borrowing' ||
      raw === 'not borrowing' ||
      raw === 'notborrowed' ||
      raw === 'no'
    ) {
      return 'native';
    }

    if (
      raw === 'borrowed' ||
      raw === 'confirmed' ||
      raw === 'borrowing' ||
      raw === 'loan' ||
      raw === 'yes'
    ) {
      return 'borrowed';
    }

    if (
      raw === 'uncertain' ||
      raw === 'undecided' ||
      raw === 'unknown' ||
      raw === 'maybe'
    ) {
      return 'uncertain';
    }

    if (raw === 'skip' || raw === 'skipped') {
      return 'skip';
    }

    return '';
  }

  function borrowingStatusForDecision(decision) {
    if (decision === 'borrowed') return 'confirmed';
    if (decision === 'native') return 'not_borrowing';
    return 'undecided';
  }

  function persistEnrichments(reason) {
    const moduleApi = toObject(P.modules).enrichmentsIO;
    const fallback = toObject(P.modules).enrichments;

    if (moduleApi && typeof moduleApi.write === 'function') {
      return moduleApi.write(reason);
    }

    if (moduleApi && typeof moduleApi.save === 'function') {
      return moduleApi.save(reason);
    }

    if (fallback && typeof fallback.save === 'function') {
      return fallback.save(reason);
    }

    return Promise.resolve(false);
  }

  function onBorrowingDecision(event) {
    const detail = toObject(event && event.detail);
    const conceptId = normalizeConceptId(detail.conceptId);
    const speakerId = toString(detail.speakerId || detail.speaker);
    const decision = normalizeBorrowingDecision(detail.decision || detail.status);
    const sourceLang = toString(detail.sourceLang || detail.source_lang).toLowerCase();

    if (!conceptId || !speakerId || !decision) {
      return;
    }

    const enrichments = ensureEnrichmentsWritable();
    const manualOverrides = toObject(enrichments.manual_overrides);
    const borrowingFlags = toObject(manualOverrides.borrowing_flags);
    const conceptFlags = toObject(borrowingFlags[conceptId]);
    const existing = toObject(conceptFlags[speakerId]);

    const nextEntry = Object.assign({}, existing, {
      decision: decision,
      status: borrowingStatusForDecision(decision),
      updated_at: new Date().toISOString(),
    });

    if (decision === 'borrowed' && sourceLang) {
      nextEntry.source_lang = sourceLang;
      nextEntry.sourceLang = sourceLang;
    } else {
      delete nextEntry.source_lang;
      delete nextEntry.sourceLang;
    }

    conceptFlags[speakerId] = nextEntry;
    borrowingFlags[conceptId] = conceptFlags;
    manualOverrides.borrowing_flags = borrowingFlags;
    enrichments.manual_overrides = manualOverrides;

    dispatchEnrichmentsUpdatedFromMemory();

    persistEnrichments('borrowing-decision').catch(function (error) {
      console.warn('[compare] failed to save borrowing decision:', error);
    });
  }

  function onCognateAcceptPersist(event) {
    const detail = toObject(event && event.detail);
    const conceptId = normalizeConceptId(detail.conceptId);
    if (!conceptId) return;

    const enrichments = ensureEnrichmentsWritable();
    const manualOverrides = toObject(enrichments.manual_overrides);
    const acceptedConcepts = toObject(manualOverrides.accepted_concepts);
    acceptedConcepts[conceptId] = new Date().toISOString();
    manualOverrides.accepted_concepts = acceptedConcepts;
    enrichments.manual_overrides = manualOverrides;

    dispatchEnrichmentsUpdatedFromMemory();

    persistEnrichments('cognate-accept').catch(function (error) {
      console.warn('[compare] failed to save cognate accept:', error);
    });
  }

  function onConceptSelected(event) {
    const detail = toObject(event && event.detail);
    const conceptId = normalizeConceptId(detail.conceptId);
    if (!conceptId) return;

    state.selectedConceptId = conceptId;
    P.currentConcept = conceptId;
    updateCompareStateSnapshot();
    renderShellContent();
    applyAssistantContext('concept-event', true);
  }

  function normalizeComputeType(value) {
    const type = toString(value).toLowerCase();
    return COMPUTE_TYPE_ORDER.indexOf(type) !== -1 ? type : 'cognates';
  }

  function normalizeComputeRequest(detail) {
    const payload = toObject(detail);
    const type = normalizeComputeType(payload.type);

    const speakersIn = Array.isArray(payload.speakers) ? payload.speakers : state.selectedSpeakers;
    const speakers = normalizeSpeakerList(speakersIn);

    const conceptIdsIn = Array.isArray(payload.conceptIds) ? payload.conceptIds : visibleConceptIds();
    const conceptIds = [];
    for (let i = 0; i < conceptIdsIn.length; i += 1) {
      const conceptId = normalizeConceptId(conceptIdsIn[i]);
      if (!conceptId) continue;
      conceptIds.push(numericOrTextConceptId(conceptId));
    }

    const request = {
      type: type,
      speakers: speakers,
      conceptIds: conceptIds,
    };

    if (payload.contactLanguages) {
      request.contactLanguages = payload.contactLanguages;
    } else {
      const contact = toObject(toObject(P.project).language).contact_languages;
      if (Array.isArray(contact) && contact.length) {
        request.contactLanguages = contact.slice();
      }
    }

    const threshold = toFiniteNumber(payload.lexstatThreshold);
    if (Number.isFinite(threshold)) {
      request.lexstatThreshold = threshold;
    }

    return request;
  }

  async function requestComputeStart(request) {
    const type = normalizeComputeType(request.type);

    const aiClient = toObject(P.modules).aiClient;
    if (aiClient && typeof aiClient.requestCompute === 'function') {
      const aiOptions = {};

      if (Array.isArray(request.contactLanguages)) {
        aiOptions.contactLanguages = request.contactLanguages.slice();
      }

      const threshold = toFiniteNumber(request.lexstatThreshold);
      if (Number.isFinite(threshold)) {
        aiOptions.lexstatThreshold = threshold;
      }

      const jobId = await aiClient.requestCompute(
        type,
        normalizeSpeakerList(request.speakers),
        Array.isArray(request.conceptIds) ? request.conceptIds.slice() : [],
        aiOptions
      );

      return {
        jobId: jobId,
        _emittedStarted: true,
      };
    }

    const endpointCandidates = [
      COMPUTE_START_ENDPOINTS[type],
      '/api/compute',
    ];

    let lastError = null;

    for (let i = 0; i < endpointCandidates.length; i += 1) {
      const endpoint = endpointCandidates[i];
      if (!endpoint) continue;

      try {
        const body = endpoint === '/api/compute'
          ? Object.assign({ type: type }, request)
          : request;

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json, text/plain, */*',
          },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const responseText = await response.text().catch(function () {
            return '';
          });
          lastError = new Error('HTTP ' + response.status + ' from ' + endpoint + (responseText ? ': ' + responseText : ''));
          continue;
        }

        return await parseJsonBody(response);
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('Unable to start compute request.');
  }

  async function requestStatusCandidate(candidate) {
    const requestInit = {
      method: candidate.method,
      headers: {
        Accept: 'application/json, text/plain, */*',
      },
      cache: 'no-store',
    };

    if (candidate.method === 'POST') {
      requestInit.headers['Content-Type'] = 'application/json';
      requestInit.body = JSON.stringify(candidate.body || {});
    }

    const response = await fetch(candidate.url, requestInit);
    if (!response.ok) {
      if (response.status === 404 || response.status === 405) {
        return null;
      }
      const bodyText = await response.text().catch(function () {
        return '';
      });
      throw new Error('Status endpoint failed: ' + candidate.url + ' (' + response.status + ')' + (bodyText ? ': ' + bodyText : ''));
    }

    return parseJsonBody(response);
  }

  async function requestComputeStatus(jobId, type) {
    const encodedJobId = encodeURIComponent(jobId);
    const candidates = [
      {
        method: 'POST',
        url: '/api/compute/' + type + '/status',
        body: { jobId: jobId, type: type },
      },
      {
        method: 'POST',
        url: '/api/' + type + '/status',
        body: { jobId: jobId, type: type },
      },
      {
        method: 'POST',
        url: '/api/compute/status',
        body: { jobId: jobId, type: type },
      },
      {
        method: 'GET',
        url: '/api/compute/' + type + '/status?jobId=' + encodedJobId,
      },
      {
        method: 'GET',
        url: '/api/' + type + '/status?jobId=' + encodedJobId,
      },
    ];

    let lastError = null;

    for (let i = 0; i < candidates.length; i += 1) {
      try {
        const body = await requestStatusCandidate(candidates[i]);
        if (body) return body;
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('No status endpoint responded for compute job.');
  }

  function parseStatusPayload(payload) {
    const body = toObject(payload);

    let progress = toFiniteNumber(body.progress);
    if (!Number.isFinite(progress)) {
      progress = toFiniteNumber(body.percent);
    }
    if (!Number.isFinite(progress)) {
      progress = 0;
    }
    if (progress <= 1) {
      progress = progress * 100;
    }
    progress = Math.max(0, Math.min(100, progress));

    const rawStatus = toString(body.status || body.state || body.phase).toLowerCase();
    const doneFromState = rawStatus === 'done' || rawStatus === 'completed' || rawStatus === 'success' || rawStatus === 'failed' || rawStatus === 'error' || rawStatus === 'cancelled';
    const done = body.done === true || doneFromState;

    let success;
    if (typeof body.success === 'boolean') {
      success = body.success;
    } else if (rawStatus === 'failed' || rawStatus === 'error' || rawStatus === 'cancelled') {
      success = false;
    } else if (done) {
      success = true;
    } else {
      success = false;
    }

    const message = toString(body.message || body.detail || body.error || rawStatus || 'Running');

    return {
      progress: progress,
      done: done,
      success: success,
      message: message,
      error: toString(body.error),
    };
  }

  async function pollComputeJob(jobId, type, token) {
    let failures = 0;

    while (state.initialized && token === state.computeToken) {
      await sleep(1200);

      if (token !== state.computeToken) {
        return;
      }

      try {
        const payload = await requestComputeStatus(jobId, type);
        failures = 0;

        const status = parseStatusPayload(payload);
        setComputeStatus(status.message, status.progress);

        dispatchEvent('parse:compute-progress', {
          jobId: jobId,
          type: type,
          progress: status.progress,
          message: status.message,
        });

        if (status.done) {
          if (status.success) {
            setComputeStatus('Compute complete: ' + type + '.', 100);
          } else {
            setComputeStatus('Compute failed: ' + (status.error || status.message || type), status.progress || 0);
          }

          dispatchEvent('parse:compute-done', {
            jobId: jobId,
            type: type,
            success: status.success,
            error: status.success ? undefined : (status.error || status.message || 'Compute failed.'),
          });

          if (status.success && type === 'cognates') {
            const enrichmentsModule = toObject(P.modules).enrichmentsIO;
            if (enrichmentsModule && typeof enrichmentsModule.read === 'function') {
              await enrichmentsModule.read();
            }
            syncViews();
          }
          return;
        }
      } catch (error) {
        failures += 1;
        if (failures >= 5) {
          setComputeStatus('Compute status polling failed: ' + toString(error && error.message), 0);
          dispatchEvent('parse:compute-done', {
            jobId: jobId,
            type: type,
            success: false,
            error: toString(error && error.message) || 'Status polling failed.',
          });
          return;
        }
      }
    }
  }

  async function startCompute(detail) {
    const request = normalizeComputeRequest(detail);

    if (!request.speakers.length) {
      setComputeStatus('Select at least one speaker before computing.', 0);
      return;
    }

    if (!request.conceptIds.length) {
      setComputeStatus('No concepts selected for compute request.', 0);
      return;
    }

    const type = normalizeComputeType(request.type);
    const token = state.computeToken + 1;
    state.computeToken = token;

    setComputeStatus('Submitting ' + type + ' computation...', 2);

    try {
      const responseBody = await requestComputeStart(request);
      if (token !== state.computeToken) return;

      const jobId = toString(responseBody.jobId || responseBody.job_id || (type + '-' + Date.now()));

      if (!responseBody._emittedStarted) {
        dispatchEvent('parse:compute-started', {
          jobId: jobId,
          type: type,
          estimatedDuration: responseBody.estimatedDuration,
        });
      }

      setComputeStatus('Compute started (' + type + '): ' + jobId, 4);
      await pollComputeJob(jobId, type, token);
    } catch (error) {
      if (token !== state.computeToken) return;

      const message = toString(error && error.message) || 'Compute request failed.';
      setComputeStatus(message, 0);
      dispatchEvent('parse:compute-done', {
        jobId: null,
        type: type,
        success: false,
        error: message,
      });
    }
  }

  function onComputeRequest(event) {
    startCompute(event && event.detail).catch(function (error) {
      setComputeStatus('Compute request error: ' + toString(error && error.message), 0);
    });
  }

  async function bootstrapData() {
    state.isBootstrapping = true;
    state.bootstrapErrorMessage = '';
    resetBootstrapSummary();

    state.availableSpeakers = [];
    state.concepts = [];
    state.filteredConcepts = [];
    state.selectedConceptId = '';

    setShellState('loading', 'Loading compare workspace…', 'Reading project config, source index, annotations, enrichments, and tags.');
    setComputeStatus('Loading compare mode data…', 2);

    renderHeader();
    renderMatrixPlaceholder();
    renderCognatePanelPlaceholder();
    renderBorrowingPanel();
    renderSpectrogramPanel();
    renderSidebar();
    renderShellContent();

    try {
      P.mode = 'compare';

      setComputeStatus('Loading project configuration…', 8);
      const loadedProject = await loadProjectConfig();
      state.bootstrapSummary.projectLoaded = !!(loadedProject && typeof loadedProject === 'object');

      setComputeStatus('Loading source index…', 15);
      const loadedSourceIndex = await loadSourceIndex();
      state.bootstrapSummary.sourceIndexLoaded = !!(loadedSourceIndex && typeof loadedSourceIndex === 'object');
      await ensureAnnotationStore();

      const allSpeakers = collectSpeakerIds();
      state.bootstrapSummary.discoveredSpeakers = allSpeakers.length;

      if (allSpeakers.length) {
        setComputeStatus('Loading speaker annotations…', 30);
        await loadAnnotationsForSpeakers(allSpeakers);
      } else {
        setComputeStatus('No speakers found in project/source index. Checking enrichments…', 30);
      }

      const annotationRecords = toObject(P.annotations);
      const annotationSpeakerKeys = Object.keys(annotationRecords);
      let loadedAnnotationSpeakers = 0;
      for (let i = 0; i < annotationSpeakerKeys.length; i += 1) {
        const record = annotationRecords[annotationSpeakerKeys[i]];
        if (record && typeof record === 'object' && Object.keys(record).length) {
          loadedAnnotationSpeakers += 1;
        }
      }
      state.bootstrapSummary.loadedAnnotationSpeakers = loadedAnnotationSpeakers;

      setComputeStatus('Loading enrichments and tags…', 45);
      await ensureEnrichments();
      await ensureTagsModule();
      pruneMissingActiveTags();

      state.availableSpeakers = collectSpeakerIds();
      if (state.selectedSpeakers.length) {
        state.selectedSpeakers = normalizeSpeakerList(state.selectedSpeakers).filter(function (speaker) {
          return state.availableSpeakers.indexOf(speaker) !== -1;
        });
      }

      setComputeStatus('Building concept queue…', 62);
      const annotationLabels = extractAnnotationConceptLabels();
      state.bootstrapSummary.annotationConcepts = Object.keys(annotationLabels).length;

      const csvConceptRows = await loadConceptRowsFromProject();
      state.bootstrapSummary.csvConceptRows = csvConceptRows.length;

      const enrichmentConceptList = enrichmentsConceptIds(P.enrichments);
      state.bootstrapSummary.enrichmentConcepts = enrichmentConceptList.length;

      state.concepts = buildConceptList(csvConceptRows, annotationLabels, enrichmentConceptList);
      state.filteredConcepts = buildVisibleConcepts();

      if (!state.selectedConceptId && state.filteredConcepts.length) {
        state.selectedConceptId = state.filteredConcepts[0].id;
      }

      setComputeStatus('Finalizing compare shell…', 82);
      renderHeader();
      renderBorrowingPanel();
      renderSpectrogramPanel();
      initAssistantDock(false);

      ensureSubmodules();

      // Re-broadcast after submodules subscribe, so compare UI panels hydrate from enrichments immediately.
      dispatchEnrichmentsUpdatedFromMemory();

      if (P.modules.audioPlayer && typeof P.modules.audioPlayer.init === 'function') {
        P.modules.audioPlayer.init();
      }

      syncViews();
      emitSpeakersChanged();
      emitCompareOpen();

      if (isNoDataState()) {
        setComputeStatus('No compare data detected yet. Add speaker annotations or concept CSV, then refresh.', 0);
      } else if (!state.concepts.length) {
        setComputeStatus('Compare loaded, but concept queue is empty.', 0);
      } else if (!state.filteredConcepts.length) {
        setComputeStatus('Concept queue loaded. Current filters hide all concepts.', 0);
      } else if (!state.selectedSpeakers.length) {
        setComputeStatus('Concept queue loaded. Add speakers to start speaker-form review.', 0);
      } else {
        setComputeStatus('Compare ready. Review concepts from top to bottom.', 0);
      }
    } catch (error) {
      const message = toString(error && error.message) || 'Unknown compare bootstrap failure.';
      state.bootstrapErrorMessage = message;
      console.error('[compare] bootstrap failed:', error);

      renderHeader();
      renderMatrixPlaceholder();
      renderCognatePanelPlaceholder();
      renderBorrowingPanel();
      renderSpectrogramPanel();
      initAssistantDock(false);

      try {
        ensureSubmodules();
      } catch (submoduleError) {
        console.warn('[compare] submodule fallback init skipped:', submoduleError);
      }

      setComputeStatus('Compare boot error: ' + message, 0);
    } finally {
      state.isBootstrapping = false;
      refreshShellStateFromData();
      renderShellContent();
    }
  }

  function bindEvents() {
    addListener(state.headerEl, 'click', onHeaderClick);
    addListener(state.headerEl, 'change', onHeaderChange);

    if (state.sidebarSearchEl) {
      addListener(state.sidebarSearchEl, 'input', onSidebarInput);
      addListener(state.sidebarSearchEl, 'click', onSidebarClick);
    }
    if (state.sidebarConceptListEl) {
      addListener(state.sidebarConceptListEl, 'click', onSidebarClick);
    }
    if (state.notesFieldEl) {
      addListener(state.notesFieldEl, 'input', onSidebarInput);
    }
    if (state.formsTbodyEl) {
      addListener(state.formsTbodyEl, 'click', onFormsTableClick);
    }
    for (let i = 0; i < state.navPrevButtons.length; i += 1) {
      addListener(state.navPrevButtons[i], 'click', onSidebarClick);
    }
    for (let i = 0; i < state.navNextButtons.length; i += 1) {
      addListener(state.navNextButtons[i], 'click', onSidebarClick);
    }
    for (let i = 0; i < state.acceptButtons.length; i += 1) {
      addListener(state.acceptButtons[i], 'click', onSidebarClick);
    }
    for (let i = 0; i < state.flagButtons.length; i += 1) {
      addListener(state.flagButtons[i], 'click', onSidebarClick);
    }
    const topbarEl = firstById('topbar');
    if (topbarEl) {
      addListener(topbarEl, 'click', onSidebarClick);
    }

    if (
      state.legacyFileInputEl &&
      !state.legacyFileInputEl.getAttribute('onchange') &&
      typeof state.legacyFileInputEl.onchange !== 'function'
    ) {
      addListener(state.legacyFileInputEl, 'change', onLegacyDecisionInput);
    }

    addListener(document, 'keydown', onShellKeydown);
    addListener(document, 'parse:tag-filter', onTagFilter);
    addListener(document, 'parse:tag-created', onTagDefinitionsChanged);
    addListener(document, 'parse:tag-deleted', onTagDefinitionsChanged);
    addListener(document, 'parse:items-tagged', onItemsTagged);
    addListener(document, CONCEPT_SELECTED_EVENT, onConceptSelected);
    addListener(document, 'parse:compute-request', onComputeRequest);
    addListener(document, 'parse:borrowing-decision', onBorrowingDecision);
    addListener(document, 'parse:cognate-accept', onCognateAcceptPersist);

    for (let i = 0; i < ASSISTANT_MODULE_READY_EVENTS.length; i += 1) {
      const eventName = ASSISTANT_MODULE_READY_EVENTS[i];
      addListener(document, eventName, onAssistantModuleReady);
      addListener(window, eventName, onAssistantModuleReady);
    }
  }

  /**
   * Initialize compare mode controller.
   * @param {HTMLElement} containerEl Compare container element.
   * @returns {Promise<object>} Public module API object.
   */
  async function init(containerEl) {
    if (state.initialized) {
      return P.modules.compare;
    }

    state.containerEl = containerEl || firstById(['compare-container', 'main']);
    if (!state.containerEl) {
      throw new Error('Missing compare shell container (#compare-container or #main).');
    }

    state.headerEl = firstById(['compare-header']);
    if (!state.headerEl) {
      const sidebarSession = firstById(['sidebar-session']);
      if (sidebarSession) {
        const mount = document.createElement('div');
        mount.id = 'compare-header';
        sidebarSession.appendChild(mount);
        state.headerEl = mount;
      }
    }

    state.tableEl = firstById(['compare-table']);
    state.cognatePanelEl = firstById(['compare-cognate-panel', 'cognate-panel']);
    state.borrowingPanelEl = firstById(['compare-borrowing-panel', 'borrow-panel']);
    state.spectrogramPanelEl = firstById(['compare-spectrogram']);
    state.computeStatusEl = firstById(['compare-compute-status']);
    state.sidebarSearchEl = firstById(['search-box']);
    state.sidebarConceptListEl = firstById(['concept-list']);
    state.sidebarSortButtons = Array.prototype.slice.call(document.querySelectorAll('.sort-btn[data-sort]'));
    state.sidebarFilterButtons = Array.prototype.slice.call(document.querySelectorAll('.filter-btn[data-filter]'));
    state.conceptTitleEl = firstById(['concept-title']);
    state.navPositionEl = firstById(['nav-position']);
    state.shellStateEl = firstById(['compare-shell-state']);
    state.shellStateTitleEl = firstById(['compare-shell-state-title']);
    state.shellStateMessageEl = firstById(['compare-shell-state-message']);
    state.shellStateMetaEl = firstById(['compare-shell-state-meta']);

    const footerNavButtons = Array.prototype.slice.call(document.querySelectorAll('#nav-footer .nav-btn'));
    const primaryPrev = firstById(['btn-prev']) || (footerNavButtons.length ? footerNavButtons[0] : null);
    const secondaryPrev = firstById(['btn-prev-bottom']) || null;
    const primaryNext = firstById(['btn-next']) || (footerNavButtons.length > 1 ? footerNavButtons[1] : null);
    const secondaryNext = firstById(['btn-next-bottom']) || null;

    state.navPrevButtons = uniqueElements([primaryPrev, secondaryPrev]);
    state.navNextButtons = uniqueElements([primaryNext, secondaryNext]);
    state.acceptButtons = uniqueElements([firstById(['btn-accept']), firstBySelector('#concept-actions .action-btn.accept')]);
    state.flagButtons = uniqueElements([firstById(['btn-flag']), firstBySelector('#concept-actions .action-btn.flag')]);
    state.notesFieldEl = firstById(['notes-field']);
    state.progressBadgeEl = firstById(['progress-badge']);
    state.progressBarEl = firstById(['progress-bar-fill']);
    state.refArabicFormEl = firstById(['ref-arabic-form']);
    state.refArabicIpaEl = firstById(['ref-arabic-ipa']);
    state.refPersianFormEl = firstById(['ref-persian-form']);
    state.refPersianIpaEl = firstById(['ref-persian-ipa']);
    state.formsTbodyEl = firstById(['forms-tbody']);
    state.loadButtonEl = firstById(['btn-load-decisions']) || findTopbarButtonByText(['load decisions']);
    state.saveButtonEl = firstById(['btn-save']) || findTopbarButtonByText(['save decisions', 'save']);
    state.legacyFileInputEl = firstById(['decision-input', 'file-input']);
    state.toastEl = firstById(['toast']);
    state.assistantMountEl = firstById([ASSISTANT_MOUNT_ID, 'parse-ai-dock', 'parse-chat-dock', 'parse-toolbox-dock']);

    ensureComputeStatusUI();
    loadShellDraft();

    P.compareState = toObject(P.compareState);
    state.selectedSpeakers = normalizeSpeakerList(P.compareState.selectedSpeakers || []);
    state.selectedConceptId = normalizeConceptId(P.compareState.selectedConceptId);
    (function () {
      const savedTagFilter = toObject(P.compareState.tagFilter);
      const hasModernShape =
        Array.isArray(savedTagFilter.activeTagIds) ||
        Array.isArray(savedTagFilter.activeTags) ||
        typeof savedTagFilter.includeUntagged === 'boolean';

      if (
        !hasModernShape &&
        savedTagFilter.tagId == null &&
        savedTagFilter.showUntagged === true
      ) {
        state.tagFilter = { activeTagIds: [], includeUntagged: false };
      } else {
        state.tagFilter = normalizeTagFilter(savedTagFilter);
      }
    })();

    bindLegacyShellCompatGlobals();
    bindEvents();
    state.initialized = true;

    await bootstrapData();

    return P.modules.compare;
  }

  /**
   * Destroy compare mode controller and submodule resources.
   */
  function destroy() {
    if (!state.initialized) {
      return;
    }

    state.computeToken += 1;
    state.conceptDispatchToken += 1;

    const modules = toObject(P.modules);
    if (modules.conceptTable && typeof modules.conceptTable.destroy === 'function') {
      modules.conceptTable.destroy();
    }
    if (modules.cognateControls && typeof modules.cognateControls.destroy === 'function') {
      modules.cognateControls.destroy();
    }
    if (modules.enrichmentsIO && typeof modules.enrichmentsIO.destroy === 'function') {
      modules.enrichmentsIO.destroy();
    }
    if (modules.borrowingPanel && typeof modules.borrowingPanel.destroy === 'function') {
      modules.borrowingPanel.destroy();
    }
    if (modules.speakerImport && typeof modules.speakerImport.destroy === 'function') {
      modules.speakerImport.destroy();
    }

    if (modules.audioPlayer && typeof modules.audioPlayer.destroy === 'function') {
      modules.audioPlayer.destroy();
    }

    removeListeners();
    unbindLegacyShellCompatGlobals();
    destroyAssistantDock();

    if (state.notesPersistTimer) {
      window.clearTimeout(state.notesPersistTimer);
      state.notesPersistTimer = 0;
    }

    if (state.toastTimer) {
      window.clearTimeout(state.toastTimer);
      state.toastTimer = 0;
    }

    dispatchEvent('parse:compare-close', {});

    if (state.shellFileInputEl && state.shellFileInputEl.parentNode) {
      state.shellFileInputEl.parentNode.removeChild(state.shellFileInputEl);
      state.shellFileInputEl = null;
    }

    state.initialized = false;
    state.containerEl = null;
    state.headerEl = null;
    state.tableEl = null;
    state.cognatePanelEl = null;
    state.borrowingPanelEl = null;
    state.spectrogramPanelEl = null;
    state.computeStatusEl = null;
    state.computeTextEl = null;
    state.computeProgressEl = null;
    state.sidebarSearchEl = null;
    state.sidebarConceptListEl = null;
    state.sidebarSortButtons = [];
    state.sidebarFilterButtons = [];
    state.conceptTitleEl = null;
    state.navPositionEl = null;
    state.shellStateEl = null;
    state.shellStateTitleEl = null;
    state.shellStateMessageEl = null;
    state.shellStateMetaEl = null;
    state.navPrevButtons = [];
    state.navNextButtons = [];
    state.acceptButtons = [];
    state.flagButtons = [];
    state.notesFieldEl = null;
    state.progressBadgeEl = null;
    state.progressBarEl = null;
    state.refArabicFormEl = null;
    state.refArabicIpaEl = null;
    state.refPersianFormEl = null;
    state.refPersianIpaEl = null;
    state.formsTbodyEl = null;
    state.loadButtonEl = null;
    state.saveButtonEl = null;
    state.toastEl = null;
    state.legacyFileInputEl = null;
    state.assistantMountEl = null;
    state.assistantModule = null;
    state.assistantApi = null;
    state.assistantReady = false;
    state.assistantRetryTimer = 0;
    state.assistantRetryCount = 0;
    state.assistantContextSignature = '';
    state.availableSpeakers = [];
    state.selectedSpeakers = [];
    state.concepts = [];
    state.filteredConcepts = [];
    state.selectedConceptId = '';
    state.computeType = 'cognates';
    state.conceptDispatchToken = 0;
    state.isBootstrapping = false;
    state.bootstrapErrorMessage = '';
    resetBootstrapSummary();
    state.tagFilter = { activeTagIds: [], includeUntagged: false };
  }

  /**
   * Refresh compare data from project, annotations, and enrichments.
   * @returns {Promise<void>} Completion promise.
   */
  async function refresh() {
    await bootstrapData();
  }

  /**
   * Return a copy of currently selected speakers.
   * @returns {string[]} Selected speaker ids.
   */
  function getSelectedSpeakers() {
    return state.selectedSpeakers.slice();
  }

  P.modules.compare = {
    init: init,
    destroy: destroy,
    refresh: refresh,
    getSelectedSpeakers: getSelectedSpeakers,
  };

  async function autoInit() {
    const container = firstById(['compare-container', 'main']);
    if (!container) return;

    try {
      await init(container);
    } catch (error) {
      console.error('[compare] auto-init failed:', error);
      const message = toString(error && error.message) || 'Unknown compare init error.';
      setComputeStatus('Compare init failed: ' + message, 0);
      setShellState('error', 'Compare failed to initialize.', message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit, { once: true });
  } else {
    autoInit();
  }
})();
