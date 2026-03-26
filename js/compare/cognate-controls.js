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
    selectedConceptId: null,
    selectedConceptLabel: '',
    speakers: [],
    groups: {},
    mode: 'view',
    splitTargetGroup: 'A',
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

  function normalizeGroupLetter(value) {
    const raw = String(value == null ? '' : value).trim().toUpperCase();
    if (!raw) return '';

    if (GROUP_LETTERS.indexOf(raw) !== -1) {
      return raw;
    }

    const offset = raw.charCodeAt(0) - 65;
    if (Number.isFinite(offset) && offset >= 0) {
      return GROUP_LETTERS[offset % GROUP_LETTERS.length];
    }

    return GROUP_LETTERS[0];
  }

  function nextGroupLetter(currentGroup) {
    const current = normalizeGroupLetter(currentGroup || 'A') || 'A';
    const index = GROUP_LETTERS.indexOf(current);
    if (index === -1) return GROUP_LETTERS[0];
    return GROUP_LETTERS[(index + 1) % GROUP_LETTERS.length];
  }

  function deepClone(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function colorForGroup(groupLetter) {
    const normalized = normalizeGroupLetter(groupLetter || 'A') || 'A';
    return GROUP_COLORS[normalized] || GROUP_COLORS.A;
  }

  function hexToRgba(hex, alpha) {
    const raw = String(hex || '').trim().replace('#', '');
    if (raw.length !== 6) {
      return 'rgba(74, 144, 217, ' + alpha + ')';
    }

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
    const speakerId = String(speaker == null ? '' : speaker).trim();
    const normalizedConceptId = normalizeConceptId(conceptId);
    if (!speakerId || !normalizedConceptId) return null;

    const annotations = toObject(P.annotations);
    const record = toObject(annotations[speakerId]);
    if (!record || !record.tiers) return null;

    const conceptIntervals = intervalsFromTier(record, 'concept');
    let conceptInterval = null;

    for (let i = 0; i < conceptIntervals.length; i += 1) {
      const interval = toObject(conceptIntervals[i]);
      const text = String(interval.text == null ? '' : interval.text).trim();
      if (!text) continue;

      if (normalizeConceptId(text) === normalizedConceptId) {
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
      ipa: ipa,
      ortho: ortho,
    };
  }

  function speakerHasConceptForm(speaker, conceptId) {
    const speakerId = String(speaker == null ? '' : speaker).trim();
    const normalizedConceptId = normalizeConceptId(conceptId);
    if (!speakerId || !normalizedConceptId) return false;

    const conceptTable = P.modules.conceptTable;
    if (conceptTable && typeof conceptTable.getEntryForSpeakerConcept === 'function') {
      const tableEntry = conceptTable.getEntryForSpeakerConcept(speakerId, normalizedConceptId);
      if (tableEntry) {
        const ipaFromTable = String(tableEntry.ipa == null ? '' : tableEntry.ipa).trim();
        const orthoFromTable = String(tableEntry.ortho == null ? '' : tableEntry.ortho).trim();
        return !!(ipaFromTable || orthoFromTable);
      }
      return false;
    }

    const entry = getEntryForSpeakerConcept(speakerId, normalizedConceptId);
    if (!entry) return false;
    return !!(entry.ipa || entry.ortho);
  }

  function normalizeGroups(rawGroups) {
    const source = toObject(rawGroups);
    const out = {};
    const keys = Object.keys(source);

    for (let i = 0; i < keys.length; i += 1) {
      const normalizedGroup = normalizeGroupLetter(keys[i]);
      if (!normalizedGroup) continue;

      const speakers = normalizeStringList(source[keys[i]]);
      if (!speakers.length) continue;
      out[normalizedGroup] = speakers;
    }

    return out;
  }

  function groupForSpeaker(speaker, groups) {
    const speakerId = String(speaker == null ? '' : speaker).trim();
    const safeGroups = normalizeGroups(groups);
    const keys = Object.keys(safeGroups);

    for (let i = 0; i < keys.length; i += 1) {
      const members = normalizeStringList(safeGroups[keys[i]]);
      if (members.indexOf(speakerId) !== -1) {
        return keys[i];
      }
    }

    return '';
  }

  function sanitizeGroups(groups, speakers, conceptId) {
    const targetSpeakers = normalizeStringList(speakers);
    const normalizedGroups = normalizeGroups(groups);
    const normalizedConceptId = normalizeConceptId(conceptId);
    const hasConceptContext = !!normalizedConceptId;

    const speakerHasForm = {};
    for (let i = 0; i < targetSpeakers.length; i += 1) {
      const speaker = targetSpeakers[i];
      speakerHasForm[speaker] = hasConceptContext
        ? speakerHasConceptForm(speaker, normalizedConceptId)
        : true;
    }

    const out = {};

    const seenSpeakers = new Set();
    const keys = Object.keys(normalizedGroups);
    for (let i = 0; i < keys.length; i += 1) {
      const group = keys[i];
      const members = normalizeStringList(normalizedGroups[group]).filter(function (speaker) {
        return targetSpeakers.indexOf(speaker) !== -1 && !!speakerHasForm[speaker];
      });

      const uniqueMembers = [];
      for (let j = 0; j < members.length; j += 1) {
        const speaker = members[j];
        if (seenSpeakers.has(speaker)) continue;
        seenSpeakers.add(speaker);
        uniqueMembers.push(speaker);
      }

      if (uniqueMembers.length) {
        out[group] = uniqueMembers;
      }
    }

    for (let i = 0; i < targetSpeakers.length; i += 1) {
      const speaker = targetSpeakers[i];
      if (seenSpeakers.has(speaker)) continue;
      if (!speakerHasForm[speaker]) continue;

      if (!out.A) {
        out.A = [];
      }
      out.A.push(speaker);
      seenSpeakers.add(speaker);
    }

    return out;
  }

  function readGroupsForConcept(conceptId, speakers) {
    const normalizedConceptId = normalizeConceptId(conceptId);
    if (!normalizedConceptId) {
      return sanitizeGroups({}, speakers, normalizedConceptId);
    }

    const enrichmentsIO = P.modules.enrichmentsIO;
    if (enrichmentsIO && typeof enrichmentsIO.getCognateGroupsForConcept === 'function') {
      const groups = enrichmentsIO.getCognateGroupsForConcept(normalizedConceptId);
      return sanitizeGroups(groups, speakers, normalizedConceptId);
    }

    const enrichments = toObject(P.enrichments);
    const manual = toObject(toObject(enrichments.manual_overrides).cognate_sets);
    if (manual[normalizedConceptId]) {
      return sanitizeGroups(manual[normalizedConceptId], speakers, normalizedConceptId);
    }

    const computed = toObject(enrichments.cognate_sets);
    return sanitizeGroups(computed[normalizedConceptId], speakers, normalizedConceptId);
  }

  function writeGroups(groups) {
    state.groups = sanitizeGroups(groups, state.speakers, state.selectedConceptId);
  }

  function speakerCount(groups) {
    const safeGroups = normalizeGroups(groups);
    const keys = Object.keys(safeGroups);
    let count = 0;
    for (let i = 0; i < keys.length; i += 1) {
      count += normalizeStringList(safeGroups[keys[i]]).length;
    }
    return count;
  }

  function dispatchCognatesChanged(groups) {
    if (!state.selectedConceptId) return;

    dispatch('parse:cognates-changed', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
      groups: deepClone(normalizeGroups(groups)),
    });
  }

  function setMode(mode) {
    const nextMode = String(mode == null ? 'view' : mode).trim().toLowerCase();
    if (nextMode !== 'view' && nextMode !== 'split' && nextMode !== 'cycle') {
      return;
    }
    state.mode = nextMode;
  }

  function createModeButton(text, mode, isActive) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cognate-action-btn';
    button.textContent = text;
    if (isActive) {
      button.classList.add('is-active');
    }
    button.dataset.mode = mode;
    return button;
  }

  function renderPlaceholder() {
    if (!state.containerEl) return;

    state.containerEl.innerHTML =
      '<div class="panel-title">Cognate Controls</div>' +
      '<div class="panel-placeholder">Select a concept row to manage cognate groups.</div>';
  }

  function renderSplitGroupChooser(wrapper) {
    const chooser = document.createElement('div');
    chooser.className = 'split-group-chooser';

    const label = document.createElement('span');
    label.className = 'cognate-mode-note';
    label.textContent = 'Assign selected speakers to:';
    chooser.appendChild(label);

    for (let i = 0; i < GROUP_LETTERS.length; i += 1) {
      const group = GROUP_LETTERS[i];
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'split-group-btn';
      button.textContent = group;
      button.dataset.group = group;
      if (group === state.splitTargetGroup) {
        button.classList.add('is-active');
      }

      const color = colorForGroup(group);
      button.style.borderColor = color;
      button.style.color = color;
      button.style.backgroundColor = hexToRgba(color, 0.12);

      chooser.appendChild(button);
    }

    wrapper.appendChild(chooser);
  }

  function createSpeakerBadge(speaker, group, hasForm) {
    const canGroup = !!hasForm;
    const normalizedGroup = canGroup ? (normalizeGroupLetter(group || 'A') || 'A') : '';
    const color = canGroup ? colorForGroup(normalizedGroup) : '#6d7f9e';

    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'cognate-speaker-item';
    row.dataset.speaker = speaker;
    row.dataset.missing = canGroup ? '0' : '1';

    const badge = document.createElement('span');
    badge.className = 'cognate-speaker-badge';
    badge.textContent = canGroup ? normalizedGroup : '-';
    badge.style.borderColor = color;
    badge.style.color = color;
    badge.style.backgroundColor = canGroup ? hexToRgba(color, 0.15) : 'rgba(109, 127, 158, 0.2)';

    const label = document.createElement('span');
    label.className = 'cognate-speaker-label';
    label.textContent = speaker;

    if (!canGroup) {
      row.style.borderColor = 'rgba(109, 127, 158, 0.4)';
      row.style.opacity = '0.75';
      row.style.cursor = 'not-allowed';
      label.style.color = '#91a0ba';
    }

    row.appendChild(badge);
    row.appendChild(label);
    return row;
  }

  function renderControls() {
    if (!state.containerEl) return;

    if (!state.selectedConceptId) {
      renderPlaceholder();
      return;
    }

    state.containerEl.innerHTML = '';

    const title = document.createElement('div');
    title.className = 'panel-title';
    title.textContent = 'Cognate Controls';

    const context = document.createElement('div');
    context.className = 'cognate-mode-note';
    context.textContent =
      'Concept #' + state.selectedConceptId +
      (state.selectedConceptLabel ? (': ' + state.selectedConceptLabel) : '');

    const actions = document.createElement('div');
    actions.className = 'cognate-actions';

    const acceptBtn = createModeButton('Accept', 'accept', false);
    const splitBtn = createModeButton('Split', 'split', state.mode === 'split');
    const mergeBtn = createModeButton('Merge', 'merge', false);
    const cycleBtn = createModeButton('Cycle', 'cycle', state.mode === 'cycle');

    actions.appendChild(acceptBtn);
    actions.appendChild(splitBtn);
    actions.appendChild(mergeBtn);
    actions.appendChild(cycleBtn);

    state.containerEl.appendChild(title);
    state.containerEl.appendChild(context);
    state.containerEl.appendChild(actions);

    const body = document.createElement('div');
    if (state.mode === 'split') {
      renderSplitGroupChooser(body);

      const splitDone = document.createElement('button');
      splitDone.type = 'button';
      splitDone.className = 'cognate-action-btn';
      splitDone.textContent = 'Done Split';
      splitDone.dataset.mode = 'split-done';
      body.appendChild(splitDone);

      const splitNote = document.createElement('div');
      splitNote.className = 'cognate-mode-note';
      splitNote.textContent = 'Split mode: click speaker badges to assign to the active group.';
      body.appendChild(splitNote);
    } else if (state.mode === 'cycle') {
      const cycleNote = document.createElement('div');
      cycleNote.className = 'cognate-mode-note';
      cycleNote.textContent = 'Cycle mode: click speaker badges to cycle A -> B -> C -> D -> E.';
      body.appendChild(cycleNote);
    } else {
      const viewNote = document.createElement('div');
      viewNote.className = 'cognate-mode-note';
      viewNote.textContent = 'View mode: choose Split or Cycle to edit groups.';
      body.appendChild(viewNote);
    }

    const speakerGrid = document.createElement('div');
    speakerGrid.className = 'cognate-speaker-grid';

    for (let i = 0; i < state.speakers.length; i += 1) {
      const speaker = state.speakers[i];
      const hasForm = speakerHasConceptForm(speaker, state.selectedConceptId);
      const group = hasForm ? (groupForSpeaker(speaker, state.groups) || 'A') : '';
      speakerGrid.appendChild(createSpeakerBadge(speaker, group, hasForm));
    }

    body.appendChild(speakerGrid);
    state.containerEl.appendChild(body);

    addActionListeners(actions, speakerGrid, body);
  }

  function applySplitAssign(speaker) {
    const speakerId = String(speaker == null ? '' : speaker).trim();
    if (!speakerId || !state.selectedConceptId) return;
    if (!speakerHasConceptForm(speakerId, state.selectedConceptId)) return;

    const fromGroup = groupForSpeaker(speakerId, state.groups) || 'A';
    const toGroup = state.splitTargetGroup;
    if (fromGroup === toGroup) return;

    const nextGroups = normalizeGroups(state.groups);
    const keys = Object.keys(nextGroups);
    for (let i = 0; i < keys.length; i += 1) {
      nextGroups[keys[i]] = normalizeStringList(nextGroups[keys[i]]).filter(function (item) {
        return item !== speakerId;
      });
      if (!nextGroups[keys[i]].length) {
        delete nextGroups[keys[i]];
      }
    }

    if (!nextGroups[toGroup]) {
      nextGroups[toGroup] = [];
    }
    nextGroups[toGroup].push(speakerId);

    writeGroups(nextGroups);

    dispatch('parse:cognate-split-assign', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
      speaker: speakerId,
      fromGroup: fromGroup,
      toGroup: toGroup,
    });

    dispatchCognatesChanged(state.groups);
    renderControls();
  }

  function applyCycle(speaker) {
    const speakerId = String(speaker == null ? '' : speaker).trim();
    if (!speakerId || !state.selectedConceptId) return;
    if (!speakerHasConceptForm(speakerId, state.selectedConceptId)) return;

    const fromGroup = groupForSpeaker(speakerId, state.groups) || 'A';
    const toGroup = nextGroupLetter(fromGroup);

    const nextGroups = normalizeGroups(state.groups);
    const keys = Object.keys(nextGroups);
    for (let i = 0; i < keys.length; i += 1) {
      nextGroups[keys[i]] = normalizeStringList(nextGroups[keys[i]]).filter(function (item) {
        return item !== speakerId;
      });
      if (!nextGroups[keys[i]].length) {
        delete nextGroups[keys[i]];
      }
    }

    if (!nextGroups[toGroup]) {
      nextGroups[toGroup] = [];
    }
    nextGroups[toGroup].push(speakerId);

    writeGroups(nextGroups);

    dispatch('parse:cognate-cycle', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
      speaker: speakerId,
      newGroup: toGroup,
    });

    dispatchCognatesChanged(state.groups);
    renderControls();
  }

  function applyMerge() {
    if (!state.selectedConceptId) return;

    const merged = speakerCount(state.groups)
      ? { A: state.speakers.slice() }
      : {};

    writeGroups(merged);

    dispatch('parse:cognate-merge', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
    });

    dispatchCognatesChanged(state.groups);
    setMode('view');
    renderControls();
  }

  function applyAccept() {
    if (!state.selectedConceptId) return;

    dispatch('parse:cognate-accept', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
    });

    setMode('view');
    renderControls();
  }

  function completeSplit() {
    if (!state.selectedConceptId) return;

    dispatch('parse:cognate-split-done', {
      conceptId: conceptIdToEventValue(state.selectedConceptId),
      groups: deepClone(state.groups),
    });

    dispatchCognatesChanged(state.groups);
    setMode('view');
    renderControls();
  }

  function addActionListeners(actionsEl, speakerGridEl, bodyEl) {
    actionsEl.addEventListener('click', function (event) {
      const target = event.target;
      if (!target || !target.dataset) return;

      const mode = String(target.dataset.mode || '').trim();
      if (!mode) return;

      if (mode === 'accept') {
        applyAccept();
        return;
      }

      if (mode === 'merge') {
        applyMerge();
        return;
      }

      if (mode === 'split') {
        const nextMode = state.mode === 'split' ? 'view' : 'split';
        setMode(nextMode);
        if (nextMode === 'split') {
          dispatch('parse:cognate-split-start', {
            conceptId: conceptIdToEventValue(state.selectedConceptId),
          });
        }
        renderControls();
        return;
      }

      if (mode === 'cycle') {
        const nextMode = state.mode === 'cycle' ? 'view' : 'cycle';
        setMode(nextMode);
        renderControls();
      }
    });

    speakerGridEl.addEventListener('click', function (event) {
      const target = event.target;
      const row = target && typeof target.closest === 'function'
        ? target.closest('.cognate-speaker-item')
        : null;
      if (!row || !row.dataset || !row.dataset.speaker) return;
      if (row.dataset.missing === '1') return;

      const speaker = row.dataset.speaker;
      if (state.mode === 'split') {
        applySplitAssign(speaker);
      } else if (state.mode === 'cycle') {
        applyCycle(speaker);
      }
    });

    bodyEl.addEventListener('click', function (event) {
      const target = event.target;
      if (!target || !target.dataset) return;

      const selectedGroup = normalizeGroupLetter(target.dataset.group);
      if (selectedGroup && state.mode === 'split') {
        state.splitTargetGroup = selectedGroup;
        renderControls();
        return;
      }

      const mode = String(target.dataset.mode || '').trim();
      if (mode === 'split-done') {
        completeSplit();
      }
    });
  }

  function setContext(conceptId, conceptLabel, speakers) {
    const normalizedConceptId = normalizeConceptId(conceptId);
    state.selectedConceptId = normalizedConceptId || null;
    state.selectedConceptLabel = String(conceptLabel == null ? '' : conceptLabel).trim();
    state.speakers = normalizeStringList(speakers);
    state.groups = readGroupsForConcept(state.selectedConceptId, state.speakers);

    if (!state.groups || !Object.keys(state.groups).length) {
      state.groups = sanitizeGroups({}, state.speakers, state.selectedConceptId);
    }

    state.mode = 'view';
    state.splitTargetGroup = 'A';
    renderControls();
  }

  function onConceptSelected(event) {
    const detail = toObject(event && event.detail);
    setContext(detail.conceptId, detail.conceptLabel, detail.speakers);
  }

  function onSpeakersChanged(event) {
    const detail = toObject(event && event.detail);
    const speakers = normalizeStringList(detail.speakers);
    if (!speakers.length) {
      state.speakers = [];
      state.groups = {};
      renderControls();
      return;
    }

    state.speakers = speakers;
    state.groups = sanitizeGroups(state.groups, state.speakers, state.selectedConceptId);
    renderControls();
  }

  function onCognatesChanged(event) {
    const detail = toObject(event && event.detail);
    const conceptId = normalizeConceptId(detail.conceptId);
    if (!conceptId || conceptId !== state.selectedConceptId) {
      return;
    }

    state.groups = sanitizeGroups(detail.groups, state.speakers, state.selectedConceptId);
    renderControls();
  }

  function onEnrichmentsUpdated() {
    if (!state.selectedConceptId) return;

    state.groups = readGroupsForConcept(state.selectedConceptId, state.speakers);
    renderControls();
  }

  /**
   * Set the active concept context for cognate editing.
   * @param {string|number|null} conceptId Concept ID.
   * @param {string=} conceptLabel Concept label text.
   */
  function setConcept(conceptId, conceptLabel) {
    const compareState = toObject(P.compareState);
    const speakers = state.speakers.length
      ? state.speakers
      : normalizeStringList(compareState.selectedSpeakers);

    setContext(conceptId, conceptLabel, speakers);
  }

  /**
   * Update speakers shown in the panel.
   * @param {Array<string>} speakers Speaker IDs.
   */
  function setSpeakers(speakers) {
    state.speakers = normalizeStringList(speakers);
    state.groups = sanitizeGroups(state.groups, state.speakers, state.selectedConceptId);
    renderControls();
  }

  /**
   * Initialize cognate controls for Compare mode.
   * @param {HTMLElement} containerEl Compare cognate panel element.
   * @returns {object} Cognate controls module API.
   */
  function init(containerEl) {
    if (state.initialized) {
      return P.modules.cognateControls;
    }

    state.containerEl = containerEl || document.getElementById('compare-cognate-panel');
    if (!state.containerEl) {
      throw new Error('Missing #compare-cognate-panel container for cognate controls.');
    }

    renderPlaceholder();

    addListener(document, 'parse:compare-concept-select', onConceptSelected);
    addListener(document, 'parse:compare-speakers-changed', onSpeakersChanged);
    addListener(document, 'parse:cognates-changed', onCognatesChanged);
    addListener(document, 'parse:enrichments-updated', onEnrichmentsUpdated);

    state.initialized = true;
    return P.modules.cognateControls;
  }

  /**
   * Destroy cognate controls listeners and clear panel content.
   */
  function destroy() {
    removeAllListeners();

    if (state.containerEl) {
      state.containerEl.innerHTML = '';
    }

    state.initialized = false;
    state.selectedConceptId = null;
    state.selectedConceptLabel = '';
    state.speakers = [];
    state.groups = {};
    state.mode = 'view';
    state.splitTargetGroup = 'A';
  }

  P.modules.cognateControls = {
    init: init,
    destroy: destroy,
    setConcept: setConcept,
    setSpeakers: setSpeakers,
  };
})();
