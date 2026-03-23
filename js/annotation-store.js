/**
 * annotation-store.js - PARSE annotation persistence + import/export backend.
 *
 * Responsibilities:
 *  - Maintain window.PARSE.annotations (per-speaker annotation schema)
 *  - Load speaker annotations from server, fallback to localStorage
 *  - Persist mutations with immediate localStorage mirror + debounced server save
 *  - Handle TextGrid import
 *  - Export TextGrid / ELAN / CSV / segment manifests
 */
(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.annotations = window.PARSE.annotations || {};

  const P = window.PARSE;

  const MODULE_NAME = '[annotation-store]';
  const API_ANNOTATIONS_BASE = '/api/annotations/';
  const API_EXPORT_SEGMENTS = '/api/export/segments';

  const LS_KEY_PREFIX = 'parse-annotations-';
  const AUTOSAVE_DEBOUNCE_MS = 2000;
  const MATCH_EPSILON = 0.0005;
  const DELETE_TOLERANCE_SEC = 0.1;

  const CANONICAL_TIER_ORDER = {
    ipa: 1,
    ortho: 2,
    concept: 3,
    speaker: 4,
  };

  const CANONICAL_TIER_KEYS = ['ipa', 'ortho', 'concept', 'speaker'];

  const CANONICAL_TEXTGRID_NAMES = {
    ipa: 'IPA',
    ortho: 'Ortho',
    concept: 'Concept',
    speaker: 'Speaker',
  };

  const state = {
    initialized: false,
    listenersBound: false,
    autosaveTimers: Object.create(null),
    pendingSaveChains: Object.create(null),
    loadingPromises: Object.create(null),
    onImportTextGridEvent: null,
    onExportTextGridEvent: null,
    onExportElanEvent: null,
    onExportCsvEvent: null,
    onExportSegmentsEvent: null,
  };

  function logWarn() {
    const args = Array.prototype.slice.call(arguments);
    args.unshift(MODULE_NAME);
    console.warn.apply(console, args);
  }

  function logError() {
    const args = Array.prototype.slice.call(arguments);
    args.unshift(MODULE_NAME);
    console.error.apply(console, args);
  }

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function dispatchIoComplete(operation, format, success, message) {
    const payload = {
      operation: operation,
      format: format,
      success: !!success,
    };
    if (message != null && String(message).trim() !== '') {
      payload.message = String(message);
    }
    dispatch('parse:io-complete', payload);
  }

  function toFiniteNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function toText(value) {
    if (value == null) return '';
    return String(value);
  }

  function approxEqual(a, b, epsilon) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) {
      return false;
    }
    return Math.abs(a - b) <= (epsilon == null ? MATCH_EPSILON : epsilon);
  }

  function nowIsoUtc() {
    return new Date().toISOString();
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function deepCloneJson(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function basename(pathValue) {
    const text = toText(pathValue).trim();
    if (!text) return '';
    const normalized = text.replace(/\\/g, '/');
    const idx = normalized.lastIndexOf('/');
    return idx === -1 ? normalized : normalized.slice(idx + 1);
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

  function conceptIdsEqual(left, right) {
    const l = normalizeConceptId(left);
    const r = normalizeConceptId(right);

    if (!l || !r) {
      return String(left || '').trim() === String(right || '').trim();
    }

    if (l === r) return true;

    const lNum = Number(l);
    const rNum = Number(r);
    if (Number.isFinite(lNum) && Number.isFinite(rNum)) {
      return lNum === rNum;
    }

    return false;
  }

  function splitConceptText(conceptText) {
    const text = toText(conceptText).trim();
    if (!text) {
      return { conceptId: '', conceptEn: '' };
    }

    const colonIdx = text.indexOf(':');
    if (colonIdx === -1) {
      if (/^\d+$/.test(text)) {
        return { conceptId: text, conceptEn: '' };
      }
      return { conceptId: '', conceptEn: text };
    }

    return {
      conceptId: text.slice(0, colonIdx).trim(),
      conceptEn: text.slice(colonIdx + 1).trim(),
    };
  }

  function localStorageKeyForSpeaker(speaker) {
    return LS_KEY_PREFIX + speaker;
  }

  function safeLocalStorageGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (error) {
      logWarn('localStorage get failed for key:', key, error);
      return null;
    }
  }

  function safeLocalStorageSet(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch (error) {
      logWarn('localStorage set failed for key:', key, error);
      return false;
    }
  }

  function readLocalSpeakerSnapshot(speaker) {
    const raw = safeLocalStorageGet(localStorageKeyForSpeaker(speaker));
    if (!raw) return null;

    try {
      return JSON.parse(raw);
    } catch (error) {
      logWarn('Invalid local annotation JSON for speaker:', speaker, error);
      return null;
    }
  }

  function writeLocalSpeakerSnapshot(speaker, record) {
    const key = localStorageKeyForSpeaker(speaker);
    safeLocalStorageSet(key, JSON.stringify(record));
  }

  function normalizeTierKey(rawName) {
    const trimmed = toText(rawName).trim();
    if (!trimmed) return null;

    const lower = trimmed.toLowerCase();
    if (lower === 'ipa' || lower === 'ortho' || lower === 'concept' || lower === 'speaker') {
      return lower;
    }
    return trimmed;
  }

  function tierNameForTextGrid(tierKey) {
    const lower = toText(tierKey).trim().toLowerCase();
    if (CANONICAL_TEXTGRID_NAMES[lower]) {
      return CANONICAL_TEXTGRID_NAMES[lower];
    }
    return toText(tierKey).trim();
  }

  function tierKeyFromTextGridName(tierName) {
    const normalized = toText(tierName).trim();
    const lower = normalized.toLowerCase();
    if (lower === 'ipa') return 'ipa';
    if (lower === 'ortho') return 'ortho';
    if (lower === 'concept') return 'concept';
    if (lower === 'speaker') return 'speaker';
    return normalized;
  }

  function emptyTier(displayOrder) {
    return {
      type: 'interval',
      display_order: displayOrder,
      intervals: [],
    };
  }

  function normalizeInterval(rawInterval) {
    if (!rawInterval || typeof rawInterval !== 'object') return null;

    const start = toFiniteNumber(rawInterval.start != null ? rawInterval.start : rawInterval.xmin);
    const end = toFiniteNumber(rawInterval.end != null ? rawInterval.end : rawInterval.xmax);

    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
      return null;
    }

    return {
      start: start,
      end: end,
      text: rawInterval.text == null ? '' : String(rawInterval.text),
    };
  }

  function sortIntervals(intervals) {
    intervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });
  }

  function normalizeTier(rawTier, defaultDisplayOrder) {
    const tier = rawTier && typeof rawTier === 'object' ? rawTier : {};
    const displayOrderRaw = toFiniteNumber(tier.display_order);
    const displayOrder = Number.isFinite(displayOrderRaw) && displayOrderRaw > 0
      ? Math.floor(displayOrderRaw)
      : defaultDisplayOrder;

    const intervalsRaw = Array.isArray(tier.intervals) ? tier.intervals : [];
    const intervals = [];

    for (let i = 0; i < intervalsRaw.length; i += 1) {
      const normalized = normalizeInterval(intervalsRaw[i]);
      if (normalized) {
        intervals.push(normalized);
      }
    }

    sortIntervals(intervals);

    return {
      type: 'interval',
      display_order: displayOrder,
      intervals: intervals,
    };
  }

  function resolveProjectId() {
    if (P.project && typeof P.project === 'object' && P.project.project_id) {
      return String(P.project.project_id);
    }
    return 'parse-project';
  }

  function resolveLanguageCode(fallbackRecord) {
    if (
      P.project &&
      typeof P.project === 'object' &&
      P.project.language &&
      typeof P.project.language === 'object' &&
      P.project.language.code
    ) {
      return String(P.project.language.code);
    }

    if (
      fallbackRecord &&
      fallbackRecord.metadata &&
      typeof fallbackRecord.metadata === 'object' &&
      fallbackRecord.metadata.language_code
    ) {
      return String(fallbackRecord.metadata.language_code);
    }

    return 'und';
  }

  function getSourceIndexSpeakerEntry(speaker) {
    if (!P.sourceIndex || typeof P.sourceIndex !== 'object') return null;
    if (!P.sourceIndex.speakers || typeof P.sourceIndex.speakers !== 'object') return null;

    const entry = P.sourceIndex.speakers[speaker];
    return entry && typeof entry === 'object' ? entry : null;
  }

  function getSpeakerSourceArray(sourceEntry) {
    if (!sourceEntry || typeof sourceEntry !== 'object') return [];

    if (Array.isArray(sourceEntry.source_wavs)) {
      return sourceEntry.source_wavs;
    }

    if (Array.isArray(sourceEntry.source_files)) {
      return sourceEntry.source_files;
    }

    return [];
  }

  function resolvePrimarySourceWav(speaker) {
    const sourceEntry = getSourceIndexSpeakerEntry(speaker);
    const sourceList = getSpeakerSourceArray(sourceEntry);

    if (!sourceList.length) return '';

    let primary = null;
    for (let i = 0; i < sourceList.length; i += 1) {
      const candidate = sourceList[i];
      if (candidate && candidate.is_primary) {
        primary = candidate;
        break;
      }
    }

    const selected = primary || sourceList[0] || null;
    if (!selected) return '';

    if (selected.filename != null) return String(selected.filename);
    if (selected.file != null) return String(selected.file);
    return '';
  }

  function resolveDurationFromSourceIndex(speaker, sourceWav) {
    const sourceEntry = getSourceIndexSpeakerEntry(speaker);
    const sourceList = getSpeakerSourceArray(sourceEntry);
    if (!sourceList.length) return null;

    const wanted = toText(sourceWav).trim();
    let selected = null;

    if (wanted) {
      for (let i = 0; i < sourceList.length; i += 1) {
        const item = sourceList[i];
        const filename = item && item.filename != null ? String(item.filename) : '';
        if (filename && filename === wanted) {
          selected = item;
          break;
        }
      }
    }

    if (!selected) {
      for (let i = 0; i < sourceList.length; i += 1) {
        const item = sourceList[i];
        if (item && item.is_primary) {
          selected = item;
          break;
        }
      }
    }

    if (!selected) {
      selected = sourceList[0] || null;
    }

    if (!selected) return null;

    const duration = toFiniteNumber(selected.duration_sec);
    return Number.isFinite(duration) && duration >= 0 ? duration : null;
  }

  function computeMaxEndAcrossTiers(record) {
    if (!record || typeof record !== 'object') return 0;
    if (!record.tiers || typeof record.tiers !== 'object') return 0;

    let maxEnd = 0;
    const tierKeys = Object.keys(record.tiers);
    for (let i = 0; i < tierKeys.length; i += 1) {
      const tier = record.tiers[tierKeys[i]];
      if (!tier || !Array.isArray(tier.intervals)) continue;

      for (let j = 0; j < tier.intervals.length; j += 1) {
        const interval = tier.intervals[j];
        const end = interval && Number.isFinite(interval.end) ? interval.end : null;
        if (Number.isFinite(end) && end > maxEnd) {
          maxEnd = end;
        }
      }
    }

    return maxEnd;
  }

  function makeEmptyRecord(speaker, sourceAudio, durationSec, existingRecord) {
    const now = nowIsoUtc();
    const speakerText = toText(speaker).trim();

    const durationCandidate = toFiniteNumber(durationSec);
    const safeDuration = Number.isFinite(durationCandidate) && durationCandidate >= 0
      ? durationCandidate
      : 0;

    const sourceAudioText = toText(sourceAudio).trim() || resolvePrimarySourceWav(speakerText);

    const record = {
      version: 1,
      project_id: resolveProjectId(),
      speaker: speakerText,
      source_audio: sourceAudioText,
      source_audio_duration_sec: safeDuration,
      tiers: {
        ipa: emptyTier(1),
        ortho: emptyTier(2),
        concept: emptyTier(3),
        speaker: emptyTier(4),
      },
      metadata: {
        language_code: resolveLanguageCode(existingRecord),
        created: now,
        modified: now,
      },
    };

    return record;
  }

  function normalizeFlatAnnotation(rawAnnotation, defaults) {
    const raw = rawAnnotation && typeof rawAnnotation === 'object' ? rawAnnotation : {};

    const startSec = toFiniteNumber(
      raw.startSec != null ? raw.startSec :
      raw.start_sec != null ? raw.start_sec :
      raw.start != null ? raw.start :
      raw.xmin
    );

    const endSec = toFiniteNumber(
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
      speaker: raw.speaker != null ? String(raw.speaker) : (defaults && defaults.speaker) || '',
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
          : (defaults && defaults.sourceWav) || '',
    };
  }

  function findIntervalIndexByBounds(intervals, startSec, endSec, epsilon) {
    const list = Array.isArray(intervals) ? intervals : [];
    for (let i = 0; i < list.length; i += 1) {
      const interval = list[i];
      if (
        interval &&
        approxEqual(interval.start, startSec, epsilon) &&
        approxEqual(interval.end, endSec, epsilon)
      ) {
        return i;
      }
    }
    return -1;
  }

  function upsertInterval(intervals, startSec, endSec, text) {
    const safeText = text == null ? '' : String(text);
    const index = findIntervalIndexByBounds(intervals, startSec, endSec, MATCH_EPSILON);

    if (index !== -1) {
      if (intervals[index].text !== safeText) {
        intervals[index].text = safeText;
        return true;
      }
      return false;
    }

    intervals.push({
      start: startSec,
      end: endSec,
      text: safeText,
    });
    sortIntervals(intervals);
    return true;
  }

  function removeIntervalsByBounds(intervals, startSec, endSec, epsilon) {
    if (!Array.isArray(intervals) || intervals.length === 0) return 0;

    let removed = 0;
    for (let i = intervals.length - 1; i >= 0; i -= 1) {
      const interval = intervals[i];
      if (
        interval &&
        approxEqual(interval.start, startSec, epsilon) &&
        approxEqual(interval.end, endSec, epsilon)
      ) {
        intervals.splice(i, 1);
        removed += 1;
      }
    }
    return removed;
  }

  function recordFromFlatAnnotations(rawEntries, speakerHint, sourceWavHint) {
    const speaker = toText(speakerHint).trim();
    const sourceWav = toText(sourceWavHint).trim() || resolvePrimarySourceWav(speaker);
    const record = makeEmptyRecord(speaker, sourceWav, 0, null);

    const entries = Array.isArray(rawEntries) ? rawEntries : [];
    for (let i = 0; i < entries.length; i += 1) {
      const normalized = normalizeFlatAnnotation(entries[i], {
        speaker: speaker,
        sourceWav: sourceWav,
      });
      if (!normalized) continue;

      if (normalized.sourceWav && !record.source_audio) {
        record.source_audio = normalized.sourceWav;
      }
      if (normalized.endSec > record.source_audio_duration_sec) {
        record.source_audio_duration_sec = normalized.endSec;
      }

      const conceptText = toText(normalized.concept).trim() || toText(normalized.conceptId).trim();

      upsertInterval(record.tiers.ipa.intervals, normalized.startSec, normalized.endSec, normalized.ipa);
      upsertInterval(record.tiers.ortho.intervals, normalized.startSec, normalized.endSec, normalized.ortho);
      upsertInterval(record.tiers.concept.intervals, normalized.startSec, normalized.endSec, conceptText);
    }

    syncSpeakerTier(record);
    touchRecordMetadata(record, true);
    return record;
  }

  function normalizeRecord(rawRecord, speakerHint) {
    const speakerFromHint = toText(speakerHint).trim();

    if (Array.isArray(rawRecord)) {
      return recordFromFlatAnnotations(rawRecord, speakerFromHint, '');
    }

    if (!rawRecord || typeof rawRecord !== 'object') {
      const sourceAudio = resolvePrimarySourceWav(speakerFromHint);
      const sourceDuration = resolveDurationFromSourceIndex(speakerFromHint, sourceAudio) || 0;
      return makeEmptyRecord(speakerFromHint, sourceAudio, sourceDuration, null);
    }

    if (Array.isArray(rawRecord.annotations)) {
      const speakerFromRecord = rawRecord.speaker != null ? String(rawRecord.speaker) : speakerFromHint;
      const sourceFromRecord = rawRecord.source_audio != null ? String(rawRecord.source_audio) : '';
      return recordFromFlatAnnotations(rawRecord.annotations, speakerFromRecord, sourceFromRecord);
    }

    const speaker = rawRecord.speaker != null
      ? String(rawRecord.speaker)
      : speakerFromHint;

    const sourceAudio = rawRecord.source_audio != null
      ? String(rawRecord.source_audio)
      : resolvePrimarySourceWav(speaker);

    const sourceDurationRaw = toFiniteNumber(rawRecord.source_audio_duration_sec);
    const sourceDuration = Number.isFinite(sourceDurationRaw) && sourceDurationRaw >= 0
      ? sourceDurationRaw
      : (resolveDurationFromSourceIndex(speaker, sourceAudio) || 0);

    const normalized = makeEmptyRecord(speaker, sourceAudio, sourceDuration, rawRecord);
    normalized.version = 1;
    normalized.project_id = rawRecord.project_id != null
      ? String(rawRecord.project_id)
      : resolveProjectId();

    const tiersIn = rawRecord.tiers && typeof rawRecord.tiers === 'object'
      ? rawRecord.tiers
      : {};

    const tierKeys = Object.keys(tiersIn);
    let nextCustomDisplayOrder = 5;

    for (let i = 0; i < tierKeys.length; i += 1) {
      const originalKey = tierKeys[i];
      const normalizedKey = normalizeTierKey(originalKey);
      if (!normalizedKey) continue;

      const defaultOrder = CANONICAL_TIER_ORDER[normalizedKey] || nextCustomDisplayOrder;
      const tier = normalizeTier(tiersIn[originalKey], defaultOrder);
      normalized.tiers[normalizedKey] = tier;

      if (!CANONICAL_TIER_ORDER[normalizedKey]) {
        nextCustomDisplayOrder = Math.max(nextCustomDisplayOrder, tier.display_order + 1);
      }
    }

    if (!normalized.tiers.ipa) normalized.tiers.ipa = emptyTier(1);
    if (!normalized.tiers.ortho) normalized.tiers.ortho = emptyTier(2);
    if (!normalized.tiers.concept) normalized.tiers.concept = emptyTier(3);
    if (!normalized.tiers.speaker) normalized.tiers.speaker = emptyTier(4);

    const metadataIn = rawRecord.metadata && typeof rawRecord.metadata === 'object'
      ? rawRecord.metadata
      : {};

    const now = nowIsoUtc();
    normalized.metadata = {
      language_code: metadataIn.language_code != null
        ? String(metadataIn.language_code)
        : resolveLanguageCode(rawRecord),
      created: metadataIn.created != null ? String(metadataIn.created) : now,
      modified: metadataIn.modified != null ? String(metadataIn.modified) : now,
    };

    const maxEnd = computeMaxEndAcrossTiers(normalized);
    if (maxEnd > normalized.source_audio_duration_sec) {
      normalized.source_audio_duration_sec = maxEnd;
    }

    const sourceIndexDuration = resolveDurationFromSourceIndex(speaker, normalized.source_audio);
    if (Number.isFinite(sourceIndexDuration) && sourceIndexDuration > normalized.source_audio_duration_sec) {
      normalized.source_audio_duration_sec = sourceIndexDuration;
    }

    if (!normalized.source_audio) {
      normalized.source_audio = resolvePrimarySourceWav(speaker);
    }

    syncSpeakerTier(normalized);
    sortAllIntervals(normalized);

    return normalized;
  }

  function sortAllIntervals(record) {
    if (!record || !record.tiers || typeof record.tiers !== 'object') return;
    const tierKeys = Object.keys(record.tiers);
    for (let i = 0; i < tierKeys.length; i += 1) {
      const tier = record.tiers[tierKeys[i]];
      if (tier && Array.isArray(tier.intervals)) {
        sortIntervals(tier.intervals);
      }
    }
  }

  function collectSpeakerAlignedIntervals(record) {
    if (!record || !record.tiers || typeof record.tiers !== 'object') {
      return [];
    }

    const tierPriority = ['concept', 'ipa', 'ortho'];

    for (let t = 0; t < tierPriority.length; t += 1) {
      const tierKey = tierPriority[t];
      const tier = record.tiers[tierKey];
      if (!tier || !Array.isArray(tier.intervals)) {
        continue;
      }

      const aligned = [];
      const seen = Object.create(null);

      for (let i = 0; i < tier.intervals.length; i += 1) {
        const normalized = normalizeInterval(tier.intervals[i]);
        if (!normalized) continue;
        if (toText(normalized.text).trim() === '') continue;

        const dedupeKey = normalized.start.toFixed(6) + '|' + normalized.end.toFixed(6);
        if (seen[dedupeKey]) continue;
        seen[dedupeKey] = true;

        aligned.push({
          start: normalized.start,
          end: normalized.end,
        });
      }

      if (aligned.length) {
        return aligned;
      }
    }

    const fallbackSpeakerTier = record.tiers.speaker;
    if (!fallbackSpeakerTier || !Array.isArray(fallbackSpeakerTier.intervals)) {
      return [];
    }

    const fallback = [];
    for (let i = 0; i < fallbackSpeakerTier.intervals.length; i += 1) {
      const normalized = normalizeInterval(fallbackSpeakerTier.intervals[i]);
      if (normalized) {
        fallback.push({
          start: normalized.start,
          end: normalized.end,
        });
      }
    }

    return fallback;
  }

  function syncSpeakerTier(record) {
    if (!record || typeof record !== 'object') return;

    if (!record.tiers || typeof record.tiers !== 'object') {
      record.tiers = {};
    }

    if (!record.tiers.speaker || typeof record.tiers.speaker !== 'object') {
      record.tiers.speaker = emptyTier(4);
    }

    record.tiers.speaker.type = 'interval';
    record.tiers.speaker.display_order = 4;

    const duration = Math.max(0, toFiniteNumber(record.source_audio_duration_sec) || 0);
    const speakerText = toText(record.speaker).trim();
    const alignedIntervals = collectSpeakerAlignedIntervals(record);

    record.source_audio_duration_sec = duration;
    record.tiers.speaker.intervals = alignedIntervals.map(function (interval) {
      return {
        start: interval.start,
        end: interval.end,
        text: speakerText,
      };
    });
  }

  function touchRecordMetadata(record, preserveCreated) {
    if (!record || typeof record !== 'object') return;

    if (!record.metadata || typeof record.metadata !== 'object') {
      record.metadata = {};
    }

    if (!preserveCreated || !record.metadata.created) {
      record.metadata.created = nowIsoUtc();
    }
    record.metadata.modified = nowIsoUtc();

    if (!record.metadata.language_code) {
      record.metadata.language_code = resolveLanguageCode(record);
    }
  }

  function ensureSpeakerRecord(speaker, sourceWavHint) {
    const speakerId = toText(speaker).trim();
    if (!speakerId) {
      return null;
    }

    const existing = P.annotations[speakerId];
    const normalizedExisting = normalizeRecord(existing, speakerId);

    if (sourceWavHint != null && String(sourceWavHint).trim() !== '') {
      normalizedExisting.source_audio = String(sourceWavHint).trim();
    }

    if (!normalizedExisting.source_audio) {
      normalizedExisting.source_audio = resolvePrimarySourceWav(speakerId);
    }

    const sourceDuration = resolveDurationFromSourceIndex(speakerId, normalizedExisting.source_audio);
    if (Number.isFinite(sourceDuration) && sourceDuration > normalizedExisting.source_audio_duration_sec) {
      normalizedExisting.source_audio_duration_sec = sourceDuration;
    }

    normalizedExisting.speaker = speakerId;
    syncSpeakerTier(normalizedExisting);
    sortAllIntervals(normalizedExisting);

    P.annotations[speakerId] = normalizedExisting;
    return normalizedExisting;
  }

  function countNonEmptyTierIntervals(tier) {
    if (!tier || !Array.isArray(tier.intervals)) {
      return 0;
    }

    let count = 0;
    for (let i = 0; i < tier.intervals.length; i += 1) {
      const interval = tier.intervals[i];
      if (!interval) continue;
      if (String(interval.text || '').trim() !== '') {
        count += 1;
      }
    }

    return count;
  }

  function countAnnotations(record) {
    if (!record || typeof record !== 'object') return 0;
    if (!record.tiers || typeof record.tiers !== 'object') return 0;

    return Math.max(
      countNonEmptyTierIntervals(record.tiers.concept),
      countNonEmptyTierIntervals(record.tiers.ipa),
      countNonEmptyTierIntervals(record.tiers.ortho)
    );
  }

  function dispatchAnnotationsLoaded(speaker) {
    const record = P.annotations[speaker];
    dispatch('parse:annotations-loaded', {
      speaker: speaker,
      count: countAnnotations(record),
    });
  }

  function dispatchAnnotationsChanged(speaker) {
    const record = P.annotations[speaker];
    dispatch('parse:annotations-changed', {
      speaker: speaker,
      totalAnnotations: countAnnotations(record),
    });
  }

  function annotationsApiUrl(speaker) {
    return API_ANNOTATIONS_BASE + encodeURIComponent(speaker);
  }

  async function fetchSpeakerFromServer(speaker) {
    const response = await fetch(annotationsApiUrl(speaker), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (response.status === 404) {
      return { status: 'not_found', record: null };
    }

    if (!response.ok) {
      throw new Error('HTTP ' + response.status + ' while loading annotations for ' + speaker);
    }

    const payload = await response.json();
    return {
      status: 'ok',
      record: payload,
    };
  }

  async function postSpeakerToServer(speaker, recordSnapshot) {
    const response = await fetch(annotationsApiUrl(speaker), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(recordSnapshot),
    });

    if (!response.ok) {
      let body = '';
      try {
        body = await response.text();
      } catch (_) {
        body = '';
      }

      throw new Error(
        'HTTP ' + response.status + ' while saving annotations for ' + speaker +
        (body ? ': ' + body : '')
      );
    }
  }

  function enqueueServerSave(speaker) {
    if (!P.annotations[speaker]) return;

    let snapshot;
    try {
      snapshot = deepCloneJson(P.annotations[speaker]);
    } catch (error) {
      logWarn('Failed to clone annotation snapshot for server save:', speaker, error);
      return;
    }

    const prior = state.pendingSaveChains[speaker] || Promise.resolve();

    const chain = prior
      .catch(function () {
        return null;
      })
      .then(function () {
        return postSpeakerToServer(speaker, snapshot);
      })
      .catch(function (error) {
        logWarn('Server unavailable, using localStorage only for speaker:', speaker, error);
      });

    state.pendingSaveChains[speaker] = chain;

    chain.finally(function () {
      if (state.pendingSaveChains[speaker] === chain) {
        delete state.pendingSaveChains[speaker];
      }
    });
  }

  function scheduleServerSave(speaker) {
    if (state.autosaveTimers[speaker]) {
      clearTimeout(state.autosaveTimers[speaker]);
    }

    state.autosaveTimers[speaker] = setTimeout(function () {
      delete state.autosaveTimers[speaker];
      enqueueServerSave(speaker);
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  function persistSpeakerMutation(speaker) {
    const record = P.annotations[speaker];
    if (!record) return;

    writeLocalSpeakerSnapshot(speaker, record);
    scheduleServerSave(speaker);
    dispatchAnnotationsChanged(speaker);
  }

  async function loadSpeaker(speaker) {
    const speakerId = toText(speaker).trim();
    if (!speakerId) return null;

    if (state.loadingPromises[speakerId]) {
      return state.loadingPromises[speakerId];
    }

    const loader = (async function () {
      let record = null;

      try {
        const serverResult = await fetchSpeakerFromServer(speakerId);
        if (serverResult.status === 'ok') {
          record = normalizeRecord(serverResult.record, speakerId);
        } else if (serverResult.status === 'not_found') {
          const localSnapshot = readLocalSpeakerSnapshot(speakerId);
          if (localSnapshot != null) {
            record = normalizeRecord(localSnapshot, speakerId);
          }
        }
      } catch (error) {
        logWarn('Server unavailable while loading speaker', speakerId, '- using localStorage fallback.', error);
        const localSnapshot = readLocalSpeakerSnapshot(speakerId);
        if (localSnapshot != null) {
          record = normalizeRecord(localSnapshot, speakerId);
        }
      }

      if (!record) {
        const existingInMemory = P.annotations[speakerId];
        if (existingInMemory != null) {
          record = normalizeRecord(existingInMemory, speakerId);
        }
      }

      if (!record) {
        const sourceAudio = resolvePrimarySourceWav(speakerId);
        const sourceDuration = resolveDurationFromSourceIndex(speakerId, sourceAudio) || 0;
        record = makeEmptyRecord(speakerId, sourceAudio, sourceDuration, null);
      }

      syncSpeakerTier(record);
      sortAllIntervals(record);
      P.annotations[speakerId] = record;

      // Keep crash recovery mirror fresh on every successful load path.
      writeLocalSpeakerSnapshot(speakerId, record);

      dispatchAnnotationsLoaded(speakerId);
      return record;
    })();

    state.loadingPromises[speakerId] = loader;

    try {
      return await loader;
    } finally {
      delete state.loadingPromises[speakerId];
    }
  }

  function getSourceIndexSpeakerIds() {
    if (!P.sourceIndex || typeof P.sourceIndex !== 'object') return [];
    if (!P.sourceIndex.speakers || typeof P.sourceIndex.speakers !== 'object') return [];
    return Object.keys(P.sourceIndex.speakers);
  }

  async function loadInitialSpeakers() {
    const sourceSpeakers = getSourceIndexSpeakerIds();

    if (!sourceSpeakers.length) {
      return;
    }

    const jobs = [];
    for (let i = 0; i < sourceSpeakers.length; i += 1) {
      jobs.push(loadSpeaker(sourceSpeakers[i]));
    }

    await Promise.all(jobs);
  }

  function findNearestConceptIntervalIndex(intervals, startSec, conceptId, toleranceSec) {
    if (!Array.isArray(intervals) || !intervals.length) return -1;

    const tolerance = Number.isFinite(toleranceSec) ? toleranceSec : DELETE_TOLERANCE_SEC;

    function scan(enforceConceptId) {
      let bestIndex = -1;
      let bestDelta = Number.POSITIVE_INFINITY;

      for (let i = 0; i < intervals.length; i += 1) {
        const interval = intervals[i];
        if (!interval || !Number.isFinite(interval.start)) continue;

        if (enforceConceptId && conceptId) {
          if (!conceptIdsEqual(interval.text, conceptId)) {
            continue;
          }
        }

        const delta = Math.abs(interval.start - startSec);
        if (delta <= tolerance && delta < bestDelta) {
          bestDelta = delta;
          bestIndex = i;
        }
      }

      return bestIndex;
    }

    let index = scan(true);
    if (index === -1 && conceptId) {
      index = scan(false);
    }
    return index;
  }

  function onAnnotationSave(event) {
    const detail = event && event.detail ? event.detail : {};

    const speaker = toText(detail.speaker).trim();
    if (!speaker) {
      logWarn('Ignoring parse:annotation-save without speaker detail.');
      return;
    }

    const startSec = toFiniteNumber(detail.startSec);
    const endSec = toFiniteNumber(detail.endSec);
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || endSec < startSec) {
      logWarn('Ignoring parse:annotation-save with invalid start/end:', detail);
      return;
    }

    const sourceWav = toText(detail.sourceWav).trim();
    const conceptId = toText(detail.conceptId).trim();
    const conceptText = toText(detail.concept).trim() || conceptId;

    const record = ensureSpeakerRecord(speaker, sourceWav);
    if (!record) return;

    if (sourceWav) {
      record.source_audio = sourceWav;
    }

    if (endSec > record.source_audio_duration_sec) {
      record.source_audio_duration_sec = endSec;
    }

    const ipaTier = record.tiers.ipa;
    const orthoTier = record.tiers.ortho;
    const conceptTier = record.tiers.concept;
    const speakerTier = record.tiers.speaker;

    let changed = false;
    changed = upsertInterval(ipaTier.intervals, startSec, endSec, detail.ipa == null ? '' : String(detail.ipa)) || changed;
    changed = upsertInterval(orthoTier.intervals, startSec, endSec, detail.ortho == null ? '' : String(detail.ortho)) || changed;
    changed = upsertInterval(conceptTier.intervals, startSec, endSec, conceptText) || changed;
    changed = upsertInterval(speakerTier.intervals, startSec, endSec, speaker) || changed;

    if (!changed) {
      return;
    }

    sortAllIntervals(record);
    syncSpeakerTier(record);
    touchRecordMetadata(record, true);

    P.annotations[speaker] = record;
    persistSpeakerMutation(speaker);
  }

  function onAnnotationDelete(event) {
    const detail = event && event.detail ? event.detail : {};

    const speaker = toText(detail.speaker).trim();
    if (!speaker) {
      logWarn('Ignoring parse:annotation-delete without speaker detail.');
      return;
    }

    const startSec = toFiniteNumber(detail.startSec);
    if (!Number.isFinite(startSec)) {
      logWarn('Ignoring parse:annotation-delete with invalid startSec:', detail);
      return;
    }

    const conceptId = toText(detail.conceptId).trim();
    const record = ensureSpeakerRecord(speaker, '');
    if (!record) return;

    const conceptTier = record.tiers.concept;
    const nearestIndex = findNearestConceptIntervalIndex(
      conceptTier.intervals,
      startSec,
      conceptId,
      DELETE_TOLERANCE_SEC
    );

    if (nearestIndex === -1) {
      return;
    }

    const targetInterval = conceptTier.intervals[nearestIndex];
    if (!targetInterval) return;

    const targetStart = targetInterval.start;
    const targetEnd = targetInterval.end;

    let removedCount = 0;
    removedCount += removeIntervalsByBounds(record.tiers.concept.intervals, targetStart, targetEnd, MATCH_EPSILON);
    removedCount += removeIntervalsByBounds(record.tiers.ipa.intervals, targetStart, targetEnd, MATCH_EPSILON);
    removedCount += removeIntervalsByBounds(record.tiers.ortho.intervals, targetStart, targetEnd, MATCH_EPSILON);
    removedCount += removeIntervalsByBounds(record.tiers.speaker.intervals, targetStart, targetEnd, MATCH_EPSILON);

    if (removedCount <= 0) {
      return;
    }

    touchRecordMetadata(record, true);
    syncSpeakerTier(record);
    sortAllIntervals(record);

    P.annotations[speaker] = record;
    persistSpeakerMutation(speaker);
  }

  function readTextGridStringToken(token, context) {
    const value = toText(token).trim();
    if (value.length < 2 || value.charAt(0) !== '"' || value.charAt(value.length - 1) !== '"') {
      throw new Error('Expected quoted string for ' + context + ', got: ' + value);
    }

    return value.slice(1, -1).replace(/""/g, '"');
  }

  function assignmentValue(line, expectedKey) {
    const text = toText(line).trim();
    const eqIndex = text.indexOf('=');

    if (eqIndex === -1) {
      return text;
    }

    const left = text.slice(0, eqIndex).trim();
    const right = text.slice(eqIndex + 1).trim();

    if (expectedKey && left !== expectedKey) {
      throw new Error('Expected "' + expectedKey + ' = ...", got: ' + text);
    }

    return right;
  }

  function parseTextGridNumber(token, context) {
    const value = assignmentValue(token, null);
    const num = toFiniteNumber(value);
    if (!Number.isFinite(num)) {
      throw new Error('Expected numeric value for ' + context + ', got: ' + token);
    }
    return num;
  }

  function createLineReader(content) {
    const lines = String(content)
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .split('\n');

    let cursor = 0;

    function nextNonEmpty(context) {
      while (cursor < lines.length) {
        let line = lines[cursor];
        cursor += 1;

        if (cursor === 1) {
          line = line.replace(/^\uFEFF/, '');
        }

        const trimmed = line.trim();
        if (trimmed !== '') {
          return {
            line: trimmed,
            lineNo: cursor,
          };
        }
      }

      throw new Error('Unexpected end of TextGrid while ' + context);
    }

    return {
      nextNonEmpty: nextNonEmpty,
    };
  }

  function parseTextGridLong(content) {
    const reader = createLineReader(content);

    const fileTypeLine = reader.nextNonEmpty('reading File type');
    const fileTypeToken = assignmentValue(fileTypeLine.line, 'File type');
    const fileType = readTextGridStringToken(fileTypeToken, 'File type').toLowerCase();
    if (fileType.indexOf('ootextfile') === -1) {
      throw new Error('Unsupported TextGrid File type');
    }

    const objectClassLine = reader.nextNonEmpty('reading Object class');
    const objectClassToken = assignmentValue(objectClassLine.line, 'Object class');
    const objectClass = readTextGridStringToken(objectClassToken, 'Object class');
    if (objectClass !== 'TextGrid') {
      throw new Error('Unsupported TextGrid object class: ' + objectClass);
    }

    const xminLine = reader.nextNonEmpty('reading xmin');
    const xmaxLine = reader.nextNonEmpty('reading xmax');
    const xmin = parseTextGridNumber(assignmentValue(xminLine.line, 'xmin'), 'xmin');
    const xmax = parseTextGridNumber(assignmentValue(xmaxLine.line, 'xmax'), 'xmax');

    const tiersMarker = reader.nextNonEmpty('reading tiers marker').line;
    if (!/^tiers\?\s*<exists>$/.test(tiersMarker)) {
      throw new Error('Expected "tiers? <exists>" marker in TextGrid long format');
    }

    const sizeLine = reader.nextNonEmpty('reading tier count');
    const tierCount = parseInt(assignmentValue(sizeLine.line, 'size'), 10);
    if (!Number.isInteger(tierCount) || tierCount < 0) {
      throw new Error('Invalid TextGrid tier count');
    }

    const itemHeader = reader.nextNonEmpty('reading item list header').line;
    if (!/^item\s*\[\s*\]\s*:$/.test(itemHeader)) {
      throw new Error('Expected "item []:" header for TextGrid long format');
    }

    const tiers = [];

    for (let t = 0; t < tierCount; t += 1) {
      const itemHeaderLine = reader.nextNonEmpty('reading tier header').line;
      if (!/^item\s*\[\s*\d+\s*\]\s*:$/.test(itemHeaderLine)) {
        throw new Error('Malformed tier header: ' + itemHeaderLine);
      }

      const classLine = reader.nextNonEmpty('reading tier class');
      const tierClass = readTextGridStringToken(assignmentValue(classLine.line, 'class'), 'tier class');
      if (tierClass !== 'IntervalTier') {
        throw new Error('Only IntervalTier is supported, got: ' + tierClass);
      }

      const nameLine = reader.nextNonEmpty('reading tier name');
      const tierName = readTextGridStringToken(assignmentValue(nameLine.line, 'name'), 'tier name');

      const tierXminLine = reader.nextNonEmpty('reading tier xmin');
      const tierXmaxLine = reader.nextNonEmpty('reading tier xmax');
      const tierXmin = parseTextGridNumber(assignmentValue(tierXminLine.line, 'xmin'), 'tier xmin');
      const tierXmax = parseTextGridNumber(assignmentValue(tierXmaxLine.line, 'xmax'), 'tier xmax');

      const intervalsLine = reader.nextNonEmpty('reading interval count').line;
      const intervalMatch = intervalsLine.match(/^intervals:\s*size\s*=\s*(.+)$/);
      if (!intervalMatch) {
        throw new Error('Expected "intervals: size = N", got: ' + intervalsLine);
      }

      const intervalCount = parseInt(intervalMatch[1].trim(), 10);
      if (!Number.isInteger(intervalCount) || intervalCount < 0) {
        throw new Error('Invalid interval count for tier ' + tierName);
      }

      const intervals = [];
      for (let i = 0; i < intervalCount; i += 1) {
        const intHeader = reader.nextNonEmpty('reading interval header').line;
        if (!/^intervals\s*\[\s*\d+\s*\]\s*:$/.test(intHeader)) {
          throw new Error('Malformed interval header: ' + intHeader);
        }

        const intXminLine = reader.nextNonEmpty('reading interval xmin');
        const intXmaxLine = reader.nextNonEmpty('reading interval xmax');
        const intTextLine = reader.nextNonEmpty('reading interval text');

        const start = parseTextGridNumber(assignmentValue(intXminLine.line, 'xmin'), 'interval xmin');
        const end = parseTextGridNumber(assignmentValue(intXmaxLine.line, 'xmax'), 'interval xmax');
        const text = readTextGridStringToken(assignmentValue(intTextLine.line, 'text'), 'interval text');

        if (end < start) {
          throw new Error('Interval end < start in tier ' + tierName);
        }

        intervals.push({
          start: start,
          end: end,
          text: text,
        });
      }

      tiers.push({
        name: tierName,
        className: tierClass,
        xmin: tierXmin,
        xmax: tierXmax,
        intervals: intervals,
      });
    }

    return {
      xmin: xmin,
      xmax: xmax,
      tiers: tiers,
    };
  }

  function parseTextGridShort(content) {
    const reader = createLineReader(content);

    const fileTypeLine = reader.nextNonEmpty('reading File type').line;
    const fileTypeToken = assignmentValue(fileTypeLine, fileTypeLine.indexOf('=') !== -1 ? 'File type' : null);
    const fileType = fileTypeToken.charAt(0) === '"'
      ? readTextGridStringToken(fileTypeToken, 'File type')
      : fileTypeToken;

    if (fileType.toLowerCase().indexOf('ootextfile') === -1) {
      throw new Error('Unsupported TextGrid short File type');
    }

    const objectClassLine = reader.nextNonEmpty('reading Object class').line;
    let objectClassToken;
    if (objectClassLine.indexOf('=') !== -1) {
      objectClassToken = assignmentValue(objectClassLine, 'Object class');
    } else {
      objectClassToken = objectClassLine;
    }
    const objectClass = objectClassToken.charAt(0) === '"'
      ? readTextGridStringToken(objectClassToken, 'Object class')
      : objectClassToken;
    if (objectClass !== 'TextGrid') {
      throw new Error('Unsupported TextGrid object class in short format');
    }

    const xmin = parseTextGridNumber(reader.nextNonEmpty('reading xmin').line, 'xmin');
    const xmax = parseTextGridNumber(reader.nextNonEmpty('reading xmax').line, 'xmax');

    const marker = reader.nextNonEmpty('reading tiers marker').line;
    if (!(marker === '<exists>' || /^tiers\?\s*<exists>$/.test(marker))) {
      throw new Error('Expected <exists> marker in TextGrid short format');
    }

    const tierCount = parseInt(parseTextGridNumber(reader.nextNonEmpty('reading tier count').line, 'tier count'), 10);
    if (!Number.isInteger(tierCount) || tierCount < 0) {
      throw new Error('Invalid tier count in TextGrid short format');
    }

    const tiers = [];
    for (let t = 0; t < tierCount; t += 1) {
      const classLine = reader.nextNonEmpty('reading tier class').line;
      const classToken = assignmentValue(classLine, classLine.indexOf('=') !== -1 ? 'class' : null);
      const className = classToken.charAt(0) === '"'
        ? readTextGridStringToken(classToken, 'tier class')
        : classToken;
      if (className !== 'IntervalTier') {
        throw new Error('Only IntervalTier is supported in short format');
      }

      const nameLine = reader.nextNonEmpty('reading tier name').line;
      const nameToken = assignmentValue(nameLine, nameLine.indexOf('=') !== -1 ? 'name' : null);
      const tierName = nameToken.charAt(0) === '"'
        ? readTextGridStringToken(nameToken, 'tier name')
        : nameToken;

      const tierXmin = parseTextGridNumber(reader.nextNonEmpty('reading tier xmin').line, 'tier xmin');
      const tierXmax = parseTextGridNumber(reader.nextNonEmpty('reading tier xmax').line, 'tier xmax');
      const intervalCount = parseInt(parseTextGridNumber(reader.nextNonEmpty('reading interval count').line, 'interval count'), 10);

      if (!Number.isInteger(intervalCount) || intervalCount < 0) {
        throw new Error('Invalid interval count in tier ' + tierName);
      }

      const intervals = [];
      for (let i = 0; i < intervalCount; i += 1) {
        const start = parseTextGridNumber(reader.nextNonEmpty('reading interval start').line, 'interval start');
        const end = parseTextGridNumber(reader.nextNonEmpty('reading interval end').line, 'interval end');
        const textLine = reader.nextNonEmpty('reading interval text').line;
        const textToken = assignmentValue(textLine, textLine.indexOf('=') !== -1 ? 'text' : null);
        const text = textToken.charAt(0) === '"'
          ? readTextGridStringToken(textToken, 'interval text')
          : textToken;

        if (end < start) {
          throw new Error('Interval end < start in tier ' + tierName);
        }

        intervals.push({
          start: start,
          end: end,
          text: text,
        });
      }

      tiers.push({
        name: tierName,
        className: className,
        xmin: tierXmin,
        xmax: tierXmax,
        intervals: intervals,
      });
    }

    return {
      xmin: xmin,
      xmax: xmax,
      tiers: tiers,
    };
  }

  function parseTextGrid(content) {
    const text = String(content || '');
    const trimmedStart = text.replace(/^\uFEFF/, '').trimStart();

    const tryShortFirst = /^"?ooTextFile\s+short/i.test(trimmedStart) ||
      /^File type\s*=\s*"[^"]*short/i.test(trimmedStart);

    if (tryShortFirst) {
      try {
        return parseTextGridShort(text);
      } catch (shortError) {
        return parseTextGridLong(text);
      }
    }

    try {
      return parseTextGridLong(text);
    } catch (longError) {
      return parseTextGridShort(text);
    }
  }

  function parsedTextGridToRecord(parsed, speaker, sourceAudio, targetSpeaker) {
    const speakerId = toText(speaker).trim();
    if (!speakerId) {
      throw new Error('Missing target speaker for TextGrid import');
    }

    const parsedXmax = parsed && Number.isFinite(parsed.xmax) ? parsed.xmax : null;

    let durationSec = Number.isFinite(parsedXmax) && parsedXmax >= 0 ? parsedXmax : 0;
    const sourceDuration = resolveDurationFromSourceIndex(targetSpeaker || speakerId, sourceAudio);
    if (Number.isFinite(sourceDuration) && sourceDuration > durationSec) {
      durationSec = sourceDuration;
    }

    const existing = P.annotations[speakerId];
    const base = makeEmptyRecord(
      speakerId,
      sourceAudio || resolvePrimarySourceWav(targetSpeaker || speakerId),
      durationSec,
      existing
    );

    const tiers = parsed && Array.isArray(parsed.tiers) ? parsed.tiers : [];
    let nextCustomDisplayOrder = 5;

    for (let i = 0; i < tiers.length; i += 1) {
      const tier = tiers[i];
      if (!tier || typeof tier !== 'object') continue;

      const tierName = toText(tier.name).trim();
      if (!tierName) continue;

      const tierKey = tierKeyFromTextGridName(tierName);
      const defaultOrder = CANONICAL_TIER_ORDER[tierKey] || nextCustomDisplayOrder;
      const normalizedTier = normalizeTier(
        {
          type: 'interval',
          display_order: defaultOrder,
          intervals: tier.intervals,
        },
        defaultOrder
      );

      base.tiers[tierKey] = normalizedTier;
      if (!CANONICAL_TIER_ORDER[tierKey]) {
        nextCustomDisplayOrder = Math.max(nextCustomDisplayOrder, normalizedTier.display_order + 1);
      }
    }

    if (!base.tiers.ipa) base.tiers.ipa = emptyTier(1);
    if (!base.tiers.ortho) base.tiers.ortho = emptyTier(2);
    if (!base.tiers.concept) base.tiers.concept = emptyTier(3);
    if (!base.tiers.speaker) base.tiers.speaker = emptyTier(4);

    base.source_audio_duration_sec = Math.max(base.source_audio_duration_sec, computeMaxEndAcrossTiers(base));
    touchRecordMetadata(base, false);
    syncSpeakerTier(base);
    sortAllIntervals(base);

    return base;
  }

  function mergeTierIntervals(targetTier, incomingTier) {
    if (!targetTier || !Array.isArray(targetTier.intervals)) {
      return false;
    }
    if (!incomingTier || !Array.isArray(incomingTier.intervals)) {
      return false;
    }

    let changed = false;

    for (let i = 0; i < incomingTier.intervals.length; i += 1) {
      const normalized = normalizeInterval(incomingTier.intervals[i]);
      if (!normalized) continue;

      changed = upsertInterval(
        targetTier.intervals,
        normalized.start,
        normalized.end,
        normalized.text
      ) || changed;
    }

    return changed;
  }

  function mergeImportedRecord(existingRecord, importedRecord) {
    const merged = normalizeRecord(existingRecord, importedRecord && importedRecord.speaker);
    const incoming = normalizeRecord(importedRecord, importedRecord && importedRecord.speaker);

    let changed = false;

    if (!toText(merged.source_audio).trim() && toText(incoming.source_audio).trim()) {
      merged.source_audio = String(incoming.source_audio);
      changed = true;
    }

    if (incoming.source_audio_duration_sec > merged.source_audio_duration_sec) {
      merged.source_audio_duration_sec = incoming.source_audio_duration_sec;
      changed = true;
    }

    changed = mergeTierIntervals(merged.tiers.ipa, incoming.tiers.ipa) || changed;
    changed = mergeTierIntervals(merged.tiers.ortho, incoming.tiers.ortho) || changed;
    changed = mergeTierIntervals(merged.tiers.concept, incoming.tiers.concept) || changed;

    syncSpeakerTier(merged);
    sortAllIntervals(merged);

    if (changed) {
      touchRecordMetadata(merged, true);
    }

    return merged;
  }

  function readBrowserFileText(file) {
    return new Promise(function (resolve, reject) {
      if (!file) {
        reject(new Error('No TextGrid file provided.'));
        return;
      }

      if (typeof FileReader === 'function') {
        try {
          const reader = new FileReader();
          reader.onload = function () {
            resolve(typeof reader.result === 'string' ? reader.result : String(reader.result || ''));
          };
          reader.onerror = function () {
            reject(reader.error || new Error('Failed to read TextGrid file.'));
          };
          reader.readAsText(file);
          return;
        } catch (error) {
          reject(error);
          return;
        }
      }

      if (typeof file.text === 'function') {
        file.text().then(resolve).catch(reject);
        return;
      }

      reject(new Error('Browser does not support TextGrid file reading.'));
    });
  }

  async function onImportTextGrid(event) {
    const detail = event && event.detail ? event.detail : {};

    const file = detail.file;
    const targetSpeaker = toText(detail.targetSpeaker).trim();
    const rawMode = toText(detail.mode).trim().toLowerCase();
    const mode = rawMode === 'replace' || rawMode === 'new' || rawMode === 'merge'
      ? rawMode
      : 'merge';
    const newSpeakerName = toText(detail.newSpeakerName).trim();

    let importSpeaker = targetSpeaker;
    if (mode === 'new') {
      importSpeaker = newSpeakerName;
    }

    if (!file) {
      dispatchIoComplete('import', 'textgrid', false, 'No TextGrid file provided.');
      return;
    }

    if (!importSpeaker) {
      dispatchIoComplete('import', 'textgrid', false, mode === 'new'
        ? 'Missing new speaker name for TextGrid import.'
        : 'Missing target speaker for TextGrid import.');
      return;
    }

    if (mode === 'new' && P.annotations[importSpeaker]) {
      dispatchIoComplete('import', 'textgrid', false, 'Speaker already exists: ' + importSpeaker);
      return;
    }

    try {
      const textgridText = await readBrowserFileText(file);
      const parsed = parseTextGrid(textgridText);

      const sourceAudio = (mode === 'replace' && P.annotations[targetSpeaker] && P.annotations[targetSpeaker].source_audio)
        ? String(P.annotations[targetSpeaker].source_audio)
        : resolvePrimarySourceWav(targetSpeaker || importSpeaker);

      const record = parsedTextGridToRecord(parsed, importSpeaker, sourceAudio, targetSpeaker || importSpeaker);

      let nextRecord = record;
      if (mode === 'merge') {
        const existingRecord = P.annotations[importSpeaker] || makeEmptyRecord(importSpeaker, sourceAudio, 0, null);
        nextRecord = mergeImportedRecord(existingRecord, record);
      }

      P.annotations[importSpeaker] = nextRecord;
      writeLocalSpeakerSnapshot(importSpeaker, nextRecord);
      scheduleServerSave(importSpeaker);

      dispatchAnnotationsLoaded(importSpeaker);
      dispatchAnnotationsChanged(importSpeaker);
      dispatchIoComplete('import', 'textgrid', true, 'Imported TextGrid for speaker ' + importSpeaker + ' (' + mode + ').');
    } catch (error) {
      logError('TextGrid import failed:', error);
      dispatchIoComplete('import', 'textgrid', false, error.message || 'TextGrid import failed.');
    }
  }

  function textGridQuote(value) {
    return '"' + String(value).replace(/"/g, '""') + '"';
  }

  function formatNumberForTextGrid(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '0';

    const rounded = Math.round(num * 1000000) / 1000000;
    let text = String(rounded);

    if (text.indexOf('e') !== -1 || text.indexOf('E') !== -1) {
      text = rounded.toFixed(6).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
    }

    if (text === '-0') {
      text = '0';
    }

    return text;
  }

  function getOrderedExportTiers(record) {
    const tiers = [];
    if (!record || !record.tiers || typeof record.tiers !== 'object') return tiers;

    for (let i = 0; i < CANONICAL_TIER_KEYS.length; i += 1) {
      const key = CANONICAL_TIER_KEYS[i];
      const tier = record.tiers[key] && typeof record.tiers[key] === 'object'
        ? record.tiers[key]
        : emptyTier(CANONICAL_TIER_ORDER[key]);

      const intervalsRaw = Array.isArray(tier.intervals) ? tier.intervals : [];
      const intervals = [];
      for (let j = 0; j < intervalsRaw.length; j += 1) {
        const normalized = normalizeInterval(intervalsRaw[j]);
        if (normalized) intervals.push(normalized);
      }

      tiers.push({
        key: key,
        name: tierNameForTextGrid(key),
        displayOrder: CANONICAL_TIER_ORDER[key],
        intervals: intervals,
      });
    }

    return tiers;
  }

  function fillTextGridIntervalGaps(intervals, durationSec) {
    const duration = Math.max(0, toFiniteNumber(durationSec) || 0);

    const contentIntervals = [];
    for (let i = 0; i < intervals.length; i += 1) {
      const interval = intervals[i];
      if (!interval) continue;
      if (toText(interval.text).trim() === '') continue;
      contentIntervals.push(interval);
    }

    contentIntervals.sort(function (left, right) {
      return (left.start - right.start) || (left.end - right.end);
    });

    const filled = [];
    let cursor = 0;

    for (let i = 0; i < contentIntervals.length; i += 1) {
      const interval = contentIntervals[i];
      const start = Math.max(0, interval.start);
      const end = Math.max(start, interval.end);

      if (start > cursor + MATCH_EPSILON) {
        filled.push({
          start: cursor,
          end: start,
          text: '',
        });
      }

      filled.push({
        start: start,
        end: end,
        text: interval.text,
      });

      if (end > cursor) {
        cursor = end;
      }
    }

    if (duration > cursor + MATCH_EPSILON) {
      filled.push({
        start: cursor,
        end: duration,
        text: '',
      });
    }

    if (filled.length === 0) {
      filled.push({
        start: 0,
        end: duration,
        text: '',
      });
    }

    return filled;
  }

  function serializeTextGrid(record) {
    const tiers = getOrderedExportTiers(record);
    const maxEnd = computeMaxEndAcrossTiers(record);
    const durationRaw = toFiniteNumber(record && record.source_audio_duration_sec);
    const duration = Math.max(0, durationRaw || 0, maxEnd);

    const lines = [
      'File type = "ooTextFile"',
      'Object class = "TextGrid"',
      '',
      'xmin = ' + formatNumberForTextGrid(0),
      'xmax = ' + formatNumberForTextGrid(duration),
      'tiers? <exists>',
      'size = ' + String(tiers.length),
      'item []:',
    ];

    for (let t = 0; t < tiers.length; t += 1) {
      const tier = tiers[t];
      const intervals = fillTextGridIntervalGaps(tier.intervals, duration);

      lines.push('    item [' + String(t + 1) + ']:');
      lines.push('        class = "IntervalTier"');
      lines.push('        name = ' + textGridQuote(tier.name));
      lines.push('        xmin = ' + formatNumberForTextGrid(0));
      lines.push('        xmax = ' + formatNumberForTextGrid(duration));
      lines.push('        intervals: size = ' + String(intervals.length));

      for (let i = 0; i < intervals.length; i += 1) {
        const interval = intervals[i];
        lines.push('        intervals [' + String(i + 1) + ']:');
        lines.push('            xmin = ' + formatNumberForTextGrid(interval.start));
        lines.push('            xmax = ' + formatNumberForTextGrid(interval.end));
        lines.push('            text = ' + textGridQuote(interval.text));
      }
    }

    return lines.join('\n') + '\n';
  }

  function escapeXmlText(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeXmlAttr(value) {
    return escapeXmlText(value)
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  function sourceMimeType(sourceAudio) {
    const lower = toText(sourceAudio).toLowerCase();
    if (lower.endsWith('.mp3')) return 'audio/mpeg';
    if (lower.endsWith('.wav')) return 'audio/x-wav';
    if (lower.endsWith('.flac')) return 'audio/flac';
    if (lower.endsWith('.m4a') || lower.endsWith('.aac')) return 'audio/mp4';
    return 'audio/x-wav';
  }

  function serializeElan(record) {
    const tiers = getOrderedExportTiers(record);

    const timeSet = Object.create(null);
    const elanTiers = [];

    for (let i = 0; i < tiers.length; i += 1) {
      const tier = tiers[i];
      const annotations = [];

      for (let j = 0; j < tier.intervals.length; j += 1) {
        const interval = tier.intervals[j];
        const text = toText(interval.text);
        if (text.trim() === '') continue;

        const startMs = Math.round(interval.start * 1000);
        const endMs = Math.round(interval.end * 1000);
        if (endMs < startMs) continue;

        timeSet[String(startMs)] = true;
        timeSet[String(endMs)] = true;

        annotations.push({
          startMs: startMs,
          endMs: endMs,
          text: text,
        });
      }

      elanTiers.push({
        tierId: tier.name,
        annotations: annotations,
      });
    }

    const times = Object.keys(timeSet)
      .map(function (value) { return Number(value); })
      .filter(function (value) { return Number.isFinite(value); })
      .sort(function (a, b) { return a - b; });

    const slotByTime = Object.create(null);
    for (let i = 0; i < times.length; i += 1) {
      slotByTime[times[i]] = 'ts' + String(i + 1);
    }

    let annotationIdCounter = 1;
    const lines = [];

    lines.push('<?xml version="1.0" encoding="UTF-8"?>');
    lines.push(
      '<ANNOTATION_DOCUMENT AUTHOR="" DATE="' + escapeXmlAttr(nowIsoUtc()) +
      '" FORMAT="3.0" VERSION="3.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' +
      'xsi:noNamespaceSchemaLocation="http://www.mpi.nl/tools/elan/EAFv3.0.xsd">'
    );
    lines.push('  <HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">');
    lines.push(
      '    <MEDIA_DESCRIPTOR MEDIA_URL="' + escapeXmlAttr(toText(record.source_audio)) +
      '" MIME_TYPE="' + escapeXmlAttr(sourceMimeType(record.source_audio)) +
      '" RELATIVE_MEDIA_URL="" />'
    );
    lines.push('    <PROPERTY NAME="lastUsedAnnotationId">0</PROPERTY>');
    lines.push('  </HEADER>');
    lines.push('  <TIME_ORDER>');

    for (let i = 0; i < times.length; i += 1) {
      const time = times[i];
      lines.push(
        '    <TIME_SLOT TIME_SLOT_ID="' + slotByTime[time] + '" TIME_VALUE="' + String(time) + '" />'
      );
    }

    lines.push('  </TIME_ORDER>');

    for (let t = 0; t < elanTiers.length; t += 1) {
      const tier = elanTiers[t];
      lines.push('  <TIER LINGUISTIC_TYPE_REF="default-lt" TIER_ID="' + escapeXmlAttr(tier.tierId) + '">');

      for (let i = 0; i < tier.annotations.length; i += 1) {
        const ann = tier.annotations[i];
        lines.push('    <ANNOTATION>');
        lines.push(
          '      <ALIGNABLE_ANNOTATION ANNOTATION_ID="a' + String(annotationIdCounter) +
          '" TIME_SLOT_REF1="' + slotByTime[ann.startMs] +
          '" TIME_SLOT_REF2="' + slotByTime[ann.endMs] + '">'
        );
        lines.push('        <ANNOTATION_VALUE>' + escapeXmlText(ann.text) + '</ANNOTATION_VALUE>');
        lines.push('      </ALIGNABLE_ANNOTATION>');
        lines.push('    </ANNOTATION>');
        annotationIdCounter += 1;
      }

      lines.push('  </TIER>');
    }

    lines.push('  <LINGUISTIC_TYPE GRAPHIC_REFERENCES="false" LINGUISTIC_TYPE_ID="default-lt" TIME_ALIGNABLE="true" />');
    lines.push('</ANNOTATION_DOCUMENT>');

    return lines.join('\n') + '\n';
  }

  function intervalOverlapSeconds(aStart, aEnd, bStart, bEnd) {
    if (!(aStart < bEnd && aEnd > bStart)) return 0;
    return Math.min(aEnd, bEnd) - Math.max(aStart, bStart);
  }

  function bestTextMatchByTime(intervals, startSec, endSec) {
    if (!Array.isArray(intervals) || !intervals.length) return '';

    for (let i = 0; i < intervals.length; i += 1) {
      const interval = intervals[i];
      if (
        interval &&
        approxEqual(interval.start, startSec, MATCH_EPSILON) &&
        approxEqual(interval.end, endSec, MATCH_EPSILON)
      ) {
        return toText(interval.text);
      }
    }

    let bestText = '';
    let bestOverlap = 0;

    for (let i = 0; i < intervals.length; i += 1) {
      const interval = intervals[i];
      if (!interval) continue;

      const overlap = intervalOverlapSeconds(startSec, endSec, interval.start, interval.end);
      if (overlap > bestOverlap) {
        bestOverlap = overlap;
        bestText = toText(interval.text);
      }
    }

    return bestText;
  }

  function formatCsvSeconds(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '';
    const rounded = Math.round(num * 1000000) / 1000000;
    let text = rounded.toFixed(6);
    text = text.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
    if (text === '-0') text = '0';
    return text;
  }

  function csvEscape(value) {
    const text = value == null ? '' : String(value);
    if (/[",\r\n]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function rowsToCsv(rows) {
    const columns = [
      'speaker',
      'concept_id',
      'concept_en',
      'start_sec',
      'end_sec',
      'duration_sec',
      'ipa',
      'ortho',
      'source_file',
    ];

    const lines = [columns.join(',')];

    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i] || {};
      const line = columns.map(function (column) {
        return csvEscape(row[column]);
      }).join(',');
      lines.push(line);
    }

    return lines.join('\r\n') + '\r\n';
  }

  function buildCsvRowsForSpeaker(speaker, record) {
    const rows = [];
    if (!record || !record.tiers || typeof record.tiers !== 'object') {
      return rows;
    }

    const conceptTier = record.tiers.concept && Array.isArray(record.tiers.concept.intervals)
      ? record.tiers.concept.intervals
      : [];
    const ipaTier = record.tiers.ipa && Array.isArray(record.tiers.ipa.intervals)
      ? record.tiers.ipa.intervals
      : [];
    const orthoTier = record.tiers.ortho && Array.isArray(record.tiers.ortho.intervals)
      ? record.tiers.ortho.intervals
      : [];

    const sourceFile = toText(record.source_audio).trim();

    for (let i = 0; i < ipaTier.length; i += 1) {
      const ipaInterval = ipaTier[i];
      if (!ipaInterval) continue;

      const ipaText = toText(ipaInterval.text).trim();
      if (!ipaText) {
        continue;
      }

      const startSec = ipaInterval.start;
      const endSec = ipaInterval.end;
      const durationSec = Math.max(0, endSec - startSec);
      const conceptText = toText(bestTextMatchByTime(conceptTier, startSec, endSec)).trim();
      const orthoText = toText(bestTextMatchByTime(orthoTier, startSec, endSec));
      const split = splitConceptText(conceptText);
      let conceptId = split.conceptId;
      let conceptEn = split.conceptEn;

      if (!conceptId && !conceptEn && conceptText) {
        conceptId = normalizeConceptId(conceptText);
      }

      rows.push({
        speaker: speaker,
        concept_id: conceptId,
        concept_en: conceptEn,
        start_sec: formatCsvSeconds(startSec),
        end_sec: formatCsvSeconds(endSec),
        duration_sec: formatCsvSeconds(durationSec),
        ipa: ipaText,
        ortho: orthoText,
        source_file: sourceFile,
        _startSort: startSec,
        _endSort: endSec,
      });
    }

    rows.sort(function (left, right) {
      return (left._startSort - right._startSort) || (left._endSort - right._endSort);
    });

    return rows;
  }

  function serializeCsvForSpeakers(speakerIds) {
    const speakers = Array.isArray(speakerIds) ? speakerIds : [];
    const rows = [];

    for (let i = 0; i < speakers.length; i += 1) {
      const speaker = speakers[i];
      const record = P.annotations[speaker];
      const speakerRows = buildCsvRowsForSpeaker(speaker, record);
      for (let j = 0; j < speakerRows.length; j += 1) {
        rows.push(speakerRows[j]);
      }
    }

    rows.sort(function (left, right) {
      return left.speaker.localeCompare(right.speaker) ||
        (left._startSort - right._startSort) ||
        (left._endSort - right._endSort);
    });

    return rowsToCsv(rows);
  }

  function collectSegmentRows(speakerIds) {
    const speakers = Array.isArray(speakerIds) ? speakerIds : [];
    const rows = [];

    for (let i = 0; i < speakers.length; i += 1) {
      const speaker = speakers[i];
      const record = P.annotations[speaker];
      if (!record || !record.tiers || !record.tiers.concept || !Array.isArray(record.tiers.concept.intervals)) {
        continue;
      }

      const sourceAudio = toText(record.source_audio);
      const conceptIntervals = record.tiers.concept.intervals;

      for (let j = 0; j < conceptIntervals.length; j += 1) {
        const interval = conceptIntervals[j];
        if (!interval) continue;

        const conceptText = toText(interval.text).trim();
        if (!conceptText) continue;

        const split = splitConceptText(conceptText);

        rows.push({
          speaker: speaker,
          concept_id: split.conceptId || normalizeConceptId(conceptText),
          concept_en: split.conceptEn || '',
          concept: conceptText,
          start_sec: interval.start,
          end_sec: interval.end,
          source_audio: sourceAudio,
        });
      }
    }

    rows.sort(function (left, right) {
      return left.speaker.localeCompare(right.speaker) || (left.start_sec - right.start_sec);
    });

    return rows;
  }

  function triggerDownload(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType || 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');

    anchor.href = url;
    anchor.download = filename;
    anchor.style.display = 'none';

    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 0);
  }

  async function resolveSpeakerIdsForExport(requestedSpeaker) {
    const target = toText(requestedSpeaker).trim();

    if (target === 'all') {
      const seen = Object.create(null);
      const speakerIds = [];
      const loadedSpeakers = Object.keys(P.annotations || {});
      const indexedSpeakers = getSourceIndexSpeakerIds();

      function addSpeakerId(speakerId) {
        const normalized = toText(speakerId).trim();
        if (!normalized || seen[normalized]) {
          return;
        }
        seen[normalized] = true;
        speakerIds.push(normalized);
      }

      for (let i = 0; i < indexedSpeakers.length; i += 1) {
        addSpeakerId(indexedSpeakers[i]);
      }
      for (let i = 0; i < loadedSpeakers.length; i += 1) {
        addSpeakerId(loadedSpeakers[i]);
      }

      speakerIds.sort();
      await Promise.all(speakerIds.map(function (speakerId) {
        return loadSpeaker(speakerId).catch(function () {
          return null;
        });
      }));

      return speakerIds;
    }

    if (!target) {
      return [];
    }

    const record = P.annotations[target] || await loadSpeaker(target);
    return record ? [target] : [];
  }

  async function onExportTextGrid(event) {
    const detail = event && event.detail ? event.detail : {};
    const speaker = toText(detail.speaker).trim();

    if (!speaker) {
      dispatchIoComplete('export', 'textgrid', false, 'Missing speaker for TextGrid export.');
      return;
    }

    try {
      const record = P.annotations[speaker] || await loadSpeaker(speaker);
      if (!record) {
        throw new Error('No annotations found for speaker ' + speaker);
      }

      const textgrid = serializeTextGrid(record);
      triggerDownload(textgrid, speaker + '.TextGrid', 'text/plain;charset=utf-8');
      dispatchIoComplete('export', 'textgrid', true, 'TextGrid exported for ' + speaker + '.');
    } catch (error) {
      logError('TextGrid export failed:', error);
      dispatchIoComplete('export', 'textgrid', false, error.message || 'TextGrid export failed.');
    }
  }

  async function onExportElan(event) {
    const detail = event && event.detail ? event.detail : {};
    const speaker = toText(detail.speaker).trim();

    if (!speaker) {
      dispatchIoComplete('export', 'elan', false, 'Missing speaker for ELAN export.');
      return;
    }

    try {
      const record = P.annotations[speaker] || await loadSpeaker(speaker);
      if (!record) {
        throw new Error('No annotations found for speaker ' + speaker);
      }

      const xml = serializeElan(record);
      triggerDownload(xml, speaker + '.eaf', 'application/xml;charset=utf-8');
      dispatchIoComplete('export', 'elan', true, 'ELAN export complete for ' + speaker + '.');
    } catch (error) {
      logError('ELAN export failed:', error);
      dispatchIoComplete('export', 'elan', false, error.message || 'ELAN export failed.');
    }
  }

  async function onExportCsv(event) {
    const detail = event && event.detail ? event.detail : {};
    const requestedSpeaker = toText(detail.speaker).trim();

    if (!requestedSpeaker) {
      dispatchIoComplete('export', 'csv', false, 'Missing speaker for CSV export.');
      return;
    }

    const filename = requestedSpeaker === 'all'
      ? 'all_annotations.csv'
      : requestedSpeaker + '.csv';

    try {
      const speakerIds = await resolveSpeakerIdsForExport(requestedSpeaker);
      if (!speakerIds.length) {
        throw new Error(requestedSpeaker === 'all'
          ? 'No loaded speakers available for CSV export.'
          : 'No annotations found for speaker ' + requestedSpeaker + '.');
      }

      const csv = serializeCsvForSpeakers(speakerIds);
      triggerDownload(csv, filename, 'text/csv;charset=utf-8');
      dispatchIoComplete('export', 'csv', true, 'CSV export complete.');
    } catch (error) {
      logError('CSV export failed:', error);
      dispatchIoComplete('export', 'csv', false, error.message || 'CSV export failed.');
    }
  }

  async function onExportSegments(event) {
    const detail = event && event.detail ? event.detail : {};
    const requestedSpeaker = toText(detail.speaker).trim();

    if (!requestedSpeaker) {
      dispatchIoComplete('export', 'segments', false, 'Missing speaker for segment export.');
      return;
    }

    const manifestFilename = requestedSpeaker === 'all'
      ? 'all_segments_manifest.json'
      : requestedSpeaker + '_segments_manifest.json';

    try {
      const speakerIds = await resolveSpeakerIdsForExport(requestedSpeaker);
      if (!speakerIds.length) {
        throw new Error(requestedSpeaker === 'all'
          ? 'No loaded speakers available for segment export.'
          : 'No annotations found for speaker ' + requestedSpeaker + '.');
      }

      const segmentRows = collectSegmentRows(speakerIds);
      if (!segmentRows.length) {
        throw new Error('No concept intervals available to export as segments.');
      }

      const payload = {
        speaker: requestedSpeaker === 'all' ? 'all' : speakerIds[0],
        segments: segmentRows,
      };

      try {
        const response = await fetch(API_EXPORT_SEGMENTS, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error('HTTP ' + response.status + ' from segment export endpoint');
        }

        let responseJson = null;
        try {
          responseJson = await response.json();
        } catch (_) {
          responseJson = null;
        }

        if (responseJson && responseJson.download_url) {
          window.location.href = String(responseJson.download_url);
        }

        dispatchIoComplete('export', 'segments', true, responseJson && responseJson.message
          ? String(responseJson.message)
          : 'Segment export requested successfully.');
      } catch (error) {
        logWarn('Segment export endpoint unavailable; downloading JSON manifest fallback.', error);

        const fallbackManifest = {
          generated_at: nowIsoUtc(),
          requested_speaker: requestedSpeaker,
          segments: segmentRows,
        };

        triggerDownload(
          JSON.stringify(fallbackManifest, null, 2),
          manifestFilename,
          'application/json;charset=utf-8'
        );

        dispatchIoComplete(
          'export',
          'segments',
          true,
          'Server unavailable. Downloaded segment manifest JSON instead.'
        );
      }
    } catch (error) {
      logError('Segment export failed:', error);
      dispatchIoComplete('export', 'segments', false, error.message || 'Segment export failed.');
    }
  }

  function bindListeners() {
    if (state.listenersBound) return;

    document.addEventListener('parse:annotation-save', onAnnotationSave);
    document.addEventListener('parse:annotation-delete', onAnnotationDelete);

    state.onImportTextGridEvent = function (event) {
      onImportTextGrid(event).catch(function (error) {
        logError('Unhandled TextGrid import error:', error);
        dispatchIoComplete('import', 'textgrid', false, error.message || 'TextGrid import failed.');
      });
    };
    document.addEventListener('parse:import-textgrid', state.onImportTextGridEvent);

    state.onExportTextGridEvent = function (event) {
      onExportTextGrid(event).catch(function (error) {
        logError('Unhandled TextGrid export error:', error);
        dispatchIoComplete('export', 'textgrid', false, error.message || 'TextGrid export failed.');
      });
    };
    document.addEventListener('parse:export-textgrid', state.onExportTextGridEvent);

    state.onExportElanEvent = function (event) {
      onExportElan(event).catch(function (error) {
        logError('Unhandled ELAN export error:', error);
        dispatchIoComplete('export', 'elan', false, error.message || 'ELAN export failed.');
      });
    };
    document.addEventListener('parse:export-elan', state.onExportElanEvent);

    state.onExportCsvEvent = function (event) {
      onExportCsv(event).catch(function (error) {
        logError('Unhandled CSV export error:', error);
        dispatchIoComplete('export', 'csv', false, error.message || 'CSV export failed.');
      });
    };
    document.addEventListener('parse:export-csv', state.onExportCsvEvent);

    state.onExportSegmentsEvent = function (event) {
      onExportSegments(event).catch(function (error) {
        logError('Unhandled segments export error:', error);
        dispatchIoComplete('export', 'segments', false, error.message || 'Segment export failed.');
      });
    };
    document.addEventListener('parse:export-segments', state.onExportSegmentsEvent);

    state.listenersBound = true;
  }

  function unbindListeners() {
    if (!state.listenersBound) return;

    document.removeEventListener('parse:annotation-save', onAnnotationSave);
    document.removeEventListener('parse:annotation-delete', onAnnotationDelete);

    if (state.onImportTextGridEvent) {
      document.removeEventListener('parse:import-textgrid', state.onImportTextGridEvent);
      state.onImportTextGridEvent = null;
    }
    if (state.onExportTextGridEvent) {
      document.removeEventListener('parse:export-textgrid', state.onExportTextGridEvent);
      state.onExportTextGridEvent = null;
    }
    if (state.onExportElanEvent) {
      document.removeEventListener('parse:export-elan', state.onExportElanEvent);
      state.onExportElanEvent = null;
    }
    if (state.onExportCsvEvent) {
      document.removeEventListener('parse:export-csv', state.onExportCsvEvent);
      state.onExportCsvEvent = null;
    }
    if (state.onExportSegmentsEvent) {
      document.removeEventListener('parse:export-segments', state.onExportSegmentsEvent);
      state.onExportSegmentsEvent = null;
    }

    state.listenersBound = false;
  }

  function clearAutosaveTimers() {
    const timerSpeakers = Object.keys(state.autosaveTimers);
    for (let i = 0; i < timerSpeakers.length; i += 1) {
      clearTimeout(state.autosaveTimers[timerSpeakers[i]]);
      delete state.autosaveTimers[timerSpeakers[i]];
    }
  }

  /**
   * init - bind event listeners and load all known speakers.
   */
  function init() {
    if (state.initialized) {
      return P.modules.annotationStore;
    }

    P.annotations = P.annotations && typeof P.annotations === 'object'
      ? P.annotations
      : {};

    bindListeners();
    state.initialized = true;

    loadInitialSpeakers().catch(function (error) {
      logWarn('Initial speaker load failed:', error);
    });

    return P.modules.annotationStore;
  }

  /**
   * destroy - cleanup timers and listeners.
   */
  function destroy() {
    clearAutosaveTimers();
    unbindListeners();
    state.initialized = false;
  }

  function getSpeakerRecord(speaker) {
    const speakerId = toText(speaker).trim();
    if (!speakerId) return null;
    return P.annotations[speakerId] || null;
  }

  P.modules.annotationStore = {
    init: init,
    destroy: destroy,
    loadSpeaker: loadSpeaker,
    getSpeakerRecord: getSpeakerRecord,
    serializeTextGrid: serializeTextGrid,
    serializeElan: serializeElan,
    serializeCsvForSpeakers: serializeCsvForSpeakers,
  };
})();
