/**
 * suggestions-panel.js — AI suggestions + positional prior selector
 *
 * Responsibilities:
 *  - Attach to window.SourceExplorer.modules.suggestions
 *  - Render the positional prior speaker selector into #se-priors
 *  - Render AI suggestion cards into #se-suggestions
 *  - Listen for se:panel-open / se:panel-close
 *  - Listen for se:priors-changed and re-rank suggestions client-side
 *  - Emit se:suggestion-click and se:seek when a suggestion is chosen
 *  - Preserve the underlying suggestion store (window.SourceExplorer.suggestions)
 *    by computing derived scores on copies only
 */
(function () {
  'use strict';

  window.SourceExplorer = window.SourceExplorer || {};
  window.SourceExplorer.modules = window.SourceExplorer.modules || {};

  const SE = window.SourceExplorer;

  const PRIORS_CONTAINER_ID = 'se-priors';
  const SUGGESTIONS_CONTAINER_ID = 'se-suggestions';
  const PRIORS_STORAGE_KEY = 'se-suggestions-priors';

  const MAX_POSITIONAL_BOOST = 0.25;
  const BOOST_CUTOFF_SEC = 120;
  const BOOST_SIGMA_SEC = 45;
  const DEFAULT_COVERAGE_THRESHOLD = 50;
  const DEFAULT_REGION_FALLBACK_SEC = 3;

  const state = {
    rootEl: null,
    priorsEl: null,
    suggestionsEl: null,
    currentContext: null,
    conceptEntry: null,
    baseSuggestions: [],
    derivedSuggestions: [],
    anchors: {},
    selectedPriors: [],
    expectedTimeSec: null,
    usablePriorSpeakers: [],
    lastClickedSuggestion: null,
    pendingSeek: null,
    bound: {
      panelOpen: null,
      panelClose: null,
      priorsChanged: null,
      priorsInteraction: null,
      suggestionsClick: null,
    },
  };

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function asFiniteNumber(value, fallback) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function formatTimeSec(sec) {
    if (!Number.isFinite(sec) || sec < 0) return '—';
    const total = Math.floor(sec);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;

    if (hours > 0) {
      return hours + ':' + pad2(minutes) + ':' + pad2(seconds);
    }
    return minutes + ':' + pad2(seconds);
  }

  function pad2(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function truncateText(text, maxLen) {
    if (!text) return '';
    const str = String(text).trim();
    if (str.length <= maxLen) return str;
    return str.slice(0, Math.max(0, maxLen - 1)).trimEnd() + '…';
  }

  function basename(path) {
    if (!path) return '';
    const parts = String(path).split('/');
    return parts[parts.length - 1] || String(path);
  }

  function median(values) {
    if (!Array.isArray(values) || values.length === 0) return null;
    const sorted = values
      .map(function (v) { return Number(v); })
      .filter(function (v) { return Number.isFinite(v); })
      .sort(function (a, b) { return a - b; });

    if (!sorted.length) return null;

    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 1) {
      return sorted[mid];
    }
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function scoreToConfidence(score) {
    const numeric = asFiniteNumber(score, 0);
    if (numeric >= 0.80) return 'high';
    if (numeric >= 0.50) return 'medium';
    return 'low';
  }

  function methodLabel(method) {
    switch (method) {
      case 'exact_ortho_match':
        return 'Exact orthographic';
      case 'fuzzy_ortho_match':
        return 'Fuzzy orthographic';
      case 'romanized_phonetic_match':
        return 'Romanized phonetic';
      default:
        return method ? String(method) : 'Unknown method';
    }
  }

  function coveragePercent(rawCoverage) {
    const coverage = asFiniteNumber(rawCoverage, 0);
    if (coverage <= 1) {
      return clamp(coverage * 100, 0, 100);
    }
    // The current data generator stores counts (e.g. 82), not percentages.
    return clamp((coverage / 82) * 100, 0, 100);
  }

  function coverageLabel(anchorEntry) {
    if (!anchorEntry || anchorEntry.concept_coverage == null) {
      return 'coverage unknown';
    }
    const rawCoverage = asFiniteNumber(anchorEntry.concept_coverage, 0);
    if (rawCoverage > 1) {
      return rawCoverage + '/82';
    }
    return Math.round(coveragePercent(rawCoverage)) + '%';
  }

  function isRecommendedPrior(anchorEntry) {
    return coveragePercent(anchorEntry && anchorEntry.concept_coverage) >= DEFAULT_COVERAGE_THRESHOLD;
  }

  function highlightToken(text, token) {
    const safeText = escapeHtml(text || '');
    if (!token) return safeText;

    const raw = String(text || '');
    const rawToken = String(token);
    const idx = raw.indexOf(rawToken);
    if (idx === -1) return safeText;

    const before = escapeHtml(raw.slice(0, idx));
    const match = escapeHtml(raw.slice(idx, idx + rawToken.length));
    const after = escapeHtml(raw.slice(idx + rawToken.length));
    return before + '<mark style="background:#fff1a8;padding:0 2px;border-radius:2px;">' + match + '</mark>' + after;
  }

  function getSuggestionsStore() {
    return SE && SE.suggestions ? SE.suggestions : null;
  }

  function getAnchorSpeakers() {
    return Object.keys(state.anchors || {}).filter(function (speaker) {
      return !state.currentContext || speaker !== state.currentContext.speaker;
    });
  }

  function resolveConceptEntry(conceptId) {
    const store = getSuggestionsStore();
    if (!store || !store.suggestions) return null;
    return store.suggestions[String(conceptId)] || null;
  }

  function resolvePrimarySourceWav(speaker) {
    const sourceIndex = SE && SE.sourceIndex && SE.sourceIndex.speakers
      ? SE.sourceIndex.speakers[speaker]
      : null;

    if (!sourceIndex || !Array.isArray(sourceIndex.source_wavs) || !sourceIndex.source_wavs.length) {
      return null;
    }

    const wavEntry = sourceIndex.source_wavs.find(function (entry) { return entry && entry.is_primary; }) || sourceIndex.source_wavs[0];
    return wavEntry && wavEntry.filename ? wavEntry.filename : null;
  }

  function resolveLexiconStartSec(speaker, sourceWav) {
    const sourceIndex = SE && SE.sourceIndex && SE.sourceIndex.speakers
      ? SE.sourceIndex.speakers[speaker]
      : null;

    if (!sourceIndex || !Array.isArray(sourceIndex.source_wavs)) {
      return null;
    }

    const wavEntry = sourceWav
      ? sourceIndex.source_wavs.find(function (entry) { return entry && entry.filename === sourceWav; })
      : sourceIndex.source_wavs.find(function (entry) { return entry && entry.is_primary; }) || sourceIndex.source_wavs[0];

    return wavEntry && Number.isFinite(Number(wavEntry.lexicon_start_sec))
      ? Number(wavEntry.lexicon_start_sec)
      : null;
  }

  function loadStoredPriorSelections() {
    try {
      const raw = localStorage.getItem(PRIORS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function saveStoredPriorSelections(speaker, selectedSpeakers) {
    if (!speaker) return;
    try {
      const current = loadStoredPriorSelections();
      current[speaker] = Array.isArray(selectedSpeakers) ? selectedSpeakers.slice() : [];
      localStorage.setItem(PRIORS_STORAGE_KEY, JSON.stringify(current));
    } catch (_) {
      // Ignore storage failures.
    }
  }

  function getDefaultPriorSelection(targetSpeaker, conceptId) {
    const anchorSpeakers = getAnchorSpeakers();
    if (!anchorSpeakers.length) return [];

    const recommended = anchorSpeakers.filter(function (speaker) {
      return speaker !== targetSpeaker && isRecommendedPrior(state.anchors[speaker]);
    });

    if (recommended.length) {
      return recommended;
    }

    const withConceptAnchor = anchorSpeakers.filter(function (speaker) {
      const timestamps = state.anchors[speaker] && state.anchors[speaker].timestamps;
      return timestamps && timestamps[String(conceptId)] != null;
    });

    if (withConceptAnchor.length) {
      return withConceptAnchor;
    }

    return anchorSpeakers;
  }

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function computeExpectedTimeSec(conceptId, selectedSpeakers) {
    const usable = [];

    (selectedSpeakers || []).forEach(function (speaker) {
      const anchor = state.anchors && state.anchors[speaker];
      const timestamps = anchor && anchor.timestamps;
      if (!timestamps) return;

      const ts = asFiniteNumber(timestamps[String(conceptId)], NaN);
      if (!Number.isFinite(ts) || ts < 0) return;

      usable.push({ speaker: speaker, timeSec: ts });
    });

    return {
      expectedTimeSec: median(usable.map(function (entry) { return entry.timeSec; })),
      usablePriorSpeakers: usable.map(function (entry) { return entry.speaker; }),
    };
  }

  function computePositionalBoost(distanceSec) {
    if (!Number.isFinite(distanceSec) || distanceSec < 0 || distanceSec >= BOOST_CUTOFF_SEC) {
      return 0;
    }

    const gaussianWeight = Math.exp(-0.5 * Math.pow(distanceSec / BOOST_SIGMA_SEC, 2));
    return MAX_POSITIONAL_BOOST * gaussianWeight;
  }

  function deriveSuggestions() {
    const conceptId = state.currentContext && state.currentContext.conceptId;
    const expected = computeExpectedTimeSec(conceptId, state.selectedPriors);

    state.expectedTimeSec = expected.expectedTimeSec;
    state.usablePriorSpeakers = expected.usablePriorSpeakers;

    const derived = state.baseSuggestions.map(function (item, originalIndex) {
      const baseScore = clamp(asFiniteNumber(item.confidence_score, 0), 0, 1);
      const startSec = asFiniteNumber(item.segment_start_sec, 0);
      const endSec = asFiniteNumber(item.segment_end_sec, startSec + DEFAULT_REGION_FALLBACK_SEC);
      const distanceSec = Number.isFinite(state.expectedTimeSec)
        ? Math.abs(startSec - state.expectedTimeSec)
        : null;
      const positionalBoost = Number.isFinite(distanceSec)
        ? computePositionalBoost(distanceSec)
        : 0;
      const finalScore = clamp(baseScore + positionalBoost, 0, 1);

      return Object.assign({}, item, {
        _originalIndex: originalIndex,
        baseScore: baseScore,
        finalScore: finalScore,
        positionalBoost: positionalBoost,
        distanceSec: distanceSec,
        derivedConfidence: scoreToConfidence(finalScore),
        segment_start_sec: startSec,
        segment_end_sec: endSec,
      });
    });

    if (Number.isFinite(state.expectedTimeSec)) {
      derived.sort(function (a, b) {
        if (b.finalScore !== a.finalScore) return b.finalScore - a.finalScore;

        const aDist = Number.isFinite(a.distanceSec) ? a.distanceSec : Number.POSITIVE_INFINITY;
        const bDist = Number.isFinite(b.distanceSec) ? b.distanceSec : Number.POSITIVE_INFINITY;
        if (aDist !== bDist) return aDist - bDist;

        if (b.baseScore !== a.baseScore) return b.baseScore - a.baseScore;
        if (a.segment_start_sec !== b.segment_start_sec) return a.segment_start_sec - b.segment_start_sec;
        return a._originalIndex - b._originalIndex;
      });
    } else {
      derived.sort(function (a, b) {
        if (b.baseScore !== a.baseScore) return b.baseScore - a.baseScore;
        if (a.segment_start_sec !== b.segment_start_sec) return a.segment_start_sec - b.segment_start_sec;
        return a._originalIndex - b._originalIndex;
      });
    }

    derived.forEach(function (item, idx) {
      item.rank = idx + 1;
    });

    state.derivedSuggestions = derived;
  }

  function priorsSummaryHtml() {
    const totalSelected = state.selectedPriors.length;
    const usableCount = state.usablePriorSpeakers.length;

    if (!totalSelected) {
      return '<div class="se-priors__summary" style="font-size:0.92em;color:#666;">No positional prior selected — showing base suggestion scores only.</div>';
    }

    if (!Number.isFinite(state.expectedTimeSec)) {
      return '<div class="se-priors__summary" style="font-size:0.92em;color:#666;">' +
        'Selected ' + totalSelected + ' reference speaker' + (totalSelected === 1 ? '' : 's') +
        ', but none has an anchor for this concept. Base scores are unchanged.' +
      '</div>';
    }

    return '<div class="se-priors__summary" style="font-size:0.92em;color:#555;">' +
      'Expected timestamp ≈ <strong>' + escapeHtml(formatTimeSec(state.expectedTimeSec)) + '</strong>' +
      ' using ' + usableCount + '/' + totalSelected + ' selected anchor' + (totalSelected === 1 ? '' : 's') + '.' +
    '</div>';
  }

  function renderPriors() {
    if (!state.priorsEl) return;

    if (!state.currentContext) {
      state.priorsEl.innerHTML = '';
      return;
    }

    const conceptId = state.currentContext.conceptId;
    const anchorSpeakers = getAnchorSpeakers().sort(function (a, b) {
      const aCoverage = coveragePercent(state.anchors[a] && state.anchors[a].concept_coverage);
      const bCoverage = coveragePercent(state.anchors[b] && state.anchors[b].concept_coverage);
      if (bCoverage !== aCoverage) return bCoverage - aCoverage;
      return a.localeCompare(b);
    });

    if (!anchorSpeakers.length) {
      state.priorsEl.innerHTML =
        '<div class="se-priors se-priors--empty" style="padding:10px 12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;">' +
          '<strong>Positional prior</strong>' +
          '<div style="margin-top:6px;color:#666;">No positional anchors are available for re-ranking.</div>' +
        '</div>';
      return;
    }

    const rows = anchorSpeakers.map(function (speaker) {
      const anchor = state.anchors[speaker] || {};
      const hasConceptAnchor = !!(anchor.timestamps && anchor.timestamps[String(conceptId)] != null);
      const selected = state.selectedPriors.indexOf(speaker) !== -1;
      const recommended = isRecommendedPrior(anchor);
      const lowCoverage = !recommended;
      const hint = hasConceptAnchor
        ? 'has anchor for this concept at ' + formatTimeSec(asFiniteNumber(anchor.timestamps[String(conceptId)], 0))
        : 'no anchor for this concept';

      return '<label class="se-priors__option" style="display:inline-flex;align-items:flex-start;gap:8px;padding:6px 8px;border:1px solid ' + (selected ? '#7aa7ff' : '#ddd') + ';border-radius:8px;background:' + (selected ? '#eef4ff' : '#fff') + ';cursor:pointer;">' +
        '<input type="checkbox" data-role="prior-checkbox" data-speaker="' + escapeHtml(speaker) + '" ' + (selected ? 'checked' : '') + ' style="margin-top:2px;" />' +
        '<span style="display:flex;flex-direction:column;gap:2px;">' +
          '<span style="font-weight:600;color:#222;">' + escapeHtml(speaker) +
            (recommended ? ' <span style="color:#2d6a4f;font-weight:500;">recommended</span>' : '') +
            (lowCoverage ? ' <span title="Lower anchor coverage" style="color:#a66;">⚠</span>' : '') +
          '</span>' +
          '<span style="font-size:0.85em;color:#666;">' + escapeHtml(coverageLabel(anchor)) + ' · ' + escapeHtml(hint) + '</span>' +
        '</span>' +
      '</label>';
    }).join('');

    state.priorsEl.innerHTML =
      '<div class="se-priors" style="padding:10px 12px;border:1px solid #ddd;border-radius:10px;background:#fcfcfd;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">' +
          '<div>' +
            '<strong>Positional prior</strong>' +
            '<div style="font-size:0.88em;color:#666;margin-top:3px;">Select reference speakers to nudge rankings toward the expected timestamp.</div>' +
          '</div>' +
          '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
            '<button type="button" data-role="priors-recommended" class="se-btn" style="padding:4px 8px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;">Recommended</button>' +
            '<button type="button" data-role="priors-clear" class="se-btn" style="padding:4px 8px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;">Clear</button>' +
          '</div>' +
        '</div>' +
        '<div style="margin-top:8px;">' + priorsSummaryHtml() + '</div>' +
        '<div class="se-priors__list" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">' + rows + '</div>' +
      '</div>';
  }

  function currentSuggestionIsActive(suggestion) {
    const active = state.lastClickedSuggestion;
    if (!active || !suggestion) return false;

    return active.sourceWav === suggestion.source_wav &&
      active.segmentStartSec === suggestion.segment_start_sec &&
      active.segmentEndSec === suggestion.segment_end_sec;
  }

  function renderSuggestions() {
    if (!state.suggestionsEl) return;

    if (!state.currentContext) {
      state.suggestionsEl.innerHTML = '';
      return;
    }

    const conceptLabel = state.conceptEntry && state.conceptEntry.concept_en
      ? String(state.conceptEntry.concept_en)
      : '#' + state.currentContext.conceptId;

    if (!state.baseSuggestions.length) {
      state.suggestionsEl.innerHTML =
        '<div class="se-suggestions se-suggestions--empty" style="padding:12px;border:1px dashed #ccc;border-radius:10px;background:#fafafa;color:#666;">' +
          '<strong>No AI suggestions</strong>' +
          '<div style="margin-top:6px;">No transcript-window candidates were found for concept ' + escapeHtml(conceptLabel) + ' × ' + escapeHtml(state.currentContext.speaker) + '.</div>' +
        '</div>';
      return;
    }

    const cards = state.derivedSuggestions.map(function (item, idx) {
      const active = currentSuggestionIsActive(item);
      const confidence = item.derivedConfidence;
      const badgeBg = confidence === 'high'
        ? '#dff6e5'
        : confidence === 'medium'
          ? '#fff1d6'
          : '#f7e2e2';
      const badgeColor = confidence === 'high'
        ? '#1f7a3d'
        : confidence === 'medium'
          ? '#9c6b00'
          : '#9b2c2c';
      const regionDuration = Math.max(0.2, item.segment_end_sec - item.segment_start_sec);
      const sourceChanged = !!(state.currentContext.sourceWav && item.source_wav && item.source_wav !== state.currentContext.sourceWav);
      const scoreLine = item.positionalBoost > 0.0005
        ? 'base ' + item.baseScore.toFixed(2) + ' + prior ' + item.positionalBoost.toFixed(2) + ' = ' + item.finalScore.toFixed(2)
        : 'base ' + item.baseScore.toFixed(2);
      const distanceLine = Number.isFinite(item.distanceSec) && item.positionalBoost > 0
        ? ' · Δ ' + Math.round(item.distanceSec) + 's'
        : '';

      return '<button type="button" class="se-suggestion-card" data-role="suggestion-card" data-index="' + idx + '" ' +
        'style="display:block;width:100%;text-align:left;padding:12px 14px;border:1px solid ' + (active ? '#7aa7ff' : '#ddd') + ';border-radius:10px;background:' + (active ? '#eef4ff' : '#fff') + ';cursor:pointer;">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">' +
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
            '<strong style="font-size:1em;color:#222;">#' + item.rank + ' · ' + escapeHtml(formatTimeSec(item.segment_start_sec)) + '</strong>' +
            '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:' + badgeBg + ';color:' + badgeColor + ';font-size:0.82em;font-weight:700;text-transform:uppercase;">' + escapeHtml(confidence) + '</span>' +
            '<span style="font-size:0.86em;color:#666;">' + escapeHtml(methodLabel(item.method)) + '</span>' +
          '</div>' +
          '<span style="font-size:0.84em;color:#666;white-space:nowrap;">' + escapeHtml(scoreLine + distanceLine) + '</span>' +
        '</div>' +
        '<div style="margin-top:7px;font-size:0.94em;color:#222;line-height:1.45;">“' + highlightToken(truncateText(item.transcript_text, 240), item.matched_token) + '”</div>' +
        '<div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;font-size:0.85em;color:#555;">' +
          '<span><strong>Source:</strong> ' + escapeHtml(basename(item.source_wav || state.currentContext.sourceWav || '')) + '</span>' +
          '<span><strong>Window:</strong> ' + escapeHtml(formatTimeSec(item.segment_start_sec)) + ' → ' + escapeHtml(formatTimeSec(item.segment_end_sec)) + ' (' + regionDuration.toFixed(1) + 's)</span>' +
          (item.reference_form_source ? '<span><strong>Reference:</strong> ' + escapeHtml(String(item.reference_form_source)) + '</span>' : '') +
          (sourceChanged ? '<span style="color:#8a5a00;"><strong>Action:</strong> switches source audio first</span>' : '') +
        '</div>' +
        (item.note
          ? '<div style="margin-top:6px;font-size:0.84em;color:#666;">' + escapeHtml(item.note) + '</div>'
          : '') +
      '</button>';
    }).join('');

    state.suggestionsEl.innerHTML =
      '<div class="se-suggestions" style="display:flex;flex-direction:column;gap:10px;">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;">' +
          '<div>' +
            '<strong>AI suggestions</strong>' +
            '<div style="font-size:0.88em;color:#666;margin-top:3px;">Candidates for ' + escapeHtml(state.currentContext.speaker) + ' × ' + escapeHtml(conceptLabel) + '. Click a card to seek and create a region.</div>' +
          '</div>' +
          '<div style="font-size:0.86em;color:#666;">' + state.derivedSuggestions.length + ' candidate' + (state.derivedSuggestions.length === 1 ? '' : 's') + '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:10px;">' + cards + '</div>' +
      '</div>';
  }

  function rerankAndRender() {
    deriveSuggestions();
    renderPriors();
    renderSuggestions();
  }

  function finalizeSuggestionSelection(suggestion, rank) {
    if (!suggestion) return;

    state.lastClickedSuggestion = {
      rank: rank,
      originalIndex: suggestion._originalIndex,
      sourceWav: suggestion.source_wav || state.currentContext.sourceWav || null,
      segmentStartSec: suggestion.segment_start_sec,
      segmentEndSec: suggestion.segment_end_sec,
      confidence: suggestion.derivedConfidence,
      score: suggestion.finalScore,
      method: suggestion.method || null,
      matchedToken: suggestion.matched_token || null,
    };

    renderSuggestions();

    emit('se:suggestion-click', {
      suggestionIndex: rank,
      segmentStartSec: suggestion.segment_start_sec,
      segmentEndSec: suggestion.segment_end_sec,
    });

    emit('se:seek', {
      timeSec: suggestion.segment_start_sec,
      createRegion: true,
      regionDurationSec: Math.max(0.2, suggestion.segment_end_sec - suggestion.segment_start_sec),
    });
  }

  function findRenderedSuggestionForPending(pending) {
    if (!pending) return null;

    for (let i = 0; i < state.derivedSuggestions.length; i += 1) {
      const suggestion = state.derivedSuggestions[i];
      if (
        suggestion.source_wav === pending.sourceWav &&
        suggestion.segment_start_sec === pending.segmentStartSec &&
        suggestion.segment_end_sec === pending.segmentEndSec
      ) {
        return suggestion;
      }
    }

    return null;
  }

  function handleSuggestionSelection(suggestion) {
    if (!suggestion || !state.currentContext) return;

    const suggestionSource = suggestion.source_wav || state.currentContext.sourceWav || null;
    const currentSource = state.currentContext.sourceWav || null;

    if (suggestionSource && currentSource && suggestionSource !== currentSource) {
      state.pendingSeek = {
        speaker: state.currentContext.speaker,
        conceptId: state.currentContext.conceptId,
        sourceWav: suggestionSource,
        segmentStartSec: suggestion.segment_start_sec,
        segmentEndSec: suggestion.segment_end_sec,
      };

      const panelModule = SE && SE.modules ? SE.modules.panel : null;
      const nextContext = {
        speaker: state.currentContext.speaker,
        conceptId: state.currentContext.conceptId,
        sourceWav: suggestionSource,
        lexiconStartSec: resolveLexiconStartSec(state.currentContext.speaker, suggestionSource),
      };

      if (panelModule && typeof panelModule.open === 'function') {
        panelModule.open(nextContext);
      } else {
        emit('se:panel-open', nextContext);
      }
      return;
    }

    state.pendingSeek = null;
    finalizeSuggestionSelection(suggestion, suggestion.rank || 1);
  }

  function collectCheckedPriorSpeakers() {
    if (!state.priorsEl) return [];

    return Array.prototype.slice.call(
      state.priorsEl.querySelectorAll('input[data-role="prior-checkbox"]:checked')
    )
      .map(function (input) { return input.getAttribute('data-speaker'); })
      .filter(function (speaker) { return !!speaker; });
  }

  function handlePriorsInteraction(event) {
    if (!state.currentContext || !state.priorsEl) return;

    const target = event.target;
    if (!target) return;

    if (event.type === 'change' && target.matches && target.matches('input[data-role="prior-checkbox"]')) {
      emit('se:priors-changed', {
        selectedSpeakers: collectCheckedPriorSpeakers(),
      });
      return;
    }

    if (event.type === 'click' && target.matches) {
      if (target.matches('[data-role="priors-clear"]')) {
        event.preventDefault();
        emit('se:priors-changed', { selectedSpeakers: [] });
        return;
      }

      if (target.matches('[data-role="priors-recommended"]')) {
        event.preventDefault();
        emit('se:priors-changed', {
          selectedSpeakers: getDefaultPriorSelection(state.currentContext.speaker, state.currentContext.conceptId),
        });
      }
    }
  }

  function handleSuggestionsClick(event) {
    if (!state.currentContext || !state.suggestionsEl) return;

    const card = event.target && event.target.closest
      ? event.target.closest('[data-role="suggestion-card"]')
      : null;

    if (!card) return;

    const index = asFiniteNumber(card.getAttribute('data-index'), -1);
    const suggestion = index >= 0 ? state.derivedSuggestions[index] : null;
    if (!suggestion) return;

    handleSuggestionSelection(suggestion);
  }

  function handlePanelOpen(event) {
    const detail = event && event.detail ? event.detail : {};
    const store = getSuggestionsStore();

    state.currentContext = {
      speaker: detail.speaker || null,
      conceptId: detail.conceptId != null ? String(detail.conceptId) : null,
      sourceWav: detail.sourceWav || resolvePrimarySourceWav(detail.speaker || null),
      lexiconStartSec: Number.isFinite(Number(detail.lexiconStartSec)) ? Number(detail.lexiconStartSec) : null,
    };

    state.anchors = store && store.positional_anchors && typeof store.positional_anchors === 'object'
      ? store.positional_anchors
      : {};
    state.conceptEntry = resolveConceptEntry(state.currentContext.conceptId);

    const rawSuggestions = state.conceptEntry && state.conceptEntry.speakers
      ? state.conceptEntry.speakers[state.currentContext.speaker]
      : null;

    state.baseSuggestions = Array.isArray(rawSuggestions)
      ? rawSuggestions.slice()
      : [];

    const storedSelections = loadStoredPriorSelections();
    const storedForSpeaker = state.currentContext.speaker
      ? storedSelections[state.currentContext.speaker]
      : null;
    const validAnchorSpeakers = getAnchorSpeakers();

    if (Array.isArray(storedForSpeaker)) {
      state.selectedPriors = storedForSpeaker.filter(function (speaker) {
        return validAnchorSpeakers.indexOf(speaker) !== -1;
      });
    } else {
      state.selectedPriors = getDefaultPriorSelection(state.currentContext.speaker, state.currentContext.conceptId);
    }

    rerankAndRender();

    if (
      state.pendingSeek &&
      state.pendingSeek.speaker === state.currentContext.speaker &&
      state.pendingSeek.conceptId === state.currentContext.conceptId &&
      state.pendingSeek.sourceWav === state.currentContext.sourceWav
    ) {
      const pendingSuggestion = findRenderedSuggestionForPending(state.pendingSeek);
      const pendingRank = pendingSuggestion ? pendingSuggestion.rank : 1;
      const nextSuggestion = pendingSuggestion || {
        source_wav: state.pendingSeek.sourceWav,
        segment_start_sec: state.pendingSeek.segmentStartSec,
        segment_end_sec: state.pendingSeek.segmentEndSec,
        derivedConfidence: scoreToConfidence(0),
        finalScore: 0,
      };
      state.pendingSeek = null;
      requestAnimationFrame(function () {
        finalizeSuggestionSelection(nextSuggestion, pendingRank);
      });
    }
  }

  function handlePanelClose() {
    const preservePending = !!state.pendingSeek;

    state.currentContext = null;
    state.conceptEntry = null;
    state.baseSuggestions = [];
    state.derivedSuggestions = [];
    state.anchors = {};
    state.selectedPriors = [];
    state.expectedTimeSec = null;
    state.usablePriorSpeakers = [];

    if (!preservePending) {
      state.lastClickedSuggestion = null;
    }

    if (state.priorsEl) {
      state.priorsEl.innerHTML = '';
    }
    if (state.suggestionsEl) {
      state.suggestionsEl.innerHTML = '';
    }
  }

  function handlePriorsChanged(event) {
    if (!state.currentContext) return;

    const detail = event && event.detail ? event.detail : {};
    const selectedSpeakers = Array.isArray(detail.selectedSpeakers)
      ? detail.selectedSpeakers.slice()
      : [];
    const validAnchorSpeakers = getAnchorSpeakers();

    state.selectedPriors = selectedSpeakers.filter(function (speaker, idx, arr) {
      return validAnchorSpeakers.indexOf(speaker) !== -1 && arr.indexOf(speaker) === idx;
    });

    saveStoredPriorSelections(state.currentContext.speaker, state.selectedPriors);
    rerankAndRender();
  }

  function resolveContainers(containerEl) {
    state.rootEl = containerEl || state.rootEl || document.body;
    state.priorsEl = document.getElementById(PRIORS_CONTAINER_ID) || state.priorsEl;
    state.suggestionsEl = document.getElementById(SUGGESTIONS_CONTAINER_ID) || state.suggestionsEl;
  }

  function init(containerEl) {
    if (state.bound.panelOpen) {
      resolveContainers(containerEl);
      return SE.modules.suggestions;
    }

    resolveContainers(containerEl);

    if (!state.priorsEl) {
      console.warn('[suggestions-panel] #' + PRIORS_CONTAINER_ID + ' not found.');
    }
    if (!state.suggestionsEl) {
      console.warn('[suggestions-panel] #' + SUGGESTIONS_CONTAINER_ID + ' not found.');
    }

    state.bound.panelOpen = handlePanelOpen;
    state.bound.panelClose = handlePanelClose;
    state.bound.priorsChanged = handlePriorsChanged;
    state.bound.priorsInteraction = handlePriorsInteraction;
    state.bound.suggestionsClick = handleSuggestionsClick;

    document.addEventListener('se:panel-open', state.bound.panelOpen);
    document.addEventListener('se:panel-close', state.bound.panelClose);
    document.addEventListener('se:priors-changed', state.bound.priorsChanged);

    if (state.priorsEl) {
      state.priorsEl.addEventListener('change', state.bound.priorsInteraction);
      state.priorsEl.addEventListener('click', state.bound.priorsInteraction);
    }

    if (state.suggestionsEl) {
      state.suggestionsEl.addEventListener('click', state.bound.suggestionsClick);
    }

    return SE.modules.suggestions;
  }

  function destroy() {
    if (state.bound.panelOpen) {
      document.removeEventListener('se:panel-open', state.bound.panelOpen);
    }
    if (state.bound.panelClose) {
      document.removeEventListener('se:panel-close', state.bound.panelClose);
    }
    if (state.bound.priorsChanged) {
      document.removeEventListener('se:priors-changed', state.bound.priorsChanged);
    }
    if (state.priorsEl && state.bound.priorsInteraction) {
      state.priorsEl.removeEventListener('change', state.bound.priorsInteraction);
      state.priorsEl.removeEventListener('click', state.bound.priorsInteraction);
    }
    if (state.suggestionsEl && state.bound.suggestionsClick) {
      state.suggestionsEl.removeEventListener('click', state.bound.suggestionsClick);
    }

    handlePanelClose();
    state.pendingSeek = null;
    state.lastClickedSuggestion = null;
    state.rootEl = null;
    state.priorsEl = null;
    state.suggestionsEl = null;
    state.bound.panelOpen = null;
    state.bound.panelClose = null;
    state.bound.priorsChanged = null;
    state.bound.priorsInteraction = null;
    state.bound.suggestionsClick = null;
  }

  function getState() {
    return {
      currentContext: state.currentContext ? Object.assign({}, state.currentContext) : null,
      selectedPriors: state.selectedPriors.slice(),
      expectedTimeSec: state.expectedTimeSec,
      usablePriorSpeakers: state.usablePriorSpeakers.slice(),
      suggestionCount: state.derivedSuggestions.length,
    };
  }

  function getSuggestions() {
    return state.derivedSuggestions.slice();
  }

  function getLastClickedSuggestion() {
    return state.lastClickedSuggestion ? Object.assign({}, state.lastClickedSuggestion) : null;
  }

  function rerank(selectedSpeakers) {
    emit('se:priors-changed', {
      selectedSpeakers: Array.isArray(selectedSpeakers) ? selectedSpeakers.slice() : [],
    });
  }

  SE.modules.suggestions = {
    init: init,
    destroy: destroy,
    rerank: rerank,
    getState: getState,
    getSuggestions: getSuggestions,
    getLastClickedSuggestion: getLastClickedSuggestion,
  };
}());
