(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const GROUP_LETTERS = ['A', 'B', 'C', 'D', 'E'];
  const GROUP_COLORS = {
    A: '#4a90d9',
    B: '#27ae60',
    C: '#e67e22',
    D: '#8e44ad',
    E: '#e74c3c',
  };
  const MATCH_EPSILON = 0.01;

  const state = {
    initialized: false,
    containerEl: null,
    scrollEl: null,
    tableEl: null,
    concepts: [],
    selectedSpeakers: [],
    selectedConceptId: null,
    visibleConceptIds: [],
    listeners: [],
  };

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function addListener(target, type, handler) {
    target.addEventListener(type, handler);
    state.listeners.push({ target: target, type: type, handler: handler });
  }

  function removeAllListeners() {
    for (let i = 0; i < state.listeners.length; i += 1) {
      const item = state.listeners[i];
      item.target.removeEventListener(item.type, item.handler);
    }
    state.listeners = [];
  }

  function toObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function normalizeStringList(value) {
    if (!Array.isArray(value)) return [];

    const out = [];
    const seen = new Set();
    for (let i = 0; i < value.length; i += 1) {
      const text = String(value[i] == null ? '' : value[i]).trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      out.push(text);
    }
    return out;
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

  function conceptIdToEventValue(conceptId) {
    const id = normalizeConceptId(conceptId);
    const numeric = Number(id);
    return Number.isFinite(numeric) ? numeric : id;
  }

  function parseConceptEntry(rawEntry, index) {
    let rawId = '';
    let label = '';

    if (rawEntry && typeof rawEntry === 'object') {
      rawId = rawEntry.id;
      if (rawId == null) rawId = rawEntry.concept_id;
      if (rawId == null) rawId = rawEntry.conceptId;
      if (rawId == null) rawId = rawEntry.key;
      if (rawId == null) rawId = rawEntry.number;

      label = rawEntry.label;
      if (label == null) label = rawEntry.english;
      if (label == null) label = rawEntry.gloss;
      if (label == null) label = rawEntry.name;
      if (label == null) label = rawEntry.concept_en;
      if (label == null) label = rawEntry.text;
    } else if (typeof rawEntry === 'string') {
      const text = rawEntry.trim();
      const colonIndex = text.indexOf(':');
      if (colonIndex !== -1) {
        rawId = text.slice(0, colonIndex).trim();
        label = text.slice(colonIndex + 1).trim();
      } else {
        rawId = text;
      }
    } else if (typeof rawEntry === 'number') {
      rawId = String(rawEntry);
    }

    const id = normalizeConceptId(rawId || String(index + 1));
    if (!id) return null;

    return {
      id: id,
      label: String(label == null ? '' : label).trim(),
    };
  }

  function normalizeConceptList(concepts) {
    const raw = Array.isArray(concepts) ? concepts : [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < raw.length; i += 1) {
      const parsed = parseConceptEntry(raw[i], i);
      if (!parsed || seen.has(parsed.id)) continue;
      seen.add(parsed.id);
      out.push(parsed);
    }

    return out;
  }

  function getConceptLabel(concept) {
    if (!concept) return '';
    const label = String(concept.label == null ? '' : concept.label).trim();
    if (label) return label;
    return 'Concept ' + concept.id;
  }

  function normalizeGroupLetter(value) {
    const raw = String(value == null ? '' : value).trim().toUpperCase();
    if (!raw) return '';

    const direct = GROUP_LETTERS.indexOf(raw);
    if (direct !== -1) {
      return raw;
    }

    const code = raw.charCodeAt(0) - 65;
    if (Number.isFinite(code) && code >= 0) {
      return GROUP_LETTERS[code % GROUP_LETTERS.length];
    }

    return GROUP_LETTERS[0];
  }

  function colorForGroup(groupLetter) {
    const normalized = normalizeGroupLetter(groupLetter);
    return GROUP_COLORS[normalized] || GROUP_COLORS.A;
  }

  function hexToRgba(hex, alpha) {
    const raw = String(hex || '').trim().replace('#', '');
    if (raw.length !== 6) return 'rgba(74, 144, 217, ' + alpha + ')';

    const r = parseInt(raw.slice(0, 2), 16);
    const g = parseInt(raw.slice(2, 4), 16);
    const b = parseInt(raw.slice(4, 6), 16);
    if (!Number.isFinite(r) || !Number.isFinite(g) || !Number.isFinite(b)) {
      return 'rgba(74, 144, 217, ' + alpha + ')';
    }
    return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + alpha + ')';
  }

  function intervalsFromTier(record, tierName) {
    const tiers = toObject(record && record.tiers);
    const tier = toObject(tiers[tierName]);
    return Array.isArray(tier.intervals) ? tier.intervals : [];
  }

  function approxEqual(left, right, epsilon) {
    return Math.abs(Number(left) - Number(right)) <= epsilon;
  }

  function findIntervalTextByBounds(intervals, startSec, endSec) {
    const list = Array.isArray(intervals) ? intervals : [];

    for (let i = 0; i < list.length; i += 1) {
      const interval = toObject(list[i]);
      if (
        Number.isFinite(Number(interval.start)) &&
        Number.isFinite(Number(interval.end)) &&
        approxEqual(interval.start, startSec, MATCH_EPSILON) &&
        approxEqual(interval.end, endSec, MATCH_EPSILON)
      ) {
        return String(interval.text == null ? '' : interval.text).trim();
      }
    }

    return '';
  }

  function getEntryForSpeakerConcept(speaker, conceptId) {
    const annotations = toObject(P.annotations);
    const record = toObject(annotations[speaker]);
    if (!record || !record.tiers) return null;

    const conceptIntervals = intervalsFromTier(record, 'concept');
    let conceptInterval = null;

    for (let i = 0; i < conceptIntervals.length; i += 1) {
      const interval = toObject(conceptIntervals[i]);
      const text = String(interval.text == null ? '' : interval.text).trim();
      if (!text) continue;

      if (normalizeConceptId(text) === conceptId) {
        conceptInterval = interval;
        break;
      }
    }

    if (!conceptInterval) return null;

    const startSec = Number(conceptInterval.start);
    const endSec = Number(conceptInterval.end);
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec <= startSec) {
      return null;
    }

    const ipaIntervals = intervalsFromTier(record, 'ipa');
    const orthoIntervals = intervalsFromTier(record, 'ortho');
    const ipa = findIntervalTextByBounds(ipaIntervals, startSec, endSec);
    const ortho = findIntervalTextByBounds(orthoIntervals, startSec, endSec);

    return {
      sourceWav: String(record.source_audio == null ? '' : record.source_audio).trim(),
      startSec: startSec,
      endSec: endSec,
      ipa: ipa,
      ortho: ortho,
    };
  }

  function groupsFromEnrichments(conceptId) {
    const enrichmentsIO = P.modules.enrichmentsIO;
    if (enrichmentsIO && typeof enrichmentsIO.getCognateGroupsForConcept === 'function') {
      return toObject(enrichmentsIO.getCognateGroupsForConcept(conceptId));
    }

    const enrichments = toObject(P.enrichments);
    const manualOverrides = toObject(enrichments.manual_overrides);
    const manualCognates = toObject(manualOverrides.cognate_sets);
    if (manualCognates[conceptId]) {
      return toObject(manualCognates[conceptId]);
    }

    const computed = toObject(enrichments.cognate_sets);
    return toObject(computed[conceptId]);
  }

  function groupForSpeaker(conceptId, speaker) {
    const enrichmentsIO = P.modules.enrichmentsIO;
    if (enrichmentsIO && typeof enrichmentsIO.getGroupForSpeaker === 'function') {
      const group = enrichmentsIO.getGroupForSpeaker(conceptId, speaker);
      return normalizeGroupLetter(group);
    }

    const groups = groupsFromEnrichments(conceptId);
    const keys = Object.keys(groups);
    const speakerId = String(speaker == null ? '' : speaker).trim();

    for (let i = 0; i < keys.length; i += 1) {
      const group = normalizeGroupLetter(keys[i]);
      const members = normalizeStringList(groups[keys[i]]);
      if (members.indexOf(speakerId) !== -1) {
        return group;
      }
    }

    return '';
  }

  function isConceptVisible(conceptId) {
    const tagsModule = P.modules.tags;
    if (!tagsModule || typeof tagsModule.matchesFilter !== 'function') {
      return true;
    }
    return tagsModule.matchesFilter(conceptIdToEventValue(conceptId));
  }

  function selectConcept(conceptId) {
    const normalized = normalizeConceptId(conceptId);
    if (!normalized) return;

    state.selectedConceptId = normalized;
    P.currentConcept = normalized;
    P.compareState = toObject(P.compareState);
    P.compareState.selectedConceptId = normalized;

    const selectedConcept = state.concepts.find(function (concept) {
      return concept.id === normalized;
    }) || null;
    const conceptLabel = selectedConcept ? getConceptLabel(selectedConcept) : '';

    dispatch('parse:compare-concept-select', {
      conceptId: conceptIdToEventValue(normalized),
      conceptLabel: conceptLabel,
      speakers: state.selectedSpeakers.slice(),
    });

    /**
     * Mirrors concept selection for compare-level listeners.
     * @event parse:compare-concept-selected
     * @type {CustomEvent}
     * @property {{conceptId: string}} detail Selected concept id.
     */
    dispatch('parse:compare-concept-selected', {
      conceptId: normalized,
      conceptLabel: conceptLabel,
      speakers: state.selectedSpeakers.slice(),
    });

    render();
  }

  function navigateToAnnotate(speaker, conceptId) {
    const speakerId = String(speaker == null ? '' : speaker).trim();
    const normalizedConceptId = normalizeConceptId(conceptId);
    if (!speakerId || !normalizedConceptId) return;

    const url = new URL('parse.html', window.location.href);
    url.searchParams.set('speaker', speakerId);
    url.searchParams.set('concept', normalizedConceptId);
    window.location.href = url.pathname + url.search;
  }

  function isPromiseLike(value) {
    return !!value && typeof value.then === 'function';
  }

  async function flushPendingEnrichments() {
    const enrichmentsIO = P.modules && P.modules.enrichmentsIO;
    if (!enrichmentsIO || typeof enrichmentsIO.flushPending !== 'function') {
      return;
    }

    const maybePromise = enrichmentsIO.flushPending();
    if (isPromiseLike(maybePromise)) {
      await maybePromise;
    }
  }

  async function navigateToAnnotateWithFlush(speaker, conceptId) {
    try {
      await flushPendingEnrichments();
    } catch (error) {
      console.warn('[concept-table] Failed to flush enrichments before navigation:', error);
    }
    navigateToAnnotate(speaker, conceptId);
  }

  function dispatchAudioPlay(speaker, conceptId, entry) {
    if (!entry || !entry.sourceWav) return;

    dispatch('parse:audio-play', {
      sourceWav: entry.sourceWav,
      startSec: entry.startSec,
      endSec: entry.endSec,
      speaker: speaker,
      conceptId: conceptIdToEventValue(conceptId),
    });
  }

  function createConceptCell(concept) {
    const td = document.createElement('td');
    td.className = 'compare-concept-cell';

    const label = document.createElement('div');
    label.className = 'compare-concept-label';
    label.textContent = getConceptLabel(concept);

    const id = document.createElement('div');
    id.className = 'compare-concept-id';
    id.textContent = '#' + concept.id;

    td.appendChild(label);
    td.appendChild(id);

    return td;
  }

  function createEmptyCell() {
    const td = document.createElement('td');
    const empty = document.createElement('span');
    empty.className = 'compare-empty';
    empty.textContent = 'No form';
    empty.title = 'No annotated form for this speaker at the selected concept.';
    td.appendChild(empty);
    return td;
  }

  function createBadge(groupLetter) {
    const badge = document.createElement('span');
    badge.className = 'compare-cognate-badge';

    const normalized = normalizeGroupLetter(groupLetter || 'A') || 'A';
    const color = colorForGroup(normalized);
    badge.textContent = normalized;
    badge.dataset.group = normalized;
    badge.style.borderColor = color;
    badge.style.color = color;
    badge.style.backgroundColor = hexToRgba(color, 0.15);
    return badge;
  }

  function createPopulatedCell(speaker, conceptId, entry) {
    const td = document.createElement('td');

    const wrapper = document.createElement('div');
    wrapper.className = 'compare-entry';

    const playButton = document.createElement('button');
    playButton.type = 'button';
    playButton.className = 'compare-play-btn';
    playButton.textContent = '▶';
    playButton.setAttribute('aria-label', 'Play ' + speaker + ' concept ' + conceptId);

    const lines = document.createElement('div');
    lines.className = 'compare-cell-lines';

    const ipa = document.createElement('div');
    ipa.className = 'compare-ipa';
    ipa.textContent = entry.ipa || '—';

    const ortho = document.createElement('div');
    ortho.className = 'compare-ortho';
    ortho.textContent = entry.ortho || '—';

    const resolvedGroup = groupForSpeaker(conceptId, speaker) || 'A';
    const badge = createBadge(resolvedGroup);

    lines.appendChild(ipa);
    lines.appendChild(ortho);

    wrapper.appendChild(playButton);
    wrapper.appendChild(lines);
    wrapper.appendChild(badge);
    td.appendChild(wrapper);

    td.addEventListener('click', function (event) {
      selectConcept(conceptId);

      const target = event && event.target;
      const playButtonTarget = target && typeof target.closest === 'function'
        ? target.closest('.compare-play-btn')
        : null;

      if (playButtonTarget) {
        dispatchAudioPlay(speaker, conceptId, entry);
      }
    });

    td.addEventListener('dblclick', function () {
      void navigateToAnnotateWithFlush(speaker, conceptId);
    });

    return td;
  }

  function maybeNormalizeSelectedConcept() {
    if (!state.selectedConceptId) return;

    const foundVisible = state.visibleConceptIds.some(function (conceptId) {
      return normalizeConceptId(conceptId) === state.selectedConceptId;
    });

    if (!foundVisible) {
      state.selectedConceptId = null;
      P.currentConcept = null;
      P.compareState = toObject(P.compareState);
      P.compareState.selectedConceptId = null;

      dispatch('parse:compare-concept-select', {
        conceptId: null,
        conceptLabel: '',
        speakers: state.selectedSpeakers.slice(),
      });

      dispatch('parse:compare-concept-selected', {
        conceptId: null,
        conceptLabel: '',
        speakers: state.selectedSpeakers.slice(),
      });
    }
  }

  function renderEmptyBodyRow(tbody, message, columnCount) {
    const tr = document.createElement('tr');
    tr.className = 'compare-empty-row';

    const td = document.createElement('td');
    td.colSpan = Math.max(1, Number(columnCount) || 1);

    const copy = document.createElement('div');
    copy.className = 'panel-placeholder';
    copy.textContent = String(message == null ? '' : message).trim();

    td.appendChild(copy);
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function render() {
    if (!state.tableEl) return;

    state.tableEl.classList.remove('hidden');
    state.tableEl.removeAttribute('aria-hidden');
    state.tableEl.innerHTML = '';
    state.visibleConceptIds = [];

    const visibleConcepts = [];
    for (let i = 0; i < state.concepts.length; i += 1) {
      const concept = state.concepts[i];
      if (!isConceptVisible(concept.id)) continue;

      visibleConcepts.push(concept);
      state.visibleConceptIds.push(conceptIdToEventValue(concept.id));
    }

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const conceptHeader = document.createElement('th');
    conceptHeader.textContent = 'Concept';
    headerRow.appendChild(conceptHeader);

    for (let i = 0; i < state.selectedSpeakers.length; i += 1) {
      const th = document.createElement('th');
      th.textContent = state.selectedSpeakers[i];
      headerRow.appendChild(th);
    }

    thead.appendChild(headerRow);
    state.tableEl.appendChild(thead);

    const tbody = document.createElement('tbody');

    if (!visibleConcepts.length) {
      const compareState = toObject(P.compareState);
      const queueHasConcepts = Array.isArray(compareState.concepts) && compareState.concepts.length > 0;
      const message = queueHasConcepts
        ? 'No concepts match current queue filters. Clear search, tag, or status filters in the sidebar.'
        : 'Concept queue is empty. Add concept CSV/annotation data, then refresh Compare.';

      renderEmptyBodyRow(tbody, message, state.selectedSpeakers.length + 1);
    } else if (!state.selectedSpeakers.length) {
      renderEmptyBodyRow(
        tbody,
        'No speakers selected. Add speakers in Compare controls to populate this secondary matrix cross-check.',
        1
      );
    } else {
      for (let i = 0; i < visibleConcepts.length; i += 1) {
        const concept = visibleConcepts[i];

        const tr = document.createElement('tr');
        tr.dataset.conceptId = concept.id;
        if (state.selectedConceptId && state.selectedConceptId === concept.id) {
          tr.classList.add('is-selected');
        }

        const conceptCell = createConceptCell(concept);
        conceptCell.addEventListener('click', function (event) {
          const rowConceptId = event.currentTarget.parentElement
            ? event.currentTarget.parentElement.dataset.conceptId
            : concept.id;
          selectConcept(rowConceptId);
        });
        tbody.appendChild(tr);
        tr.appendChild(conceptCell);

        for (let j = 0; j < state.selectedSpeakers.length; j += 1) {
          const speaker = state.selectedSpeakers[j];
          const entry = getEntryForSpeakerConcept(speaker, concept.id);

          if (!entry) {
            const emptyCell = createEmptyCell();
            emptyCell.addEventListener('click', function () {
              selectConcept(concept.id);
            });
            emptyCell.addEventListener('dblclick', function () {
              void navigateToAnnotateWithFlush(speaker, concept.id);
            });
            tr.appendChild(emptyCell);
          } else {
            tr.appendChild(createPopulatedCell(speaker, concept.id, entry));
          }
        }
      }
    }

    state.tableEl.appendChild(tbody);
    maybeNormalizeSelectedConcept();
  }

  function ensureDefaultConcepts() {
    if (state.concepts.length) return;

    const compareState = toObject(P.compareState);
    const fromCompareState = normalizeConceptList(compareState.concepts);
    if (fromCompareState.length) {
      state.concepts = fromCompareState;
      return;
    }

    const project = toObject(P.project);
    const rawConcepts = project.concepts;
    let entries = [];

    if (Array.isArray(rawConcepts)) {
      entries = rawConcepts;
    } else if (rawConcepts && typeof rawConcepts === 'object') {
      if (Array.isArray(rawConcepts.list)) {
        entries = rawConcepts.list;
      } else if (Array.isArray(rawConcepts.items)) {
        entries = rawConcepts.items;
      }
    }

    state.concepts = normalizeConceptList(entries);

    if (!state.concepts.length) {
      const total = Number(rawConcepts && rawConcepts.total);
      if (Number.isFinite(total) && total > 0) {
        const generated = [];
        for (let i = 1; i <= Math.floor(total); i += 1) {
          generated.push({ id: String(i), label: '' });
        }
        state.concepts = generated;
      }
    }
  }

  function ensureDefaultSpeakers() {
    if (state.selectedSpeakers.length) return;

    const compareState = toObject(P.compareState);
    const fromCompareState = normalizeStringList(compareState.selectedSpeakers);
    if (fromCompareState.length) {
      state.selectedSpeakers = fromCompareState;
      return;
    }

    const project = toObject(P.project);
    const speakersObj = toObject(project.speakers);
    const fromProject = Object.keys(speakersObj);
    state.selectedSpeakers = fromProject;
  }

  function buildUi() {
    if (!state.containerEl) return;

    state.containerEl.innerHTML = '';

    const title = document.createElement('div');
    title.className = 'panel-title';
    title.textContent = 'Concept × Speaker Matrix';

    const note = document.createElement('div');
    note.className = 'panel-placeholder';
    note.textContent = 'Secondary cross-check surface. Primary review stays in the sidebar concept queue.';

    const scroll = document.createElement('div');
    scroll.className = 'compare-table-scroll';

    const table = document.createElement('table');
    table.className = 'compare-matrix';

    scroll.appendChild(table);
    state.containerEl.appendChild(title);
    state.containerEl.appendChild(note);
    state.containerEl.appendChild(scroll);

    state.scrollEl = scroll;
    state.tableEl = table;
  }

  function onEnrichmentsUpdated() {
    render();
  }

  function onTagFilter() {
    render();
  }

  function onCognatesChanged() {
    render();
  }

  function onSpeakersChanged(event) {
    const detail = toObject(event && event.detail);
    if (Array.isArray(detail.speakers)) {
      state.selectedSpeakers = normalizeStringList(detail.speakers);
      render();
    }
  }

  function onConceptSelect(event) {
    const detail = toObject(event && event.detail);

    if (detail.conceptId == null || String(detail.conceptId).trim() === '') {
      if (!state.selectedConceptId) return;
      state.selectedConceptId = null;
      render();
      return;
    }

    const conceptId = normalizeConceptId(detail.conceptId);
    if (!conceptId) return;
    if (state.selectedConceptId === conceptId) return;

    state.selectedConceptId = conceptId;
    render();
  }

  function onAnnotationsChanged() {
    render();
  }

  /**
   * Initialize the concept table module.
   * @param {HTMLElement} containerEl Compare table container element.
   * @returns {object} Concept table module API.
   */
  function init(containerEl) {
    if (state.initialized) {
      return P.modules.conceptTable;
    }

    state.containerEl = containerEl || document.getElementById('compare-table');
    if (!state.containerEl) {
      throw new Error('Missing #compare-table container for concept table module.');
    }

    buildUi();
    ensureDefaultConcepts();
    ensureDefaultSpeakers();

    addListener(document, 'parse:enrichments-updated', onEnrichmentsUpdated);
    addListener(document, 'parse:tag-filter', onTagFilter);
    addListener(document, 'parse:cognates-changed', onCognatesChanged);
    addListener(document, 'parse:compare-speakers-changed', onSpeakersChanged);
    addListener(document, 'parse:compare-concept-select', onConceptSelect);
    addListener(document, 'parse:annotations-changed', onAnnotationsChanged);

    if (!state.selectedConceptId && state.concepts.length) {
      state.selectedConceptId = state.concepts[0].id;
    }

    if (state.selectedConceptId) {
      selectConcept(state.selectedConceptId);
    } else {
      render();
    }

    state.initialized = true;
    return P.modules.conceptTable;
  }

  /**
   * Destroy concept table listeners and clear rendered content.
   */
  function destroy() {
    removeAllListeners();

    if (state.containerEl) {
      state.containerEl.innerHTML = '';
    }

    state.initialized = false;
    state.scrollEl = null;
    state.tableEl = null;
    state.visibleConceptIds = [];
  }

  /**
   * Set concepts for the matrix rows.
   * @param {Array<object|string|number>} concepts Concept definitions.
   */
  function setConcepts(concepts) {
    state.concepts = normalizeConceptList(concepts);
    if (state.initialized) {
      render();
    }
  }

  /**
   * Set selected speakers for matrix columns.
   * @param {Array<string>} speakers Speaker IDs.
   */
  function setSpeakers(speakers) {
    state.selectedSpeakers = normalizeStringList(speakers);
    if (state.initialized) {
      render();
    }
  }

  /**
   * Set full concept table data payload.
   * @param {{concepts?: Array, speakers?: Array, annotations?: object, selectedConceptId?: string|number}} payload Data payload.
   */
  function setData(payload) {
    const data = toObject(payload);

    if (Array.isArray(data.concepts)) {
      state.concepts = normalizeConceptList(data.concepts);
    }

    if (Array.isArray(data.speakers)) {
      state.selectedSpeakers = normalizeStringList(data.speakers);
    }

    if (data.annotations && typeof data.annotations === 'object') {
      P.annotations = data.annotations;
    }

    if (data.selectedConceptId != null) {
      const selected = normalizeConceptId(data.selectedConceptId);
      state.selectedConceptId = selected || null;
    }

    if (state.initialized) {
      render();
    }
  }

  /**
   * Refresh the rendered table.
   */
  function refresh() {
    if (!state.initialized) return;
    render();
  }

  /**
   * Return visible concept IDs after active filtering.
   * @returns {Array<number|string>} Visible concept IDs.
   */
  function getVisibleConceptIds() {
    return state.visibleConceptIds.slice();
  }

  P.modules.conceptTable = {
    init: init,
    destroy: destroy,
    setConcepts: setConcepts,
    setSpeakers: setSpeakers,
    setData: setData,
    refresh: refresh,
    getVisibleConceptIds: getVisibleConceptIds,
    getEntryForSpeakerConcept: getEntryForSpeakerConcept,
  };
})();
