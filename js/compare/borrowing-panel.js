(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;
  const MATCH_EPSILON = 0.01;
  const STYLE_ID = 'parse-borrowing-panel-style';
  const CONTACT_CONFIG_URL = '/config/sil_contact_languages.json';
  const DECISION_ORDER = ['native', 'borrowed', 'uncertain', 'skip'];

  const DEFAULT_CONTACT_LANGUAGES = {
    ar: {
      name: 'Arabic',
      family: 'Semitic',
      concepts: {},
    },
    fa: {
      name: 'Persian',
      family: 'Iranian',
      concepts: {},
    },
    ckb: {
      name: 'Central Kurdish (Sorani)',
      family: 'Iranian',
      concepts: {},
    },
    tr: {
      name: 'Turkish',
      family: 'Turkic',
      concepts: {},
    },
  };

  const state = {
    initialized: false,
    containerEl: null,
    listeners: [],
    currentConceptId: '',
    currentConceptLabel: '',
    selectedSpeakers: [],
    contactLanguages: cloneDefaults(),
    contactLanguageOrder: Object.keys(DEFAULT_CONTACT_LANGUAGES),
    openSections: {},
    localDecisions: {},
    loadPromise: null,
  };

  function cloneDefaults() {
    const out = {};
    const keys = Object.keys(DEFAULT_CONTACT_LANGUAGES);
    for (let i = 0; i < keys.length; i += 1) {
      const code = keys[i];
      out[code] = {
        name: DEFAULT_CONTACT_LANGUAGES[code].name,
        family: DEFAULT_CONTACT_LANGUAGES[code].family,
        concepts: {},
      };
    }
    return out;
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

  function toFiniteNumber(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const text = value.trim();
      if (!text) return null;
      const num = Number(text);
      return Number.isFinite(num) ? num : null;
    }
    return null;
  }

  function deepClone(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function toStringArray(value) {
    if (!Array.isArray(value)) return [];
    const out = [];
    const seen = new Set();

    for (let i = 0; i < value.length; i += 1) {
      const text = toString(value[i]);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      out.push(text);
    }

    return out;
  }

  function normalizeSpeakerList(value) {
    return toStringArray(value);
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

  function conceptIdToEventValue(conceptId) {
    const normalized = normalizeConceptId(conceptId);
    const numeric = Number(normalized);
    return Number.isFinite(numeric) ? numeric : normalized;
  }

  function normalizeLangCode(value) {
    return toString(value).toLowerCase();
  }

  function normalizeDecision(value) {
    if (typeof value === 'boolean') {
      return value ? 'borrowed' : 'native';
    }

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

  function scoreBand(score) {
    if (!Number.isFinite(score)) {
      return {
        label: 'No data',
        color: 'var(--muted)',
      };
    }

    if (score < 0.3) {
      return {
        label: 'unlikely',
        color: 'var(--ok)',
      };
    }

    if (score < 0.6) {
      return {
        label: 'possible',
        color: 'var(--warn)',
      };
    }

    return {
      label: 'likely borrowed',
      color: 'var(--danger)',
    };
  }

  function formatScore(score) {
    if (!Number.isFinite(score)) return 'No data';
    return score.toFixed(2);
  }

  function sanitizeDomId(value) {
    return toString(value).replace(/[^a-zA-Z0-9_-]+/g, '_') || 'item';
  }

  function lookupByKey(source, key, normalizeKeyFn) {
    const obj = toObject(source);
    if (!obj) return undefined;

    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      return obj[key];
    }

    const keys = Object.keys(obj);
    const normalizer = typeof normalizeKeyFn === 'function'
      ? normalizeKeyFn
      : function (value) {
        return toString(value);
      };

    const wanted = normalizer(key);
    for (let i = 0; i < keys.length; i += 1) {
      if (normalizer(keys[i]) === wanted) {
        return obj[keys[i]];
      }
    }

    return undefined;
  }

  function lookupConceptNode(source, conceptId) {
    return lookupByKey(source, conceptId, normalizeConceptId);
  }

  function lookupSpeakerNode(source, speakerId) {
    return lookupByKey(source, speakerId, function (value) {
      return toString(value);
    });
  }

  function lookupLanguageNode(source, langCode) {
    return lookupByKey(source, langCode, normalizeLangCode);
  }

  function uniqueConcat(base, values) {
    const out = Array.isArray(base) ? base.slice() : [];
    const seen = new Set(out);
    const list = Array.isArray(values) ? values : [];

    for (let i = 0; i < list.length; i += 1) {
      const text = toString(list[i]);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      out.push(text);
    }

    return out;
  }

  function collectTextValues(value) {
    if (value == null) return [];

    if (typeof value === 'string' || typeof value === 'number') {
      const text = toString(value);
      return text ? [text] : [];
    }

    if (Array.isArray(value)) {
      let out = [];
      for (let i = 0; i < value.length; i += 1) {
        out = uniqueConcat(out, collectTextValues(value[i]));
      }
      return out;
    }

    if (value && typeof value === 'object') {
      const obj = value;
      const keys = [
        'reference_forms',
        'referenceForms',
        'forms',
        'references',
        'ipa',
        'orthography',
        'ortho',
        'form',
      ];

      let out = [];
      for (let i = 0; i < keys.length; i += 1) {
        if (!Object.prototype.hasOwnProperty.call(obj, keys[i])) continue;
        out = uniqueConcat(out, collectTextValues(obj[keys[i]]));
      }
      return out;
    }

    return [];
  }

  function parseScore(rawScore) {
    const num = toFiniteNumber(rawScore);
    if (!Number.isFinite(num)) return null;
    return Math.max(0, Math.min(1, num));
  }

  function createSimilarityInfo() {
    return {
      score: null,
      hasReferenceData: null,
      referenceForms: [],
      found: false,
    };
  }

  function parseSimilarityPayload(raw) {
    const out = createSimilarityInfo();

    if (raw == null) {
      return out;
    }

    const directScore = parseScore(raw);
    if (Number.isFinite(directScore)) {
      out.score = directScore;
      out.hasReferenceData = true;
      out.found = true;
      return out;
    }

    if (raw && typeof raw === 'object') {
      const obj = raw;
      const scoreCandidates = [
        obj.score,
        obj.similarity,
        obj.value,
        obj.similarity_score,
        obj.similarityScore,
      ];

      for (let i = 0; i < scoreCandidates.length; i += 1) {
        const candidate = parseScore(scoreCandidates[i]);
        if (Number.isFinite(candidate)) {
          out.score = candidate;
          break;
        }
      }

      if (typeof obj.has_reference_data === 'boolean') {
        out.hasReferenceData = obj.has_reference_data;
      } else if (typeof obj.hasReferenceData === 'boolean') {
        out.hasReferenceData = obj.hasReferenceData;
      } else if (typeof obj.has_data === 'boolean') {
        out.hasReferenceData = obj.has_data;
      } else if (typeof obj.hasData === 'boolean') {
        out.hasReferenceData = obj.hasData;
      }

      out.referenceForms = collectTextValues(obj);

      if (out.hasReferenceData == null && Number.isFinite(out.score)) {
        out.hasReferenceData = true;
      }

      if (
        Number.isFinite(out.score) ||
        typeof out.hasReferenceData === 'boolean' ||
        out.referenceForms.length > 0
      ) {
        out.found = true;
      }
    }

    return out;
  }

  function mergeSimilarityInfo(base, extra) {
    const merged = {
      score: base.score,
      hasReferenceData: base.hasReferenceData,
      referenceForms: uniqueConcat(base.referenceForms, extra.referenceForms),
      found: !!(base.found || extra.found),
    };

    if (!Number.isFinite(merged.score) && Number.isFinite(extra.score)) {
      merged.score = extra.score;
    }

    if (merged.hasReferenceData == null && typeof extra.hasReferenceData === 'boolean') {
      merged.hasReferenceData = extra.hasReferenceData;
    }

    return merged;
  }

  function firstResolvedSimilarity(candidates) {
    const list = Array.isArray(candidates) ? candidates : [];
    let merged = createSimilarityInfo();

    for (let i = 0; i < list.length; i += 1) {
      const parsed = parseSimilarityPayload(list[i]);
      merged = mergeSimilarityInfo(merged, parsed);

      if (
        Number.isFinite(merged.score) &&
        merged.hasReferenceData !== false
      ) {
        break;
      }
    }

    return merged;
  }

  function extractSimilarityFromSpeakerNode(speakerNode, langCode) {
    const speakerObj = toObject(speakerNode);
    const candidates = [];

    const direct = lookupLanguageNode(speakerObj, langCode);
    if (direct !== undefined) candidates.push(direct);

    const buckets = ['languages', 'similarity', 'scores', 'by_language', 'byLanguage'];
    for (let i = 0; i < buckets.length; i += 1) {
      const bucket = toObject(speakerObj[buckets[i]]);
      const fromBucket = lookupLanguageNode(bucket, langCode);
      if (fromBucket !== undefined) {
        candidates.push(fromBucket);
      }
    }

    candidates.push(speakerNode);
    return firstResolvedSimilarity(candidates);
  }

  function extractSimilarityFromLanguageNode(languageNode, speakerId) {
    const languageObj = toObject(languageNode);
    const candidates = [];

    const direct = lookupSpeakerNode(languageObj, speakerId);
    if (direct !== undefined) candidates.push(direct);

    const buckets = ['speakers', 'values', 'scores', 'by_speaker', 'bySpeaker'];
    for (let i = 0; i < buckets.length; i += 1) {
      const bucket = toObject(languageObj[buckets[i]]);
      const fromBucket = lookupSpeakerNode(bucket, speakerId);
      if (fromBucket !== undefined) {
        candidates.push(fromBucket);
      }
    }

    candidates.push(languageNode);
    return firstResolvedSimilarity(candidates);
  }

  function resolveSimilarityForSpeaker(conceptId, speakerId, langCode) {
    const similarity = toObject(toObject(P.enrichments).similarity);
    const conceptNode = lookupConceptNode(similarity, conceptId);
    if (conceptNode === undefined) {
      return createSimilarityInfo();
    }

    const conceptObj = toObject(conceptNode);
    let merged = createSimilarityInfo();

    const speakerCandidates = [];
    const directSpeaker = lookupSpeakerNode(conceptObj, speakerId);
    if (directSpeaker !== undefined) speakerCandidates.push(directSpeaker);
    const speakerBucket = toObject(conceptObj.speakers);
    const bucketSpeaker = lookupSpeakerNode(speakerBucket, speakerId);
    if (bucketSpeaker !== undefined) speakerCandidates.push(bucketSpeaker);

    for (let i = 0; i < speakerCandidates.length; i += 1) {
      const resolved = extractSimilarityFromSpeakerNode(speakerCandidates[i], langCode);
      merged = mergeSimilarityInfo(merged, resolved);
    }

    const languageCandidates = [];
    const directLanguage = lookupLanguageNode(conceptObj, langCode);
    if (directLanguage !== undefined) languageCandidates.push(directLanguage);
    const languageBucket = toObject(conceptObj.languages);
    const bucketLanguage = lookupLanguageNode(languageBucket, langCode);
    if (bucketLanguage !== undefined) languageCandidates.push(bucketLanguage);

    for (let i = 0; i < languageCandidates.length; i += 1) {
      const resolved = extractSimilarityFromLanguageNode(languageCandidates[i], speakerId);
      merged = mergeSimilarityInfo(merged, resolved);
    }

    return merged;
  }

  function normalizeDecisionEntry(entry) {
    const out = {
      decision: '',
      sourceLang: '',
    };

    if (entry == null) {
      return out;
    }

    if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
      const obj = entry;
      out.decision = normalizeDecision(
        obj.decision != null
          ? obj.decision
          : (obj.status != null ? obj.status : obj.value)
      );

      out.sourceLang = normalizeLangCode(
        obj.sourceLang != null
          ? obj.sourceLang
          : (obj.source_lang != null
            ? obj.source_lang
            : (obj.source != null ? obj.source : ''))
      );

      if (!out.decision && typeof obj.borrowed === 'boolean') {
        out.decision = obj.borrowed ? 'borrowed' : 'native';
      }

      if (!out.decision && out.sourceLang) {
        out.decision = 'borrowed';
      }

      return out;
    }

    out.decision = normalizeDecision(entry);
    return out;
  }

  function readDecisionFromSource(flagsSource, conceptId, speakerId) {
    const conceptNode = lookupConceptNode(flagsSource, conceptId);
    if (conceptNode === undefined) {
      return { decision: '', sourceLang: '' };
    }

    const direct = lookupSpeakerNode(toObject(conceptNode), speakerId);
    if (direct !== undefined) {
      return normalizeDecisionEntry(direct);
    }

    const speakersBucket = toObject(toObject(conceptNode).speakers);
    const inBucket = lookupSpeakerNode(speakersBucket, speakerId);
    if (inBucket !== undefined) {
      return normalizeDecisionEntry(inBucket);
    }

    return { decision: '', sourceLang: '' };
  }

  function readDecisionFromEnrichments(conceptId, speakerId) {
    const enrichments = toObject(P.enrichments);
    const manualFlags = toObject(toObject(enrichments.manual_overrides).borrowing_flags);
    const baseFlags = toObject(enrichments.borrowing_flags);

    const manual = readDecisionFromSource(manualFlags, conceptId, speakerId);
    if (manual.decision || manual.sourceLang) {
      return manual;
    }

    return readDecisionFromSource(baseFlags, conceptId, speakerId);
  }

  function localDecisionMap(conceptId) {
    const key = normalizeConceptId(conceptId);
    if (!key) return {};

    if (!state.localDecisions[key]) {
      state.localDecisions[key] = {};
    }

    return state.localDecisions[key];
  }

  function getResolvedDecision(conceptId, speakerId) {
    const key = normalizeConceptId(conceptId);
    const speakerKey = toString(speakerId);
    if (!key || !speakerKey) {
      return { decision: '', sourceLang: '' };
    }

    const local = toObject(localDecisionMap(key))[speakerKey];
    if (local) {
      return normalizeDecisionEntry(local);
    }

    return normalizeDecisionEntry(readDecisionFromEnrichments(key, speakerKey));
  }

  function setLocalDecision(conceptId, speakerId, decision, sourceLang) {
    const conceptKey = normalizeConceptId(conceptId);
    const speakerKey = toString(speakerId);
    if (!conceptKey || !speakerKey) return;

    const decisionMap = localDecisionMap(conceptKey);
    decisionMap[speakerKey] = {
      decision: normalizeDecision(decision),
      sourceLang: normalizeLangCode(sourceLang),
      updatedAt: new Date().toISOString(),
    };
  }

  function mergeDecisionMaps(base, extra) {
    const merged = deepClone(base || {});
    const extraConcepts = Object.keys(toObject(extra));

    for (let i = 0; i < extraConcepts.length; i += 1) {
      const conceptKey = normalizeConceptId(extraConcepts[i]);
      if (!conceptKey) continue;

      if (!merged[conceptKey]) merged[conceptKey] = {};

      const speakers = Object.keys(toObject(extra[extraConcepts[i]]));
      for (let j = 0; j < speakers.length; j += 1) {
        const speakerKey = toString(speakers[j]);
        if (!speakerKey) continue;
        merged[conceptKey][speakerKey] = normalizeDecisionEntry(extra[extraConcepts[i]][speakers[j]]);
      }
    }

    return merged;
  }

  function collectDecisionMapFromEnrichments() {
    const enrichments = toObject(P.enrichments);
    const baseFlags = toObject(enrichments.borrowing_flags);
    const manualFlags = toObject(toObject(enrichments.manual_overrides).borrowing_flags);

    const mapFromFlags = {};

    function absorb(source) {
      const concepts = Object.keys(toObject(source));
      for (let i = 0; i < concepts.length; i += 1) {
        const conceptKey = normalizeConceptId(concepts[i]);
        if (!conceptKey) continue;
        if (!mapFromFlags[conceptKey]) mapFromFlags[conceptKey] = {};

        const conceptNode = toObject(source[concepts[i]]);
        const speakers = Object.keys(conceptNode);
        for (let j = 0; j < speakers.length; j += 1) {
          const speakerKey = toString(speakers[j]);
          if (!speakerKey) continue;
          mapFromFlags[conceptKey][speakerKey] = normalizeDecisionEntry(conceptNode[speakers[j]]);
        }

        const nestedSpeakers = toObject(conceptNode.speakers);
        const nestedKeys = Object.keys(nestedSpeakers);
        for (let j = 0; j < nestedKeys.length; j += 1) {
          const speakerKey = toString(nestedKeys[j]);
          if (!speakerKey) continue;
          mapFromFlags[conceptKey][speakerKey] = normalizeDecisionEntry(nestedSpeakers[nestedKeys[j]]);
        }
      }
    }

    absorb(baseFlags);
    absorb(manualFlags);

    return mapFromFlags;
  }

  function decisionCount() {
    const fromEnrichments = collectDecisionMapFromEnrichments();
    const merged = mergeDecisionMaps(fromEnrichments, state.localDecisions);
    let total = 0;

    const concepts = Object.keys(merged);
    for (let i = 0; i < concepts.length; i += 1) {
      const conceptNode = toObject(merged[concepts[i]]);
      const speakers = Object.keys(conceptNode);

      for (let j = 0; j < speakers.length; j += 1) {
        const record = normalizeDecisionEntry(conceptNode[speakers[j]]);
        if (record.decision && record.decision !== 'skip') {
          total += 1;
        }
      }
    }

    return total;
  }

  function intervalsFromTier(record, tierName) {
    const tier = toObject(toObject(record && record.tiers)[tierName]);
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
        return toString(interval.text);
      }
    }

    return '';
  }

  function getEntryForSpeakerConcept(speakerId, conceptId) {
    const speakerKey = toString(speakerId);
    const conceptKey = normalizeConceptId(conceptId);
    if (!speakerKey || !conceptKey) return null;

    const record = toObject(toObject(P.annotations)[speakerKey]);
    if (!record.tiers) return null;

    const conceptIntervals = intervalsFromTier(record, 'concept');
    let conceptInterval = null;

    for (let i = 0; i < conceptIntervals.length; i += 1) {
      const interval = toObject(conceptIntervals[i]);
      const intervalConceptId = normalizeConceptId(interval.text);
      if (!intervalConceptId) continue;
      if (intervalConceptId === conceptKey) {
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

    const ipa = findIntervalTextByBounds(intervalsFromTier(record, 'ipa'), startSec, endSec);
    const ortho = findIntervalTextByBounds(intervalsFromTier(record, 'ortho'), startSec, endSec);

    return {
      speakerId: speakerKey,
      startSec: startSec,
      endSec: endSec,
      ipa: ipa,
      ortho: ortho,
      sourceWav: toString(record.source_audio),
      hasForm: !!(ipa || ortho),
    };
  }

  function getCurrentSpeakerEntries() {
    const out = [];
    for (let i = 0; i < state.selectedSpeakers.length; i += 1) {
      const speakerId = state.selectedSpeakers[i];
      const entry = getEntryForSpeakerConcept(speakerId, state.currentConceptId);
      out.push({
        speakerId: speakerId,
        entry: entry,
      });
    }
    return out;
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
      label: toString(label),
    };
  }

  function findConceptLabel(conceptId) {
    const wanted = normalizeConceptId(conceptId);
    if (!wanted) return '';

    const compareState = toObject(P.compareState);
    const lists = [
      Array.isArray(compareState.filteredConcepts) ? compareState.filteredConcepts : [],
      Array.isArray(compareState.concepts) ? compareState.concepts : [],
    ];

    for (let l = 0; l < lists.length; l += 1) {
      const list = lists[l];
      for (let i = 0; i < list.length; i += 1) {
        const parsed = parseConceptEntry(list[i], i);
        if (!parsed) continue;
        if (parsed.id === wanted) {
          return parsed.label;
        }
      }
    }

    return '';
  }

  function readConfiguredContactLanguages() {
    const requiredDefaults = ['ar', 'fa', 'ckb', 'tr'];

    const enrichmentsCodes = toStringArray(toObject(toObject(P.enrichments).config).contact_languages)
      .map(normalizeLangCode)
      .filter(Boolean);

    if (enrichmentsCodes.length) {
      return uniqueConcat(requiredDefaults, enrichmentsCodes);
    }

    const projectCodes = toStringArray(toObject(toObject(P.project).language).contact_languages)
      .map(normalizeLangCode)
      .filter(Boolean);

    if (projectCodes.length) {
      return uniqueConcat(requiredDefaults, projectCodes);
    }

    return requiredDefaults;
  }

  function ensureLangDef(langCode) {
    const code = normalizeLangCode(langCode);
    if (!code) {
      return {
        code: '',
        name: 'Unknown',
        family: 'Unknown',
        concepts: {},
      };
    }

    if (!state.contactLanguages[code]) {
      state.contactLanguages[code] = {
        name: code.toUpperCase(),
        family: 'Unknown',
        concepts: {},
      };
    }

    const def = state.contactLanguages[code];
    return {
      code: code,
      name: toString(def.name) || code.toUpperCase(),
      family: toString(def.family) || 'Unknown',
      concepts: toObject(def.concepts),
    };
  }

  function getActiveLanguageCodes() {
    const configured = readConfiguredContactLanguages();
    const out = [];
    const seen = new Set();

    for (let i = 0; i < configured.length; i += 1) {
      const code = normalizeLangCode(configured[i]);
      if (!code || seen.has(code)) continue;
      seen.add(code);
      out.push(code);
    }

    if (!out.length) {
      const fallback = state.contactLanguageOrder.length
        ? state.contactLanguageOrder
        : Object.keys(state.contactLanguages);
      for (let i = 0; i < fallback.length; i += 1) {
        const code = normalizeLangCode(fallback[i]);
        if (!code || seen.has(code)) continue;
        seen.add(code);
        out.push(code);
      }
    }

    return out;
  }

  function getConfigReferenceForms(conceptId, langCode) {
    const def = ensureLangDef(langCode);
    const conceptNode = lookupConceptNode(toObject(def.concepts), conceptId);
    if (conceptNode === undefined) return [];
    return collectTextValues(conceptNode);
  }

  function buildLanguageMetrics(conceptId, speakerEntries, langCode) {
    const languageDef = ensureLangDef(langCode);
    const rows = [];
    let references = getConfigReferenceForms(conceptId, langCode);

    for (let i = 0; i < speakerEntries.length; i += 1) {
      const speakerId = speakerEntries[i].speakerId;
      const similarity = resolveSimilarityForSpeaker(conceptId, speakerId, langCode);
      references = uniqueConcat(references, similarity.referenceForms);

      const score = Number.isFinite(similarity.score) ? similarity.score : null;
      const hasReferenceData = typeof similarity.hasReferenceData === 'boolean'
        ? similarity.hasReferenceData
        : null;
      const noData = hasReferenceData === false || score == null;

      rows.push({
        speakerId: speakerId,
        score: score,
        hasReferenceData: hasReferenceData,
        noData: noData,
      });
    }

    const validScores = rows
      .filter(function (row) {
        return !row.noData && Number.isFinite(row.score);
      })
      .map(function (row) {
        return row.score;
      });

    let aggregate = null;
    if (validScores.length) {
      const sum = validScores.reduce(function (acc, value) {
        return acc + value;
      }, 0);
      aggregate = Math.max(0, Math.min(1, sum / validScores.length));
    }

    return {
      code: langCode,
      name: languageDef.name,
      family: languageDef.family,
      aggregateScore: aggregate,
      noData: aggregate == null,
      rows: rows,
      referenceForms: references,
    };
  }

  function pickDefaultSourceLanguage(speakerId, languageCodes) {
    const langs = Array.isArray(languageCodes) ? languageCodes : [];
    if (!langs.length) return '';

    let bestLang = '';
    let bestScore = -1;

    for (let i = 0; i < langs.length; i += 1) {
      const code = normalizeLangCode(langs[i]);
      const similarity = resolveSimilarityForSpeaker(state.currentConceptId, speakerId, code);
      const score = Number.isFinite(similarity.score) ? similarity.score : null;
      const noData = similarity.hasReferenceData === false || score == null;
      if (noData || score == null) continue;
      if (score > bestScore) {
        bestScore = score;
        bestLang = code;
      }
    }

    if (bestLang) return bestLang;
    return normalizeLangCode(langs[0]);
  }

  function getResolvedDecisionForSpeaker(speakerId, entryHasForm, languageCodes) {
    const resolved = getResolvedDecision(state.currentConceptId, speakerId);
    let decision = resolved.decision || 'skip';
    let sourceLang = normalizeLangCode(resolved.sourceLang);

    if (!entryHasForm && decision !== 'skip') {
      decision = 'skip';
      sourceLang = '';
    }

    if (decision !== 'borrowed') {
      sourceLang = '';
    } else if (!sourceLang) {
      sourceLang = pickDefaultSourceLanguage(speakerId, languageCodes);
    }

    return {
      decision: decision,
      sourceLang: sourceLang,
    };
  }

  function upsertDecisionAndDispatch(speakerId, decision, sourceLang) {
    const conceptKey = normalizeConceptId(state.currentConceptId);
    const speakerKey = toString(speakerId);
    const normalizedDecision = normalizeDecision(decision) || 'skip';
    const normalizedSource = normalizedDecision === 'borrowed' ? normalizeLangCode(sourceLang) : '';

    if (!conceptKey || !speakerKey) return;

    setLocalDecision(conceptKey, speakerKey, normalizedDecision, normalizedSource);

    dispatch('parse:borrowing-decision', {
      conceptId: conceptIdToEventValue(conceptKey),
      speakerId: speakerKey,
      decision: normalizedDecision,
      sourceLang: normalizedSource || null,
    });
  }

  function updateDecisionFromRadio(speakerId, decision) {
    const languages = getActiveLanguageCodes();
    const resolved = getResolvedDecisionForSpeaker(speakerId, true, languages);
    let sourceLang = resolved.sourceLang;

    const normalizedDecision = normalizeDecision(decision) || 'skip';
    if (normalizedDecision === 'borrowed') {
      if (!sourceLang) {
        sourceLang = pickDefaultSourceLanguage(speakerId, languages);
      }
    } else {
      sourceLang = '';
    }

    upsertDecisionAndDispatch(speakerId, normalizedDecision, sourceLang);
    render();
  }

  function updateSourceLanguage(speakerId, sourceLang) {
    const resolved = getResolvedDecisionForSpeaker(speakerId, true, getActiveLanguageCodes());
    const decision = resolved.decision === 'borrowed' ? 'borrowed' : 'borrowed';
    upsertDecisionAndDispatch(speakerId, decision, sourceLang);
    render();
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;

    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ID;
    styleEl.textContent =
      '.borrowing-panel-root { display: flex; flex-direction: column; gap: 10px; }' +
      '.bp-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }' +
      '.bp-title-wrap { min-width: 0; }' +
      '.bp-title-wrap .panel-title { margin-bottom: 4px; }' +
      '.bp-concept-line { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }' +
      '.bp-count-badge { border: 1px solid var(--border); border-radius: 999px; padding: 4px 8px; font-size: 11px; font-weight: 700; color: var(--accent); background: rgba(17, 26, 42, 0.7); }' +
      '.bp-section-title { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }' +
      '.bp-context-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px; }' +
      '.bp-context-card { border: 1px solid var(--border); border-radius: 8px; background: rgba(16, 25, 43, 0.72); padding: 6px 8px; }' +
      '.bp-context-speaker { font-size: 11px; color: var(--muted); margin-bottom: 3px; }' +
      '.bp-context-ipa { font-family: "Noto Serif", "Gentium Plus", serif; color: #c6defa; font-size: 13px; line-height: 1.25; word-break: break-word; }' +
      '.bp-context-ortho { color: #f4dba8; font-size: 12px; line-height: 1.25; word-break: break-word; }' +
      '.bp-context-empty { color: #7f8fae; font-style: italic; font-size: 12px; }' +
      '.bp-lang-list { display: flex; flex-direction: column; gap: 8px; }' +
      '.bp-lang-section { border: 1px solid var(--border); border-radius: 8px; background: rgba(17, 26, 42, 0.65); }' +
      '.bp-lang-section summary { list-style: none; display: grid; grid-template-columns: minmax(120px, 1fr) minmax(140px, 2fr); align-items: center; gap: 10px; cursor: pointer; padding: 8px; }' +
      '.bp-lang-section summary::-webkit-details-marker { display: none; }' +
      '.bp-lang-name { font-size: 12px; font-weight: 700; color: var(--text); }' +
      '.bp-lang-family { color: var(--muted); font-size: 11px; margin-top: 2px; }' +
      '.bp-score-wrap { display: flex; align-items: center; gap: 8px; min-width: 0; }' +
      '.bp-score-track { position: relative; height: 10px; border-radius: 999px; border: 1px solid var(--border); background: #10192b; flex: 1; overflow: hidden; }' +
      '.bp-score-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0%; border-radius: inherit; }' +
      '.bp-score-track.is-empty { border-style: dashed; background: rgba(109, 127, 158, 0.24); }' +
      '.bp-score-label { font-size: 11px; color: var(--muted); min-width: 86px; text-align: right; }' +
      '.bp-lang-body { padding: 0 8px 8px; display: flex; flex-direction: column; gap: 8px; }' +
      '.bp-refs { font-size: 12px; color: var(--muted); }' +
      '.bp-refs strong { color: var(--text); font-weight: 600; }' +
      '.bp-speaker-score-list { display: flex; flex-direction: column; gap: 5px; }' +
      '.bp-speaker-score-row { display: grid; grid-template-columns: minmax(70px, 100px) minmax(140px, 1fr); align-items: center; gap: 8px; }' +
      '.bp-speaker-name { color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }' +
      '.bp-decision-list { display: flex; flex-direction: column; gap: 8px; }' +
      '.bp-decision-row { border: 1px solid var(--border); border-radius: 8px; background: rgba(16, 25, 43, 0.72); padding: 8px; display: flex; flex-direction: column; gap: 6px; }' +
      '.bp-row-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; }' +
      '.bp-speaker-id { font-weight: 700; color: var(--text); font-size: 12px; }' +
      '.bp-speaker-form { color: var(--muted); font-size: 12px; }' +
      '.bp-radios { display: flex; flex-wrap: wrap; gap: 10px; }' +
      '.bp-radio-label { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text); }' +
      '.bp-radio-label input { accent-color: var(--accent); }' +
      '.bp-source-row { display: flex; align-items: center; gap: 8px; }' +
      '.bp-source-row label { color: var(--muted); font-size: 12px; }' +
      '.bp-source-row select { border-radius: 6px; border: 1px solid var(--border); background: #10192b; color: var(--text); font-size: 12px; padding: 5px 6px; min-width: 180px; }' +
      '.bp-source-row.is-hidden { display: none; }' +
      '@media (max-width: 1100px) {' +
      '  .bp-lang-section summary { grid-template-columns: 1fr; }' +
      '  .bp-speaker-score-row { grid-template-columns: 1fr; }' +
      '}';

    document.head.appendChild(styleEl);
  }

  function renderScoreRow(score, noData) {
    const band = scoreBand(score);
    const wrapper = document.createElement('div');
    wrapper.className = 'bp-score-wrap';

    const track = document.createElement('div');
    track.className = 'bp-score-track';
    if (noData) {
      track.classList.add('is-empty');
    }

    const fill = document.createElement('span');
    fill.className = 'bp-score-fill';
    fill.style.background = band.color;
    fill.style.width = noData ? '0%' : (Math.max(0, Math.min(1, score)) * 100).toFixed(1) + '%';
    track.appendChild(fill);

    const label = document.createElement('span');
    label.className = 'bp-score-label';
    label.textContent = noData ? 'No data' : (formatScore(score) + ' ' + band.label);

    wrapper.appendChild(track);
    wrapper.appendChild(label);
    return wrapper;
  }

  function renderContextSection(rootEl, speakerEntries) {
    const section = document.createElement('section');

    const title = document.createElement('h4');
    title.className = 'bp-section-title';
    title.textContent = 'Current concept forms';
    section.appendChild(title);

    const grid = document.createElement('div');
    grid.className = 'bp-context-grid';

    for (let i = 0; i < speakerEntries.length; i += 1) {
      const speakerId = speakerEntries[i].speakerId;
      const entry = speakerEntries[i].entry;

      const card = document.createElement('div');
      card.className = 'bp-context-card';

      const speaker = document.createElement('div');
      speaker.className = 'bp-context-speaker';
      speaker.textContent = speakerId;
      card.appendChild(speaker);

      if (entry && entry.hasForm) {
        const ipa = document.createElement('div');
        ipa.className = 'bp-context-ipa';
        ipa.textContent = entry.ipa || '-';
        card.appendChild(ipa);

        const ortho = document.createElement('div');
        ortho.className = 'bp-context-ortho';
        ortho.textContent = entry.ortho || '-';
        card.appendChild(ortho);
      } else {
        const empty = document.createElement('div');
        empty.className = 'bp-context-empty';
        empty.textContent = 'No annotated form';
        card.appendChild(empty);
      }

      grid.appendChild(card);
    }

    section.appendChild(grid);
    rootEl.appendChild(section);
  }

  function renderSimilaritySection(rootEl, languageMetrics) {
    const section = document.createElement('section');

    const title = document.createElement('h4');
    title.className = 'bp-section-title';
    title.textContent = 'Contact language similarity';
    section.appendChild(title);

    const langList = document.createElement('div');
    langList.className = 'bp-lang-list';

    for (let i = 0; i < languageMetrics.length; i += 1) {
      const metrics = languageMetrics[i];
      const details = document.createElement('details');
      details.className = 'bp-lang-section';
      details.dataset.bpLang = metrics.code;

      const openState = state.openSections[metrics.code];
      if (typeof openState === 'boolean') {
        details.open = openState;
      } else if (i === 0) {
        details.open = true;
      }

      const summary = document.createElement('summary');

      const nameWrap = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'bp-lang-name';
      name.textContent = metrics.name;

      const family = document.createElement('div');
      family.className = 'bp-lang-family';
      family.textContent = metrics.family;

      nameWrap.appendChild(name);
      nameWrap.appendChild(family);
      summary.appendChild(nameWrap);
      summary.appendChild(renderScoreRow(metrics.aggregateScore, metrics.noData));

      const body = document.createElement('div');
      body.className = 'bp-lang-body';

      const refs = document.createElement('div');
      refs.className = 'bp-refs';
      if (metrics.referenceForms.length) {
        const strong = document.createElement('strong');
        strong.textContent = 'Reference forms:';
        refs.appendChild(strong);
        refs.appendChild(document.createTextNode(' ' + metrics.referenceForms.join(', ')));
      } else {
        refs.textContent = 'Reference forms: none available.';
      }
      body.appendChild(refs);

      const rows = document.createElement('div');
      rows.className = 'bp-speaker-score-list';
      for (let r = 0; r < metrics.rows.length; r += 1) {
        const row = metrics.rows[r];
        const rowEl = document.createElement('div');
        rowEl.className = 'bp-speaker-score-row';

        const speaker = document.createElement('div');
        speaker.className = 'bp-speaker-name';
        speaker.textContent = row.speakerId;

        rowEl.appendChild(speaker);
        rowEl.appendChild(renderScoreRow(row.score, row.noData));
        rows.appendChild(rowEl);
      }

      body.appendChild(rows);
      details.appendChild(summary);
      details.appendChild(body);
      langList.appendChild(details);
    }

    section.appendChild(langList);
    rootEl.appendChild(section);
  }

  function radioOptionLabel(optionValue) {
    if (optionValue === 'native') return 'Native';
    if (optionValue === 'borrowed') return 'Borrowed';
    if (optionValue === 'uncertain') return 'Uncertain';
    return 'Skip';
  }

  function renderDecisionSection(rootEl, speakerEntries, languageCodes) {
    const section = document.createElement('section');

    const title = document.createElement('h4');
    title.className = 'bp-section-title';
    title.textContent = 'Borrowing adjudication';
    section.appendChild(title);

    const list = document.createElement('div');
    list.className = 'bp-decision-list';

    for (let i = 0; i < speakerEntries.length; i += 1) {
      const speakerId = speakerEntries[i].speakerId;
      const entry = speakerEntries[i].entry;
      const hasForm = !!(entry && entry.hasForm);
      const resolved = getResolvedDecisionForSpeaker(speakerId, hasForm, languageCodes);

      const row = document.createElement('div');
      row.className = 'bp-decision-row';

      const head = document.createElement('div');
      head.className = 'bp-row-head';

      const speakerEl = document.createElement('div');
      speakerEl.className = 'bp-speaker-id';
      speakerEl.textContent = speakerId;

      const formEl = document.createElement('div');
      formEl.className = 'bp-speaker-form';
      if (hasForm) {
        const ipa = entry.ipa || '-';
        const ortho = entry.ortho || '-';
        formEl.textContent = ipa + ' | ' + ortho;
      } else {
        formEl.textContent = 'No form available';
      }

      head.appendChild(speakerEl);
      head.appendChild(formEl);
      row.appendChild(head);

      const radios = document.createElement('div');
      radios.className = 'bp-radios';
      const radioName = 'bp-' + sanitizeDomId(state.currentConceptId) + '-' + sanitizeDomId(speakerId);

      for (let r = 0; r < DECISION_ORDER.length; r += 1) {
        const optionValue = DECISION_ORDER[r];
        const label = document.createElement('label');
        label.className = 'bp-radio-label';

        const input = document.createElement('input');
        input.type = 'radio';
        input.name = radioName;
        input.value = optionValue;
        input.dataset.bpDecision = optionValue;
        input.dataset.bpSpeaker = speakerId;
        input.checked = resolved.decision === optionValue;

        if (!hasForm && optionValue !== 'skip') {
          input.disabled = true;
        }

        label.appendChild(input);
        label.appendChild(document.createTextNode(radioOptionLabel(optionValue)));
        radios.appendChild(label);
      }

      row.appendChild(radios);

      const sourceRow = document.createElement('div');
      sourceRow.className = 'bp-source-row';
      if (resolved.decision !== 'borrowed') {
        sourceRow.classList.add('is-hidden');
      }

      const sourceLabel = document.createElement('label');
      sourceLabel.textContent = 'Source language';

      const sourceSelect = document.createElement('select');
      sourceSelect.dataset.bpSource = '1';
      sourceSelect.dataset.bpSpeaker = speakerId;

      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = 'Select source';
      sourceSelect.appendChild(placeholder);

      for (let l = 0; l < languageCodes.length; l += 1) {
        const code = normalizeLangCode(languageCodes[l]);
        const langDef = ensureLangDef(code);

        const option = document.createElement('option');
        option.value = code;
        option.textContent = langDef.name + ' (' + langDef.family + ')';
        option.selected = resolved.sourceLang === code;
        sourceSelect.appendChild(option);
      }

      sourceLabel.appendChild(sourceSelect);
      sourceRow.appendChild(sourceLabel);
      row.appendChild(sourceRow);

      list.appendChild(row);
    }

    section.appendChild(list);
    rootEl.appendChild(section);
  }

  function renderPlaceholder(message) {
    if (!state.containerEl) return;
    state.containerEl.innerHTML =
      '<div class="panel-title">Borrowing adjudication</div>' +
      '<div class="panel-placeholder">' +
      (toString(message) || 'Select a concept to adjudicate potential borrowings.') +
      '</div>';
  }

  function render() {
    if (!state.containerEl) return;

    ensureStyles();

    if (!state.currentConceptId) {
      renderPlaceholder('Select a concept to adjudicate potential borrowings.');
      return;
    }

    if (!state.selectedSpeakers.length) {
      renderPlaceholder('No speakers selected for comparison.');
      return;
    }

    const speakerEntries = getCurrentSpeakerEntries();
    const activeLanguages = getActiveLanguageCodes();
    const languageMetrics = activeLanguages.map(function (code) {
      return buildLanguageMetrics(state.currentConceptId, speakerEntries, code);
    });

    state.containerEl.innerHTML = '';

    const root = document.createElement('div');
    root.className = 'borrowing-panel-root';

    const header = document.createElement('div');
    header.className = 'bp-header';

    const titleWrap = document.createElement('div');
    titleWrap.className = 'bp-title-wrap';

    const panelTitle = document.createElement('div');
    panelTitle.className = 'panel-title';
    panelTitle.textContent = 'Borrowing adjudication';

    const conceptLine = document.createElement('div');
    conceptLine.className = 'bp-concept-line';
    conceptLine.textContent =
      'Concept #' + state.currentConceptId +
      (state.currentConceptLabel ? ': ' + state.currentConceptLabel : '');

    titleWrap.appendChild(panelTitle);
    titleWrap.appendChild(conceptLine);

    const countBadge = document.createElement('div');
    countBadge.className = 'bp-count-badge';
    countBadge.textContent = decisionCount() + ' decisions';

    header.appendChild(titleWrap);
    header.appendChild(countBadge);

    root.appendChild(header);

    renderContextSection(root, speakerEntries);
    renderSimilaritySection(root, languageMetrics);
    renderDecisionSection(root, speakerEntries, activeLanguages);

    state.containerEl.appendChild(root);
  }

  function updateContextFromDetail(detail) {
    const payload = toObject(detail);
    const conceptId = normalizeConceptId(payload.conceptId);
    if (conceptId) {
      state.currentConceptId = conceptId;
      P.currentConcept = conceptId;
    }

    const conceptLabel = toString(payload.conceptLabel);
    if (conceptLabel) {
      state.currentConceptLabel = conceptLabel;
    } else if (state.currentConceptId) {
      state.currentConceptLabel = findConceptLabel(state.currentConceptId);
    }

    const incomingSpeakers = normalizeSpeakerList(payload.speakers);
    if (incomingSpeakers.length) {
      state.selectedSpeakers = incomingSpeakers;
    }
  }

  function syncContextFromGlobalState() {
    const compareState = toObject(P.compareState);

    if (!state.currentConceptId) {
      state.currentConceptId = normalizeConceptId(compareState.selectedConceptId || P.currentConcept);
    }

    if (!state.currentConceptLabel && state.currentConceptId) {
      state.currentConceptLabel = findConceptLabel(state.currentConceptId);
    }

    if (!state.selectedSpeakers.length) {
      state.selectedSpeakers = normalizeSpeakerList(compareState.selectedSpeakers);
    }
  }

  function onConceptSelected(event) {
    updateContextFromDetail(event && event.detail);
    render();
  }

  function onSpeakersChanged(event) {
    const detail = toObject(event && event.detail);
    const speakers = normalizeSpeakerList(detail.speakers);
    if (!speakers.length) return;

    state.selectedSpeakers = speakers;
    render();
  }

  function onEnrichmentsUpdated() {
    render();
  }

  function onCompareOpen(event) {
    updateContextFromDetail(event && event.detail);
    syncContextFromGlobalState();
    render();
  }

  function onAnnotationsChanged() {
    render();
  }

  function onContainerChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.matches('input[type="radio"][data-bp-decision]')) {
      const speakerId = target.dataset.bpSpeaker;
      const decision = target.value;
      updateDecisionFromRadio(speakerId, decision);
      return;
    }

    if (target.matches('select[data-bp-source]')) {
      const speakerId = target.dataset.bpSpeaker;
      updateSourceLanguage(speakerId, target.value);
    }
  }

  function onContainerToggle(event) {
    const target = event.target;
    if (!(target instanceof HTMLDetailsElement)) return;
    if (!target.matches('details[data-bp-lang]')) return;
    const code = normalizeLangCode(target.dataset.bpLang);
    if (!code) return;
    state.openSections[code] = target.open;
  }

  function normalizeContactLanguageDefinitions(rawConfig) {
    const input = toObject(rawConfig);
    const out = cloneDefaults();

    const keys = Object.keys(input);
    for (let i = 0; i < keys.length; i += 1) {
      const code = normalizeLangCode(keys[i]);
      if (!code) continue;

      const node = toObject(input[keys[i]]);
      out[code] = {
        name: toString(node.name) || code.toUpperCase(),
        family: toString(node.family) || 'Unknown',
        concepts: toObject(node.concepts),
      };
    }

    return out;
  }

  async function loadContactLanguages() {
    if (state.loadPromise) return state.loadPromise;

    state.loadPromise = fetch(CONTACT_CONFIG_URL, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
      },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status + ' while loading ' + CONTACT_CONFIG_URL);
        }
        return response.json();
      })
      .then(function (data) {
        state.contactLanguages = normalizeContactLanguageDefinitions(data);
        state.contactLanguageOrder = Object.keys(state.contactLanguages);
      })
      .catch(function (error) {
        console.warn('[borrowing-panel] contact language config fallback:', error);
        state.contactLanguages = cloneDefaults();
        state.contactLanguageOrder = Object.keys(state.contactLanguages);
      })
      .finally(function () {
        if (state.initialized) {
          render();
        }
      });

    return state.loadPromise;
  }

  /**
   * Initialize borrowing adjudication panel.
   * @param {HTMLElement} containerEl Compare borrowing panel container.
   * @returns {object} Public borrowing panel API.
   */
  function init(containerEl) {
    if (state.initialized) {
      return P.modules.borrowingPanel;
    }

    state.containerEl = containerEl || document.getElementById('compare-borrowing-panel');
    if (!state.containerEl) {
      throw new Error('Missing #compare-borrowing-panel container for borrowing panel.');
    }

    syncContextFromGlobalState();
    render();

    addListener(document, 'parse:compare-concept-selected', onConceptSelected);
    addListener(document, 'parse:enrichments-updated', onEnrichmentsUpdated);
    addListener(document, 'parse:compare-speakers-changed', onSpeakersChanged);
    addListener(document, 'parse:compare-open', onCompareOpen);
    addListener(document, 'parse:annotations-changed', onAnnotationsChanged);
    addListener(state.containerEl, 'change', onContainerChange);
    addListener(state.containerEl, 'toggle', onContainerToggle);

    state.initialized = true;
    void loadContactLanguages();

    return P.modules.borrowingPanel;
  }

  /**
   * Destroy borrowing panel listeners and clear panel content.
   */
  function destroy() {
    removeAllListeners();

    if (state.containerEl) {
      state.containerEl.innerHTML = '';
    }

    state.initialized = false;
    state.containerEl = null;
    state.currentConceptId = '';
    state.currentConceptLabel = '';
    state.selectedSpeakers = [];
    state.openSections = {};
    state.localDecisions = {};
    state.loadPromise = null;
  }

  P.modules.borrowingPanel = {
    init: init,
    destroy: destroy,
  };
})();
