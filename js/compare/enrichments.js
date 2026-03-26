(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const HISTORY_LIMIT = 10;
  const SAVE_DEBOUNCE_MS = 500;
  const ENRICHMENTS_URL = '/api/enrichments';
  const GROUP_LETTERS = ['A', 'B', 'C', 'D', 'E'];

  const state = {
    initialized: false,
    saveTimer: null,
    listeners: [],
    writingChain: Promise.resolve(),
    dirty: false,
    pendingSaveReason: null,
    error: null,
  };

  function dispatchEvent(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function deepClone(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function toErrorMessage(value) {
    const fromError = value && typeof value === 'object' && typeof value.message === 'string'
      ? value.message
      : '';
    const text = String(fromError || value || '').trim();
    return text || 'Unknown enrichments error.';
  }

  function normalizeConceptId(value) {
    if (value == null) return '';

    let text = String(value).trim();
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

  function toObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function toStringArray(value) {
    if (!Array.isArray(value)) return [];
    const seen = new Set();
    const result = [];
    for (let i = 0; i < value.length; i += 1) {
      const text = String(value[i] == null ? '' : value[i]).trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      result.push(text);
    }
    return result;
  }

  function normalizeGroups(rawGroups) {
    const groupsIn = toObject(rawGroups);
    const groupsOut = {};

    const keys = Object.keys(groupsIn);
    for (let i = 0; i < keys.length; i += 1) {
      const key = String(keys[i]).trim().toUpperCase();
      if (!key) continue;
      const speakers = toStringArray(groupsIn[keys[i]]);
      if (speakers.length) {
        groupsOut[key] = speakers;
      }
    }

    return groupsOut;
  }

  function normalizeCognateSets(rawCognateSets) {
    const inSets = toObject(rawCognateSets);
    const outSets = {};

    const conceptKeys = Object.keys(inSets);
    for (let i = 0; i < conceptKeys.length; i += 1) {
      const conceptId = normalizeConceptId(conceptKeys[i]);
      if (!conceptId) continue;
      outSets[conceptId] = normalizeGroups(inSets[conceptKeys[i]]);
    }

    return outSets;
  }

  function normalizeManualCognateSets(rawCognateSets) {
    const sets = normalizeCognateSets(rawCognateSets);
    const outSets = {};

    const conceptKeys = Object.keys(sets);
    for (let i = 0; i < conceptKeys.length; i += 1) {
      const conceptId = conceptKeys[i];
      const groups = normalizeGroups(sets[conceptId]);
      if (Object.keys(groups).length) {
        outSets[conceptId] = groups;
      }
    }

    return outSets;
  }

  function normalizeManualOverrides(rawManualOverrides) {
    const overridesIn = toObject(rawManualOverrides);
    const overridesOut = deepClone(overridesIn);

    overridesOut.cognate_sets = normalizeManualCognateSets(overridesIn.cognate_sets);
    overridesOut.borrowing_flags = toObject(overridesIn.borrowing_flags);
    overridesOut.accepted_concepts = toObject(overridesIn.accepted_concepts);

    return overridesOut;
  }

  function ensureEnrichmentsShape(rawEnrichments) {
    const source = toObject(rawEnrichments);

    const enrichments = {
      computed_at: typeof source.computed_at === 'string' ? source.computed_at : null,
      config: toObject(source.config),
      cognate_sets: normalizeCognateSets(source.cognate_sets),
      similarity: toObject(source.similarity),
      borrowing_flags: toObject(source.borrowing_flags),
      manual_overrides: normalizeManualOverrides(source.manual_overrides),
      history: Array.isArray(source.history) ? deepClone(source.history) : [],
    };

    return enrichments;
  }

  function conceptIdsFromEnrichments(enrichments) {
    const ids = new Set();

    const computed = toObject(enrichments.cognate_sets);
    const computedKeys = Object.keys(computed);
    for (let i = 0; i < computedKeys.length; i += 1) {
      ids.add(computedKeys[i]);
    }

    const manual = toObject(enrichments.manual_overrides.cognate_sets);
    const manualKeys = Object.keys(manual);
    for (let i = 0; i < manualKeys.length; i += 1) {
      ids.add(manualKeys[i]);
    }

    return Array.from(ids).map(function (id) {
      const num = Number(id);
      return Number.isFinite(num) ? num : id;
    });
  }

  function speakersFromEnrichments(enrichments) {
    const speakers = new Set();
    const config = toObject(enrichments.config);

    const configured = toStringArray(config.speakers_included);
    for (let i = 0; i < configured.length; i += 1) {
      speakers.add(configured[i]);
    }

    const allSets = [
      toObject(enrichments.cognate_sets),
      toObject(enrichments.manual_overrides.cognate_sets),
    ];

    for (let s = 0; s < allSets.length; s += 1) {
      const conceptSets = allSets[s];
      const conceptKeys = Object.keys(conceptSets);
      for (let i = 0; i < conceptKeys.length; i += 1) {
        const groups = toObject(conceptSets[conceptKeys[i]]);
        const groupKeys = Object.keys(groups);
        for (let j = 0; j < groupKeys.length; j += 1) {
          const groupSpeakers = toStringArray(groups[groupKeys[j]]);
          for (let k = 0; k < groupSpeakers.length; k += 1) {
            speakers.add(groupSpeakers[k]);
          }
        }
      }
    }

    return Array.from(speakers);
  }

  function emitEnrichmentsUpdated() {
    const enrichments = ensureEnrichmentsShape(P.enrichments);
    P.enrichments = enrichments;

    dispatchEvent('parse:enrichments-updated', {
      computedAt: enrichments.computed_at,
      speakers: speakersFromEnrichments(enrichments),
      concepts: conceptIdsFromEnrichments(enrichments),
    });
  }

  function getCurrentEnrichments() {
    if (!P.enrichments) {
      P.enrichments = ensureEnrichmentsShape(null);
    }
    P.enrichments = ensureEnrichmentsShape(P.enrichments);
    return P.enrichments;
  }

  function buildVersionSnapshot(reason) {
    const enrichments = getCurrentEnrichments();
    return {
      saved_at: nowIso(),
      reason: String(reason || 'manual-update'),
      computed_at: enrichments.computed_at,
      cognate_sets: deepClone(enrichments.cognate_sets),
      borrowing_flags: deepClone(enrichments.borrowing_flags),
      manual_overrides: deepClone(enrichments.manual_overrides),
    };
  }

  function appendHistory(reason) {
    const enrichments = getCurrentEnrichments();
    const history = Array.isArray(enrichments.history) ? enrichments.history : [];
    const snapshot = buildVersionSnapshot(reason);
    const nextHistory = history.concat([snapshot]);
    enrichments.history = nextHistory.slice(Math.max(nextHistory.length - HISTORY_LIMIT, 0));
  }

  async function postEnrichments(payload) {
    const bodyCandidates = buildPostBodyCandidates(payload);

    let lastError = null;

    for (let i = 0; i < bodyCandidates.length; i += 1) {
      try {
        const response = await fetch(ENRICHMENTS_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json, text/plain, */*',
          },
          body: JSON.stringify(bodyCandidates[i]),
        });

        if (response.ok) {
          return true;
        }

        const message = await response.text().catch(function () {
          return '';
        });
        lastError = new Error('POST /api/enrichments failed: HTTP ' + response.status + (message ? ' - ' + message : ''));
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('Unable to persist enrichments.');
  }

  function buildPostBodyCandidates(payload) {
    return [
      { enrichments: payload },
      payload,
    ];
  }

  function postEnrichmentsSync(payload) {
    const bodyCandidates = buildPostBodyCandidates(payload);
    let lastError = null;

    for (let i = 0; i < bodyCandidates.length; i += 1) {
      try {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', ENRICHMENTS_URL, false);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('Accept', 'application/json, text/plain, */*');
        xhr.send(JSON.stringify(bodyCandidates[i]));

        if (xhr.status >= 200 && xhr.status < 300) {
          return true;
        }

        const message = String(xhr.responseText || '').trim();
        lastError = new Error('POST /api/enrichments failed: HTTP ' + xhr.status + (message ? ' - ' + message : ''));
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('Unable to persist enrichments.');
  }

  function scheduleWrite(reason) {
    state.dirty = true;
    state.pendingSaveReason = String(reason || 'write');

    if (state.saveTimer) {
      window.clearTimeout(state.saveTimer);
    }

    state.saveTimer = window.setTimeout(function () {
      state.saveTimer = null;
      write(reason).catch(function (error) {
        console.warn('[enrichments] write failed:', error);
      });
    }, SAVE_DEBOUNCE_MS);
  }

  function getGroupsFromSource(enrichments, conceptId) {
    const manualSets = toObject(enrichments.manual_overrides.cognate_sets);
    if (manualSets[conceptId]) {
      const manualGroups = normalizeGroups(manualSets[conceptId]);
      if (Object.keys(manualGroups).length) {
        return manualGroups;
      }
    }

    const computedSets = toObject(enrichments.cognate_sets);
    return normalizeGroups(computedSets[conceptId]);
  }

  function flattenSpeakers(groups) {
    const result = [];
    const seen = new Set();

    const keys = Object.keys(groups);
    for (let i = 0; i < keys.length; i += 1) {
      const speakers = toStringArray(groups[keys[i]]);
      for (let j = 0; j < speakers.length; j += 1) {
        const speaker = speakers[j];
        if (seen.has(speaker)) continue;
        seen.add(speaker);
        result.push(speaker);
      }
    }

    return result;
  }

  function upsertBorrowingOverride(conceptId, speaker, patch) {
    const enrichments = getCurrentEnrichments();
    const conceptKey = normalizeConceptId(conceptId);
    const speakerKey = String(speaker || '').trim();
    if (!conceptKey || !speakerKey) return;

    const overrides = toObject(enrichments.manual_overrides.borrowing_flags);
    const conceptOverrides = toObject(overrides[conceptKey]);
    conceptOverrides[speakerKey] = Object.assign({}, conceptOverrides[speakerKey] || {}, patch);
    overrides[conceptKey] = conceptOverrides;
    enrichments.manual_overrides.borrowing_flags = overrides;

    emitEnrichmentsUpdated();
    scheduleWrite('borrowing-override');
  }

  function nextGroupLetter(currentLetter) {
    const current = String(currentLetter || 'A').trim().toUpperCase();
    const currentIndex = GROUP_LETTERS.indexOf(current);
    if (currentIndex < 0) {
      return GROUP_LETTERS[0];
    }
    return GROUP_LETTERS[(currentIndex + 1) % GROUP_LETTERS.length];
  }

  function groupForSpeaker(groups, speaker) {
    const speakerKey = String(speaker || '').trim();
    if (!speakerKey) return '';

    const keys = Object.keys(groups);
    for (let i = 0; i < keys.length; i += 1) {
      const group = keys[i];
      const speakers = toStringArray(groups[group]);
      for (let j = 0; j < speakers.length; j += 1) {
        if (speakers[j] === speakerKey) {
          return group;
        }
      }
    }

    return '';
  }

  function setAcceptedConcept(conceptId) {
    const enrichments = getCurrentEnrichments();
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return;

    const accepted = toObject(enrichments.manual_overrides.accepted_concepts);
    accepted[conceptKey] = nowIso();
    enrichments.manual_overrides.accepted_concepts = accepted;

    emitEnrichmentsUpdated();
    scheduleWrite('cognate-accept');
  }

  function applyCognateMerge(detail) {
    const conceptId = normalizeConceptId(detail.conceptId);
    if (!conceptId) return;

    const existingGroups = getCognateGroupsForConcept(conceptId);
    let speakers = flattenSpeakers(existingGroups);

    if (!speakers.length) {
      const compareState = toObject(P.compareState);
      speakers = toStringArray(compareState.selectedSpeakers);
    }

    const merged = speakers.length ? { A: speakers } : {};
    setCognateGroups(conceptId, merged, 'merge');
  }

  function applyCognateCycle(detail) {
    const conceptId = normalizeConceptId(detail.conceptId);
    const speaker = String(detail.speaker || '').trim();
    if (!conceptId || !speaker) return;

    const groups = getCognateGroupsForConcept(conceptId);
    const currentGroup = groupForSpeaker(groups, speaker) || 'A';
    const newGroup = String(detail.newGroup || nextGroupLetter(currentGroup)).trim().toUpperCase();

    const nextGroups = deepClone(groups);
    const keys = Object.keys(nextGroups);
    for (let i = 0; i < keys.length; i += 1) {
      nextGroups[keys[i]] = toStringArray(nextGroups[keys[i]]).filter(function (item) {
        return item !== speaker;
      });
      if (!nextGroups[keys[i]].length) {
        delete nextGroups[keys[i]];
      }
    }

    if (!nextGroups[newGroup]) {
      nextGroups[newGroup] = [];
    }
    nextGroups[newGroup].push(speaker);

    setCognateGroups(conceptId, nextGroups, 'cycle');
  }

  function onCognateAccept(event) {
    const detail = toObject(event && event.detail);
    setAcceptedConcept(detail.conceptId);
  }

  function onCognateSplitDone(event) {
    const detail = toObject(event && event.detail);
    setCognateGroups(detail.conceptId, toObject(detail.groups), 'split');
  }

  function onCognateMerge(event) {
    applyCognateMerge(toObject(event && event.detail));
  }

  function onCognateCycle(event) {
    applyCognateCycle(toObject(event && event.detail));
  }

  function onBorrowingChanged(event) {
    const detail = toObject(event && event.detail);
    upsertBorrowingOverride(detail.conceptId, detail.speaker, {
      status: detail.status,
      updated_at: nowIso(),
    });
  }

  function onBorrowingHandle(event) {
    const detail = toObject(event && event.detail);
    upsertBorrowingOverride(detail.conceptId, detail.speaker, {
      handling: detail.handling,
      updated_at: nowIso(),
    });
  }

  function onCompareClose() {
    const success = flushPending();
    if (!success) {
      console.warn('[enrichments] flush on compare close failed.');
    }
  }

  function onBeforeUnload() {
    flushPending();
  }

  function onPageHide() {
    flushPending();
  }

  function addDocumentListener(name, handler) {
    document.addEventListener(name, handler);
    state.listeners.push({ target: document, name: name, handler: handler });
  }

  function addWindowListener(name, handler) {
    window.addEventListener(name, handler);
    state.listeners.push({ target: window, name: name, handler: handler });
  }

  function removeListeners() {
    for (let i = 0; i < state.listeners.length; i += 1) {
      const item = state.listeners[i];
      const target = item.target || document;
      target.removeEventListener(item.name, item.handler);
    }
    state.listeners = [];
  }

  /**
   * Read enrichments from the backend and refresh window.PARSE.enrichments.
   * @returns {Promise<object>} Resolved enrichments object.
   */
  async function read() {
    try {
      const response = await fetch(ENRICHMENTS_URL, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
        },
        cache: 'no-store',
      });

      if (!response.ok) {
        throw new Error('GET /api/enrichments failed with HTTP ' + response.status);
      }

      const payload = await response.json();
      const rawEnrichments = payload && typeof payload === 'object' && payload.enrichments
        ? payload.enrichments
        : payload;

      P.enrichments = ensureEnrichmentsShape(rawEnrichments);
      state.error = null;
      emitEnrichmentsUpdated();
      return P.enrichments;
    } catch (error) {
      if (!P.enrichments) {
        P.enrichments = ensureEnrichmentsShape(null);
      } else {
        P.enrichments = ensureEnrichmentsShape(P.enrichments);
      }

      state.error = {
        message: toErrorMessage(error),
        timestamp: nowIso(),
      };

      dispatchEvent('parse:enrichments-error', deepClone(state.error));
      console.warn('[enrichments] read fallback to in-memory data:', error);
      return P.enrichments;
    }
  }

  /**
   * Persist current enrichments to backend and append a version snapshot.
   * @param {string} reason Human-readable save reason.
   * @returns {Promise<object>} Saved enrichments object.
   */
  async function write(reason) {
    const saveReason = String(reason || 'write');

    if (state.saveTimer) {
      window.clearTimeout(state.saveTimer);
      state.saveTimer = null;
    }

    state.writingChain = state.writingChain
      .catch(function () {
        return null;
      })
      .then(async function () {
        const enrichments = getCurrentEnrichments();
        appendHistory(saveReason);
        await postEnrichments(enrichments);
        state.dirty = false;
        state.pendingSaveReason = null;
        emitEnrichmentsUpdated();
        return enrichments;
      })
      .catch(function (error) {
        state.dirty = true;
        state.pendingSaveReason = saveReason;
        throw error;
      });

    return state.writingChain;
  }

  /**
   * Flush any pending debounced save immediately.
   * Uses synchronous XHR to avoid data loss during navigation.
   * @returns {boolean} True when save succeeded or nothing was pending.
   */
  function flushPending() {
    const hadPendingTimer = !!state.saveTimer;

    if (state.saveTimer) {
      window.clearTimeout(state.saveTimer);
      state.saveTimer = null;
    }

    if (!hadPendingTimer && !state.dirty) {
      return true;
    }

    const saveReason = state.pendingSaveReason || 'flush-pending';

    try {
      const enrichments = getCurrentEnrichments();
      appendHistory(saveReason);
      postEnrichmentsSync(enrichments);
      state.dirty = false;
      state.pendingSaveReason = null;
      emitEnrichmentsUpdated();
      return true;
    } catch (error) {
      state.dirty = true;
      state.pendingSaveReason = saveReason;
      console.warn('[enrichments] flushPending failed:', error);
      return false;
    }
  }

  /**
   * Return cognate groups for a concept, preferring manual overrides.
   * @param {string|number} conceptId Concept id.
   * @returns {Object<string, string[]>} Group-to-speaker mapping.
   */
  function getCognateGroupsForConcept(conceptId) {
    const enrichments = getCurrentEnrichments();
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return {};
    return getGroupsFromSource(enrichments, conceptKey);
  }

  /**
   * Resolve the cognate group letter for one speaker+concept pair.
   * @param {string|number} conceptId Concept id.
   * @param {string} speaker Speaker id.
   * @returns {string} Group letter or empty string.
   */
  function getGroupForSpeaker(conceptId, speaker) {
    const groups = getCognateGroupsForConcept(conceptId);
    return groupForSpeaker(groups, speaker);
  }

  /**
   * Set manual cognate groups for a concept and broadcast updates.
   * @param {string|number} conceptId Concept id.
   * @param {Object<string, string[]>} groups Group mapping.
   * @param {string} source Change source label.
   */
  function setCognateGroups(conceptId, groups, source) {
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return;

    const enrichments = getCurrentEnrichments();
    const normalized = normalizeGroups(groups);

    const overrides = toObject(enrichments.manual_overrides.cognate_sets);
    if (Object.keys(normalized).length) {
      overrides[conceptKey] = normalized;
    } else {
      delete overrides[conceptKey];
    }
    enrichments.manual_overrides.cognate_sets = overrides;

    const resolvedGroups = getGroupsFromSource(enrichments, conceptKey);

    dispatchEvent('parse:cognates-changed', {
      conceptId: Number.isFinite(Number(conceptKey)) ? Number(conceptKey) : conceptKey,
      groups: deepClone(resolvedGroups),
      source: source || 'manual',
    });

    emitEnrichmentsUpdated();
    scheduleWrite(source || 'cognates-changed');
  }

  /**
   * Clear one concept-level manual cognate override.
   * @param {string|number} conceptId Concept id.
   * @returns {boolean} True when an override existed and was removed.
   */
  function clearManualOverride(conceptId) {
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return false;

    const enrichments = getCurrentEnrichments();
    const overrides = toObject(enrichments.manual_overrides.cognate_sets);
    if (!Object.prototype.hasOwnProperty.call(overrides, conceptKey)) {
      return false;
    }

    delete overrides[conceptKey];
    enrichments.manual_overrides.cognate_sets = overrides;

    const resolvedGroups = getGroupsFromSource(enrichments, conceptKey);

    dispatchEvent('parse:cognates-changed', {
      conceptId: Number.isFinite(Number(conceptKey)) ? Number(conceptKey) : conceptKey,
      groups: deepClone(resolvedGroups),
      source: 'manual-override-cleared',
    });

    emitEnrichmentsUpdated();
    scheduleWrite('manual-override-cleared');
    return true;
  }

  /**
   * Return the latest enrichments read error, if any.
   * @returns {{message: string, timestamp: string}|null} Error details or null.
   */
  function getError() {
    return state.error ? deepClone(state.error) : null;
  }

  /**
   * Initialize enrichments IO listeners and fetch current enrichments.
   * @returns {Promise<object>} Module API object.
   */
  async function init() {
    if (state.initialized) {
      return P.modules.enrichmentsIO;
    }

    addDocumentListener('parse:cognate-accept', onCognateAccept);
    addDocumentListener('parse:cognate-split-done', onCognateSplitDone);
    addDocumentListener('parse:cognate-merge', onCognateMerge);
    addDocumentListener('parse:cognate-cycle', onCognateCycle);
    addDocumentListener('parse:borrowing-changed', onBorrowingChanged);
    addDocumentListener('parse:borrowing-handle', onBorrowingHandle);
    addDocumentListener('parse:compare-close', onCompareClose);
    addWindowListener('beforeunload', onBeforeUnload);
    addWindowListener('pagehide', onPageHide);

    state.initialized = true;
    await read();
    return P.modules.enrichmentsIO;
  }

  /**
   * Destroy listeners and pending save timer.
   */
  function destroy() {
    if (state.initialized) {
      flushPending();
    }

    removeListeners();
    state.initialized = false;
  }

  P.modules.enrichmentsIO = {
    init: init,
    destroy: destroy,
    read: read,
    write: write,
    flushPending: flushPending,
    getError: getError,
    getCognateGroupsForConcept: getCognateGroupsForConcept,
    getGroupForSpeaker: getGroupForSpeaker,
    setCognateGroups: setCognateGroups,
    clearManualOverride: clearManualOverride,
  };
})();
