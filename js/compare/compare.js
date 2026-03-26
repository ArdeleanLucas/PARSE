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
    listeners: [],
    availableSpeakers: [],
    selectedSpeakers: [],
    concepts: [],
    filteredConcepts: [],
    selectedConceptId: '',
    tagFilter: {
      activeTagIds: [],
      includeUntagged: false,
    },
    computeType: 'cognates',
    computeToken: 0,
    conceptDispatchToken: 0,
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

  async function parseJsonBody(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (_) {
      return { raw: text };
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

  function buildConceptList(csvConceptRows, annotationLabels) {
    const csvRows = Array.isArray(csvConceptRows) ? csvConceptRows : [];
    const labelsFromAnnotations = toObject(annotationLabels);

    const csvLabelMap = {};
    for (let i = 0; i < csvRows.length; i += 1) {
      const row = csvRows[i];
      const id = normalizeConceptId(row && row.id);
      if (!id) continue;
      const label = toString(row && row.label);
      if (label) {
        csvLabelMap[id] = label;
      }
    }

    const conceptConfig = toObject(toObject(P.project).concepts);
    const projectTotal = toFiniteNumber(conceptConfig.total);
    const total = Number.isFinite(projectTotal) && projectTotal > 0
      ? Math.floor(projectTotal)
      : 85;

    const concepts = [];
    const seen = new Set();

    for (let i = 1; i <= total; i += 1) {
      const id = String(i);
      const label = csvLabelMap[id] || labelsFromAnnotations[id] || ('Concept ' + id);
      concepts.push({ id: id, label: label });
      seen.add(id);
    }

    const extras = Object.keys(csvLabelMap).concat(Object.keys(labelsFromAnnotations));
    for (let i = 0; i < extras.length; i += 1) {
      const id = normalizeConceptId(extras[i]);
      if (!id || seen.has(id)) continue;
      concepts.push({
        id: id,
        label: csvLabelMap[id] || labelsFromAnnotations[id] || ('Concept ' + id),
      });
      seen.add(id);
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
    const selectedConcept = state.filteredConcepts.find(function (concept) {
      return concept.id === state.selectedConceptId;
    }) || null;

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

  function renderBorrowingPanel() {
    if (!state.borrowingPanelEl) return;

    state.borrowingPanelEl.innerHTML =
      '<div class="panel-title">Borrowing adjudication</div>' +
      '<div class="panel-placeholder">Similarity bars and borrowing decisions will appear here as enrichments are computed.</div>';
  }

  function renderSpectrogramPanel() {
    if (!state.spectrogramPanelEl) return;

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

    if (modules.conceptTable && typeof modules.conceptTable.init === 'function') {
      modules.conceptTable.init(state.tableEl);
    }

    if (modules.cognateControls && typeof modules.cognateControls.init === 'function') {
      modules.cognateControls.init(state.cognatePanelEl);
    }

    // Wave 12 L5 - module not yet built, guard for graceful degradation
    if (modules.borrowingPanel && typeof modules.borrowingPanel.init === 'function') {
      modules.borrowingPanel.init(state.borrowingPanelEl);
    }
    if (modules.speakerImport && typeof modules.speakerImport.init === 'function') {
      modules.speakerImport.init(document.getElementById('compare-speaker-import'));
    }
  }

  function syncViews() {
    state.filteredConcepts = applyTagFilter(state.concepts);

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

    const conceptTable = toObject(P.modules).conceptTable;
    if (conceptTable && typeof conceptTable.setSpeakers === 'function') {
      conceptTable.setSpeakers(state.selectedSpeakers);
    }

    if (conceptTable && typeof conceptTable.setConcepts === 'function') {
      conceptTable.setConcepts(state.filteredConcepts);
    }

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
    updateCompareStateSnapshot();
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
    setComputeStatus('Loading compare mode data...', 2);

    P.mode = 'compare';

    await loadProjectConfig();
    await loadSourceIndex();
    await ensureAnnotationStore();

    const allSpeakers = collectSpeakerIds();
    await loadAnnotationsForSpeakers(allSpeakers);
    await ensureEnrichments();
    await ensureTagsModule();
    pruneMissingActiveTags();

    state.availableSpeakers = collectSpeakerIds();
    if (!state.selectedSpeakers.length) {
      state.selectedSpeakers = state.availableSpeakers.slice();
    }

    const annotationLabels = extractAnnotationConceptLabels();
    const csvConceptRows = await loadConceptRowsFromProject();
    state.concepts = buildConceptList(csvConceptRows, annotationLabels);
    state.filteredConcepts = applyTagFilter(state.concepts);

    if (!state.selectedConceptId && state.filteredConcepts.length) {
      state.selectedConceptId = state.filteredConcepts[0].id;
    }

    renderHeader();
    renderBorrowingPanel();
    renderSpectrogramPanel();

    ensureSubmodules();

    // Re-broadcast after submodules subscribe, so compare UI panels hydrate from enrichments immediately.
    dispatchEnrichmentsUpdatedFromMemory();

    if (P.modules.audioPlayer && typeof P.modules.audioPlayer.init === 'function') {
      P.modules.audioPlayer.init();
    }

    syncViews();
    emitSpeakersChanged();
    emitCompareOpen();

    setComputeStatus('Ready.', 0);
  }

  function bindEvents() {
    addListener(state.headerEl, 'click', onHeaderClick);
    addListener(state.headerEl, 'change', onHeaderChange);

    addListener(document, 'parse:tag-filter', onTagFilter);
    addListener(document, 'parse:tag-created', onTagDefinitionsChanged);
    addListener(document, 'parse:tag-deleted', onTagDefinitionsChanged);
    addListener(document, 'parse:items-tagged', onItemsTagged);
    addListener(document, CONCEPT_SELECTED_EVENT, onConceptSelected);
    addListener(document, 'parse:compute-request', onComputeRequest);
    addListener(document, 'parse:borrowing-decision', onBorrowingDecision);
    addListener(document, 'parse:cognate-accept', onCognateAcceptPersist);
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

    state.containerEl = containerEl || document.getElementById('compare-container');
    if (!state.containerEl) {
      throw new Error('Missing #compare-container for compare mode.');
    }

    state.headerEl = document.getElementById('compare-header');
    state.tableEl = document.getElementById('compare-table');
    state.cognatePanelEl = document.getElementById('compare-cognate-panel');
    state.borrowingPanelEl = document.getElementById('compare-borrowing-panel');
    state.spectrogramPanelEl = document.getElementById('compare-spectrogram');
    state.computeStatusEl = document.getElementById('compare-compute-status');

    ensureComputeStatusUI();

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

    dispatchEvent('parse:compare-close', {});

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
    state.availableSpeakers = [];
    state.selectedSpeakers = [];
    state.concepts = [];
    state.filteredConcepts = [];
    state.selectedConceptId = '';
    state.computeType = 'cognates';
    state.conceptDispatchToken = 0;
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
    const container = document.getElementById('compare-container');
    if (!container) return;

    try {
      await init(container);
    } catch (error) {
      console.error('[compare] auto-init failed:', error);
      setComputeStatus('Compare init failed: ' + toString(error && error.message), 0);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit, { once: true });
  } else {
    autoInit();
  }
})();
