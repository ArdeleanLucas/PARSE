(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const HISTORY_LIMIT = 20;
  const HISTORY_FIELD = '_history';
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

  function normalizeTimestamp(value) {
    const text = String(value == null ? '' : value).trim();
    if (!text) return '';

    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) {
      return '';
    }

    return parsed.toISOString();
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

  function normalizeIncludeInAnalysisOverrides(rawOverrides) {
    const overridesIn = toObject(rawOverrides);
    const overridesOut = {};

    const keys = Object.keys(overridesIn);
    for (let i = 0; i < keys.length; i += 1) {
      const conceptId = normalizeConceptId(keys[i]);
      if (!conceptId) continue;

      if (overridesIn[keys[i]] === false) {
        overridesOut[conceptId] = false;
      }
    }

    return overridesOut;
  }

  function normalizeManualOverrides(rawManualOverrides) {
    const overridesIn = toObject(rawManualOverrides);
    const overridesOut = deepClone(overridesIn);

    overridesOut.cognate_sets = normalizeManualCognateSets(overridesIn.cognate_sets);
    overridesOut.borrowing_flags = toObject(overridesIn.borrowing_flags);
    overridesOut.accepted_concepts = toObject(overridesIn.accepted_concepts);
    overridesOut.include_in_analysis = normalizeIncludeInAnalysisOverrides(overridesIn.include_in_analysis);

    return overridesOut;
  }

  function normalizeEnrichmentsCore(rawEnrichments) {
    const source = toObject(rawEnrichments);

    return {
      computed_at: typeof source.computed_at === 'string' ? source.computed_at : null,
      config: toObject(source.config),
      cognate_sets: normalizeCognateSets(source.cognate_sets),
      similarity: toObject(source.similarity),
      borrowing_flags: toObject(source.borrowing_flags),
      manual_overrides: normalizeManualOverrides(source.manual_overrides),
    };
  }

  function snapshotDataFromEnrichments(rawEnrichments) {
    return deepClone(normalizeEnrichmentsCore(rawEnrichments));
  }

  function formatSnapshotFilename(timestamp) {
    const normalized = normalizeTimestamp(timestamp) || nowIso();
    let base = normalized;

    if (base.charAt(base.length - 1) === 'Z') {
      base = base.slice(0, -1);
    }

    const dotIndex = base.indexOf('.');
    if (dotIndex !== -1) {
      base = base.slice(0, dotIndex);
    }

    base = base.replace(/:/g, '-');
    return 'snapshot-' + base + '.json';
  }

  function hasSnapshotData(value) {
    const data = toObject(value);
    return (
      !!data.computed_at ||
      !!data.config ||
      !!data.cognate_sets ||
      !!data.similarity ||
      !!data.borrowing_flags ||
      !!data.manual_overrides
    );
  }

  function normalizeHistoryEntry(rawEntry) {
    const entry = toObject(rawEntry);
    if (!entry || !Object.keys(entry).length) {
      return null;
    }

    const timestamp = normalizeTimestamp(entry.timestamp || entry.saved_at || entry.created_at || entry.modified_at) || nowIso();
    const reason = String(entry.reason || 'snapshot').trim() || 'snapshot';

    const directData = toObject(entry.data);
    const legacyData = {
      computed_at: entry.computed_at,
      config: entry.config,
      cognate_sets: entry.cognate_sets,
      similarity: entry.similarity,
      borrowing_flags: entry.borrowing_flags,
      manual_overrides: entry.manual_overrides,
    };

    const payload = hasSnapshotData(directData) ? directData : legacyData;
    const normalizedData = snapshotDataFromEnrichments(payload);

    return {
      timestamp: timestamp,
      filename: String(entry.filename || formatSnapshotFilename(timestamp)).trim() || formatSnapshotFilename(timestamp),
      reason: reason,
      data: normalizedData,
    };
  }

  function normalizeHistory(rawHistory) {
    if (!Array.isArray(rawHistory)) {
      return [];
    }

    const out = [];
    for (let i = 0; i < rawHistory.length; i += 1) {
      const normalizedEntry = normalizeHistoryEntry(rawHistory[i]);
      if (normalizedEntry) {
        out.push(normalizedEntry);
      }
    }

    if (out.length <= HISTORY_LIMIT) {
      return out;
    }

    return out.slice(out.length - HISTORY_LIMIT);
  }

  function ensureEnrichmentsShape(rawEnrichments) {
    const source = toObject(rawEnrichments);
    const enrichments = normalizeEnrichmentsCore(source);

    enrichments[HISTORY_FIELD] = normalizeHistory(source[HISTORY_FIELD] || source.history);
    return enrichments;
  }

  function addNormalizedConceptIds(targetSet, source) {
    const object = toObject(source);
    const keys = Object.keys(object);
    for (let i = 0; i < keys.length; i += 1) {
      const conceptId = normalizeConceptId(keys[i]);
      if (conceptId) {
        targetSet.add(conceptId);
      }
    }
  }

  function conceptIdsFromEnrichments(enrichments) {
    const ids = new Set();

    addNormalizedConceptIds(ids, enrichments.cognate_sets);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).cognate_sets);
    addNormalizedConceptIds(ids, enrichments.borrowing_flags);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).borrowing_flags);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).accepted_concepts);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).include_in_analysis);

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

  function getHistoryEntries(enrichments) {
    return normalizeHistory(toObject(enrichments)[HISTORY_FIELD]);
  }

  function setHistoryEntries(enrichments, historyEntries) {
    const normalized = normalizeHistory(historyEntries);
    toObject(enrichments)[HISTORY_FIELD] = normalized;
    return normalized;
  }

  function buildVersionSnapshot(reason) {
    const enrichments = getCurrentEnrichments();
    const timestamp = nowIso();
    return {
      timestamp: timestamp,
      filename: formatSnapshotFilename(timestamp),
      reason: String(reason || 'manual-update'),
      data: snapshotDataFromEnrichments(enrichments),
    };
  }

  function appendHistory(reason) {
    const enrichments = getCurrentEnrichments();
    const history = getHistoryEntries(enrichments);
    const snapshot = normalizeHistoryEntry(buildVersionSnapshot(reason));
    const nextHistory = history.concat(snapshot ? [snapshot] : []);
    setHistoryEntries(enrichments, nextHistory);
    return snapshot;
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

  function normalizeBorrowingDecision(value) {
    if (typeof value === 'boolean') {
      return value ? 'borrowed' : 'native';
    }

    const raw = String(value == null ? '' : value).trim().toLowerCase();
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

  function normalizeSourceLanguage(value) {
    return String(value == null ? '' : value).trim().toLowerCase();
  }

  function normalizeBorrowingRecord(entry) {
    const out = {
      decision: '',
      source: '',
      handling: '',
    };

    if (entry == null) {
      return out;
    }

    if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
      const objectEntry = toObject(entry);
      out.decision = normalizeBorrowingDecision(
        objectEntry.decision != null
          ? objectEntry.decision
          : (objectEntry.status != null ? objectEntry.status : objectEntry.value)
      );

      out.source = normalizeSourceLanguage(
        objectEntry.source != null
          ? objectEntry.source
          : (objectEntry.sourceLang != null
            ? objectEntry.sourceLang
            : (objectEntry.source_lang != null
              ? objectEntry.source_lang
              : (objectEntry.lang != null ? objectEntry.lang : objectEntry.language)))
      );

      out.handling = String(objectEntry.handling == null ? '' : objectEntry.handling).trim().toLowerCase();

      if (!out.decision && typeof objectEntry.borrowed === 'boolean') {
        out.decision = objectEntry.borrowed ? 'borrowed' : 'native';
      }
    } else {
      out.decision = normalizeBorrowingDecision(entry);
    }

    if (out.decision === 'skip') {
      out.decision = '';
    }

    if (!out.decision && out.source) {
      out.decision = 'borrowed';
    }

    if (out.decision && out.decision !== 'borrowed') {
      out.source = '';
    }

    return out;
  }

  function hasBorrowingData(record) {
    const normalized = toObject(record);
    return !!(
      String(normalized.decision || '').trim() ||
      String(normalized.source || '').trim() ||
      String(normalized.handling || '').trim()
    );
  }

  function mergeBorrowingRecord(baseRecord, patchRecord) {
    const base = normalizeBorrowingRecord(baseRecord);
    const patch = normalizeBorrowingRecord(patchRecord);

    if (patch.decision) {
      base.decision = patch.decision;
    }

    if (patch.handling) {
      base.handling = patch.handling;
    }

    if (patch.source && (patch.decision === 'borrowed' || base.decision === 'borrowed' || !base.decision)) {
      base.source = patch.source;
      if (!base.decision) {
        base.decision = 'borrowed';
      }
    }

    if (base.decision && base.decision !== 'borrowed') {
      base.source = '';
    }

    return hasBorrowingData(base) ? base : null;
  }

  function absorbBorrowingConceptNode(targetConceptMap, conceptNode) {
    const node = toObject(conceptNode);
    const directKeys = Object.keys(node);
    const reserved = {
      speakers: true,
      updated_at: true,
      updatedAt: true,
      note: true,
      notes: true,
      status: true,
      decision: true,
      handling: true,
      source: true,
      source_lang: true,
      sourceLang: true,
      value: true,
      borrowed: true,
    };

    for (let i = 0; i < directKeys.length; i += 1) {
      const speakerKey = String(directKeys[i] == null ? '' : directKeys[i]).trim();
      if (!speakerKey || reserved[speakerKey]) continue;

      const merged = mergeBorrowingRecord(targetConceptMap[speakerKey], node[directKeys[i]]);
      if (merged) {
        targetConceptMap[speakerKey] = merged;
      }
    }

    const nested = toObject(node.speakers);
    const nestedKeys = Object.keys(nested);
    for (let i = 0; i < nestedKeys.length; i += 1) {
      const speakerKey = String(nestedKeys[i] == null ? '' : nestedKeys[i]).trim();
      if (!speakerKey) continue;

      const merged = mergeBorrowingRecord(targetConceptMap[speakerKey], nested[nestedKeys[i]]);
      if (merged) {
        targetConceptMap[speakerKey] = merged;
      }
    }
  }

  function collectBorrowingDecisionMap(enrichments) {
    const out = {};
    const source = toObject(enrichments);

    function absorb(flagsSource) {
      const flags = toObject(flagsSource);
      const conceptKeys = Object.keys(flags);
      for (let i = 0; i < conceptKeys.length; i += 1) {
        const conceptId = normalizeConceptId(conceptKeys[i]);
        if (!conceptId) continue;

        if (!out[conceptId]) {
          out[conceptId] = {};
        }

        absorbBorrowingConceptNode(out[conceptId], flags[conceptKeys[i]]);

        if (!Object.keys(out[conceptId]).length) {
          delete out[conceptId];
        }
      }
    }

    absorb(source.borrowing_flags);
    absorb(toObject(source.manual_overrides).borrowing_flags);
    return out;
  }

  function getIncludeInAnalysisOverrideMap(enrichments) {
    const overrides = toObject(toObject(enrichments).manual_overrides);
    return normalizeIncludeInAnalysisOverrides(overrides.include_in_analysis);
  }

  function getGlobalIncludedMap() {
    return normalizeIncludeInAnalysisOverrides(toObject(P.tags).included);
  }

  function isIncludedInAnalysis(conceptId, enrichments) {
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return true;

    const localOverrides = getIncludeInAnalysisOverrideMap(enrichments);
    if (Object.prototype.hasOwnProperty.call(localOverrides, conceptKey)) {
      return localOverrides[conceptKey] !== false;
    }

    const globalIncluded = getGlobalIncludedMap();
    if (Object.prototype.hasOwnProperty.call(globalIncluded, conceptKey)) {
      return globalIncluded[conceptKey] !== false;
    }

    return true;
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

  function setIncludeInAnalysis(conceptId, included) {
    const enrichments = getCurrentEnrichments();
    const conceptKey = normalizeConceptId(conceptId);
    if (!conceptKey) return;

    const overrides = toObject(enrichments.manual_overrides.include_in_analysis);
    if (included === false) {
      overrides[conceptKey] = false;
    } else {
      delete overrides[conceptKey];
    }

    enrichments.manual_overrides.include_in_analysis = overrides;

    emitEnrichmentsUpdated();
    scheduleWrite('analysis-toggle');
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
    const speaker = detail.speaker || detail.speakerId;
    upsertBorrowingOverride(detail.conceptId, speaker, {
      status: detail.status,
      updated_at: nowIso(),
    });
  }

  function onBorrowingHandle(event) {
    const detail = toObject(event && event.detail);
    const speaker = detail.speaker || detail.speakerId;
    upsertBorrowingOverride(detail.conceptId, speaker, {
      handling: detail.handling,
      updated_at: nowIso(),
    });
  }

  function onBorrowingDecision(event) {
    const detail = toObject(event && event.detail);
    const speaker = detail.speaker || detail.speakerId;
    const patch = {
      decision: detail.decision,
      updated_at: nowIso(),
    };

    const sourceLanguage = detail.sourceLang != null ? detail.sourceLang : detail.source;
    if (sourceLanguage != null && String(sourceLanguage).trim()) {
      patch.source_lang = sourceLanguage;
    }

    const normalizedDecision = normalizeBorrowingDecision(detail.decision);
    if (normalizedDecision && normalizedDecision !== 'borrowed') {
      patch.source_lang = '';
    }

    upsertBorrowingOverride(detail.conceptId, speaker, patch);
  }

  function onAnalysisToggle(event) {
    const detail = toObject(event && event.detail);
    setIncludeInAnalysis(detail.conceptId, detail.included !== false);
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

  function compareConceptIdOrder(leftId, rightId) {
    const leftNum = Number(leftId);
    const rightNum = Number(rightId);

    if (Number.isFinite(leftNum) && Number.isFinite(rightNum)) {
      return leftNum - rightNum;
    }

    return String(leftId).localeCompare(String(rightId));
  }

  function parseConceptMeta(rawEntry, index) {
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

    const conceptId = normalizeConceptId(rawId || String(index + 1));
    if (!conceptId) {
      return null;
    }

    return {
      id: conceptId,
      label: String(label == null ? '' : label).trim(),
    };
  }

  function getConceptLabelMap() {
    const out = {};
    const compareState = toObject(P.compareState);
    const lists = [];

    if (Array.isArray(compareState.concepts)) {
      lists.push(compareState.concepts);
    }

    if (Array.isArray(compareState.filteredConcepts)) {
      lists.push(compareState.filteredConcepts);
    }

    for (let l = 0; l < lists.length; l += 1) {
      const list = lists[l];
      for (let i = 0; i < list.length; i += 1) {
        const parsed = parseConceptMeta(list[i], i);
        if (!parsed) continue;
        if (parsed.label && !out[parsed.id]) {
          out[parsed.id] = parsed.label;
        }
      }
    }

    return out;
  }

  function getTotalConceptCount(enrichments, labelMap) {
    const compareConcepts = Array.isArray(toObject(P.compareState).concepts)
      ? toObject(P.compareState).concepts
      : [];
    if (compareConcepts.length) {
      return compareConcepts.length;
    }

    const configured = toStringArray(toObject(enrichments.config).concepts_included);
    if (configured.length) {
      return configured.length;
    }

    const ids = new Set(Object.keys(toObject(labelMap)));
    addNormalizedConceptIds(ids, enrichments.cognate_sets);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).cognate_sets);
    addNormalizedConceptIds(ids, enrichments.borrowing_flags);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).borrowing_flags);
    addNormalizedConceptIds(ids, toObject(enrichments.manual_overrides).accepted_concepts);
    return ids.size;
  }

  function summarizeEnrichments(rawEnrichments) {
    const enrichments = ensureEnrichmentsShape(rawEnrichments);
    const conceptIds = new Set();

    addNormalizedConceptIds(conceptIds, enrichments.cognate_sets);
    addNormalizedConceptIds(conceptIds, toObject(enrichments.manual_overrides).cognate_sets);
    addNormalizedConceptIds(conceptIds, toObject(enrichments.manual_overrides).accepted_concepts);

    const sortedConceptIds = Array.from(conceptIds).sort(compareConceptIdOrder);
    let cognateConcepts = 0;
    let cognateGroups = 0;

    for (let i = 0; i < sortedConceptIds.length; i += 1) {
      const groups = getGroupsFromSource(enrichments, sortedConceptIds[i]);
      const count = Object.keys(groups).length;
      if (count > 0) {
        cognateConcepts += 1;
        cognateGroups += count;
      }
    }

    const borrowingMap = collectBorrowingDecisionMap(enrichments);
    const borrowingConceptIds = Object.keys(borrowingMap);
    let borrowingDecisions = 0;
    let borrowedForms = 0;

    for (let i = 0; i < borrowingConceptIds.length; i += 1) {
      const speakers = Object.keys(toObject(borrowingMap[borrowingConceptIds[i]]));
      for (let j = 0; j < speakers.length; j += 1) {
        const record = normalizeBorrowingRecord(toObject(borrowingMap[borrowingConceptIds[i]])[speakers[j]]);
        if (record.decision) {
          borrowingDecisions += 1;
          if (record.decision === 'borrowed') {
            borrowedForms += 1;
          }
        }
      }
    }

    const acceptedConceptIds = new Set();
    addNormalizedConceptIds(acceptedConceptIds, toObject(enrichments.manual_overrides).accepted_concepts);
    const excludedConceptIds = new Set();
    addNormalizedConceptIds(excludedConceptIds, toObject(enrichments.manual_overrides).include_in_analysis);

    return {
      cognateConcepts: cognateConcepts,
      cognateGroups: cognateGroups,
      borrowingDecisions: borrowingDecisions,
      borrowedForms: borrowedForms,
      acceptedConcepts: acceptedConceptIds.size,
      excludedConcepts: excludedConceptIds.size,
    };
  }

  function getHistory() {
    const enrichments = getCurrentEnrichments();
    const history = getHistoryEntries(enrichments);

    return history.map(function (entry) {
      return {
        timestamp: entry.timestamp,
        summary: summarizeEnrichments(entry.data),
      };
    });
  }

  function restoreSnapshot(timestamp) {
    const requested = String(timestamp == null ? '' : timestamp).trim();
    const normalizedTimestamp = normalizeTimestamp(requested);

    if (!requested || !normalizedTimestamp) {
      throw new Error('restoreSnapshot(timestamp) requires a valid ISO timestamp.');
    }

    const enrichments = getCurrentEnrichments();
    const history = getHistoryEntries(enrichments);
    let snapshot = null;

    for (let i = history.length - 1; i >= 0; i -= 1) {
      const entry = history[i];
      const candidate = normalizeTimestamp(entry.timestamp) || String(entry.timestamp || '').trim();
      if (candidate === normalizedTimestamp || String(entry.timestamp || '').trim() === requested) {
        snapshot = entry;
        break;
      }
    }

    if (!snapshot) {
      throw new Error('Snapshot not found for timestamp: ' + requested);
    }

    const restored = ensureEnrichmentsShape(snapshot.data);
    setHistoryEntries(restored, history);
    P.enrichments = restored;

    emitEnrichmentsUpdated();
    scheduleWrite('restore-snapshot');
    return deepClone(P.enrichments);
  }

  function collectDecisionConceptIds(enrichments, borrowingMap) {
    const conceptIds = new Set();

    addNormalizedConceptIds(conceptIds, toObject(enrichments.manual_overrides).cognate_sets);
    addNormalizedConceptIds(conceptIds, toObject(enrichments.manual_overrides).accepted_concepts);
    addNormalizedConceptIds(conceptIds, borrowingMap);
    addNormalizedConceptIds(conceptIds, toObject(enrichments.manual_overrides).include_in_analysis);
    addNormalizedConceptIds(conceptIds, getGlobalIncludedMap());

    return Array.from(conceptIds).sort(compareConceptIdOrder);
  }

  function buildConceptExportKey(conceptId, labelMap) {
    const label = String(toObject(labelMap)[conceptId] || '').trim();
    if (!label) {
      return conceptId;
    }
    return conceptId + ':' + label;
  }

  function exportBorrowingForConcept(speakerMap) {
    const speakers = Object.keys(toObject(speakerMap));
    const out = {};
    let borrowedCount = 0;

    for (let i = 0; i < speakers.length; i += 1) {
      const speaker = String(speakers[i] == null ? '' : speakers[i]).trim();
      if (!speaker) continue;

      const record = normalizeBorrowingRecord(toObject(speakerMap)[speakers[i]]);
      if (!hasBorrowingData(record)) {
        continue;
      }

      const entry = {};
      if (record.decision) {
        entry.decision = record.decision;
      }
      if (record.decision === 'borrowed') {
        borrowedCount += 1;
        if (record.source) {
          entry.source = record.source;
        }
      }
      if (record.handling) {
        entry.handling = record.handling;
      }

      if (Object.keys(entry).length) {
        out[speaker] = entry;
      }
    }

    return {
      borrowing: out,
      borrowedCount: borrowedCount,
    };
  }

  function exportDecisions() {
    const enrichments = getCurrentEnrichments();
    const labelMap = getConceptLabelMap();
    const borrowingMap = collectBorrowingDecisionMap(enrichments);
    const decisionConceptIds = collectDecisionConceptIds(enrichments, borrowingMap);
    const manualOverrides = toObject(enrichments.manual_overrides);
    const manualCognates = toObject(manualOverrides.cognate_sets);
    const acceptedConcepts = toObject(manualOverrides.accepted_concepts);
    const includeOverrides = getIncludeInAnalysisOverrideMap(enrichments);
    const globalIncluded = getGlobalIncludedMap();

    const conceptsOut = {};
    let totalBorrowings = 0;

    for (let i = 0; i < decisionConceptIds.length; i += 1) {
      const conceptId = decisionConceptIds[i];
      const manualGroups = normalizeGroups(manualCognates[conceptId]);
      const hasManualCognateDecision = Object.keys(manualGroups).length > 0;
      const hasAcceptedDecision = Object.prototype.hasOwnProperty.call(acceptedConcepts, conceptId);
      const hasCognateDecision = hasManualCognateDecision || hasAcceptedDecision;

      const includeDecision = (
        Object.prototype.hasOwnProperty.call(includeOverrides, conceptId) ||
        Object.prototype.hasOwnProperty.call(globalIncluded, conceptId)
      );

      const borrowingExport = exportBorrowingForConcept(toObject(borrowingMap[conceptId]));
      const hasBorrowingDecision = Object.keys(borrowingExport.borrowing).length > 0;

      if (!hasCognateDecision && !hasBorrowingDecision && !includeDecision) {
        continue;
      }

      const conceptOut = {};

      if (hasCognateDecision) {
        const groups = getGroupsFromSource(enrichments, conceptId);
        if (Object.keys(groups).length) {
          conceptOut.cognateSet = {
            groups: deepClone(groups),
          };
        }
      }

      if (hasBorrowingDecision) {
        conceptOut.borrowing = borrowingExport.borrowing;
        totalBorrowings += borrowingExport.borrowedCount;
      }

      conceptOut.includeInAnalysis = isIncludedInAnalysis(conceptId, enrichments);

      const conceptKey = buildConceptExportKey(conceptId, labelMap);
      conceptsOut[conceptKey] = conceptOut;
    }

    return {
      exportedAt: nowIso(),
      version: '1.0',
      concepts: conceptsOut,
      stats: {
        totalConcepts: getTotalConceptCount(enrichments, labelMap),
        decidedConcepts: Object.keys(conceptsOut).length,
        totalBorrowings: totalBorrowings,
      },
    };
  }

  function exportDecisionsAsFile() {
    const exportPayload = exportDecisions();
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });

    const objectUrl = URL.createObjectURL(blob);
    const linkEl = document.createElement('a');
    linkEl.href = objectUrl;
    linkEl.download = 'decisions.json';
    linkEl.style.display = 'none';

    document.body.appendChild(linkEl);
    linkEl.click();

    window.setTimeout(function () {
      URL.revokeObjectURL(objectUrl);
      if (linkEl.parentNode) {
        linkEl.parentNode.removeChild(linkEl);
      }
    }, 0);

    return exportPayload;
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
    addDocumentListener('parse:borrowing-decision', onBorrowingDecision);
    addDocumentListener('parse:analysis-toggle', onAnalysisToggle);
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
    getHistory: getHistory,
    restoreSnapshot: restoreSnapshot,
    exportDecisions: exportDecisions,
    exportDecisionsAsFile: exportDecisionsAsFile,
  };
})();
