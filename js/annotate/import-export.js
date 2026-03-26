(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.annotations = window.PARSE.annotations || {};

  const P = window.PARSE;

  const MODAL_ID = 'parse-io-modal';
  const CONTROLS_ID = 'parse-controls';
  const OPEN_BTN_ID = 'parse-btn-import-export';
  const STYLE_ID = 'parse-import-export-styles';
  const STATUS_CLEAR_DELAY_MS = 4600;

  const state = {
    initialized: false,
    listenersBound: false,
    isOpen: false,

    containerEl: null,
    dialogEl: null,
    openBtnEl: null,

    currentSpeakerEl: null,
    noSpeakersEl: null,
    statusEl: null,

    fileInputEl: null,
    targetSpeakerEl: null,
    modeReplaceEl: null,
    modeNewEl: null,
    newSpeakerRowEl: null,
    newSpeakerInputEl: null,
    importBtnEl: null,

    exportTextGridBtnEl: null,
    exportElanBtnEl: null,
    exportCsvBtnEl: null,
    exportSegmentsBtnEl: null,
    exportAllCsvBtnEl: null,
    exportAllSegmentsBtnEl: null,

    currentSpeaker: null,
    clearStatusTimer: null,

    onPanelOpenEvent: null,
    onIoCompleteEvent: null,
    onKeyDownEvent: null,
    onBackdropClickEvent: null,
  };

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function toText(value) {
    if (value == null) return '';
    return String(value).trim();
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ID;
    styleEl.textContent = [
      '.parse-io-modal{position:fixed;inset:0;z-index:4500;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(15,23,42,0.48);}',
      '.parse-io-modal.hidden{display:none !important;}',
      '.parse-io-modal__dialog{width:min(760px,100%);max-height:calc(100vh - 36px);overflow:auto;border:1px solid #d6e0ea;border-radius:14px;background:#fff;box-shadow:0 18px 45px rgba(15,23,42,0.24);}',
      '.parse-io-modal__head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 16px;border-bottom:1px solid #e4ebf3;}',
      '.parse-io-modal__title{font-size:16px;font-weight:700;color:#1f2937;line-height:1.2;}',
      '.parse-io-modal__close{border:1px solid #c9d5e3;border-radius:8px;background:#fff;color:#334155;padding:6px 10px;font:inherit;cursor:pointer;}',
      '.parse-io-modal__close:hover{background:#f8fafc;}',
      '.parse-io-modal__section{padding:14px 16px;border-top:1px solid #eef3f8;}',
      '.parse-io-modal__section:first-of-type{border-top:none;}',
      '.parse-io-modal__section-title{font-size:12px;font-weight:700;letter-spacing:0.03em;color:#3b4a5a;text-transform:uppercase;margin-bottom:10px;}',
      '.parse-io-modal__field{display:flex;flex-direction:column;gap:6px;margin-bottom:10px;}',
      '.parse-io-modal__label{font-size:13px;font-weight:600;color:#334155;}',
      '.parse-io-modal__input,.parse-io-modal__select{width:100%;box-sizing:border-box;border:1px solid #c9d5e3;border-radius:8px;padding:8px 10px;background:#fff;color:#0f172a;font:inherit;}',
      '.parse-io-modal__input:focus,.parse-io-modal__select:focus{outline:none;border-color:#2f6edb;box-shadow:0 0 0 3px rgba(47,110,219,0.16);}',
      '.parse-io-modal__radio-row{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:10px;}',
      '.parse-io-modal__radio{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#334155;}',
      '.parse-io-modal__hint{font-size:12px;color:#9a3412;}',
      '.parse-io-modal__actions{display:flex;flex-wrap:wrap;gap:8px;}',
      '.parse-io-modal__btn{border:1px solid transparent;border-radius:8px;background:#1f56ac;color:#fff;padding:8px 12px;font:inherit;font-weight:600;cursor:pointer;}',
      '.parse-io-modal__btn:hover{background:#1c4f9f;}',
      '.parse-io-modal__btn:disabled{opacity:0.56;cursor:not-allowed;}',
      '.parse-io-modal__btn--alt{background:#fff;color:#1f2937;border-color:#c9d5e3;font-weight:600;}',
      '.parse-io-modal__btn--alt:hover{background:#f8fafc;}',
      '.parse-io-modal__btn-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}',
      '.parse-io-modal__status{margin:0 16px 14px;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.4;}',
      '.parse-io-modal__status.hidden{display:none !important;}',
      '.parse-io-modal__status.is-info{background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;}',
      '.parse-io-modal__status.is-success{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;}',
      '.parse-io-modal__status.is-error{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;}',
      '.parse-io-modal__status.is-warn{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;}',
      '.parse-io-open-btn{border:1px solid #c9d5e3;border-radius:8px;background:#fff;color:#1f2937;padding:8px 12px;font:inherit;font-weight:600;cursor:pointer;}',
      '.parse-io-open-btn:hover{background:#f8fafc;}',
      '.parse-io-open-btn:focus{outline:none;border-color:#2f6edb;box-shadow:0 0 0 3px rgba(47,110,219,0.16);}',
      '@media (max-width: 720px){',
      '  .parse-io-modal{align-items:flex-start;padding:10px;}',
      '  .parse-io-modal__dialog{max-height:calc(100vh - 20px);}',
      '  .parse-io-modal__btn-grid{grid-template-columns:1fr;}',
      '  .parse-io-modal__actions{flex-direction:column;}',
      '  .parse-io-modal__btn{width:100%;}',
      '}'
    ].join('');

    document.head.appendChild(styleEl);
  }

  function resolveModalContainer(containerEl) {
    if (containerEl && containerEl.nodeType === 1) {
      if (containerEl.id === MODAL_ID) {
        return containerEl;
      }

      const scoped = containerEl.querySelector('#' + MODAL_ID);
      if (scoped) {
        return scoped;
      }
    }

    const existing = document.getElementById(MODAL_ID);
    if (existing) {
      return existing;
    }

    const created = document.createElement('div');
    created.id = MODAL_ID;
    document.body.appendChild(created);
    return created;
  }

  function ensureControlsContainer() {
    const existing = document.getElementById(CONTROLS_ID);
    if (existing) {
      return existing;
    }

    const created = document.createElement('div');
    created.id = CONTROLS_ID;

    const panelEl = document.getElementById('parse-panel') || document.getElementById('se-panel');
    if (panelEl) {
      const sideCol = panelEl.querySelector('.parse-col-side') || panelEl.querySelector('.se-col-side');
      if (sideCol) {
        sideCol.insertBefore(created, sideCol.firstChild || null);
      } else {
        panelEl.appendChild(created);
      }
    } else {
      document.body.appendChild(created);
    }

    return created;
  }

  function getSourceIndexSpeakerIds() {
    const sourceIndex = P.sourceIndex;
    if (!sourceIndex || typeof sourceIndex !== 'object') {
      return [];
    }

    if (!sourceIndex.speakers || typeof sourceIndex.speakers !== 'object') {
      return [];
    }

    return Object.keys(sourceIndex.speakers).sort();
  }

  function getAnnotationSpeakerIds() {
    if (!P.annotations || typeof P.annotations !== 'object') {
      return [];
    }
    return Object.keys(P.annotations).sort();
  }

  function getSpeakerIdsForDropdown() {
    const sourceSpeakers = getSourceIndexSpeakerIds();
    if (sourceSpeakers.length) {
      return sourceSpeakers;
    }
    return getAnnotationSpeakerIds();
  }

  function clearStatusTimer() {
    if (state.clearStatusTimer) {
      clearTimeout(state.clearStatusTimer);
      state.clearStatusTimer = null;
    }
  }

  function setStatus(kind, message, autoClear) {
    if (!state.statusEl) {
      return;
    }

    clearStatusTimer();

    const text = toText(message);
    if (!text) {
      state.statusEl.textContent = '';
      state.statusEl.className = 'parse-io-modal__status hidden';
      return;
    }

    const flavor = kind || 'info';
    state.statusEl.textContent = text;
    state.statusEl.className = 'parse-io-modal__status is-' + flavor;

    if (autoClear) {
      state.clearStatusTimer = setTimeout(function () {
        setStatus('', '', false);
      }, STATUS_CLEAR_DELAY_MS);
    }
  }

  function updateCurrentSpeakerHeading() {
    if (!state.currentSpeakerEl) {
      return;
    }

    const speaker = toText(state.currentSpeaker) || '-';
    state.currentSpeakerEl.textContent = 'EXPORT — Current speaker (' + speaker + ')';
  }

  function preferredSpeakerFromState(nextPreferred) {
    const candidates = [
      toText(nextPreferred),
      toText(state.currentSpeaker),
      state.targetSpeakerEl ? toText(state.targetSpeakerEl.value) : '',
    ];

    for (let i = 0; i < candidates.length; i += 1) {
      if (candidates[i]) {
        return candidates[i];
      }
    }

    return '';
  }

  function refreshSpeakerDropdown(nextPreferred) {
    if (!state.targetSpeakerEl) {
      return;
    }

    const speakers = getSpeakerIdsForDropdown();
    const wanted = preferredSpeakerFromState(nextPreferred);
    state.targetSpeakerEl.innerHTML = '';

    if (!speakers.length) {
      const emptyOption = document.createElement('option');
      emptyOption.value = '';
      emptyOption.textContent = 'No speakers available';
      state.targetSpeakerEl.appendChild(emptyOption);
      state.targetSpeakerEl.disabled = true;
      if (state.noSpeakersEl) {
        state.noSpeakersEl.classList.remove('hidden');
        state.noSpeakersEl.textContent = 'No speakers loaded yet — open a panel first';
      }
      return;
    }

    state.targetSpeakerEl.disabled = false;

    for (let i = 0; i < speakers.length; i += 1) {
      const speaker = speakers[i];
      const option = document.createElement('option');
      option.value = speaker;
      option.textContent = speaker;
      state.targetSpeakerEl.appendChild(option);
    }

    const selected = speakers.indexOf(wanted) !== -1 ? wanted : speakers[0];
    state.targetSpeakerEl.value = selected;

    if (state.noSpeakersEl) {
      state.noSpeakersEl.classList.add('hidden');
      state.noSpeakersEl.textContent = '';
    }
  }

  function selectedImportMode() {
    if (state.modeNewEl && state.modeNewEl.checked) {
      return 'new';
    }
    return 'replace';
  }

  function updateModeUi() {
    const mode = selectedImportMode();
    if (state.newSpeakerRowEl) {
      state.newSpeakerRowEl.classList.toggle('hidden', mode !== 'new');
    }
  }

  function resolveCurrentSpeakerForExport() {
    const current = toText(state.currentSpeaker);
    return current || '';
  }

  function updateActionStates() {
    const mode = selectedImportMode();
    const dropdownSpeakers = getSpeakerIdsForDropdown();
    const hasSpeakers = dropdownSpeakers.length > 0;
    const hasFile = !!(state.fileInputEl && state.fileInputEl.files && state.fileInputEl.files.length > 0);
    const targetSpeaker = state.targetSpeakerEl ? toText(state.targetSpeakerEl.value) : '';
    const newSpeakerName = state.newSpeakerInputEl ? toText(state.newSpeakerInputEl.value) : '';

    let canImport = hasFile && hasSpeakers && !!targetSpeaker;
    if (mode === 'new') {
      canImport = canImport && !!newSpeakerName;
    }

    if (state.importBtnEl) {
      state.importBtnEl.disabled = !canImport;
    }

    const currentSpeaker = resolveCurrentSpeakerForExport();
    const canExportCurrent = !!currentSpeaker;

    if (state.exportTextGridBtnEl) state.exportTextGridBtnEl.disabled = !canExportCurrent;
    if (state.exportElanBtnEl) state.exportElanBtnEl.disabled = !canExportCurrent;
    if (state.exportCsvBtnEl) state.exportCsvBtnEl.disabled = !canExportCurrent;
    if (state.exportSegmentsBtnEl) state.exportSegmentsBtnEl.disabled = !canExportCurrent;
  }

  function syncUi(nextPreferredSpeaker) {
    refreshSpeakerDropdown(nextPreferredSpeaker);
    updateCurrentSpeakerHeading();
    updateModeUi();
    updateActionStates();
  }

  function setOpenState(nextOpen) {
    if (!state.containerEl) {
      return;
    }

    state.isOpen = !!nextOpen;
    state.containerEl.classList.toggle('hidden', !state.isOpen);
    state.containerEl.setAttribute('aria-hidden', state.isOpen ? 'false' : 'true');

    if (state.openBtnEl) {
      state.openBtnEl.setAttribute('aria-expanded', state.isOpen ? 'true' : 'false');
    }
  }

  function open() {
    syncUi(state.currentSpeaker);
    setOpenState(true);
  }

  function close() {
    setOpenState(false);
  }

  function toggleOpen() {
    setOpenState(!state.isOpen);
  }

  function ensureTextGridFile(file) {
    if (!file || !file.name) {
      return false;
    }
    return /\.textgrid$/i.test(file.name);
  }

  function onImportClick() {
    const file = state.fileInputEl && state.fileInputEl.files ? state.fileInputEl.files[0] : null;
    const targetSpeaker = state.targetSpeakerEl ? toText(state.targetSpeakerEl.value) : '';
    const mode = selectedImportMode();
    const newSpeakerName = state.newSpeakerInputEl ? toText(state.newSpeakerInputEl.value) : '';

    if (!file) {
      setStatus('warn', 'Choose a .TextGrid file first.', true);
      return;
    }

    if (!ensureTextGridFile(file)) {
      setStatus('warn', 'Selected file must end with .TextGrid.', true);
      return;
    }

    if (!targetSpeaker) {
      setStatus('warn', 'No speakers loaded yet — open a panel first', true);
      return;
    }

    if (mode === 'new' && !newSpeakerName) {
      setStatus('warn', 'Enter a new speaker name before importing.', true);
      return;
    }

    const payload = {
      file: file,
      targetSpeaker: targetSpeaker,
      mode: mode,
    };

    if (mode === 'new') {
      payload.newSpeakerName = newSpeakerName;
    }

    setStatus('info', 'Importing TextGrid...', false);
    dispatch('parse:import-textgrid', payload);
  }

  function exportCurrent(eventName, label) {
    const speaker = resolveCurrentSpeakerForExport();
    if (!speaker) {
      setStatus('warn', 'Open a speaker panel before running current-speaker export.', true);
      return;
    }

    setStatus('info', 'Starting ' + label + ' export for ' + speaker + '...', false);
    dispatch(eventName, { speaker: speaker });
  }

  function exportAll(eventName, label) {
    const speakers = getAnnotationSpeakerIds();
    if (!speakers.length) {
      setStatus('warn', 'No annotations loaded for all-speaker export yet.', true);
      return;
    }

    setStatus('info', 'Starting ' + label + ' export for all speakers...', false);
    dispatch(eventName, { speaker: 'all' });
  }

  function renderModalShell(containerEl) {
    containerEl.classList.add('parse-io-modal', 'hidden');
    containerEl.setAttribute('aria-hidden', 'true');
    containerEl.innerHTML = '';

    const dialogEl = document.createElement('section');
    dialogEl.className = 'parse-io-modal__dialog';
    dialogEl.setAttribute('role', 'dialog');
    dialogEl.setAttribute('aria-modal', 'true');
    dialogEl.setAttribute('aria-labelledby', 'parse-io-modal-title');

    const headEl = document.createElement('div');
    headEl.className = 'parse-io-modal__head';

    const titleEl = document.createElement('div');
    titleEl.id = 'parse-io-modal-title';
    titleEl.className = 'parse-io-modal__title';
    titleEl.textContent = 'Import / Export';

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'parse-io-modal__close';
    closeBtn.textContent = '✕ Close';
    closeBtn.addEventListener('click', close);

    headEl.appendChild(titleEl);
    headEl.appendChild(closeBtn);

    const importSection = document.createElement('div');
    importSection.className = 'parse-io-modal__section';

    const importTitle = document.createElement('div');
    importTitle.className = 'parse-io-modal__section-title';
    importTitle.textContent = 'IMPORT';

    const fileField = document.createElement('div');
    fileField.className = 'parse-io-modal__field';
    const fileLabel = document.createElement('label');
    fileLabel.className = 'parse-io-modal__label';
    fileLabel.textContent = 'TextGrid file:';
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.className = 'parse-io-modal__input';
    fileInput.accept = '.TextGrid,.textgrid';
    fileInput.addEventListener('change', function () {
      updateActionStates();
    });
    fileField.appendChild(fileLabel);
    fileField.appendChild(fileInput);

    const speakerField = document.createElement('div');
    speakerField.className = 'parse-io-modal__field';
    const speakerLabel = document.createElement('label');
    speakerLabel.className = 'parse-io-modal__label';
    speakerLabel.textContent = 'Target speaker:';
    const speakerSelect = document.createElement('select');
    speakerSelect.className = 'parse-io-modal__select';
    speakerSelect.addEventListener('change', function () {
      updateActionStates();
    });
    const noSpeakersEl = document.createElement('div');
    noSpeakersEl.className = 'parse-io-modal__hint hidden';
    noSpeakersEl.textContent = 'No speakers loaded yet — open a panel first';
    speakerField.appendChild(speakerLabel);
    speakerField.appendChild(speakerSelect);
    speakerField.appendChild(noSpeakersEl);

    const modeLabel = document.createElement('div');
    modeLabel.className = 'parse-io-modal__label';
    modeLabel.textContent = 'Mode:';

    const modeRow = document.createElement('div');
    modeRow.className = 'parse-io-modal__radio-row';

    const replaceLabel = document.createElement('label');
    replaceLabel.className = 'parse-io-modal__radio';
    const replaceRadio = document.createElement('input');
    replaceRadio.type = 'radio';
    replaceRadio.name = 'parse-io-import-mode';
    replaceRadio.value = 'replace';
    replaceRadio.checked = true;
    replaceRadio.addEventListener('change', function () {
      updateModeUi();
      updateActionStates();
    });
    replaceLabel.appendChild(replaceRadio);
    replaceLabel.appendChild(document.createTextNode('Replace existing'));

    const newLabel = document.createElement('label');
    newLabel.className = 'parse-io-modal__radio';
    const newRadio = document.createElement('input');
    newRadio.type = 'radio';
    newRadio.name = 'parse-io-import-mode';
    newRadio.value = 'new';
    newRadio.addEventListener('change', function () {
      updateModeUi();
      updateActionStates();
    });
    newLabel.appendChild(newRadio);
    newLabel.appendChild(document.createTextNode('New speaker'));

    modeRow.appendChild(replaceLabel);
    modeRow.appendChild(newLabel);

    const newSpeakerRow = document.createElement('div');
    newSpeakerRow.className = 'parse-io-modal__field hidden';
    const newSpeakerLabel = document.createElement('label');
    newSpeakerLabel.className = 'parse-io-modal__label';
    newSpeakerLabel.textContent = 'New speaker name:';
    const newSpeakerInput = document.createElement('input');
    newSpeakerInput.type = 'text';
    newSpeakerInput.className = 'parse-io-modal__input';
    newSpeakerInput.placeholder = 'Enter speaker ID';
    newSpeakerInput.addEventListener('input', function () {
      updateActionStates();
    });
    newSpeakerRow.appendChild(newSpeakerLabel);
    newSpeakerRow.appendChild(newSpeakerInput);

    const importActions = document.createElement('div');
    importActions.className = 'parse-io-modal__actions';
    const importBtn = document.createElement('button');
    importBtn.type = 'button';
    importBtn.className = 'parse-io-modal__btn';
    importBtn.textContent = 'Import TextGrid';
    importBtn.addEventListener('click', onImportClick);
    importActions.appendChild(importBtn);

    importSection.appendChild(importTitle);
    importSection.appendChild(fileField);
    importSection.appendChild(speakerField);
    importSection.appendChild(modeLabel);
    importSection.appendChild(modeRow);
    importSection.appendChild(newSpeakerRow);
    importSection.appendChild(importActions);

    const exportCurrentSection = document.createElement('div');
    exportCurrentSection.className = 'parse-io-modal__section';
    const exportCurrentTitle = document.createElement('div');
    exportCurrentTitle.className = 'parse-io-modal__section-title';
    exportCurrentTitle.textContent = 'EXPORT — Current speaker (-)';

    const exportCurrentGrid = document.createElement('div');
    exportCurrentGrid.className = 'parse-io-modal__btn-grid';

    const exportTextGridBtn = document.createElement('button');
    exportTextGridBtn.type = 'button';
    exportTextGridBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportTextGridBtn.textContent = 'Export TextGrid';
    exportTextGridBtn.addEventListener('click', function () {
      exportCurrent('parse:export-textgrid', 'TextGrid');
    });

    const exportElanBtn = document.createElement('button');
    exportElanBtn.type = 'button';
    exportElanBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportElanBtn.textContent = 'Export ELAN';
    exportElanBtn.addEventListener('click', function () {
      exportCurrent('parse:export-elan', 'ELAN');
    });

    const exportCsvBtn = document.createElement('button');
    exportCsvBtn.type = 'button';
    exportCsvBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportCsvBtn.textContent = 'Export CSV';
    exportCsvBtn.addEventListener('click', function () {
      exportCurrent('parse:export-csv', 'CSV');
    });

    const exportSegmentsBtn = document.createElement('button');
    exportSegmentsBtn.type = 'button';
    exportSegmentsBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportSegmentsBtn.textContent = 'Export Segments';
    exportSegmentsBtn.addEventListener('click', function () {
      exportCurrent('parse:export-segments', 'segments');
    });

    exportCurrentGrid.appendChild(exportTextGridBtn);
    exportCurrentGrid.appendChild(exportElanBtn);
    exportCurrentGrid.appendChild(exportCsvBtn);
    exportCurrentGrid.appendChild(exportSegmentsBtn);

    exportCurrentSection.appendChild(exportCurrentTitle);
    exportCurrentSection.appendChild(exportCurrentGrid);

    const exportAllSection = document.createElement('div');
    exportAllSection.className = 'parse-io-modal__section';
    const exportAllTitle = document.createElement('div');
    exportAllTitle.className = 'parse-io-modal__section-title';
    exportAllTitle.textContent = 'EXPORT — All speakers';

    const exportAllGrid = document.createElement('div');
    exportAllGrid.className = 'parse-io-modal__btn-grid';

    const exportAllCsvBtn = document.createElement('button');
    exportAllCsvBtn.type = 'button';
    exportAllCsvBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportAllCsvBtn.textContent = 'Export All CSV';
    exportAllCsvBtn.addEventListener('click', function () {
      exportAll('parse:export-csv', 'CSV');
    });

    const exportAllSegmentsBtn = document.createElement('button');
    exportAllSegmentsBtn.type = 'button';
    exportAllSegmentsBtn.className = 'parse-io-modal__btn parse-io-modal__btn--alt';
    exportAllSegmentsBtn.textContent = 'Export All Segments';
    exportAllSegmentsBtn.addEventListener('click', function () {
      exportAll('parse:export-segments', 'segments');
    });

    exportAllGrid.appendChild(exportAllCsvBtn);
    exportAllGrid.appendChild(exportAllSegmentsBtn);
    exportAllSection.appendChild(exportAllTitle);
    exportAllSection.appendChild(exportAllGrid);

    const statusEl = document.createElement('div');
    statusEl.className = 'parse-io-modal__status hidden';
    statusEl.setAttribute('aria-live', 'polite');

    dialogEl.appendChild(headEl);
    dialogEl.appendChild(importSection);
    dialogEl.appendChild(exportCurrentSection);
    dialogEl.appendChild(exportAllSection);
    dialogEl.appendChild(statusEl);

    containerEl.appendChild(dialogEl);

    state.dialogEl = dialogEl;
    state.currentSpeakerEl = exportCurrentTitle;
    state.noSpeakersEl = noSpeakersEl;
    state.statusEl = statusEl;

    state.fileInputEl = fileInput;
    state.targetSpeakerEl = speakerSelect;
    state.modeReplaceEl = replaceRadio;
    state.modeNewEl = newRadio;
    state.newSpeakerRowEl = newSpeakerRow;
    state.newSpeakerInputEl = newSpeakerInput;
    state.importBtnEl = importBtn;

    state.exportTextGridBtnEl = exportTextGridBtn;
    state.exportElanBtnEl = exportElanBtn;
    state.exportCsvBtnEl = exportCsvBtn;
    state.exportSegmentsBtnEl = exportSegmentsBtn;
    state.exportAllCsvBtnEl = exportAllCsvBtn;
    state.exportAllSegmentsBtnEl = exportAllSegmentsBtn;

    if (state.onBackdropClickEvent && state.containerEl) {
      state.containerEl.removeEventListener('click', state.onBackdropClickEvent);
    }

    state.onBackdropClickEvent = function (event) {
      if (event.target === state.containerEl) {
        close();
      }
    };
    containerEl.addEventListener('click', state.onBackdropClickEvent);
  }

  function ensureOpenButton() {
    const controlsEl = ensureControlsContainer();
    let buttonEl = document.getElementById(OPEN_BTN_ID);

    if (!buttonEl) {
      buttonEl = document.createElement('button');
      buttonEl.id = OPEN_BTN_ID;
      buttonEl.type = 'button';
      buttonEl.className = 'parse-io-open-btn';
      buttonEl.textContent = 'Import/Export';
    }

    if (buttonEl.parentNode !== controlsEl) {
      controlsEl.appendChild(buttonEl);
    }

    buttonEl.onclick = function () {
      toggleOpen();
    };

    buttonEl.setAttribute('aria-haspopup', 'dialog');
    buttonEl.setAttribute('aria-controls', MODAL_ID);
    buttonEl.setAttribute('aria-expanded', state.isOpen ? 'true' : 'false');

    state.openBtnEl = buttonEl;
  }

  function buildIoCompleteMessage(detail) {
    const operation = toText(detail.operation);
    const format = toText(detail.format);
    const success = !!detail.success;
    const operationLabel = operation || 'operation';
    const formatLabel = format || 'io';

    if (success) {
      return operationLabel + ' ' + formatLabel + ' completed.';
    }
    return operationLabel + ' ' + formatLabel + ' failed.';
  }

  function onPanelOpen(event) {
    const detail = (event && event.detail) || {};
    state.currentSpeaker = toText(detail.speaker) || null;
    syncUi(state.currentSpeaker);
  }

  function onIoComplete(event) {
    const detail = (event && event.detail) || {};
    const message = toText(detail.message) || buildIoCompleteMessage(detail);
    setStatus(detail.success ? 'success' : 'error', message, true);
    syncUi(state.currentSpeaker);
  }

  function onKeyDown(event) {
    if (!state.isOpen) {
      return;
    }
    if (event.key === 'Escape') {
      close();
      event.preventDefault();
    }
  }

  function bindDocumentListeners() {
    if (state.listenersBound) {
      return;
    }

    state.onPanelOpenEvent = onPanelOpen;
    state.onIoCompleteEvent = onIoComplete;
    state.onKeyDownEvent = onKeyDown;

    document.addEventListener('parse:panel-open', state.onPanelOpenEvent);
    document.addEventListener('parse:io-complete', state.onIoCompleteEvent);
    document.addEventListener('keydown', state.onKeyDownEvent);

    state.listenersBound = true;
  }

  /**
   * Initialize the import/export modal and inject the launch button.
   * @param {HTMLElement} containerEl
   * @returns {{init: Function, open: Function, close: Function}}
   */
  function init(containerEl) {
    ensureStyles();

    const resolvedContainer = resolveModalContainer(containerEl);
    state.containerEl = resolvedContainer;

    renderModalShell(resolvedContainer);
    ensureOpenButton();
    bindDocumentListeners();

    state.initialized = true;
    state.currentSpeaker = state.currentSpeaker || null;

    syncUi(state.currentSpeaker);
    close();

    P.modules.importExport = {
      init: init,
      open: open,
      close: close,
    };

    return P.modules.importExport;
  }

  P.modules.importExport = {
    init: init,
  };
}());
