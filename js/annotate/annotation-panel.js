/**
 * annotation-panel.js - PARSE annotation editor panel
 *
 * Responsibilities:
 *  - Attach to window.PARSE.modules.annotationPanel
 *  - Render IPA / Ortho / Concept fields in #parse-annotation
 *  - Listen to parse:* panel and region lifecycle events
 *  - Dispatch parse:annotation-save and parse:annotation-delete
 *  - Read existing annotations from window.PARSE.annotations
 */
(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.annotations = window.PARSE.annotations || {};

  const P = window.PARSE;

  const CONTAINER_ID = 'parse-annotation';
  const STYLE_ID = 'parse-annotation-panel-styles';
  const MATCH_EPSILON = 0.0005;

  const state = {
    initialized: false,
    listenersBound: false,

    containerEl: null,
    rootEl: null,
    titleEl: null,
    regionEl: null,
    warningEl: null,
    listEl: null,
    emptyEl: null,
    existingHeadingEl: null,

    ipaInputEl: null,
    orthoInputEl: null,
    conceptInputEl: null,
    saveBtnEl: null,
    clearBtnEl: null,

    currentSpeaker: null,
    currentConceptId: null,
    currentSourceWav: null,
    defaultConceptLabel: '',
    currentPlaybackSec: null,
    currentRegion: {
      startSec: null,
      endSec: null,
    },
    currentAnnotations: [],
    isOpen: false,
  };

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.parse-annotation-panel{margin-top:12px;padding:12px;border:1px solid #d6e0ea;border-radius:12px;background:linear-gradient(180deg,#fff,#f6f9fc);box-shadow:0 4px 14px rgba(15,23,42,0.05);}',
      '.parse-annotation-panel.hidden{display:none !important;}',
      '.parse-annotation-panel__header{display:flex;flex-direction:column;gap:4px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e1e8f0;}',
      '.parse-annotation-panel__title{font-size:15px;font-weight:700;color:#1f2937;line-height:1.3;}',
      '.parse-annotation-panel__region{font-size:13px;color:#475569;font-variant-numeric:tabular-nums;}',
      '.parse-annotation-panel__fields{display:flex;flex-direction:column;gap:8px;}',
      '.parse-annotation-panel__field{display:grid;grid-template-columns:86px minmax(0,1fr);align-items:center;gap:10px;}',
      '.parse-annotation-panel__field-label{font-size:13px;font-weight:600;color:#334155;}',
      '.parse-annotation-panel__input{width:100%;padding:8px 10px;border:1px solid #c9d5e3;border-radius:8px;background:#fff;color:#0f172a;font:inherit;}',
      '.parse-annotation-panel__input:focus{outline:none;border-color:#2f6edb;box-shadow:0 0 0 3px rgba(47,110,219,0.16);}',
      '.parse-annotation-panel__actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}',
      '.parse-annotation-panel__btn{border:1px solid transparent;border-radius:8px;padding:8px 12px;font:inherit;cursor:pointer;}',
      '.parse-annotation-panel__btn:disabled{opacity:0.6;cursor:not-allowed;}',
      '.parse-annotation-panel__btn--primary{background:#215ebf;border-color:#1f56ac;color:#fff;font-weight:600;}',
      '.parse-annotation-panel__btn--primary:hover{background:#1d53aa;}',
      '.parse-annotation-panel__btn--ghost{background:#fff;border-color:#c8d4e1;color:#1f2937;}',
      '.parse-annotation-panel__btn--ghost:hover{background:#f8fafc;}',
      '.parse-annotation-panel__warning{min-height:1.25em;margin-top:8px;font-size:12px;color:#9a3412;}',
      '.parse-annotation-panel__existing{margin-top:12px;padding-top:10px;border-top:1px solid #e1e8f0;}',
      '.parse-annotation-panel__existing-heading{font-size:13px;font-weight:600;color:#334155;margin-bottom:8px;}',
      '.parse-annotation-panel__empty{font-size:12px;color:#64748b;}',
      '.parse-annotation-panel__list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px;}',
      '.parse-annotation-panel__item{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 8px;border:1px solid #d8e2ee;border-radius:8px;background:#fff;}',
      '.parse-annotation-panel__item.is-active{border-color:#6aa2f0;box-shadow:inset 3px 0 0 #3b82f6;background:#f4f9ff;}',
      '.parse-annotation-panel__item-text{font-size:12px;color:#1e293b;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}',
      '.parse-annotation-panel__delete{background:#fff1f2;border:1px solid #fecdd3;color:#9f1239;border-radius:6px;padding:5px 8px;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap;}',
      '.parse-annotation-panel__delete:hover{background:#ffe4e6;}',
      '@media (max-width: 720px){',
      '  .parse-annotation-panel{padding:10px;}',
      '  .parse-annotation-panel__field{grid-template-columns:1fr;gap:4px;}',
      '  .parse-annotation-panel__actions{flex-direction:column;align-items:stretch;}',
      '  .parse-annotation-panel__btn{width:100%;}',
      '  .parse-annotation-panel__item{flex-direction:column;align-items:flex-start;}',
      '}'
    ].join('');

    document.head.appendChild(style);
  }

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function toNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function approxEqual(a, b, epsilon) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) {
      return false;
    }
    return Math.abs(a - b) <= (epsilon || MATCH_EPSILON);
  }

  function hasRegion() {
    return Number.isFinite(state.currentRegion.startSec) && Number.isFinite(state.currentRegion.endSec);
  }

  function normalizeConceptId(value) {
    if (value == null) return '';
    let text = String(value).trim();
    if (!text) return '';

    if (text.charAt(0) === '#') {
      text = text.slice(1).trim();
    }

    const colonIdx = text.indexOf(':');
    if (colonIdx !== -1) {
      text = text.slice(0, colonIdx).trim();
    }

    return text;
  }

  function conceptIdsEqual(a, b) {
    const left = normalizeConceptId(a);
    const right = normalizeConceptId(b);

    if (!left || !right) {
      return String(a || '').trim() === String(b || '').trim();
    }

    if (left === right) return true;

    const leftNum = Number(left);
    const rightNum = Number(right);
    if (Number.isFinite(leftNum) && Number.isFinite(rightNum)) {
      return leftNum === rightNum;
    }

    return false;
  }

  function formatSecValue(sec) {
    if (!Number.isFinite(sec)) return '-';

    const rounded = Math.round(sec * 1000) / 1000;
    let text = rounded.toFixed(3).replace(/\.0+$/, '.0').replace(/(\.\d*[1-9])0+$/, '$1');
    if (text.indexOf('.') === -1) {
      text += '.0';
    }
    return text;
  }

  function formatSecWithSuffix(sec) {
    return formatSecValue(sec) + 's';
  }

  function formatDurationSec(startSec, endSec) {
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec)) {
      return '-';
    }
    return formatSecWithSuffix(Math.max(0, endSec - startSec));
  }

  function getSuggestionConceptLabel(conceptId) {
    const cid = conceptId == null ? '' : String(conceptId);
    if (!cid || !P || !P.suggestions || !P.suggestions.suggestions) {
      return '';
    }

    const byKey = P.suggestions.suggestions[cid];
    if (byKey && byKey.concept_en) {
      return String(byKey.concept_en);
    }

    const normalizedTarget = normalizeConceptId(cid);
    if (!normalizedTarget) {
      return '';
    }

    const keys = Object.keys(P.suggestions.suggestions);
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (conceptIdsEqual(key, normalizedTarget)) {
        const entry = P.suggestions.suggestions[key];
        if (entry && entry.concept_en) {
          return String(entry.concept_en);
        }
      }
    }

    return '';
  }

  function getDefaultConceptLabel() {
    if (!state.currentConceptId) return '';

    const conceptIdText = String(state.currentConceptId);
    if (conceptIdText.indexOf(':') !== -1) {
      return conceptIdText;
    }

    const label = getSuggestionConceptLabel(conceptIdText);
    if (!label) {
      return conceptIdText;
    }

    return conceptIdText + ':' + label;
  }

  function intervalTextAt(intervals, startSec, endSec, fallbackIndex) {
    if (!Array.isArray(intervals) || intervals.length === 0) {
      return '';
    }

    for (let i = 0; i < intervals.length; i += 1) {
      const interval = intervals[i] || {};
      const start = toNumber(interval.start != null ? interval.start : interval.xmin);
      const end = toNumber(interval.end != null ? interval.end : interval.xmax);
      if (approxEqual(start, startSec, MATCH_EPSILON) && approxEqual(end, endSec, MATCH_EPSILON)) {
        return interval.text != null ? String(interval.text) : '';
      }
    }

    if (Number.isInteger(fallbackIndex) && fallbackIndex >= 0 && fallbackIndex < intervals.length) {
      const fallback = intervals[fallbackIndex] || {};
      return fallback.text != null ? String(fallback.text) : '';
    }

    return '';
  }

  function normalizeFlatAnnotation(rawAnnotation, defaults) {
    const raw = rawAnnotation || {};
    const startSec = toNumber(
      raw.startSec != null ? raw.startSec :
      raw.start_sec != null ? raw.start_sec :
      raw.start != null ? raw.start :
      raw.xmin
    );
    const endSec = toNumber(
      raw.endSec != null ? raw.endSec :
      raw.end_sec != null ? raw.end_sec :
      raw.end != null ? raw.end :
      raw.xmax
    );

    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec < startSec) {
      return null;
    }

    const concept = raw.concept != null
      ? String(raw.concept)
      : raw.concept_text != null
        ? String(raw.concept_text)
        : raw.conceptLabel != null
          ? String(raw.conceptLabel)
          : raw.concept_id != null
            ? String(raw.concept_id)
            : raw.conceptId != null
              ? String(raw.conceptId)
              : '';

    const conceptId = raw.conceptId != null
      ? String(raw.conceptId)
      : raw.concept_id != null
        ? String(raw.concept_id)
        : normalizeConceptId(concept);

    return {
      speaker: raw.speaker != null ? String(raw.speaker) : (defaults && defaults.speaker) || null,
      conceptId: conceptId,
      concept: concept,
      startSec: startSec,
      endSec: endSec,
      ipa: raw.ipa != null ? String(raw.ipa) : raw.ipa_text != null ? String(raw.ipa_text) : '',
      ortho: raw.ortho != null ? String(raw.ortho) : raw.ortho_text != null ? String(raw.ortho_text) : '',
      sourceWav: raw.sourceWav != null
        ? String(raw.sourceWav)
        : raw.source_wav != null
          ? String(raw.source_wav)
          : (defaults && defaults.sourceWav) || null,
    };
  }

  function extractAnnotationsFromTierFile(speakerData, speaker) {
    const tiers = speakerData && speakerData.tiers;
    if (!tiers || typeof tiers !== 'object') {
      return [];
    }

    const conceptIntervals = tiers.concept && Array.isArray(tiers.concept.intervals)
      ? tiers.concept.intervals
      : [];
    const ipaIntervals = tiers.ipa && Array.isArray(tiers.ipa.intervals)
      ? tiers.ipa.intervals
      : [];
    const orthoIntervals = tiers.ortho && Array.isArray(tiers.ortho.intervals)
      ? tiers.ortho.intervals
      : [];

    const sourceWav = speakerData.source_audio != null ? String(speakerData.source_audio) : null;
    const out = [];

    for (let i = 0; i < conceptIntervals.length; i += 1) {
      const conceptInterval = conceptIntervals[i] || {};
      const startSec = toNumber(conceptInterval.start != null ? conceptInterval.start : conceptInterval.xmin);
      const endSec = toNumber(conceptInterval.end != null ? conceptInterval.end : conceptInterval.xmax);
      if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec < startSec) {
        continue;
      }

      const conceptText = conceptInterval.text != null ? String(conceptInterval.text) : '';
      const ipaText = intervalTextAt(ipaIntervals, startSec, endSec, i);
      const orthoText = intervalTextAt(orthoIntervals, startSec, endSec, i);

      out.push({
        speaker: speaker,
        conceptId: normalizeConceptId(conceptText),
        concept: conceptText,
        startSec: startSec,
        endSec: endSec,
        ipa: ipaText,
        ortho: orthoText,
        sourceWav: sourceWav,
      });
    }

    return out;
  }

  function getSpeakerAnnotations(speaker) {
    if (!speaker || !P.annotations || typeof P.annotations !== 'object') {
      return [];
    }

    const speakerData = P.annotations[speaker];
    if (!speakerData) {
      return [];
    }

    if (Array.isArray(speakerData)) {
      return speakerData
        .map(function (entry) {
          return normalizeFlatAnnotation(entry, { speaker: speaker, sourceWav: null });
        })
        .filter(Boolean);
    }

    if (Array.isArray(speakerData.annotations)) {
      return speakerData.annotations
        .map(function (entry) {
          return normalizeFlatAnnotation(entry, {
            speaker: speaker,
            sourceWav: speakerData.source_audio != null ? String(speakerData.source_audio) : null,
          });
        })
        .filter(Boolean);
    }

    if (speakerData.tiers && typeof speakerData.tiers === 'object') {
      return extractAnnotationsFromTierFile(speakerData, speaker);
    }

    return [];
  }

  function getAnnotationsForCurrentConcept() {
    if (!state.currentSpeaker || !state.currentConceptId) {
      return [];
    }

    const currentConceptId = String(state.currentConceptId);

    return getSpeakerAnnotations(state.currentSpeaker)
      .filter(function (annotation) {
        if (!annotation) return false;

        const annotationConcept = annotation.conceptId || annotation.concept || '';
        return conceptIdsEqual(annotationConcept, currentConceptId);
      })
      .sort(function (a, b) {
        return (a.startSec - b.startSec) || (a.endSec - b.endSec);
      });
  }

  function chooseReferenceAnnotation(annotations) {
    if (!Array.isArray(annotations) || annotations.length === 0) {
      return null;
    }

    if (hasRegion()) {
      for (let i = 0; i < annotations.length; i += 1) {
        const item = annotations[i];
        if (
          approxEqual(item.startSec, state.currentRegion.startSec, MATCH_EPSILON) &&
          approxEqual(item.endSec, state.currentRegion.endSec, MATCH_EPSILON)
        ) {
          return item;
        }
      }
    }

    return annotations[0] || null;
  }

  function setWarning(message) {
    if (!state.warningEl) return;
    state.warningEl.textContent = message || '';
  }

  function clearWarning() {
    setWarning('');
  }

  function setPanelVisibility(visible) {
    if (!state.rootEl) return;
    state.rootEl.classList.toggle('hidden', !visible);
    state.rootEl.setAttribute('aria-hidden', visible ? 'false' : 'true');
  }

  function updateHeader() {
    if (!state.titleEl) return;

    if (!state.currentSpeaker || !state.currentConceptId) {
      state.titleEl.textContent = 'Annotation';
      return;
    }

    state.titleEl.textContent =
      'Annotation - ' +
      String(state.currentSpeaker) +
      ' / concept: ' +
      (state.defaultConceptLabel || String(state.currentConceptId));
  }

  function updateRegionDisplay() {
    if (!state.regionEl) return;

    if (!hasRegion()) {
      state.regionEl.textContent = 'Region: not selected';
      return;
    }

    const startSec = state.currentRegion.startSec;
    const endSec = state.currentRegion.endSec;
    state.regionEl.textContent =
      'Region: ' +
      formatSecWithSuffix(startSec) +
      ' - ' +
      formatSecWithSuffix(endSec) +
      ' (' +
      formatDurationSec(startSec, endSec) +
      ')';
  }

  function updatePlaybackHighlight() {
    if (!state.listEl) return;

    const items = state.listEl.querySelectorAll('[data-role="annotation-item"]');
    const timeSec = state.currentPlaybackSec;

    items.forEach(function (itemEl) {
      const startSec = Number(itemEl.getAttribute('data-start-sec'));
      const endSec = Number(itemEl.getAttribute('data-end-sec'));
      const isActive = Number.isFinite(timeSec) && Number.isFinite(startSec) && Number.isFinite(endSec) && timeSec >= startSec && timeSec <= endSec;
      itemEl.classList.toggle('is-active', isActive);
    });
  }

  function renderExistingList() {
    if (!state.listEl || !state.emptyEl || !state.existingHeadingEl) {
      return;
    }

    state.listEl.innerHTML = '';

    const hasConcept = !!state.currentConceptId;
    state.existingHeadingEl.textContent = hasConcept
      ? 'Existing annotations for this concept:'
      : 'Existing annotations:';

    if (!state.currentAnnotations || state.currentAnnotations.length === 0) {
      state.emptyEl.hidden = false;
      state.emptyEl.textContent = hasConcept
        ? 'No annotations for this concept yet.'
        : 'No annotations yet.';
      return;
    }

    state.emptyEl.hidden = true;

    const frag = document.createDocumentFragment();

    state.currentAnnotations.forEach(function (annotation) {
      const itemEl = document.createElement('li');
      itemEl.className = 'parse-annotation-panel__item';
      itemEl.setAttribute('data-role', 'annotation-item');
      itemEl.setAttribute('data-start-sec', String(annotation.startSec));
      itemEl.setAttribute('data-end-sec', String(annotation.endSec));

      const textEl = document.createElement('span');
      textEl.className = 'parse-annotation-panel__item-text';
      const ipa = annotation.ipa != null ? String(annotation.ipa) : '';
      const ortho = annotation.ortho != null ? String(annotation.ortho) : '';
      textEl.textContent =
        formatSecValue(annotation.startSec) +
        '-' +
        formatSecValue(annotation.endSec) +
        ': "' + ipa + '" / "' + ortho + '"';

      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'parse-annotation-panel__delete';
      deleteBtn.setAttribute('data-action', 'delete-annotation');
      deleteBtn.setAttribute('data-start-sec', String(annotation.startSec));
      deleteBtn.textContent = 'Delete';

      itemEl.appendChild(textEl);
      itemEl.appendChild(deleteBtn);
      frag.appendChild(itemEl);
    });

    state.listEl.appendChild(frag);
    updatePlaybackHighlight();
  }

  function populateFieldsFromExisting() {
    if (!state.ipaInputEl || !state.orthoInputEl || !state.conceptInputEl) {
      return;
    }

    const reference = chooseReferenceAnnotation(state.currentAnnotations);
    if (!reference) {
      state.ipaInputEl.value = '';
      state.orthoInputEl.value = '';
      state.conceptInputEl.value = state.defaultConceptLabel || '';
      return;
    }

    state.ipaInputEl.value = reference.ipa || '';
    state.orthoInputEl.value = reference.ortho || '';
    state.conceptInputEl.value = reference.concept || state.defaultConceptLabel || '';
  }

  function refreshFromStore(options) {
    const opts = options || {};
    state.currentAnnotations = getAnnotationsForCurrentConcept();
    renderExistingList();

    if (opts.populateFields) {
      populateFieldsFromExisting();
    }
  }

  function clearInputs() {
    if (state.ipaInputEl) state.ipaInputEl.value = '';
    if (state.orthoInputEl) state.orthoInputEl.value = '';
    if (state.conceptInputEl) state.conceptInputEl.value = '';
    clearWarning();
  }

  function resetContext() {
    state.currentSpeaker = null;
    state.currentConceptId = null;
    state.currentSourceWav = null;
    state.defaultConceptLabel = '';
    state.currentPlaybackSec = null;
    state.currentAnnotations = [];
    state.currentRegion.startSec = null;
    state.currentRegion.endSec = null;
  }

  function resolveContainer(containerEl) {
    if (containerEl && containerEl.nodeType === 1) {
      if (containerEl.id === CONTAINER_ID) {
        return containerEl;
      }

      const scoped = containerEl.querySelector('#' + CONTAINER_ID);
      if (scoped) {
        return scoped;
      }
    }

    const existing = document.getElementById(CONTAINER_ID);
    if (existing) {
      return existing;
    }

    const created = document.createElement('div');
    created.id = CONTAINER_ID;

    const panelEl = document.getElementById('parse-panel') || document.getElementById('se-panel');
    if (panelEl) {
      const controlsEl = panelEl.querySelector('#parse-controls') || panelEl.querySelector('#se-controls');
      if (controlsEl && controlsEl.parentNode === panelEl) {
        panelEl.insertBefore(created, controlsEl);
      } else {
        panelEl.appendChild(created);
      }
    } else {
      document.body.appendChild(created);
    }

    return created;
  }

  function buildUiShell() {
    if (!state.containerEl) {
      return;
    }

    if (state.rootEl && state.rootEl.parentNode !== state.containerEl) {
      state.containerEl.appendChild(state.rootEl);
      return;
    }

    if (state.rootEl) {
      return;
    }

    const rootEl = document.createElement('section');
    rootEl.className = 'parse-annotation-panel hidden';
    rootEl.setAttribute('aria-hidden', 'true');

    const headerEl = document.createElement('div');
    headerEl.className = 'parse-annotation-panel__header';

    const titleEl = document.createElement('div');
    titleEl.className = 'parse-annotation-panel__title';
    titleEl.textContent = 'Annotation';

    const regionEl = document.createElement('div');
    regionEl.className = 'parse-annotation-panel__region';
    regionEl.textContent = 'Region: not selected';

    headerEl.appendChild(titleEl);
    headerEl.appendChild(regionEl);

    const fieldsEl = document.createElement('div');
    fieldsEl.className = 'parse-annotation-panel__fields';

    const ipaField = createInputRow('IPA', 'parse-annotation-panel__ipa', { dir: 'ltr' });
    const orthoField = createInputRow('Ortho', 'parse-annotation-panel__ortho', { dir: 'rtl' });
    const conceptField = createInputRow('Concept', 'parse-annotation-panel__concept', { dir: 'ltr' });

    fieldsEl.appendChild(ipaField.rowEl);
    fieldsEl.appendChild(orthoField.rowEl);
    fieldsEl.appendChild(conceptField.rowEl);

    const actionsEl = document.createElement('div');
    actionsEl.className = 'parse-annotation-panel__actions';

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'parse-annotation-panel__btn parse-annotation-panel__btn--primary';
    saveBtn.textContent = 'Save Annotation';

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'parse-annotation-panel__btn parse-annotation-panel__btn--ghost';
    clearBtn.textContent = 'Clear';

    actionsEl.appendChild(saveBtn);
    actionsEl.appendChild(clearBtn);

    const warningEl = document.createElement('div');
    warningEl.className = 'parse-annotation-panel__warning';
    warningEl.setAttribute('aria-live', 'polite');

    const existingEl = document.createElement('div');
    existingEl.className = 'parse-annotation-panel__existing';

    const existingHeadingEl = document.createElement('div');
    existingHeadingEl.className = 'parse-annotation-panel__existing-heading';
    existingHeadingEl.textContent = 'Existing annotations for this concept:';

    const listEl = document.createElement('ul');
    listEl.className = 'parse-annotation-panel__list';

    const emptyEl = document.createElement('div');
    emptyEl.className = 'parse-annotation-panel__empty';
    emptyEl.textContent = 'No annotations for this concept yet.';

    existingEl.appendChild(existingHeadingEl);
    existingEl.appendChild(listEl);
    existingEl.appendChild(emptyEl);

    rootEl.appendChild(headerEl);
    rootEl.appendChild(fieldsEl);
    rootEl.appendChild(actionsEl);
    rootEl.appendChild(warningEl);
    rootEl.appendChild(existingEl);

    state.containerEl.appendChild(rootEl);

    state.rootEl = rootEl;
    state.titleEl = titleEl;
    state.regionEl = regionEl;
    state.warningEl = warningEl;
    state.listEl = listEl;
    state.emptyEl = emptyEl;
    state.existingHeadingEl = existingHeadingEl;

    state.ipaInputEl = ipaField.inputEl;
    state.orthoInputEl = orthoField.inputEl;
    state.conceptInputEl = conceptField.inputEl;
    state.saveBtnEl = saveBtn;
    state.clearBtnEl = clearBtn;

    saveBtn.addEventListener('click', onSaveClick);
    clearBtn.addEventListener('click', onClearClick);
    listEl.addEventListener('click', onListClick);
  }

  function createInputRow(labelText, inputClassName, attrs) {
    const rowEl = document.createElement('label');
    rowEl.className = 'parse-annotation-panel__field';

    const labelEl = document.createElement('span');
    labelEl.className = 'parse-annotation-panel__field-label';
    labelEl.textContent = labelText + ':';

    const inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'parse-annotation-panel__input ' + inputClassName;
    if (attrs && attrs.dir) {
      inputEl.setAttribute('dir', attrs.dir);
    }

    rowEl.appendChild(labelEl);
    rowEl.appendChild(inputEl);

    return { rowEl: rowEl, inputEl: inputEl };
  }

  function onPanelOpen(event) {
    const detail = (event && event.detail) || {};

    state.currentSpeaker = detail.speaker != null ? String(detail.speaker) : null;
    state.currentConceptId = detail.conceptId != null ? String(detail.conceptId) : null;
    state.currentSourceWav = detail.sourceWav != null ? String(detail.sourceWav) : null;
    state.defaultConceptLabel = getDefaultConceptLabel();

    state.currentRegion.startSec = null;
    state.currentRegion.endSec = null;
    state.currentPlaybackSec = null;
    state.isOpen = true;

    buildUiShell();
    setPanelVisibility(true);
    updateHeader();
    updateRegionDisplay();
    clearWarning();

    refreshFromStore({ populateFields: true });

    if (state.ipaInputEl) {
      state.ipaInputEl.focus();
    }
  }

  function onPanelClose(event) {
    const detail = (event && event.detail) || {};
    if (detail.speaker && state.currentSpeaker && String(detail.speaker) !== state.currentSpeaker) {
      return;
    }

    state.isOpen = false;
    clearInputs();
    resetContext();
    updateHeader();
    updateRegionDisplay();
    renderExistingList();
    setPanelVisibility(false);
  }

  function onRegionUpdated(event) {
    if (!state.isOpen) return;

    const detail = (event && event.detail) || {};
    const startSec = toNumber(detail.startSec);
    const endSec = toNumber(detail.endSec);

    if (Number.isFinite(startSec) && Number.isFinite(endSec) && endSec >= startSec) {
      state.currentRegion.startSec = startSec;
      state.currentRegion.endSec = endSec;
    } else {
      state.currentRegion.startSec = null;
      state.currentRegion.endSec = null;
    }

    updateRegionDisplay();
  }

  function onPlaybackPosition(event) {
    if (!state.isOpen) return;

    const detail = (event && event.detail) || {};
    const timeSec = toNumber(detail.timeSec);
    state.currentPlaybackSec = Number.isFinite(timeSec) ? timeSec : null;
    updatePlaybackHighlight();
  }

  function onAnnotationsLoaded(event) {
    if (!state.isOpen || !state.currentSpeaker) return;

    const detail = (event && event.detail) || {};
    if (detail.speaker && String(detail.speaker) !== state.currentSpeaker) {
      return;
    }

    refreshFromStore({ populateFields: true });
  }

  function onSaveClick() {
    if (!state.isOpen || !state.currentSpeaker || !state.currentConceptId) {
      return;
    }

    clearWarning();

    if (!hasRegion()) {
      setWarning('Please select a region on the waveform first');
      return;
    }

    const ipa = state.ipaInputEl ? state.ipaInputEl.value : '';
    const ortho = state.orthoInputEl ? state.orthoInputEl.value : '';
    let concept = state.conceptInputEl ? state.conceptInputEl.value : '';

    if (!concept) {
      concept = state.defaultConceptLabel || String(state.currentConceptId);
      if (state.conceptInputEl) {
        state.conceptInputEl.value = concept;
      }
    }

    if (!String(ipa).trim() && !String(ortho).trim()) {
      setWarning('IPA and Ortho are both empty. Saving partial annotation.');
    }

    const payload = {
      speaker: state.currentSpeaker,
      conceptId: state.currentConceptId,
      startSec: state.currentRegion.startSec,
      endSec: state.currentRegion.endSec,
      ipa: ipa,
      ortho: ortho,
      concept: concept,
      sourceWav: state.currentSourceWav,
    };

    dispatch('parse:annotation-save', payload);

    const optimistic = normalizeFlatAnnotation(payload, {
      speaker: state.currentSpeaker,
      sourceWav: state.currentSourceWav,
    });

    if (optimistic) {
      let replaced = false;
      state.currentAnnotations = state.currentAnnotations.map(function (entry) {
        if (
          !replaced &&
          approxEqual(entry.startSec, optimistic.startSec, MATCH_EPSILON) &&
          approxEqual(entry.endSec, optimistic.endSec, MATCH_EPSILON)
        ) {
          replaced = true;
          return optimistic;
        }
        return entry;
      });

      if (!replaced) {
        state.currentAnnotations.push(optimistic);
      }

      state.currentAnnotations.sort(function (a, b) {
        return (a.startSec - b.startSec) || (a.endSec - b.endSec);
      });

      renderExistingList();
    }
  }

  function onClearClick() {
    clearInputs();
  }

  function onListClick(event) {
    const target = event && event.target;
    if (!target || !target.closest) return;

    const btn = target.closest('[data-action="delete-annotation"]');
    if (!btn || !state.currentSpeaker || !state.currentConceptId) {
      return;
    }

    const startSec = Number(btn.getAttribute('data-start-sec'));
    if (!Number.isFinite(startSec)) {
      return;
    }

    dispatch('parse:annotation-delete', {
      speaker: state.currentSpeaker,
      conceptId: state.currentConceptId,
      startSec: startSec,
    });

    state.currentAnnotations = state.currentAnnotations.filter(function (entry) {
      return !approxEqual(entry.startSec, startSec, MATCH_EPSILON);
    });
    renderExistingList();
  }

  function bindGlobalListeners() {
    if (state.listenersBound) return;

    document.addEventListener('parse:panel-open', onPanelOpen);
    document.addEventListener('parse:region-updated', onRegionUpdated);
    document.addEventListener('parse:playback-position', onPlaybackPosition);
    document.addEventListener('parse:annotations-loaded', onAnnotationsLoaded);
    document.addEventListener('parse:panel-close', onPanelClose);

    state.listenersBound = true;
  }

  function unbindGlobalListeners() {
    if (!state.listenersBound) return;

    document.removeEventListener('parse:panel-open', onPanelOpen);
    document.removeEventListener('parse:region-updated', onRegionUpdated);
    document.removeEventListener('parse:playback-position', onPlaybackPosition);
    document.removeEventListener('parse:annotations-loaded', onAnnotationsLoaded);
    document.removeEventListener('parse:panel-close', onPanelClose);

    state.listenersBound = false;
  }

  /**
   * init - render panel shell and bind event listeners.
   * @param {HTMLElement} containerEl
   */
  function init(containerEl) {
    ensureStyles();

    state.containerEl = resolveContainer(containerEl);
    buildUiShell();
    setPanelVisibility(false);
    bindGlobalListeners();

    state.initialized = true;

    return {
      refresh: refresh,
      getState: getState,
    };
  }

  function refresh() {
    if (!state.isOpen) return;
    refreshFromStore({ populateFields: false });
    updateRegionDisplay();
    updateHeader();
  }

  function getState() {
    return {
      isOpen: state.isOpen,
      speaker: state.currentSpeaker,
      conceptId: state.currentConceptId,
      regionStartSec: state.currentRegion.startSec,
      regionEndSec: state.currentRegion.endSec,
      annotationsForConcept: state.currentAnnotations.length,
    };
  }

  function destroy() {
    unbindGlobalListeners();

    if (state.saveBtnEl) {
      state.saveBtnEl.removeEventListener('click', onSaveClick);
    }
    if (state.clearBtnEl) {
      state.clearBtnEl.removeEventListener('click', onClearClick);
    }
    if (state.listEl) {
      state.listEl.removeEventListener('click', onListClick);
    }

    if (state.rootEl && state.rootEl.parentNode) {
      state.rootEl.parentNode.removeChild(state.rootEl);
    }

    state.initialized = false;
    state.containerEl = null;
    state.rootEl = null;
    state.titleEl = null;
    state.regionEl = null;
    state.warningEl = null;
    state.listEl = null;
    state.emptyEl = null;
    state.existingHeadingEl = null;
    state.ipaInputEl = null;
    state.orthoInputEl = null;
    state.conceptInputEl = null;
    state.saveBtnEl = null;
    state.clearBtnEl = null;
    resetContext();
    state.isOpen = false;
  }

  P.modules.annotationPanel = {
    init: init,
    destroy: destroy,
    refresh: refresh,
    getState: getState,
  };
})();
