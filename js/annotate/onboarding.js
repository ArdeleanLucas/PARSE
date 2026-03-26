/**
 * onboarding.js - PARSE project setup wizard
 *
 * Responsibilities:
 *  - Multi-step modal overlay for creating a new project.json
 *  - Attaches to window.PARSE.modules.onboarding
 *  - Mount point: <div id="parse-onboarding">
 *  - Listens: parse:project-error (showOnboarding:true) → show()
 *  - Fires: parse:project-loaded after successful project creation
 */
(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const STYLE_ID = 'parse-onboarding-styles';
  const TOTAL_STEPS = 8;

  const COMMON_LANGS = [
    { code: 'sdh', name: 'Southern Kurdish' },
    { code: 'ckb', name: 'Central Kurdish' },
    { code: 'kmr', name: 'Northern Kurdish' },
    { code: 'ara', name: 'Arabic' },
    { code: 'pes', name: 'Persian' },
    { code: 'tur', name: 'Turkish' },
    { code: 'eng', name: 'English' },
    { code: 'deu', name: 'German' },
  ];

  const SCRIPTS = ['Arabic', 'Latin', 'Cyrillic', 'Mixed', 'Other'];

  const AI_DEFAULTS = {
    anthropic: 'claude-sonnet-4-6',
    openai: 'gpt-4o',
    ollama: 'llama3',
  };

  let containerEl = null;
  let currentStep = 1;
  let listenerBound = false;

  // Form state
  let state = {
    projectId: '',
    projectName: '',
    langCode: 'sdh',
    langName: 'Southern Kurdish',
    script: 'Arabic',
    contactLangs: [],
    speakers: [{ id: '', name: '' }],
    conceptMode: 'csv',       // 'csv' | 'manual'
    conceptCsvRaw: '',
    conceptCsvRows: [],        // parsed rows (array of arrays)
    conceptCsvHeaders: [],
    conceptIdCol: '',
    conceptLabelCol: '',
    conceptTotal: 0,
    aiEnabled: false,
    aiProvider: 'anthropic',
    aiModel: AI_DEFAULTS.anthropic,
    aiKeyEnv: 'PARSE_AI_API_KEY',
  };

  // ─── Styles ──────────────────────────────────────────────────────────────────

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `
      #parse-onboarding {
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        z-index: 10000;
        background: rgba(15, 23, 42, 0.6);
        display: flex; align-items: center; justify-content: center;
      }
      #parse-onboarding.hidden { display: none !important; }
      .ob-card {
        background: #fff;
        border-radius: 12px;
        padding: 32px;
        width: 580px;
        max-height: 85vh;
        overflow-y: auto;
        font-family: system-ui, -apple-system, sans-serif;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        color: #0f172a;
      }
      .ob-step-indicator {
        font-size: 12px; color: #64748b; margin-bottom: 4px; letter-spacing: 0.02em;
      }
      .ob-title {
        font-size: 1.25rem; font-weight: 700; margin: 0 0 20px 0; color: #0f172a;
      }
      .ob-field { margin-bottom: 16px; }
      .ob-label {
        display: block; font-size: 13px; font-weight: 500; color: #374151; margin-bottom: 4px;
      }
      .ob-input {
        width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px;
        font-size: 14px; box-sizing: border-box; font-family: inherit; color: #0f172a;
      }
      .ob-input:focus { outline: none; border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.15); }
      .ob-select {
        width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px;
        font-size: 14px; box-sizing: border-box; background: #fff; color: #0f172a;
      }
      .ob-hint { font-size: 12px; color: #64748b; margin-top: 4px; }
      .ob-error { font-size: 13px; color: #ef4444; margin-top: 6px; }
      .ob-lang-pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
      .ob-lang-pill {
        padding: 4px 10px; border: 1px solid #cbd5e1; border-radius: 20px;
        font-size: 12px; cursor: pointer; background: #f8fafc; color: #374151;
        transition: all 0.1s;
      }
      .ob-lang-pill:hover { border-color: #6366f1; color: #6366f1; }
      .ob-lang-pill.active { background: #6366f1; color: #fff; border-color: #6366f1; }
      .ob-speaker-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
      .ob-speaker-row .ob-input { flex: 1; }
      .ob-remove-btn {
        padding: 4px 10px; border: 1px solid #fca5a5; border-radius: 6px;
        background: #fff; color: #ef4444; cursor: pointer; font-size: 12px; white-space: nowrap;
      }
      .ob-add-btn {
        padding: 6px 12px; border: 1px dashed #6366f1; border-radius: 8px;
        background: #fff; color: #6366f1; cursor: pointer; font-size: 13px;
      }
      .ob-checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .ob-checkbox-row input[type=checkbox] { width: 16px; height: 16px; cursor: pointer; }
      .ob-csv-preview {
        margin-top: 10px; overflow-x: auto; font-size: 12px;
        border: 1px solid #e2e8f0; border-radius: 6px;
      }
      .ob-csv-preview table { border-collapse: collapse; width: 100%; }
      .ob-csv-preview th, .ob-csv-preview td {
        border: 1px solid #e2e8f0; padding: 4px 8px; text-align: left; white-space: nowrap;
      }
      .ob-csv-preview th { background: #f8fafc; font-weight: 600; }
      .ob-summary-pre {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
        padding: 12px; font-size: 12px; font-family: monospace; overflow-x: auto;
        white-space: pre; max-height: 260px; overflow-y: auto;
      }
      .ob-footer {
        display: flex; justify-content: space-between; align-items: center;
        margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0;
      }
      .ob-btn {
        padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 500;
        cursor: pointer; font-family: inherit; transition: all 0.1s;
      }
      .ob-btn-secondary {
        border: 1px solid #cbd5e1; background: #fff; color: #374151;
      }
      .ob-btn-secondary:hover { background: #f1f5f9; }
      .ob-btn-primary {
        border: 1px solid #6366f1; background: #6366f1; color: #fff;
      }
      .ob-btn-primary:hover { background: #4f46e5; border-color: #4f46e5; }
      .ob-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
      .ob-tab-row { display: flex; gap: 0; margin-bottom: 12px; }
      .ob-tab {
        padding: 6px 14px; border: 1px solid #cbd5e1; cursor: pointer;
        font-size: 13px; background: #f8fafc; color: #64748b;
      }
      .ob-tab:first-child { border-radius: 8px 0 0 8px; }
      .ob-tab:last-child { border-radius: 0 8px 8px 0; border-left: none; }
      .ob-tab.active { background: #6366f1; color: #fff; border-color: #6366f1; }
    `;
    document.head.appendChild(s);
  }

  // ─── Helpers ─────────────────────────────────────────────────────────────────

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'className') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else e.setAttribute(k, v);
    });
    if (children) [].concat(children).forEach(c => {
      if (typeof c === 'string') e.appendChild(document.createTextNode(c));
      else if (c) e.appendChild(c);
    });
    return e;
  }

  function parseCsv(text) {
    const lines = text.trim().split('\n').filter(l => l.trim());
    return lines.map(line => {
      const cells = [];
      let cur = '', inQ = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') { inQ = !inQ; }
        else if (ch === ',' && !inQ) { cells.push(cur.trim()); cur = ''; }
        else { cur += ch; }
      }
      cells.push(cur.trim());
      return cells;
    });
  }

  function buildProjectJson() {
    const speakers = {};
    state.speakers.forEach(sp => {
      if (sp.id) speakers[sp.id] = { source_files: [], video_files: [], has_csv_timestamps: false, notes: sp.name || '' };
    });
    return {
      parse_version: '1.0',
      project_id: state.projectId,
      project_name: state.projectName,
      language: {
        code: state.langCode,
        name: state.langName,
        script: state.script,
        contact_languages: state.contactLangs.slice(),
      },
      paths: {
        audio_original: 'audio/original',
        audio_working: 'audio/working',
        annotations: 'annotations',
        exports: 'exports',
        peaks: 'peaks',
        transcripts: 'transcripts',
      },
      concepts: {
        source: 'concepts.csv',
        id_column: state.conceptIdCol || 'concept_id',
        label_column: state.conceptLabelCol || 'english',
        total: state.conceptTotal,
      },
      speakers: speakers,
      ai: {
        enabled: state.aiEnabled,
        provider: state.aiEnabled ? state.aiProvider : null,
        model: state.aiEnabled ? state.aiModel : null,
        api_key_env: state.aiKeyEnv || 'PARSE_AI_API_KEY',
      },
      server: { port: 8766, host: '0.0.0.0' },
    };
  }

  // ─── Step renderers ───────────────────────────────────────────────────────────

  function renderStep1(body, errEl) {
    body.appendChild(el('div', { className: 'ob-field' }, [
      el('label', { className: 'ob-label', for: 'ob-proj-id' }, 'Project ID (slug, no spaces)'),
      (() => {
        const inp = document.createElement('input');
        inp.className = 'ob-input'; inp.id = 'ob-proj-id'; inp.type = 'text';
        inp.placeholder = 'sk-thesis-2026';
        inp.value = state.projectId;
        inp.addEventListener('input', () => { state.projectId = inp.value.replace(/\s+/g, '-').toLowerCase(); inp.value = state.projectId; });
        return inp;
      })(),
    ]));
    body.appendChild(el('div', { className: 'ob-field' }, [
      el('label', { className: 'ob-label', for: 'ob-proj-name' }, 'Project Name'),
      (() => {
        const inp = document.createElement('input');
        inp.className = 'ob-input'; inp.id = 'ob-proj-name'; inp.type = 'text';
        inp.placeholder = 'Southern Kurdish Thesis';
        inp.value = state.projectName;
        inp.addEventListener('input', () => { state.projectName = inp.value; });
        return inp;
      })(),
    ]));
    return () => {
      if (!state.projectId) { errEl.textContent = 'Project ID is required.'; return false; }
      if (!/^[a-z0-9-_]+$/.test(state.projectId)) { errEl.textContent = 'Project ID: lowercase letters, numbers, hyphens only.'; return false; }
      if (!state.projectName) { errEl.textContent = 'Project Name is required.'; return false; }
      return true;
    };
  }

  function renderStep2(body, errEl) {
    body.appendChild(el('div', { className: 'ob-hint' }, 'Quick-pick a language or enter a custom SIL 639-3 code:'));
    const pills = el('div', { className: 'ob-lang-pills' });
    COMMON_LANGS.forEach(lang => {
      const pill = el('div', { className: 'ob-lang-pill' + (state.langCode === lang.code ? ' active' : '') }, lang.name + ' (' + lang.code + ')');
      pill.addEventListener('click', () => {
        state.langCode = lang.code; state.langName = lang.name;
        codeInp.value = lang.code; nameInp.value = lang.name;
        pills.querySelectorAll('.ob-lang-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
      });
      pills.appendChild(pill);
    });
    body.appendChild(pills);
    const codeInp = document.createElement('input');
    codeInp.className = 'ob-input'; codeInp.style.cssText = 'margin-top:12px;';
    codeInp.placeholder = 'SIL 639-3 code (e.g. sdh)';
    codeInp.value = state.langCode;
    codeInp.addEventListener('input', () => { state.langCode = codeInp.value.toLowerCase().slice(0, 3); codeInp.value = state.langCode; });
    const nameInp = document.createElement('input');
    nameInp.className = 'ob-input'; nameInp.style.cssText = 'margin-top:8px;';
    nameInp.placeholder = 'Language name';
    nameInp.value = state.langName;
    nameInp.addEventListener('input', () => { state.langName = nameInp.value; });
    body.appendChild(codeInp);
    body.appendChild(nameInp);
    return () => {
      if (!state.langCode || state.langCode.length !== 3) { errEl.textContent = 'Language code must be exactly 3 letters.'; return false; }
      if (!state.langName) { errEl.textContent = 'Language name is required.'; return false; }
      return true;
    };
  }

  function renderStep3(body) {
    body.appendChild(el('div', { className: 'ob-field' }, [
      el('label', { className: 'ob-label' }, 'Writing script'),
      (() => {
        const sel = document.createElement('select');
        sel.className = 'ob-select';
        SCRIPTS.forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; if (s === state.script) o.selected = true; sel.appendChild(o); });
        sel.addEventListener('change', () => { state.script = sel.value; });
        return sel;
      })(),
    ]));
    return () => true;
  }

  function renderStep4(body) {
    body.appendChild(el('p', { className: 'ob-hint' }, 'Select languages that may have influenced the target language (optional):'));
    COMMON_LANGS.forEach(lang => {
      const checked = state.contactLangs.includes(lang.code);
      const row = el('div', { className: 'ob-checkbox-row' });
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.id = 'ob-contact-' + lang.code; cb.checked = checked;
      cb.addEventListener('change', () => {
        if (cb.checked) { if (!state.contactLangs.includes(lang.code)) state.contactLangs.push(lang.code); }
        else { state.contactLangs = state.contactLangs.filter(c => c !== lang.code); }
      });
      const lbl = el('label', { for: 'ob-contact-' + lang.code }, lang.name + ' (' + lang.code + ')');
      row.appendChild(cb); row.appendChild(lbl);
      body.appendChild(row);
    });
    return () => true;
  }

  function renderStep5(body, errEl) {
    if (!state.speakers.length) state.speakers = [{ id: '', name: '' }];
    const listEl = el('div');
    const renderRows = () => {
      listEl.innerHTML = '';
      state.speakers.forEach((sp, i) => {
        const row = el('div', { className: 'ob-speaker-row' });
        const idInp = document.createElement('input');
        idInp.className = 'ob-input'; idInp.placeholder = 'ID (e.g. Fail01)';
        idInp.value = sp.id;
        idInp.addEventListener('input', () => { state.speakers[i].id = idInp.value.replace(/\s+/g, ''); idInp.value = state.speakers[i].id; });
        const nameInp = document.createElement('input');
        nameInp.className = 'ob-input'; nameInp.placeholder = 'Display name (optional)';
        nameInp.value = sp.name;
        nameInp.addEventListener('input', () => { state.speakers[i].name = nameInp.value; });
        const rmBtn = el('button', { className: 'ob-remove-btn', type: 'button' }, '✕');
        rmBtn.addEventListener('click', () => { if (state.speakers.length > 1) { state.speakers.splice(i, 1); renderRows(); } });
        row.appendChild(idInp); row.appendChild(nameInp); row.appendChild(rmBtn);
        listEl.appendChild(row);
      });
    };
    renderRows();
    const addBtn = el('button', { className: 'ob-add-btn', type: 'button' }, '+ Add Speaker');
    addBtn.addEventListener('click', () => { state.speakers.push({ id: '', name: '' }); renderRows(); });
    body.appendChild(listEl);
    body.appendChild(addBtn);
    return () => {
      const valid = state.speakers.some(sp => sp.id.trim());
      if (!valid) { errEl.textContent = 'Add at least one speaker with an ID.'; return false; }
      const dups = state.speakers.map(sp => sp.id).filter((id, i, arr) => id && arr.indexOf(id) !== i);
      if (dups.length) { errEl.textContent = 'Duplicate speaker IDs: ' + dups.join(', '); return false; }
      return true;
    };
  }

  function renderStep6(body, errEl) {
    const tabs = el('div', { className: 'ob-tab-row' });
    const csvTab = el('div', { className: 'ob-tab' + (state.conceptMode === 'csv' ? ' active' : '') }, 'Paste / Upload CSV');
    const manualTab = el('div', { className: 'ob-tab' + (state.conceptMode === 'manual' ? ' active' : '') }, 'Enter count manually');
    tabs.appendChild(csvTab); tabs.appendChild(manualTab);
    body.appendChild(tabs);

    const csvPane = el('div');
    const manualPane = el('div');

    // CSV pane
    const textarea = document.createElement('textarea');
    textarea.className = 'ob-input'; textarea.rows = 5; textarea.placeholder = 'Paste CSV content here (first row = headers)';
    textarea.value = state.conceptCsvRaw;
    const previewDiv = el('div', { className: 'ob-csv-preview' });
    const colDiv = el('div', { style: 'display:flex; gap:8px; margin-top:10px;' });
    const idColSel = document.createElement('select'); idColSel.className = 'ob-select'; idColSel.style.flex = '1';
    const labelColSel = document.createElement('select'); labelColSel.className = 'ob-select'; labelColSel.style.flex = '1';
    const idColLabel = el('div', { style: 'flex:1' }, [el('div', { className: 'ob-label' }, 'ID column'), idColSel]);
    const labelColLabel = el('div', { style: 'flex:1' }, [el('div', { className: 'ob-label' }, 'Label column'), labelColSel]);
    colDiv.appendChild(idColLabel); colDiv.appendChild(labelColLabel);

    const refreshCsvPreview = () => {
      const rows = parseCsv(textarea.value);
      state.conceptCsvRows = rows; state.conceptCsvRaw = textarea.value;
      [idColSel, labelColSel].forEach(s => { s.innerHTML = ''; s.appendChild(document.createElement('option')); });
      previewDiv.innerHTML = '';
      if (rows.length < 2) return;
      const headers = rows[0];
      state.conceptCsvHeaders = headers;
      headers.forEach((h, i) => {
        const o1 = document.createElement('option'); o1.value = i; o1.textContent = h;
        const o2 = document.createElement('option'); o2.value = i; o2.textContent = h;
        if (h === state.conceptIdCol || i === 0) { o1.selected = true; state.conceptIdCol = h; }
        if (h === state.conceptLabelCol || i === 1) { o2.selected = true; state.conceptLabelCol = h; }
        idColSel.appendChild(o1); labelColSel.appendChild(o2);
      });
      state.conceptTotal = rows.length - 1;
      const tbl = document.createElement('table');
      const thead = document.createElement('thead');
      const hrow = document.createElement('tr');
      headers.forEach(h => { const th = document.createElement('th'); th.textContent = h; hrow.appendChild(th); });
      thead.appendChild(hrow); tbl.appendChild(thead);
      const tbody = document.createElement('tbody');
      rows.slice(1, 6).forEach(row => {
        const tr = document.createElement('tr');
        row.forEach(cell => { const td = document.createElement('td'); td.textContent = cell; tr.appendChild(td); });
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody); previewDiv.appendChild(tbl);
    };
    textarea.addEventListener('input', refreshCsvPreview);
    idColSel.addEventListener('change', () => { const h = state.conceptCsvHeaders[idColSel.value]; if (h) state.conceptIdCol = h; });
    labelColSel.addEventListener('change', () => { const h = state.conceptCsvHeaders[labelColSel.value]; if (h) state.conceptLabelCol = h; });
    if (state.conceptCsvRaw) refreshCsvPreview();
    csvPane.appendChild(textarea); csvPane.appendChild(colDiv); csvPane.appendChild(previewDiv);

    // Manual pane
    const countInp = document.createElement('input');
    countInp.className = 'ob-input'; countInp.type = 'number'; countInp.min = 1; countInp.placeholder = 'Number of concepts';
    countInp.value = state.conceptTotal || '';
    const idColInp = document.createElement('input');
    idColInp.className = 'ob-input'; idColInp.style.marginTop = '8px'; idColInp.placeholder = 'ID column name (e.g. concept_id)';
    idColInp.value = state.conceptIdCol;
    const lblColInp = document.createElement('input');
    lblColInp.className = 'ob-input'; lblColInp.style.marginTop = '8px'; lblColInp.placeholder = 'Label column name (e.g. english)';
    lblColInp.value = state.conceptLabelCol;
    countInp.addEventListener('input', () => { state.conceptTotal = parseInt(countInp.value) || 0; });
    idColInp.addEventListener('input', () => { state.conceptIdCol = idColInp.value; });
    lblColInp.addEventListener('input', () => { state.conceptLabelCol = lblColInp.value; });
    manualPane.appendChild(el('div', { className: 'ob-label' }, 'Total concepts'));
    manualPane.appendChild(countInp);
    manualPane.appendChild(el('div', { className: 'ob-label', style: 'margin-top:8px' }, 'ID column name'));
    manualPane.appendChild(idColInp);
    manualPane.appendChild(el('div', { className: 'ob-label', style: 'margin-top:8px' }, 'Label column name'));
    manualPane.appendChild(lblColInp);

    const showPane = () => {
      csvPane.style.display = state.conceptMode === 'csv' ? '' : 'none';
      manualPane.style.display = state.conceptMode === 'manual' ? '' : 'none';
    };
    csvTab.addEventListener('click', () => { state.conceptMode = 'csv'; csvTab.classList.add('active'); manualTab.classList.remove('active'); showPane(); });
    manualTab.addEventListener('click', () => { state.conceptMode = 'manual'; manualTab.classList.add('active'); csvTab.classList.remove('active'); showPane(); });
    body.appendChild(csvPane); body.appendChild(manualPane);
    showPane();

    return () => {
      if (state.conceptMode === 'csv') {
        if (state.conceptCsvRows.length < 2) { errEl.textContent = 'Paste a CSV with at least one data row.'; return false; }
        if (!state.conceptIdCol) { errEl.textContent = 'Select the ID column.'; return false; }
        if (!state.conceptLabelCol) { errEl.textContent = 'Select the label column.'; return false; }
      } else {
        if (!state.conceptTotal || state.conceptTotal < 1) { errEl.textContent = 'Enter the number of concepts.'; return false; }
        if (!state.conceptIdCol) { errEl.textContent = 'Enter the ID column name.'; return false; }
        if (!state.conceptLabelCol) { errEl.textContent = 'Enter the label column name.'; return false; }
      }
      return true;
    };
  }

  function renderStep7(body) {
    const row = el('div', { className: 'ob-checkbox-row' });
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.id = 'ob-ai-enable'; cb.checked = state.aiEnabled;
    const lbl = el('label', { for: 'ob-ai-enable' }, 'Enable AI features (optional)');
    row.appendChild(cb); row.appendChild(lbl);
    body.appendChild(row);

    const aiOptions = el('div', { style: state.aiEnabled ? '' : 'display:none' });
    cb.addEventListener('change', () => { state.aiEnabled = cb.checked; aiOptions.style.display = state.aiEnabled ? '' : 'none'; });

    const providerSel = document.createElement('select'); providerSel.className = 'ob-select';
    ['anthropic', 'openai', 'ollama'].forEach(p => {
      const o = document.createElement('option'); o.value = p; o.textContent = p.charAt(0).toUpperCase() + p.slice(1);
      if (p === state.aiProvider) o.selected = true;
      providerSel.appendChild(o);
    });
    const modelInp = document.createElement('input');
    modelInp.className = 'ob-input'; modelInp.style.marginTop = '8px';
    modelInp.value = state.aiModel || AI_DEFAULTS[state.aiProvider] || '';
    const keyEnvInp = document.createElement('input');
    keyEnvInp.className = 'ob-input'; keyEnvInp.style.marginTop = '8px';
    keyEnvInp.value = state.aiKeyEnv;
    providerSel.addEventListener('change', () => {
      state.aiProvider = providerSel.value;
      modelInp.value = AI_DEFAULTS[state.aiProvider] || '';
      state.aiModel = modelInp.value;
    });
    modelInp.addEventListener('input', () => { state.aiModel = modelInp.value; });
    keyEnvInp.addEventListener('input', () => { state.aiKeyEnv = keyEnvInp.value; });

    aiOptions.appendChild(el('div', { className: 'ob-label', style: 'margin-top:10px' }, 'Provider'));
    aiOptions.appendChild(providerSel);
    aiOptions.appendChild(el('div', { className: 'ob-label', style: 'margin-top:8px' }, 'Model'));
    aiOptions.appendChild(modelInp);
    aiOptions.appendChild(el('div', { className: 'ob-label', style: 'margin-top:8px' }, 'API key environment variable'));
    aiOptions.appendChild(keyEnvInp);
    aiOptions.appendChild(el('p', { className: 'ob-hint' }, 'The API key is read from the environment variable at server start. Set it before launching PARSE.'));
    body.appendChild(aiOptions);
    return () => true;
  }

  function renderStep8(body, errEl) {
    const proj = buildProjectJson();
    const pre = el('div', { className: 'ob-summary-pre' });
    pre.textContent = JSON.stringify(proj, null, 2);
    body.appendChild(pre);

    let saving = false;
    const saveErr = el('div', { className: 'ob-error' });
    body.appendChild(saveErr);

    return async () => {
      if (saving) return false;
      saving = true;
      const createBtn = containerEl.querySelector('.ob-btn-primary');
      if (createBtn) { createBtn.disabled = true; createBtn.textContent = 'Creating...'; }
      saveErr.textContent = '';
      try {
        const resp = await fetch('/api/project', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildProjectJson()),
        });
        if (!resp.ok) {
          const txt = await resp.text().catch(() => resp.statusText);
          throw new Error('Server returned ' + resp.status + ': ' + txt);
        }
        const proj = buildProjectJson();
        P.project = proj;
        emit('parse:project-loaded', {
          projectId: proj.project_id,
          projectName: proj.project_name,
          speakers: Object.keys(proj.speakers),
          language: { code: proj.language.code, name: proj.language.name },
        });
        hide();
        return true;
      } catch (err) {
        saveErr.textContent = 'Failed to create project: ' + (err.message || err);
        if (createBtn) { createBtn.disabled = false; createBtn.textContent = 'Create Project'; }
        saving = false;
        return false;
      }
    };
  }

  // ─── Render engine ────────────────────────────────────────────────────────────

  const STEP_TITLES = [
    'Name your project',
    'Target language',
    'Writing script',
    'Contact languages',
    'Speakers',
    'Concept list',
    'AI configuration',
    'Review & create',
  ];

  let validateFn = null;

  function render() {
    containerEl.innerHTML = '';
    const card = el('div', { className: 'ob-card' });

    const indicator = el('div', { className: 'ob-step-indicator' }, 'Step ' + currentStep + ' of ' + TOTAL_STEPS);
    const title = el('h2', { className: 'ob-title' }, STEP_TITLES[currentStep - 1]);
    const body = el('div');
    const errEl = el('div', { className: 'ob-error' });

    switch (currentStep) {
      case 1: validateFn = renderStep1(body, errEl); break;
      case 2: validateFn = renderStep2(body, errEl); break;
      case 3: validateFn = renderStep3(body); break;
      case 4: validateFn = renderStep4(body); break;
      case 5: validateFn = renderStep5(body, errEl); break;
      case 6: validateFn = renderStep6(body, errEl); break;
      case 7: validateFn = renderStep7(body); break;
      case 8: validateFn = renderStep8(body, errEl); break;
    }

    const footer = el('div', { className: 'ob-footer' });
    const prevBtn = el('button', { className: 'ob-btn ob-btn-secondary', type: 'button' }, currentStep === 1 ? 'Cancel' : '← Back');
    const nextBtn = el('button', { className: 'ob-btn ob-btn-primary', type: 'button' }, currentStep === TOTAL_STEPS ? 'Create Project' : 'Next →');

    prevBtn.addEventListener('click', () => {
      if (currentStep === 1) { hide(); } else { currentStep--; render(); }
    });
    nextBtn.addEventListener('click', async () => {
      errEl.textContent = '';
      const result = validateFn ? await validateFn() : true;
      if (result === false) return;
      if (currentStep < TOTAL_STEPS) { currentStep++; render(); }
    });

    footer.appendChild(prevBtn);
    footer.appendChild(nextBtn);

    card.appendChild(indicator);
    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(errEl);
    card.appendChild(footer);
    containerEl.appendChild(card);
  }

  // ─── Public API ───────────────────────────────────────────────────────────────

  function init(mountEl) {
    containerEl = mountEl || document.getElementById('parse-onboarding');
    if (!containerEl) { console.warn('[onboarding] Mount element not found.'); return api; }
    injectStyles();
    render();
    if (!listenerBound) {
      document.addEventListener('parse:project-error', _onProjectError);
      listenerBound = true;
    }
    return api;
  }

  function _onProjectError(e) {
    if (e && e.detail && e.detail.showOnboarding) show();
  }

  function show() {
    if (containerEl) { containerEl.classList.remove('hidden'); currentStep = 1; render(); }
  }

  function hide() {
    if (containerEl) containerEl.classList.add('hidden');
  }

  function destroy() {
    document.removeEventListener('parse:project-error', _onProjectError);
    listenerBound = false;
  }

  const api = { init, destroy, show, hide };
  P.modules.onboarding = api;
})();
