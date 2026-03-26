(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.annotations = window.PARSE.annotations || {};

  const P = window.PARSE;

  const STYLE_ID = 'parse-speaker-import-style';
  const TOTAL_STEPS = 5;
  const OFFSET_POLL_INTERVAL_MS = 1200;
  const STT_POLL_INTERVAL_MS = 1400;
  const MATCH_TIME_WINDOW_SEC = 14;
  const FETCH_TIMEOUT_MS = 30000;

  const STEP_TITLES = [
    'Select source',
    'Offset detection',
    'STT processing',
    'Review matches',
    'Confirm import',
  ];

  const state = {
    initialized: false,
    containerEl: null,
    listeners: [],
    open: false,
    step: 1,
    animateStep: false,
    offsetRunId: 0,
    sttRunId: 0,
    draft: defaultDraft(),
  };

  function defaultDraft() {
    return {
      speakerId: '',
      audioFile: null,
      sourceWavHint: '',
      csvFile: null,
      csvText: '',
      csvSignature: '',
      conceptRows: [],

      detectedOffsetSec: null,
      detectedOffsetConfidence: null,
      manualOffsetText: '',
      offsetStatus: 'idle',
      offsetMessage: '',
      offsetProgress: 0,
      offsetJobId: '',

      sttStatus: 'idle',
      sttMessage: '',
      sttProgress: 0,
      sttJobId: '',
      sttSegments: [],

      matches: [],
      activeMatchIndex: null,
      matchSignature: '',

      importStatus: 'idle',
      importMessage: '',
      annotationPath: '',

      validationError: '',
      runtimeError: '',
    };
  }

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

  function toString(value) {
    return String(value == null ? '' : value).trim();
  }

  function toNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function normalizeProgress(value) {
    const num = toNumber(value);
    if (!Number.isFinite(num)) return 0;
    const scaled = num <= 1 ? num * 100 : num;
    return Math.max(0, Math.min(100, scaled));
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

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function truncateText(value, maxLen) {
    const text = String(value == null ? '' : value);
    const limit = Math.max(0, Number(maxLen) || 0);
    if (!limit || text.length <= limit) return text;
    return text.slice(0, limit - 1) + '...';
  }

  function normalizeWords(value) {
    const text = toString(value).toLowerCase();
    if (!text) return [];
    const tokens = text.match(/[a-z0-9\u0600-\u06ff\u0750-\u077f]+/g);
    return Array.isArray(tokens) ? tokens : [];
  }

  function tokenSimilarity(left, right) {
    const leftTokens = normalizeWords(left);
    const rightTokens = normalizeWords(right);

    if (!leftTokens.length || !rightTokens.length) {
      return 0;
    }

    const leftSet = new Set(leftTokens);
    const rightSet = new Set(rightTokens);

    let intersection = 0;
    leftSet.forEach(function (token) {
      if (rightSet.has(token)) {
        intersection += 1;
      }
    });

    const union = leftSet.size + rightSet.size - intersection;
    if (union <= 0) return 0;
    return intersection / union;
  }

  function pickSourceWav() {
    if (state.draft.audioFile && state.draft.audioFile.name) {
      return String(state.draft.audioFile.name);
    }
    return state.draft.sourceWavHint || '';
  }

  function formatSeconds(value) {
    const sec = toNumber(value);
    if (!Number.isFinite(sec)) return '-';
    return sec.toFixed(1) + 's';
  }

  function formatOffset(value) {
    const sec = toNumber(value);
    if (!Number.isFinite(sec)) return '-';
    const sign = sec >= 0 ? '+' : '';
    return sign + sec.toFixed(1) + ' seconds';
  }

  function formatConfidence(value) {
    const scoreRaw = toNumber(value);
    if (!Number.isFinite(scoreRaw)) return 'n/a';
    const score = scoreRaw > 1 ? scoreRaw / 100 : scoreRaw;
    return Math.round(Math.max(0, Math.min(1, score)) * 100) + '%';
  }

  function isDoneStatus(payload) {
    const body = toObject(payload);
    if (body.done === true) return true;

    const status = toString(body.status || body.state || body.phase).toLowerCase();
    return status === 'done' ||
      status === 'completed' ||
      status === 'complete' ||
      status === 'success' ||
      status === 'succeeded' ||
      status === 'failed' ||
      status === 'error' ||
      status === 'cancelled' ||
      status === 'canceled';
  }

  function isSuccessStatus(payload) {
    const body = toObject(payload);
    if (typeof body.success === 'boolean') {
      return body.success;
    }

    const status = toString(body.status || body.state || body.phase).toLowerCase();
    return status === 'done' ||
      status === 'completed' ||
      status === 'complete' ||
      status === 'success' ||
      status === 'succeeded';
  }

  function fileSignature(file) {
    if (!file) return '';
    return [
      toString(file.name),
      String(file.size || 0),
      String(file.lastModified || 0),
    ].join(':');
  }

  function detectDelimiter(headerLine) {
    const text = String(headerLine || '');
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
      const ch = line.charAt(i);

      if (ch === '"') {
        if (inQuote && line.charAt(i + 1) === '"') {
          current += '"';
          i += 1;
        } else {
          inQuote = !inQuote;
        }
      } else if (ch === delimiter && !inQuote) {
        cells.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }

    cells.push(current.trim());
    return cells;
  }

  function normalizeHeader(value) {
    return toString(value).toLowerCase().replace(/[^a-z0-9]+/g, '');
  }

  function findHeaderIndex(headers, candidates) {
    const list = Array.isArray(headers) ? headers : [];
    const wanted = Array.isArray(candidates) ? candidates : [];

    for (let c = 0; c < wanted.length; c += 1) {
      const target = normalizeHeader(wanted[c]);
      for (let i = 0; i < list.length; i += 1) {
        if (normalizeHeader(list[i]) === target) {
          return i;
        }
      }
    }

    for (let c = 0; c < wanted.length; c += 1) {
      const target = normalizeHeader(wanted[c]);
      for (let i = 0; i < list.length; i += 1) {
        if (normalizeHeader(list[i]).indexOf(target) !== -1) {
          return i;
        }
      }
    }

    return -1;
  }

  function splitConceptText(value) {
    const text = toString(value);
    if (!text) {
      return {
        conceptId: '',
        label: '',
      };
    }

    const colonIndex = text.indexOf(':');
    if (colonIndex === -1) {
      return {
        conceptId: normalizeConceptId(text),
        label: text,
      };
    }

    return {
      conceptId: normalizeConceptId(text.slice(0, colonIndex)),
      label: text.slice(colonIndex + 1).trim(),
    };
  }

  function parseConceptRows(csvText) {
    const lines = String(csvText || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .split('\n')
      .filter(function (line) {
        return toString(line) !== '';
      });

    if (!lines.length) {
      return [];
    }

    const delimiter = detectDelimiter(lines[0]);
    const headers = parseDelimitedLine(lines[0], delimiter);

    const idIndex = findHeaderIndex(headers, [
      'concept_id',
      'conceptid',
      'id',
      'number',
      'concept',
    ]);

    const labelIndex = findHeaderIndex(headers, [
      'english',
      'concept_en',
      'label',
      'gloss',
      'text',
      'concept',
      'ortho',
      'ipa',
    ]);

    const timeIndex = findHeaderIndex(headers, [
      'start_sec',
      'start',
      'time_sec',
      'timestamp',
      'segment_start_sec',
      'wav_start_sec',
      't0',
    ]);

    const out = [];
    for (let i = 1; i < lines.length; i += 1) {
      const cols = parseDelimitedLine(lines[i], delimiter);
      const rawId = idIndex >= 0 ? cols[idIndex] : '';
      const rawLabel = labelIndex >= 0 ? cols[labelIndex] : '';
      const rawTime = timeIndex >= 0 ? cols[timeIndex] : '';
      const split = splitConceptText(rawLabel || rawId || '');

      const startSec = toNumber(rawTime);
      const conceptId = split.conceptId || normalizeConceptId(rawId);
      const conceptLabel = split.label || toString(rawLabel);

      if (!conceptId && !conceptLabel && !Number.isFinite(startSec)) {
        continue;
      }

      out.push({
        rowIndex: i - 1,
        conceptId: conceptId,
        label: conceptLabel,
        sourceStartSec: Number.isFinite(startSec) ? startSec : null,
        conceptText: toString(rawLabel || rawId),
      });
    }

    return out;
  }

  async function ensureCsvParsed() {
    if (!state.draft.csvFile) {
      state.draft.csvText = '';
      state.draft.csvSignature = '';
      state.draft.conceptRows = [];
      return;
    }

    const signature = fileSignature(state.draft.csvFile);
    if (signature && signature === state.draft.csvSignature && state.draft.conceptRows.length) {
      return;
    }

    const text = await state.draft.csvFile.text();
    state.draft.csvText = text;
    state.draft.csvSignature = signature;
    state.draft.conceptRows = parseConceptRows(text);
  }

  function resetOffsetState() {
    state.offsetRunId += 1;
    state.draft.detectedOffsetSec = null;
    state.draft.detectedOffsetConfidence = null;
    state.draft.manualOffsetText = '';
    state.draft.offsetStatus = 'idle';
    state.draft.offsetMessage = '';
    state.draft.offsetProgress = 0;
    state.draft.offsetJobId = '';
  }

  function resetSttState() {
    state.sttRunId += 1;
    state.draft.sttStatus = 'idle';
    state.draft.sttMessage = '';
    state.draft.sttProgress = 0;
    state.draft.sttJobId = '';
    state.draft.sttSegments = [];
    state.draft.matches = [];
    state.draft.activeMatchIndex = null;
    state.draft.matchSignature = '';
  }

  function clearImportState() {
    state.draft.importStatus = 'idle';
    state.draft.importMessage = '';
    state.draft.annotationPath = '';
  }

  function resolveOffsetSeconds() {
    const manual = toNumber(state.draft.manualOffsetText);
    if (Number.isFinite(manual)) {
      return manual;
    }
    const detected = toNumber(state.draft.detectedOffsetSec);
    if (Number.isFinite(detected)) {
      return detected;
    }
    return 0;
  }

  function segmentDisplayText(segment) {
    const row = toObject(segment);
    const text = toString(row.ortho || row.text || row.ipa);
    if (text) {
      return text;
    }
    return '(empty segment)';
  }

  function parseSttSegments(payload) {
    const body = toObject(payload);
    const result = toObject(body.result);

    const candidates = [
      Array.isArray(result.segments) ? result.segments : null,
      Array.isArray(result.items) ? result.items : null,
      Array.isArray(body.segments) ? body.segments : null,
      Array.isArray(body.items) ? body.items : null,
    ];

    let raw = [];
    for (let i = 0; i < candidates.length; i += 1) {
      if (Array.isArray(candidates[i])) {
        raw = candidates[i];
        break;
      }
    }

    const out = [];
    for (let i = 0; i < raw.length; i += 1) {
      const row = toObject(raw[i]);
      const startSec = toNumber(
        row.start != null ? row.start :
          row.startSec != null ? row.startSec :
            row.segment_start_sec
      );
      const endSecRaw = toNumber(
        row.end != null ? row.end :
          row.endSec != null ? row.endSec :
            row.segment_end_sec
      );

      if (!Number.isFinite(startSec)) {
        continue;
      }

      const endSec = Number.isFinite(endSecRaw) ? Math.max(endSecRaw, startSec) : startSec;

      out.push({
        index: i,
        startSec: startSec,
        endSec: endSec,
        text: toString(row.text || row.transcript || row.ortho || row.orth),
        ortho: toString(row.ortho || row.orth || row.text || row.transcript),
        ipa: toString(row.ipa || row.phonetic || row.phonemic),
        confidence: toNumber(row.confidence),
      });
    }

    out.sort(function (left, right) {
      return (left.startSec - right.startSec) || (left.endSec - right.endSec) || (left.index - right.index);
    });

    for (let i = 0; i < out.length; i += 1) {
      out[i].index = i;
    }

    return out;
  }

  function scoreCandidate(row, segment, offsetSec) {
    const conceptText = toString(row.label || row.conceptText || row.conceptId);
    const segmentText = toString(segment.ortho || segment.text || segment.ipa);

    const textScore = tokenSimilarity(conceptText, segmentText);

    if (Number.isFinite(row.sourceStartSec)) {
      const targetSec = row.sourceStartSec + offsetSec;
      const delta = Math.abs(segment.startSec - targetSec);
      const timeScore = Math.max(0, 1 - (delta / MATCH_TIME_WINDOW_SEC));
      const score = (timeScore * 0.70) + (textScore * 0.30);
      return {
        score: score,
        delta: delta,
      };
    }

    return {
      score: textScore,
      delta: null,
    };
  }

  function matchSignature() {
    return [
      String(state.draft.conceptRows.length),
      String(state.draft.sttSegments.length),
      resolveOffsetSeconds().toFixed(3),
    ].join('|');
  }

  function buildInitialMatches() {
    const rows = Array.isArray(state.draft.conceptRows) ? state.draft.conceptRows : [];
    const segments = Array.isArray(state.draft.sttSegments) ? state.draft.sttSegments : [];
    const offsetSec = resolveOffsetSeconds();
    const usedIndices = new Set();

    const matches = [];

    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];

      let bestIndex = null;
      let bestScore = -1;
      let bestDelta = null;

      for (let s = 0; s < segments.length; s += 1) {
        const candidate = segments[s];
        const scored = scoreCandidate(row, candidate, offsetSec);
        let rank = scored.score;

        if (usedIndices.has(candidate.index)) {
          rank *= 0.9;
        }

        if (rank > bestScore) {
          bestScore = rank;
          bestIndex = candidate.index;
          bestDelta = scored.delta;
        }
      }

      const hasTimestamp = Number.isFinite(row.sourceStartSec);
      const minScore = hasTimestamp ? 0.22 : 0.30;
      const deltaOk = !hasTimestamp || !Number.isFinite(bestDelta) || bestDelta <= 22;
      const accepted = Number.isFinite(bestScore) && bestScore >= minScore && deltaOk;

      if (accepted && bestIndex != null) {
        usedIndices.add(bestIndex);
      }

      matches.push({
        rowIndex: row.rowIndex,
        conceptId: row.conceptId,
        label: row.label,
        conceptText: row.conceptText,
        sourceStartSec: row.sourceStartSec,
        matchedSegmentIndex: accepted ? bestIndex : null,
        confidence: accepted ? Math.max(0, Math.min(1, bestScore)) : 0,
        manuallyEdited: false,
      });
    }

    state.draft.matches = matches;
    state.draft.matchSignature = matchSignature();
  }

  function ensureMatchesFresh() {
    if (!state.draft.conceptRows.length) {
      state.draft.matches = [];
      state.draft.matchSignature = '';
      return;
    }

    const signature = matchSignature();
    if (state.draft.matches.length && state.draft.matchSignature === signature) {
      return;
    }

    buildInitialMatches();
  }

  function findSegmentByIndex(index) {
    const wanted = Number(index);
    const segments = Array.isArray(state.draft.sttSegments) ? state.draft.sttSegments : [];
    for (let i = 0; i < segments.length; i += 1) {
      if (segments[i].index === wanted) {
        return segments[i];
      }
    }
    return null;
  }

  function scoreManualAssignment(match, segment) {
    const row = toObject(match);
    const seg = toObject(segment);

    const textBasis = toString(row.label || row.conceptText || row.conceptId);
    const segmentText = toString(seg.ortho || seg.text || seg.ipa);
    const textScore = tokenSimilarity(textBasis, segmentText);

    if (Number.isFinite(row.sourceStartSec)) {
      const target = row.sourceStartSec + resolveOffsetSeconds();
      const delta = Math.abs(seg.startSec - target);
      const timeScore = Math.max(0, 1 - (delta / MATCH_TIME_WINDOW_SEC));
      return Math.max(0.15, Math.min(1, (timeScore * 0.65) + (textScore * 0.35)));
    }

    return Math.max(0.20, Math.min(1, textScore || 0.45));
  }

  function computeStats() {
    const matches = Array.isArray(state.draft.matches) ? state.draft.matches : [];
    let matched = 0;

    for (let i = 0; i < matches.length; i += 1) {
      if (matches[i].matchedSegmentIndex != null) {
        matched += 1;
      }
    }

    const totalConcepts = matches.length;
    const unmatched = Math.max(0, totalConcepts - matched);

    return {
      conceptsMatched: matched,
      conceptsTotal: totalConcepts,
      segmentsTotal: state.draft.sttSegments.length,
      unmatchedConcepts: unmatched,
    };
  }

  function confidenceClass(confidence) {
    const score = toNumber(confidence);
    if (!Number.isFinite(score)) return 'is-low';
    if (score >= 0.75) return 'is-high';
    if (score >= 0.45) return 'is-mid';
    return 'is-low';
  }

  function jobIdFromPayload(payload) {
    const body = toObject(payload);
    return toString(body.jobId || body.job_id);
  }

  function extractOffsetResult(payload) {
    const body = toObject(payload);
    const result = toObject(body.result);

    const containers = [result, body];
    for (let i = 0; i < containers.length; i += 1) {
      const source = containers[i];
      const offset = toNumber(
        source.offset_sec != null ? source.offset_sec :
          source.offsetSec != null ? source.offsetSec :
            source.offset
      );

      if (!Number.isFinite(offset)) {
        continue;
      }

      const confidenceRaw = toNumber(
        source.confidence != null ? source.confidence :
          source.confidence_score != null ? source.confidence_score :
            source.score
      );

      const confidence = Number.isFinite(confidenceRaw)
        ? (confidenceRaw > 1 ? confidenceRaw / 100 : confidenceRaw)
        : null;

      return {
        offsetSec: offset,
        confidence: confidence,
      };
    }

    return null;
  }

  async function postJson(url, body, timeoutMs) {
    const timeout = Number.isFinite(Number(timeoutMs)) ? Number(timeoutMs) : FETCH_TIMEOUT_MS;

    const controller = new AbortController();
    const timer = window.setTimeout(function () {
      controller.abort();
    }, timeout);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json, text/plain, */*',
        },
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });

      const text = await response.text();
      let payload = {};
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (_) {
          payload = { raw: text };
        }
      }

      if (!response.ok) {
        const message = toString(payload.error || payload.message || payload.detail || payload.raw || ('HTTP ' + response.status));
        const error = new Error(message || ('HTTP ' + response.status));
        error.status = response.status;
        throw error;
      }

      return payload;
    } finally {
      clearTimeout(timer);
    }
  }

  async function requestOffsetStatus(jobId) {
    const endpoints = [
      {
        url: '/api/compute/offset/status',
        body: { jobId: jobId },
      },
      {
        url: '/api/offset/status',
        body: { jobId: jobId },
      },
      {
        url: '/api/compute/status',
        body: { jobId: jobId, type: 'offset' },
      },
    ];

    let lastError = null;

    for (let i = 0; i < endpoints.length; i += 1) {
      const item = endpoints[i];

      try {
        return await postJson(item.url, item.body, FETCH_TIMEOUT_MS);
      } catch (error) {
        lastError = error;
        if (error && error.status === 404) {
          continue;
        }
      }
    }

    throw lastError || new Error('Unable to poll offset status.');
  }

  function offsetRequestPayload() {
    const rows = state.draft.conceptRows.slice(0, 400).map(function (row) {
      return {
        conceptId: row.conceptId,
        concept: row.label || row.conceptText,
        startSec: row.sourceStartSec,
      };
    });

    return {
      speaker: state.draft.speakerId,
      sourceWav: pickSourceWav(),
      audio: state.draft.audioFile ? {
        name: state.draft.audioFile.name,
        size: state.draft.audioFile.size,
        type: state.draft.audioFile.type,
      } : null,
      csv: state.draft.csvFile ? {
        name: state.draft.csvFile.name,
        size: state.draft.csvFile.size,
      } : null,
      csvText: state.draft.csvText,
      anchors: rows,
    };
  }

  async function startOffsetDetection(force) {
    if (!state.open) return;
    if (!state.draft.csvFile || !state.draft.conceptRows.length) {
      state.draft.offsetStatus = 'skipped';
      state.draft.offsetMessage = 'No CSV concepts provided. Offset detection skipped.';
      state.draft.manualOffsetText = state.draft.manualOffsetText || '0';
      render();
      return;
    }

    if (!force && state.draft.offsetStatus === 'running') {
      return;
    }

    const runId = state.offsetRunId + 1;
    state.offsetRunId = runId;

    state.draft.offsetStatus = 'running';
    state.draft.offsetMessage = 'Detecting offset...';
    state.draft.offsetProgress = 5;
    state.draft.offsetJobId = '';
    state.draft.runtimeError = '';
    render();

    try {
      const startPayload = await postJson('/api/compute/offset', offsetRequestPayload(), FETCH_TIMEOUT_MS);
      if (runId !== state.offsetRunId) {
        return;
      }

      const immediate = extractOffsetResult(startPayload);
      if (immediate) {
        state.draft.detectedOffsetSec = immediate.offsetSec;
        state.draft.detectedOffsetConfidence = immediate.confidence;
        state.draft.manualOffsetText = Number(immediate.offsetSec).toFixed(2);
        state.draft.offsetStatus = 'done';
        state.draft.offsetMessage = 'Offset detection complete.';
        state.draft.offsetProgress = 100;
        render();
        return;
      }

      const jobId = jobIdFromPayload(startPayload);
      if (!jobId) {
        throw new Error('Offset endpoint did not return offset data or jobId.');
      }

      state.draft.offsetJobId = jobId;
      state.draft.offsetProgress = Math.max(state.draft.offsetProgress, 8);
      render();

      let finalPayload = null;
      for (let attempts = 0; attempts < 240; attempts += 1) {
        if (runId !== state.offsetRunId) {
          return;
        }

        const pollPayload = await requestOffsetStatus(jobId);
        if (runId !== state.offsetRunId) {
          return;
        }

        state.draft.offsetProgress = normalizeProgress(pollPayload.progress || state.draft.offsetProgress);
        state.draft.offsetMessage = toString(pollPayload.message) || 'Detecting offset...';
        render();

        if (isDoneStatus(pollPayload)) {
          finalPayload = pollPayload;
          break;
        }

        await sleep(OFFSET_POLL_INTERVAL_MS);
      }

      if (!finalPayload) {
        throw new Error('Offset detection timed out.');
      }

      if (!isSuccessStatus(finalPayload)) {
        throw new Error(toString(finalPayload.error || finalPayload.message) || 'Offset detection failed.');
      }

      const result = extractOffsetResult(finalPayload);
      if (!result) {
        throw new Error('Offset job completed without offset result.');
      }

      state.draft.detectedOffsetSec = result.offsetSec;
      state.draft.detectedOffsetConfidence = result.confidence;
      state.draft.manualOffsetText = Number(result.offsetSec).toFixed(2);
      state.draft.offsetStatus = 'done';
      state.draft.offsetMessage = 'Offset detection complete.';
      state.draft.offsetProgress = 100;
      state.draft.matchSignature = '';
      render();
    } catch (error) {
      if (runId !== state.offsetRunId) {
        return;
      }

      state.draft.offsetStatus = 'error';
      state.draft.offsetMessage = toString(error && error.message) || 'Offset detection failed.';
      if (!state.draft.manualOffsetText) {
        state.draft.manualOffsetText = '0';
      }
      state.draft.offsetProgress = 0;
      render();
    }
  }

  async function startSttProcessing(force) {
    if (!state.open) return;
    if (!force && state.draft.sttStatus === 'running') {
      return;
    }

    const speakerId = toString(state.draft.speakerId);
    const sourceWav = toString(pickSourceWav());
    if (!speakerId || !sourceWav) {
      state.draft.sttStatus = 'error';
      state.draft.sttMessage = 'Speaker ID and WAV source are required before STT.';
      render();
      return;
    }

    const aiClient = toObject(P.modules).aiClient;
    if (!aiClient || typeof aiClient.requestSTT !== 'function' || typeof aiClient.pollSTTStatus !== 'function') {
      state.draft.sttStatus = 'error';
      state.draft.sttMessage = 'aiClient module is unavailable.';
      render();
      return;
    }

    const runId = state.sttRunId + 1;
    state.sttRunId = runId;

    state.draft.sttStatus = 'running';
    state.draft.sttMessage = 'Submitting STT job...';
    state.draft.sttProgress = 2;
    state.draft.sttJobId = '';
    state.draft.runtimeError = '';
    state.draft.matches = [];
    state.draft.matchSignature = '';
    clearImportState();
    render();

    try {
      const jobId = await aiClient.requestSTT(speakerId, sourceWav);
      if (runId !== state.sttRunId) {
        return;
      }

      state.draft.sttJobId = toString(jobId);
      state.draft.sttMessage = 'Processing audio...';
      state.draft.sttProgress = 6;
      render();

      let donePayload = null;
      for (let attempts = 0; attempts < 800; attempts += 1) {
        if (runId !== state.sttRunId) {
          return;
        }

        const statusPayload = await aiClient.pollSTTStatus(jobId);
        if (runId !== state.sttRunId) {
          return;
        }

        state.draft.sttProgress = normalizeProgress(statusPayload.progress || state.draft.sttProgress);
        state.draft.sttMessage = toString(statusPayload.message) || 'Processing audio...';
        render();

        if (isDoneStatus(statusPayload)) {
          donePayload = statusPayload;
          break;
        }

        await sleep(STT_POLL_INTERVAL_MS);
      }

      if (!donePayload) {
        throw new Error('STT polling timed out.');
      }

      if (!isSuccessStatus(donePayload)) {
        throw new Error(toString(donePayload.error || donePayload.message) || 'STT failed.');
      }

      const segments = parseSttSegments(donePayload);
      state.draft.sttSegments = segments;
      state.draft.sttStatus = 'done';
      state.draft.sttProgress = 100;
      state.draft.sttMessage = 'STT complete: ' + segments.length + ' segments.';
      state.draft.matchSignature = '';

      if (state.draft.conceptRows.length) {
        ensureMatchesFresh();
      }

      render();
    } catch (error) {
      if (runId !== state.sttRunId) {
        return;
      }

      state.draft.sttStatus = 'error';
      state.draft.sttProgress = 0;
      state.draft.sttMessage = toString(error && error.message) || 'STT processing failed.';
      state.draft.sttSegments = [];
      state.draft.matches = [];
      state.draft.matchSignature = '';
      render();
    }
  }

  function annotationPathForSpeaker(speakerId) {
    return 'annotations/' + speakerId + '.parse.json';
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function conceptDisplayText(match) {
    const conceptId = toString(match.conceptId);
    const label = toString(match.label || match.conceptText);
    if (conceptId && label && label !== conceptId) {
      return conceptId + ':' + label;
    }
    if (conceptId) {
      return conceptId;
    }
    return label;
  }

  function createAnnotationRecord() {
    const speakerId = toString(state.draft.speakerId);
    const sourceWav = toString(pickSourceWav());
    const segments = Array.isArray(state.draft.sttSegments) ? state.draft.sttSegments : [];
    const matches = Array.isArray(state.draft.matches) ? state.draft.matches : [];

    const ipaIntervals = [];
    const orthoIntervals = [];
    const conceptIntervals = [];
    const speakerIntervals = [];

    const usedBounds = new Set();

    for (let i = 0; i < matches.length; i += 1) {
      const match = matches[i];
      if (match.matchedSegmentIndex == null) {
        continue;
      }

      const segment = findSegmentByIndex(match.matchedSegmentIndex);
      if (!segment) {
        continue;
      }

      const startSec = Number(segment.startSec);
      const endSec = Number(segment.endSec);
      if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec < startSec) {
        continue;
      }

      const boundsKey = startSec.toFixed(4) + '|' + endSec.toFixed(4);
      if (usedBounds.has(boundsKey)) {
        continue;
      }
      usedBounds.add(boundsKey);

      ipaIntervals.push({
        start: startSec,
        end: endSec,
        text: toString(segment.ipa),
      });

      orthoIntervals.push({
        start: startSec,
        end: endSec,
        text: toString(segment.ortho || segment.text),
      });

      conceptIntervals.push({
        start: startSec,
        end: endSec,
        text: conceptDisplayText(match),
      });

      speakerIntervals.push({
        start: startSec,
        end: endSec,
        text: speakerId,
      });
    }

    ipaIntervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });
    orthoIntervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });
    conceptIntervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });
    speakerIntervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });

    let durationSec = 0;
    for (let i = 0; i < segments.length; i += 1) {
      durationSec = Math.max(durationSec, Number(segments[i].endSec) || 0);
    }

    if (!speakerIntervals.length && durationSec > 0) {
      speakerIntervals.push({
        start: 0,
        end: durationSec,
        text: speakerId,
      });
    }

    const languageCode = toString(toObject(toObject(P.project).language).code) || 'und';
    const now = nowIso();

    return {
      version: 1,
      project_id: toString(toObject(P.project).project_id) || 'parse-project',
      speaker: speakerId,
      source_audio: sourceWav,
      source_audio_duration_sec: durationSec,
      tiers: {
        ipa: {
          type: 'interval',
          display_order: 1,
          intervals: ipaIntervals,
        },
        ortho: {
          type: 'interval',
          display_order: 2,
          intervals: orthoIntervals,
        },
        concept: {
          type: 'interval',
          display_order: 3,
          intervals: conceptIntervals,
        },
        speaker: {
          type: 'interval',
          display_order: 4,
          intervals: speakerIntervals,
        },
      },
      metadata: {
        language_code: languageCode,
        created: now,
        modified: now,
      },
    };
  }

  function persistLocalAnnotation(speakerId, record) {
    try {
      localStorage.setItem('parse-annotations-' + speakerId, JSON.stringify(record));
    } catch (_) {
      // Best effort local fallback.
    }
  }

  async function persistServerAnnotation(speakerId, record) {
    const response = await fetch('/api/annotations/' + encodeURIComponent(speakerId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/plain, */*',
      },
      body: JSON.stringify(record),
    });

    if (!response.ok) {
      const text = await response.text().catch(function () {
        return '';
      });
      const message = text || ('HTTP ' + response.status);
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
  }

  async function runImport() {
    if (!state.open) return;
    if (state.draft.importStatus === 'running') return;

    if (!toString(state.draft.speakerId)) {
      state.draft.validationError = 'Speaker ID is required.';
      render();
      return;
    }

    if (!state.draft.sttSegments.length) {
      state.draft.validationError = 'No STT segments are available to import.';
      render();
      return;
    }

    state.draft.importStatus = 'running';
    state.draft.importMessage = 'Creating annotation file...';
    state.draft.validationError = '';
    state.draft.runtimeError = '';
    render();

    try {
      ensureMatchesFresh();
      const speakerId = toString(state.draft.speakerId);
      const annotationPath = annotationPathForSpeaker(speakerId);
      const stats = computeStats();
      const record = createAnnotationRecord();

      P.annotations = toObject(P.annotations);
      P.annotations[speakerId] = record;

      persistLocalAnnotation(speakerId, record);

      let serverMessage = '';
      try {
        await persistServerAnnotation(speakerId, record);
      } catch (error) {
        const status = error && error.status;
        if (status === 404) {
          serverMessage = 'Saved locally; server annotations endpoint is unavailable.';
        } else {
          throw error;
        }
      }

      dispatch('parse:annotations-loaded', {
        speaker: speakerId,
        count: stats.conceptsMatched,
      });

      dispatch('parse:annotations-changed', {
        speaker: speakerId,
        totalAnnotations: stats.conceptsMatched,
      });

      dispatch('parse:speaker-imported', {
        speakerId: speakerId,
        annotationPath: annotationPath,
        stats: stats,
      });

      state.draft.importStatus = 'done';
      state.draft.importMessage = serverMessage || 'Import complete.';
      state.draft.annotationPath = annotationPath;
      render();

      closeWizard(false);
    } catch (error) {
      state.draft.importStatus = 'error';
      state.draft.importMessage = toString(error && error.message) || 'Import failed.';
      render();
    }
  }

  function stepIndicatorHtml() {
    let dots = '';
    for (let i = 1; i <= TOTAL_STEPS; i += 1) {
      const classes = ['psi-step-dot'];
      if (i < state.step) classes.push('is-complete');
      if (i === state.step) classes.push('is-active');

      dots +=
        '<div class="' + classes.join(' ') + '">' +
          '<span>' + i + '</span>' +
        '</div>';
    }
    return dots;
  }

  function stepOneHtml() {
    const audioName = state.draft.audioFile ? state.draft.audioFile.name : '';
    const csvName = state.draft.csvFile ? state.draft.csvFile.name : '';

    return [
      '<div class="psi-step-title">1. Select source</div>',
      '<div class="psi-field">',
      '  <label class="psi-label" for="psi-audio-file">Audio file (WAV)</label>',
      '  <input id="psi-audio-file" class="psi-input" type="file" accept=".wav,audio/wav" data-field="audio-file">',
      '  <div class="psi-hint">' +
      (audioName
        ? 'Selected audio: <strong>' + escapeHtml(audioName) + '</strong>'
        : (state.draft.sourceWavHint
          ? 'Using source WAV: <strong>' + escapeHtml(state.draft.sourceWavHint) + '</strong>'
          : 'Choose a WAV source file for STT processing.')) +
      '</div>',
      '</div>',

      '<div class="psi-field">',
      '  <label class="psi-label" for="psi-csv-file">CSV file (optional, elicitation timestamps)</label>',
      '  <input id="psi-csv-file" class="psi-input" type="file" accept=".csv,text/csv" data-field="csv-file">',
      '  <div class="psi-hint">' +
      (csvName
        ? 'Selected CSV: <strong>' + escapeHtml(csvName) + '</strong>' +
          (state.draft.conceptRows.length ? ' (' + state.draft.conceptRows.length + ' rows parsed)' : '')
        : 'Provide CSV if you want automatic offset detection and concept matching.') +
      '</div>',
      '</div>',

      '<div class="psi-field">',
      '  <label class="psi-label" for="psi-speaker-id">Speaker ID</label>',
      '  <input id="psi-speaker-id" class="psi-input" type="text" data-field="speaker-id" placeholder="Khan05" value="' + escapeHtml(state.draft.speakerId) + '">',
      '  <div class="psi-hint">Example: <code>Khan05</code></div>',
      '</div>',
    ].join('');
  }

  function stepTwoHtml() {
    const status = state.draft.offsetStatus;
    const offsetDetected = Number.isFinite(toNumber(state.draft.detectedOffsetSec));
    const confidenceDetected = Number.isFinite(toNumber(state.draft.detectedOffsetConfidence));

    return [
      '<div class="psi-step-title">2. Offset detection</div>',
      '<div class="psi-block">',
      '  <div class="psi-block-title">Auto alignment (CSV → audio timeline)</div>',
      '  <div class="psi-status-row">',
      (status === 'running'
        ? '    <span class="psi-spinner" aria-hidden="true"></span>'
        : '    <span class="psi-dot"></span>'),
      '    <span>' + escapeHtml(state.draft.offsetMessage || (status === 'running' ? 'Detecting offset...' : 'Ready to detect offset.')) + '</span>',
      '  </div>',
      (status === 'running'
        ? '  <div class="psi-progress-track"><div class="psi-progress-fill" style="width:' + normalizeProgress(state.draft.offsetProgress).toFixed(1) + '%"></div></div>'
        : ''),
      (offsetDetected
        ? '  <div class="psi-offset-result">Detected offset: <strong>' +
            escapeHtml(formatOffset(state.draft.detectedOffsetSec)) +
            '</strong>' +
            (confidenceDetected
              ? ', <strong>' + escapeHtml(formatConfidence(state.draft.detectedOffsetConfidence)) + '</strong> confidence'
              : '') +
          '</div>'
        : ''),
      (status === 'error'
        ? '  <div class="psi-error-inline">' + escapeHtml(state.draft.offsetMessage || 'Offset detection failed.') + '</div>'
        : ''),
      '  <div class="psi-action-row">',
      '    <button class="psi-btn" type="button" data-action="retry-offset"' + (status === 'running' ? ' disabled' : '') + '>Detect offset</button>',
      '  </div>',
      '</div>',

      '<div class="psi-field">',
      '  <label class="psi-label" for="psi-offset-manual">Manual offset override (seconds)</label>',
      '  <input id="psi-offset-manual" class="psi-input" type="number" step="0.1" data-field="manual-offset" value="' + escapeHtml(state.draft.manualOffsetText) + '">',
      '  <div class="psi-hint">This value is used when generating concept matches.</div>',
      '</div>',
    ].join('');
  }

  function stepThreeHtml() {
    const progress = normalizeProgress(state.draft.sttProgress);
    const status = state.draft.sttStatus;

    return [
      '<div class="psi-step-title">3. STT processing</div>',
      '<div class="psi-block">',
      '  <div class="psi-block-title">Processing audio</div>',
      '  <div class="psi-status-row">',
      (status === 'running'
        ? '    <span class="psi-spinner" aria-hidden="true"></span>'
        : '    <span class="psi-dot"></span>'),
      '    <span>' + escapeHtml(state.draft.sttMessage || (status === 'running' ? 'Processing audio...' : 'Ready to run STT.')) + '</span>',
      '  </div>',
      '  <div class="psi-progress-track"><div class="psi-progress-fill is-stt" style="width:' + progress.toFixed(1) + '%"></div></div>',
      '  <div class="psi-hint">Progress: ' + progress.toFixed(1) + '%</div>',
      (state.draft.sttJobId
        ? '  <div class="psi-hint">Job ID: <code>' + escapeHtml(state.draft.sttJobId) + '</code></div>'
        : ''),
      (status === 'error'
        ? '  <div class="psi-error-inline">' + escapeHtml(state.draft.sttMessage || 'STT failed.') + '</div>'
        : ''),
      '  <div class="psi-action-row">',
      '    <button class="psi-btn" type="button" data-action="retry-stt"' + (status === 'running' ? ' disabled' : '') + '>Process audio</button>',
      '  </div>',
      '</div>',
      '<div class="psi-hint">Segments discovered: ' + state.draft.sttSegments.length + '</div>',
    ].join('');
  }

  function stepFourHtml() {
    ensureMatchesFresh();
    const matches = Array.isArray(state.draft.matches) ? state.draft.matches : [];
    const activeIndex = Number(state.draft.activeMatchIndex);

    if (!matches.length) {
      return [
        '<div class="psi-step-title">4. Review matches</div>',
        '<div class="psi-block">',
        '  <div class="psi-empty">No concept rows are available from CSV.</div>',
        '</div>',
      ].join('');
    }

    let rowsHtml = '';
    for (let i = 0; i < matches.length; i += 1) {
      const match = matches[i];
      const segment = match.matchedSegmentIndex != null ? findSegmentByIndex(match.matchedSegmentIndex) : null;

      const conceptLabel = toString(match.label || match.conceptText || match.conceptId || ('Concept ' + (i + 1)));
      const conceptId = toString(match.conceptId);
      const conceptLead = conceptId ? ('#' + conceptId + ': ') : '';

      const segmentText = segment
        ? ('[' + formatSeconds(segment.startSec) + ' - ' + formatSeconds(segment.endSec) + '] ' + truncateText(segmentDisplayText(segment), 60))
        : 'Unmatched - click to assign';

      rowsHtml +=
        '<tr>' +
          '<td>' +
            '<div class="psi-concept-cell">' +
              '<div class="psi-concept-main">' + escapeHtml(conceptLead + conceptLabel) + '</div>' +
              (Number.isFinite(match.sourceStartSec)
                ? '<div class="psi-concept-sub">CSV time: ' + escapeHtml(formatSeconds(match.sourceStartSec)) + '</div>'
                : '<div class="psi-concept-sub">No timestamp in CSV</div>') +
            '</div>' +
          '</td>' +
          '<td>' +
            '<button class="psi-link" type="button" data-action="open-editor" data-index="' + i + '">' + escapeHtml(segmentText) + '</button>' +
          '</td>' +
          '<td>' +
            '<span class="psi-badge ' + confidenceClass(match.confidence) + '">' +
              escapeHtml(formatConfidence(match.confidence)) +
              (match.manuallyEdited ? ' *' : '') +
            '</span>' +
          '</td>' +
        '</tr>';
    }

    const editorMatch = Number.isInteger(activeIndex) ? matches[activeIndex] : null;
    let editorHtml = '';

    if (editorMatch) {
      let options = '<option value="">Unmatched</option>';
      for (let i = 0; i < state.draft.sttSegments.length; i += 1) {
        const segment = state.draft.sttSegments[i];
        const selected = editorMatch.matchedSegmentIndex === segment.index ? ' selected' : '';
        options +=
          '<option value="' + segment.index + '"' + selected + '>' +
          escapeHtml('[' + segment.index + '] ' + formatSeconds(segment.startSec) + ' - ' + truncateText(segmentDisplayText(segment), 72)) +
          '</option>';
      }

      editorHtml =
        '<div class="psi-editor">' +
          '<div class="psi-editor-title">Manual correction</div>' +
          '<div class="psi-editor-row">' +
            '<select class="psi-input" data-role="match-select">' + options + '</select>' +
            '<button class="psi-btn" type="button" data-action="apply-match">Apply</button>' +
            '<button class="psi-btn" type="button" data-action="clear-match">Clear</button>' +
          '</div>' +
        '</div>';
    }

    return [
      '<div class="psi-step-title">4. Review matches</div>',
      '<div class="psi-block">',
      '  <div class="psi-table-wrap">',
      '    <table class="psi-table">',
      '      <thead>',
      '        <tr><th>Concept</th><th>Matched segment</th><th>Confidence</th></tr>',
      '      </thead>',
      '      <tbody>' + rowsHtml + '</tbody>',
      '    </table>',
      '  </div>',
      editorHtml,
      '</div>',
      '<div class="psi-hint">Click a segment cell to reassign manually.</div>',
    ].join('');
  }

  function stepFiveHtml() {
    ensureMatchesFresh();
    const stats = computeStats();
    const sourceWav = pickSourceWav();
    const annotationPath = annotationPathForSpeaker(toString(state.draft.speakerId));

    return [
      '<div class="psi-step-title">5. Confirm import</div>',
      '<div class="psi-summary-grid">',
      '  <div class="psi-summary-card">',
      '    <div class="psi-summary-k">Concepts matched</div>',
      '    <div class="psi-summary-v">' + stats.conceptsMatched + '</div>',
      '  </div>',
      '  <div class="psi-summary-card">',
      '    <div class="psi-summary-k">Segments total</div>',
      '    <div class="psi-summary-v">' + stats.segmentsTotal + '</div>',
      '  </div>',
      '  <div class="psi-summary-card">',
      '    <div class="psi-summary-k">Unmatched concepts</div>',
      '    <div class="psi-summary-v">' + stats.unmatchedConcepts + '</div>',
      '  </div>',
      '</div>',

      '<div class="psi-block">',
      '  <div class="psi-row"><span>Speaker</span><strong>' + escapeHtml(state.draft.speakerId || '-') + '</strong></div>',
      '  <div class="psi-row"><span>Source WAV</span><strong>' + escapeHtml(sourceWav || '-') + '</strong></div>',
      '  <div class="psi-row"><span>Annotation path</span><strong>' + escapeHtml(annotationPath) + '</strong></div>',
      '  <div class="psi-row"><span>Offset used</span><strong>' + escapeHtml(formatOffset(resolveOffsetSeconds())) + '</strong></div>',
      '</div>',

      (state.draft.importMessage
        ? '<div class="' + (state.draft.importStatus === 'error' ? 'psi-error-inline' : 'psi-inline-note') + '">' +
            escapeHtml(state.draft.importMessage) +
          '</div>'
        : ''),
    ].join('');
  }

  function stepBodyHtml() {
    if (state.step === 1) return stepOneHtml();
    if (state.step === 2) return stepTwoHtml();
    if (state.step === 3) return stepThreeHtml();
    if (state.step === 4) return stepFourHtml();
    return stepFiveHtml();
  }

  function canGoBack() {
    return state.step > 1;
  }

  function canGoNext() {
    if (state.step === 1) return true;
    if (state.step === 2) return state.draft.offsetStatus !== 'running';
    if (state.step === 3) return state.draft.sttStatus === 'done';
    if (state.step === 4) return true;
    return false;
  }

  function primaryButtonLabel() {
    if (state.step === 5) {
      return state.draft.importStatus === 'running' ? 'Importing...' : 'Import';
    }
    if (state.step === 3 && state.draft.sttStatus === 'running') {
      return 'Processing...';
    }
    return 'Next';
  }

  function shouldDisablePrimary() {
    if (state.step === 5) {
      return state.draft.importStatus === 'running' || state.draft.sttSegments.length === 0;
    }
    return !canGoNext();
  }

  function render() {
    if (!state.containerEl || !state.open) {
      return;
    }

    const stepTitle = STEP_TITLES[state.step - 1] || 'Step';
    const stepPanelClass = state.animateStep ? 'psi-step-panel is-enter' : 'psi-step-panel';

    state.containerEl.classList.remove('hidden');
    state.containerEl.classList.add('psi-host');
    state.containerEl.innerHTML = [
      '<div class="psi-overlay">',
      '  <div class="psi-modal" role="dialog" aria-modal="true" aria-label="Speaker Import Wizard">',
      '    <div class="psi-header">',
      '      <div class="psi-header-main">',
      '        <div class="psi-title">Speaker Import Wizard</div>',
      '        <div class="psi-subtitle">Step ' + state.step + ' of ' + TOTAL_STEPS + ': ' + escapeHtml(stepTitle) + '</div>',
      '      </div>',
      '      <button class="psi-btn" type="button" data-action="cancel">Cancel</button>',
      '    </div>',
      '    <div class="psi-step-track">' + stepIndicatorHtml() + '</div>',
      '    <div class="' + stepPanelClass + '">',
      stepBodyHtml(),
      '    </div>',

      (state.draft.validationError
        ? '    <div class="psi-error-inline">' + escapeHtml(state.draft.validationError) + '</div>'
        : ''),
      (state.draft.runtimeError
        ? '    <div class="psi-error-inline">' + escapeHtml(state.draft.runtimeError) + '</div>'
        : ''),

      '    <div class="psi-footer">',
      '      <button class="psi-btn" type="button" data-action="prev"' + (canGoBack() ? '' : ' disabled') + '>Back</button>',
      '      <div class="psi-footer-right">',
      '        <button class="psi-btn psi-btn-primary" type="button" data-action="primary"' + (shouldDisablePrimary() ? ' disabled' : '') + '>' + escapeHtml(primaryButtonLabel()) + '</button>',
      '      </div>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');

    if (state.animateStep) {
      window.requestAnimationFrame(function () {
        if (!state.containerEl) return;
        const panel = state.containerEl.querySelector('.psi-step-panel');
        if (panel) {
          panel.classList.remove('is-enter');
        }
      });
      state.animateStep = false;
    }
  }

  function closeWizard(dispatchCancel) {
    state.offsetRunId += 1;
    state.sttRunId += 1;
    state.open = false;
    state.step = 1;
    state.animateStep = false;
    state.draft = defaultDraft();

    if (state.containerEl) {
      state.containerEl.classList.add('hidden');
      state.containerEl.classList.remove('psi-host');
      state.containerEl.innerHTML = '';
    }

    if (dispatchCancel) {
      dispatch('parse:speaker-import-cancel', {});
    }
  }

  function applyOpenDetail(detail) {
    const payload = toObject(detail);
    state.draft.speakerId = toString(payload.speakerId || payload.speaker);
    state.draft.sourceWavHint = toString(payload.sourceWav || payload.source_wav);

    const csvText = toString(payload.csvText || payload.csv_text);
    if (csvText) {
      state.draft.csvText = csvText;
      state.draft.conceptRows = parseConceptRows(csvText);
      state.draft.csvSignature = 'payload:' + csvText.length;
    }
  }

  function openWizard(detail) {
    state.offsetRunId += 1;
    state.sttRunId += 1;
    state.draft = defaultDraft();
    state.step = 1;
    state.animateStep = false;
    state.open = true;
    applyOpenDetail(detail);
    render();
  }

  function goToStep(nextStep) {
    const bounded = Math.max(1, Math.min(TOTAL_STEPS, Number(nextStep) || 1));
    if (bounded === state.step) {
      return;
    }

    state.step = bounded;
    state.animateStep = true;
    state.draft.validationError = '';
    state.draft.runtimeError = '';
    render();

    if (state.step === 2 && state.draft.csvFile && state.draft.conceptRows.length) {
      startOffsetDetection(false).catch(function () {
        // Error is surfaced in state.
      });
    }

    if (state.step === 3 && state.draft.sttStatus === 'idle') {
      startSttProcessing(false).catch(function () {
        // Error is surfaced in state.
      });
    }

    if (state.step === 4) {
      ensureMatchesFresh();
      render();
    }
  }

  function validateStepOne() {
    if (!toString(state.draft.speakerId)) {
      return 'Speaker ID is required.';
    }

    if (!state.draft.audioFile && !toString(state.draft.sourceWavHint)) {
      return 'Select a WAV source file.';
    }

    return '';
  }

  async function handleNextStep() {
    state.draft.validationError = '';

    if (state.step === 1) {
      const err = validateStepOne();
      if (err) {
        state.draft.validationError = err;
        render();
        return;
      }

      if (state.draft.csvFile) {
        try {
          await ensureCsvParsed();
        } catch (error) {
          state.draft.validationError = 'Failed to read CSV: ' + (toString(error && error.message) || 'unknown error');
          render();
          return;
        }
      }

      clearImportState();
      if (state.draft.csvFile && state.draft.conceptRows.length) {
        goToStep(2);
      } else {
        goToStep(3);
      }
      return;
    }

    if (state.step === 2) {
      if (state.draft.offsetStatus === 'running') {
        state.draft.validationError = 'Wait for offset detection to finish, or use manual override.';
        render();
        return;
      }
      goToStep(3);
      return;
    }

    if (state.step === 3) {
      if (state.draft.sttStatus !== 'done') {
        state.draft.validationError = 'STT must complete before continuing.';
        render();
        return;
      }

      if (state.draft.conceptRows.length) {
        ensureMatchesFresh();
        goToStep(4);
      } else {
        goToStep(5);
      }
      return;
    }

    if (state.step === 4) {
      ensureMatchesFresh();
      goToStep(5);
    }
  }

  function handleBackStep() {
    state.draft.validationError = '';

    if (state.step === 2) {
      goToStep(1);
      return;
    }

    if (state.step === 3) {
      if (state.draft.csvFile && state.draft.conceptRows.length) {
        goToStep(2);
      } else {
        goToStep(1);
      }
      return;
    }

    if (state.step === 4) {
      goToStep(3);
      return;
    }

    if (state.step === 5) {
      if (state.draft.conceptRows.length) {
        goToStep(4);
      } else {
        goToStep(3);
      }
    }
  }

  function handlePrimaryAction() {
    if (state.step === 5) {
      runImport().catch(function () {
        // Error is surfaced in state.
      });
      return;
    }

    handleNextStep().catch(function () {
      // Error is surfaced in state.
    });
  }

  function handleContainerClick(event) {
    if (!state.open || !state.containerEl) return;

    const actionEl = event.target.closest('[data-action]');
    if (!actionEl || !state.containerEl.contains(actionEl)) {
      return;
    }

    const action = toString(actionEl.dataset.action);

    if (action === 'cancel') {
      closeWizard(true);
      return;
    }

    if (action === 'prev') {
      handleBackStep();
      return;
    }

    if (action === 'primary') {
      handlePrimaryAction();
      return;
    }

    if (action === 'retry-offset') {
      startOffsetDetection(true).catch(function () {
        // Error is surfaced in state.
      });
      return;
    }

    if (action === 'retry-stt') {
      startSttProcessing(true).catch(function () {
        // Error is surfaced in state.
      });
      return;
    }

    if (action === 'open-editor') {
      const index = Number(actionEl.dataset.index);
      if (Number.isInteger(index) && index >= 0 && index < state.draft.matches.length) {
        state.draft.activeMatchIndex = index;
        render();
      }
      return;
    }

    if (action === 'apply-match') {
      const matchIndex = Number(state.draft.activeMatchIndex);
      if (!Number.isInteger(matchIndex) || matchIndex < 0 || matchIndex >= state.draft.matches.length) {
        return;
      }

      const selectEl = state.containerEl.querySelector('[data-role="match-select"]');
      if (!selectEl) return;

      const value = toString(selectEl.value);
      const match = state.draft.matches[matchIndex];

      if (!value) {
        match.matchedSegmentIndex = null;
        match.confidence = 0;
      } else {
        const segmentIndex = Number(value);
        const segment = findSegmentByIndex(segmentIndex);
        if (segment) {
          match.matchedSegmentIndex = segment.index;
          match.confidence = scoreManualAssignment(match, segment);
        }
      }

      match.manuallyEdited = true;
      state.draft.activeMatchIndex = null;
      render();
      return;
    }

    if (action === 'clear-match') {
      const index = Number(state.draft.activeMatchIndex);
      if (Number.isInteger(index) && index >= 0 && index < state.draft.matches.length) {
        state.draft.matches[index].matchedSegmentIndex = null;
        state.draft.matches[index].confidence = 0;
        state.draft.matches[index].manuallyEdited = true;
      }
      state.draft.activeMatchIndex = null;
      render();
    }
  }

  function handleContainerInput(event) {
    if (!state.open || !state.containerEl) return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    const field = toString(target.getAttribute('data-field'));
    if (!field) return;

    if (field === 'speaker-id') {
      state.draft.speakerId = toString(target.value);
      clearImportState();
      return;
    }

    if (field === 'manual-offset') {
      state.draft.manualOffsetText = String(target.value || '');
      state.draft.matchSignature = '';
      clearImportState();
      return;
    }
  }

  function handleContainerChange(event) {
    if (!state.open || !state.containerEl) return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    const field = toString(target.getAttribute('data-field'));
    if (!field) return;

    if (field === 'audio-file') {
      const file = target.files && target.files[0] ? target.files[0] : null;
      state.draft.audioFile = file;
      if (file && file.name) {
        state.draft.sourceWavHint = file.name;
      }
      resetSttState();
      clearImportState();
      render();
      return;
    }

    if (field === 'csv-file') {
      const file = target.files && target.files[0] ? target.files[0] : null;
      state.draft.csvFile = file;
      state.draft.csvText = '';
      state.draft.csvSignature = '';
      state.draft.conceptRows = [];
      resetOffsetState();
      state.draft.matches = [];
      state.draft.matchSignature = '';
      clearImportState();

      if (file) {
        ensureCsvParsed().then(function () {
          state.draft.matchSignature = '';
          render();
        }).catch(function (error) {
          state.draft.validationError = 'Failed to parse CSV: ' + (toString(error && error.message) || 'unknown error');
          render();
        });
      }

      render();
    }
  }

  function handleOpenEvent(event) {
    openWizard(event && event.detail);
  }

  function handleKeydown(event) {
    if (!state.open) return;
    if (event.key === 'Escape') {
      closeWizard(true);
    }
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ID;
    styleEl.textContent =
      '.psi-host { position: fixed; inset: 0; z-index: 3500; }' +
      '.psi-overlay { position: absolute; inset: 0; background: rgba(2, 6, 15, 0.72); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; padding: 16px; }' +
      '.psi-modal { width: min(960px, 96vw); max-height: min(86vh, 900px); display: flex; flex-direction: column; gap: 12px; overflow: hidden; border: 1px solid var(--border, #2c3b56); border-radius: 14px; background: linear-gradient(180deg, rgba(22, 32, 51, 0.98), rgba(14, 22, 36, 0.98)); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45); color: var(--text, #e6edf8); }' +
      '.psi-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px 0; }' +
      '.psi-header-main { min-width: 0; }' +
      '.psi-title { font-size: 18px; font-weight: 700; letter-spacing: 0.01em; color: var(--text, #e6edf8); }' +
      '.psi-subtitle { font-size: 12px; color: var(--muted, #9db0d0); margin-top: 2px; }' +
      '.psi-step-track { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; padding: 0 16px; }' +
      '.psi-step-dot { height: 26px; border: 1px solid var(--border, #2c3b56); border-radius: 999px; background: rgba(11, 18, 32, 0.55); color: var(--muted, #9db0d0); font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; transition: all 180ms ease; }' +
      '.psi-step-dot.is-active { border-color: var(--accent, #4cc2ff); color: var(--accent, #4cc2ff); transform: translateY(-1px); }' +
      '.psi-step-dot.is-complete { border-color: rgba(52, 211, 153, 0.9); color: rgba(52, 211, 153, 0.95); }' +
      '.psi-step-panel { padding: 4px 16px; overflow: auto; min-height: 320px; max-height: 54vh; transform: translateX(0); opacity: 1; transition: transform 240ms ease, opacity 240ms ease; }' +
      '.psi-step-panel.is-enter { transform: translateX(22px); opacity: 0.35; }' +
      '.psi-step-title { font-size: 15px; font-weight: 700; color: var(--text, #e6edf8); margin: 4px 0 10px; }' +
      '.psi-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }' +
      '.psi-label { font-size: 12px; font-weight: 700; color: var(--muted, #9db0d0); text-transform: uppercase; letter-spacing: 0.05em; }' +
      '.psi-input { width: 100%; border-radius: 8px; border: 1px solid var(--border, #2c3b56); background: #10192b; color: var(--text, #e6edf8); font-size: 13px; padding: 8px 10px; }' +
      '.psi-input:focus { outline: none; border-color: var(--accent, #4cc2ff); box-shadow: 0 0 0 2px rgba(76, 194, 255, 0.15); }' +
      '.psi-hint { font-size: 12px; color: var(--muted, #9db0d0); }' +
      '.psi-hint code { color: #c8d7f1; }' +
      '.psi-block { border: 1px solid var(--border, #2c3b56); border-radius: 10px; background: rgba(11, 18, 32, 0.52); padding: 10px; margin-bottom: 12px; }' +
      '.psi-block-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted, #9db0d0); margin-bottom: 8px; font-weight: 700; }' +
      '.psi-status-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text, #e6edf8); margin-bottom: 8px; }' +
      '.psi-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--muted, #9db0d0); display: inline-block; }' +
      '.psi-spinner { width: 14px; height: 14px; border-radius: 999px; border: 2px solid rgba(157, 176, 208, 0.25); border-top-color: var(--accent, #4cc2ff); animation: psi-spin 700ms linear infinite; }' +
      '.psi-progress-track { width: 100%; height: 10px; border: 1px solid var(--border, #2c3b56); border-radius: 999px; background: rgba(9, 15, 25, 0.8); overflow: hidden; margin-bottom: 8px; }' +
      '.psi-progress-fill { width: 0%; height: 100%; background: linear-gradient(90deg, #22c55e, #4cc2ff); transition: width 200ms ease; }' +
      '.psi-progress-fill.is-stt { background: linear-gradient(90deg, #38bdf8, #34d399); }' +
      '.psi-offset-result { color: #d6ecff; font-size: 13px; margin-bottom: 8px; }' +
      '.psi-action-row { display: flex; align-items: center; gap: 8px; }' +
      '.psi-btn { border-radius: 8px; border: 1px solid var(--border, #2c3b56); background: #111a2a; color: var(--text, #e6edf8); font-size: 12px; font-weight: 600; padding: 7px 10px; cursor: pointer; }' +
      '.psi-btn:hover:not(:disabled) { border-color: var(--accent, #4cc2ff); color: var(--accent, #4cc2ff); }' +
      '.psi-btn:disabled { opacity: 0.55; cursor: not-allowed; }' +
      '.psi-btn-primary { border-color: #2498df; background: linear-gradient(180deg, #3ab8ff, #2199e0); color: #05111f; }' +
      '.psi-btn-primary:hover:not(:disabled) { border-color: #5ec8ff; color: #02111f; }' +
      '.psi-table-wrap { border: 1px solid var(--border, #2c3b56); border-radius: 8px; overflow: auto; max-height: 40vh; background: rgba(10, 16, 27, 0.72); }' +
      '.psi-table { width: 100%; border-collapse: collapse; min-width: 720px; }' +
      '.psi-table th, .psi-table td { border-bottom: 1px solid rgba(44, 59, 86, 0.72); padding: 8px; text-align: left; vertical-align: top; }' +
      '.psi-table th { position: sticky; top: 0; z-index: 1; font-size: 11px; color: var(--muted, #9db0d0); text-transform: uppercase; letter-spacing: 0.05em; background: #19263e; }' +
      '.psi-concept-cell { display: flex; flex-direction: column; gap: 2px; }' +
      '.psi-concept-main { font-size: 13px; color: var(--text, #e6edf8); }' +
      '.psi-concept-sub { font-size: 11px; color: var(--muted, #9db0d0); }' +
      '.psi-link { border: 1px solid var(--border, #2c3b56); border-radius: 7px; background: rgba(17, 26, 42, 0.78); color: #c8def9; padding: 6px 8px; font-size: 12px; cursor: pointer; text-align: left; width: 100%; }' +
      '.psi-link:hover { border-color: var(--accent, #4cc2ff); color: var(--accent, #4cc2ff); }' +
      '.psi-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 56px; border-radius: 999px; border: 1px solid transparent; font-size: 11px; font-weight: 700; padding: 4px 8px; }' +
      '.psi-badge.is-high { background: rgba(34, 197, 94, 0.2); border-color: rgba(34, 197, 94, 0.8); color: #bbf7d0; }' +
      '.psi-badge.is-mid { background: rgba(251, 191, 36, 0.2); border-color: rgba(251, 191, 36, 0.8); color: #fde68a; }' +
      '.psi-badge.is-low { background: rgba(248, 113, 113, 0.2); border-color: rgba(248, 113, 113, 0.8); color: #fecaca; }' +
      '.psi-editor { margin-top: 10px; border: 1px dashed var(--border, #2c3b56); border-radius: 8px; padding: 8px; background: rgba(11, 18, 32, 0.48); }' +
      '.psi-editor-title { font-size: 12px; font-weight: 700; color: var(--muted, #9db0d0); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }' +
      '.psi-editor-row { display: flex; align-items: center; gap: 8px; }' +
      '.psi-empty { color: var(--muted, #9db0d0); font-size: 13px; }' +
      '.psi-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: 10px; }' +
      '.psi-summary-card { border: 1px solid var(--border, #2c3b56); border-radius: 9px; background: rgba(11, 18, 32, 0.62); padding: 10px; }' +
      '.psi-summary-k { font-size: 11px; color: var(--muted, #9db0d0); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }' +
      '.psi-summary-v { font-size: 24px; font-weight: 700; color: var(--text, #e6edf8); }' +
      '.psi-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--muted, #9db0d0); padding: 4px 0; }' +
      '.psi-row strong { color: var(--text, #e6edf8); font-weight: 600; text-align: right; }' +
      '.psi-inline-note { border: 1px solid rgba(52, 211, 153, 0.5); border-radius: 8px; background: rgba(16, 80, 52, 0.25); color: #bbf7d0; font-size: 12px; padding: 8px 10px; }' +
      '.psi-error-inline { border: 1px solid rgba(248, 113, 113, 0.6); border-radius: 8px; background: rgba(102, 28, 28, 0.25); color: #fecaca; font-size: 12px; padding: 8px 10px; margin: 0 16px; }' +
      '.psi-footer { border-top: 1px solid rgba(44, 59, 86, 0.72); margin-top: auto; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 16px 14px; }' +
      '.psi-footer-right { display: inline-flex; align-items: center; gap: 8px; }' +
      '@keyframes psi-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }' +
      '@media (max-width: 920px) {' +
      '  .psi-modal { width: 100%; max-height: 92vh; }' +
      '  .psi-step-track { grid-template-columns: repeat(5, minmax(40px, 1fr)); }' +
      '  .psi-summary-grid { grid-template-columns: 1fr; }' +
      '  .psi-editor-row { flex-direction: column; align-items: stretch; }' +
      '}';

    document.head.appendChild(styleEl);
  }

  function initListeners() {
    if (!state.containerEl) return;

    addListener(state.containerEl, 'click', handleContainerClick);
    addListener(state.containerEl, 'input', handleContainerInput);
    addListener(state.containerEl, 'change', handleContainerChange);

    addListener(document, 'parse:speaker-import-open', handleOpenEvent);
    addListener(document, 'keydown', handleKeydown);
  }

  /**
   * Initialize the speaker import wizard module.
   * @param {HTMLElement=} containerEl Modal container element.
   * @returns {object} Public module API.
   */
  function init(containerEl) {
    if (state.initialized) {
      return P.modules.speakerImport;
    }

    state.containerEl = containerEl || document.getElementById('compare-speaker-import');
    if (!state.containerEl) {
      throw new Error('Missing #compare-speaker-import container.');
    }

    ensureStyles();
    initListeners();
    state.initialized = true;

    return P.modules.speakerImport;
  }

  /**
   * Destroy the speaker import module and detach listeners.
   */
  function destroy() {
    if (!state.initialized) {
      return;
    }

    closeWizard(false);
    removeAllListeners();

    state.initialized = false;
    state.containerEl = null;
    state.listeners = [];
  }

  P.modules.speakerImport = {
    init: init,
    destroy: destroy,
    open: openWizard,
    close: function () {
      closeWizard(true);
    },
  };
}());
