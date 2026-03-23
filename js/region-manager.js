/**
 * region-manager.js — Source Explorer region assignment UI
 *
 * Responsibilities:
 *  - Render region status + assignment controls into #se-controls
 *  - Track the current Source Explorer context (speaker / concept / source WAV)
 *  - Track the currently selected waveform region via se:region-updated
 *  - Surface any prior assignment for the current speaker+concept
 *  - Persist source-region decisions into window.SourceExplorer.decisions
 *  - Dispatch se:region-assigned on assignment
 *  - Expose lightweight export-ready decision helpers
 */
(function () {
  'use strict';

  if (!window.SourceExplorer) {
    window.SourceExplorer = {};
  }
  if (!window.SourceExplorer.modules) {
    window.SourceExplorer.modules = {};
  }

  var SE = window.SourceExplorer;
  var DECISIONS_LS_KEY = 'se-decisions';

  var containerEl = null;
  var rootEl = null;
  var els = {};
  var isInitialized = false;

  var state = {
    context: null,
    region: null,
    priorDecision: null,
    activeSuggestion: null,
  };

  function init(mountEl) {
    if (isInitialized) {
      return api;
    }

    containerEl = mountEl || document.getElementById('se-controls');
    if (!containerEl) {
      console.warn('[region-manager] No controls container found.');
      return api;
    }

    ensureRoot();
    bindEvents();
    render();
    isInitialized = true;
    return api;
  }

  function destroy() {
    unbindEvents();
    if (rootEl && rootEl.parentNode) {
      rootEl.parentNode.removeChild(rootEl);
    }

    containerEl = null;
    rootEl = null;
    els = {};
    isInitialized = false;
    resetState();
  }

  function ensureRoot() {
    rootEl = document.createElement('section');
    rootEl.className = 'se-region-manager';
    rootEl.setAttribute('aria-label', 'Region assignment controls');
    rootEl.style.cssText = [
      'border:1px solid #d7dee8',
      'border-radius:10px',
      'padding:12px',
      'background:#f8fafc',
      'display:flex',
      'flex-direction:column',
      'gap:10px',
      'font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
      'color:#1f2937'
    ].join(';');

    rootEl.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">',
        '<div style="font-weight:700;font-size:14px;">Region assignment</div>',
        '<div data-se-region-status style="font-size:12px;color:#475569;"></div>',
      '</div>',
      '<div data-se-region-current style="padding:10px;border-radius:8px;background:#fff;border:1px solid #e2e8f0;"></div>',
      '<div data-se-region-suggestion style="display:none;padding:10px;border-radius:8px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;"></div>',
      '<div data-se-region-prior style="padding:10px;border-radius:8px;background:#fff;border:1px solid #e2e8f0;"></div>',
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">',
        '<button type="button" data-se-load-prior style="padding:8px 10px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;color:#0f172a;cursor:pointer;">Load prior region</button>',
        '<button type="button" data-se-assign style="padding:8px 12px;border-radius:8px;border:1px solid #0f766e;background:#0f766e;color:#fff;font-weight:600;cursor:pointer;">Assign to concept</button>',
      '</div>',
      '<div data-se-region-feedback style="min-height:18px;font-size:12px;color:#475569;"></div>'
    ].join('');

    containerEl.appendChild(rootEl);

    els.status = rootEl.querySelector('[data-se-region-status]');
    els.current = rootEl.querySelector('[data-se-region-current]');
    els.suggestion = rootEl.querySelector('[data-se-region-suggestion]');
    els.prior = rootEl.querySelector('[data-se-region-prior]');
    els.loadPrior = rootEl.querySelector('[data-se-load-prior]');
    els.assign = rootEl.querySelector('[data-se-assign]');
    els.feedback = rootEl.querySelector('[data-se-region-feedback]');

    els.loadPrior.addEventListener('click', onLoadPriorClick);
    els.assign.addEventListener('click', onAssignClick);
  }

  function bindEvents() {
    document.addEventListener('se:panel-open', onPanelOpen);
    document.addEventListener('se:panel-close', onPanelClose);
    document.addEventListener('se:region-updated', onRegionUpdated);
    document.addEventListener('se:suggestion-click', onSuggestionClick);
  }

  function unbindEvents() {
    document.removeEventListener('se:panel-open', onPanelOpen);
    document.removeEventListener('se:panel-close', onPanelClose);
    document.removeEventListener('se:region-updated', onRegionUpdated);
    document.removeEventListener('se:suggestion-click', onSuggestionClick);

    if (els.loadPrior) {
      els.loadPrior.removeEventListener('click', onLoadPriorClick);
    }
    if (els.assign) {
      els.assign.removeEventListener('click', onAssignClick);
    }
  }

  function onPanelOpen(event) {
    var detail = event && event.detail ? event.detail : {};
    state.context = {
      speaker: detail.speaker || null,
      conceptId: detail.conceptId != null ? String(detail.conceptId) : null,
      sourceWav: resolveSourceWav(detail.speaker, detail.conceptId, detail.sourceWav),
      lexiconStartSec: toFiniteNumber(detail.lexiconStartSec),
    };
    state.region = null;
    state.activeSuggestion = null;
    state.priorDecision = getDecisionForCurrentContext();
    setFeedback('');
    render();
  }

  function onPanelClose(event) {
    var detail = event && event.detail ? event.detail : {};
    if (
      state.context &&
      detail.speaker &&
      state.context.speaker &&
      detail.speaker !== state.context.speaker
    ) {
      return;
    }

    resetState();
    render();
  }

  function onRegionUpdated(event) {
    var detail = event && event.detail ? event.detail : {};
    var startSec = toFiniteNumber(detail.startSec);
    var endSec = toFiniteNumber(detail.endSec);

    if (isValidRegion(startSec, endSec)) {
      state.region = {
        startSec: roundSec(startSec),
        endSec: roundSec(endSec),
      };
    } else {
      state.region = null;
    }

    if (state.activeSuggestion && state.region && !regionStillMatchesSuggestion(state.region, state.activeSuggestion)) {
      state.activeSuggestion = null;
    }
    if (!state.region) {
      state.activeSuggestion = null;
    }

    render();
  }

  function onSuggestionClick(event) {
    if (!state.context) {
      return;
    }

    var detail = event && event.detail ? event.detail : {};
    var normalizedSuggestionIndex = toFiniteNumber(detail.suggestionIndex);
    var suggestion = resolveSuggestionMeta(
      state.context.conceptId,
      state.context.speaker,
      normalizedSuggestionIndex,
      detail.segmentStartSec,
      detail.segmentEndSec
    );

    state.activeSuggestion = {
      suggestionIndex: normalizedSuggestionIndex,
      segmentStartSec: toFiniteNumber(detail.segmentStartSec),
      segmentEndSec: toFiniteNumber(detail.segmentEndSec),
      meta: suggestion,
    };

    render();
  }

  function onLoadPriorClick() {
    if (!state.priorDecision) {
      return;
    }

    state.region = {
      startSec: roundSec(state.priorDecision.start_sec),
      endSec: roundSec(state.priorDecision.end_sec),
    };
    state.activeSuggestion = decisionToSuggestionContext(state.priorDecision);

    document.dispatchEvent(new CustomEvent('se:seek', {
      detail: {
        timeSec: state.priorDecision.start_sec,
        createRegion: true,
        regionDurationSec: Math.max(0.05, state.priorDecision.end_sec - state.priorDecision.start_sec),
      }
    }));

    setFeedback('Loaded prior region into the waveform.');
    render();
  }

  function onAssignClick() {
    if (!state.context || !state.context.speaker || !state.context.conceptId) {
      setFeedback('No active speaker/concept context to assign into.', true);
      render();
      return;
    }
    if (!state.region || !isValidRegion(state.region.startSec, state.region.endSec)) {
      setFeedback('Select a valid waveform region before assigning.', true);
      render();
      return;
    }

    ensureDecisionsStore();

    var conceptId = String(state.context.conceptId);
    var speaker = state.context.speaker;
    var sourceWav = state.context.sourceWav || resolveSourceWav(speaker, conceptId, null);

    if (!SE.decisions[conceptId] || typeof SE.decisions[conceptId] !== 'object') {
      SE.decisions[conceptId] = {};
    }
    if (!SE.decisions[conceptId].source_regions || typeof SE.decisions[conceptId].source_regions !== 'object') {
      SE.decisions[conceptId].source_regions = {};
    }

    var existing = SE.decisions[conceptId].source_regions[speaker] || {};
    var nextRegion = {
      source_wav: sourceWav || existing.source_wav || null,
      start_sec: roundSec(state.region.startSec),
      end_sec: roundSec(state.region.endSec),
      assigned: true,
      replaces_segment: existing.replaces_segment !== false,
    };

    if (existing.notes) {
      nextRegion.notes = existing.notes;
    }

    var suggestionPayload = buildSuggestionPayload();
    if (suggestionPayload.aiSuggestionUsed != null) {
      nextRegion.ai_suggestion_used = suggestionPayload.aiSuggestionUsed;
    }
    if (suggestionPayload.aiSuggestionConfidence != null) {
      nextRegion.ai_suggestion_confidence = suggestionPayload.aiSuggestionConfidence;
    }
    if (suggestionPayload.aiSuggestionScore != null) {
      nextRegion.ai_suggestion_score = suggestionPayload.aiSuggestionScore;
    }

    SE.decisions[conceptId].source_regions[speaker] = nextRegion;
    persistDecisions();

    state.priorDecision = clone(nextRegion);
    setFeedback('Assigned ' + formatTimeRange(nextRegion.start_sec, nextRegion.end_sec) + ' to concept #' + conceptId + '.');

    var eventDetail = {
      speaker: speaker,
      conceptId: conceptId,
      startSec: nextRegion.start_sec,
      endSec: nextRegion.end_sec,
      sourceWav: nextRegion.source_wav,
    };
    if (suggestionPayload.aiSuggestionUsed != null) {
      eventDetail.aiSuggestionUsed = suggestionPayload.aiSuggestionUsed;
    }
    if (suggestionPayload.aiSuggestionConfidence != null) {
      eventDetail.aiSuggestionConfidence = suggestionPayload.aiSuggestionConfidence;
    }
    if (suggestionPayload.aiSuggestionScore != null) {
      eventDetail.aiSuggestionScore = suggestionPayload.aiSuggestionScore;
    }

    document.dispatchEvent(new CustomEvent('se:region-assigned', {
      detail: eventDetail,
    }));

    render();
  }

  function render() {
    if (!rootEl) {
      return;
    }

    renderStatus();
    renderCurrentRegion();
    renderSuggestion();
    renderPriorDecision();
    renderButtons();
  }

  function renderStatus() {
    if (!els.status) {
      return;
    }

    if (!state.context || !state.context.speaker || !state.context.conceptId) {
      els.status.textContent = 'No source explorer panel is active.';
      return;
    }

    var contextText = state.context.speaker + ' · concept #' + state.context.conceptId;
    if (state.context.sourceWav) {
      contextText += ' · ' + basename(state.context.sourceWav);
    }
    els.status.textContent = contextText;
  }

  function renderCurrentRegion() {
    if (!els.current) {
      return;
    }

    if (!state.context) {
      els.current.innerHTML = '<div style="font-weight:600;">Current region</div><div style="margin-top:4px;color:#64748b;">Open a panel to track waveform selections.</div>';
      return;
    }

    var body = ['<div style="font-weight:600;">Current region</div>'];
    if (state.region) {
      body.push(
        '<div style="margin-top:4px;">' +
          '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:#dcfce7;color:#166534;font-weight:600;">Ready to assign</span>' +
        '</div>'
      );
      body.push('<div style="margin-top:6px;font-size:15px;">' + escapeHtml(formatTimeRange(state.region.startSec, state.region.endSec)) + '</div>');
      body.push('<div style="margin-top:2px;color:#475569;">Duration: ' + escapeHtml(formatDuration(state.region.endSec - state.region.startSec)) + '</div>');
    } else {
      body.push('<div style="margin-top:4px;color:#64748b;">No valid waveform region selected yet. Drag a region in the waveform first.</div>');
    }

    els.current.innerHTML = body.join('');
  }

  function renderSuggestion() {
    if (!els.suggestion) {
      return;
    }

    if (!state.activeSuggestion) {
      els.suggestion.style.display = 'none';
      els.suggestion.innerHTML = '';
      return;
    }

    var meta = state.activeSuggestion.meta || {};
    var parts = ['<div style="font-weight:600;">AI suggestion attached</div>'];
    var labelBits = [];

    if (state.activeSuggestion.suggestionIndex != null) {
      labelBits.push('#' + state.activeSuggestion.suggestionIndex);
    }
    if (meta.confidence) {
      labelBits.push(String(meta.confidence).toUpperCase());
    }
    if (meta.confidence_score != null) {
      labelBits.push(Number(meta.confidence_score).toFixed(2));
    }
    if (labelBits.length) {
      parts.push('<div style="margin-top:4px;">' + escapeHtml(labelBits.join(' · ')) + '</div>');
    }

    var timeText = formatTimeRange(state.activeSuggestion.segmentStartSec, state.activeSuggestion.segmentEndSec);
    if (timeText) {
      parts.push('<div style="margin-top:2px;">Suggestion window: ' + escapeHtml(timeText) + '</div>');
    }
    if (meta.method) {
      parts.push('<div style="margin-top:2px;color:#7c2d12;">Method: ' + escapeHtml(meta.method) + '</div>');
    }

    els.suggestion.style.display = 'block';
    els.suggestion.innerHTML = parts.join('');
  }

  function renderPriorDecision() {
    if (!els.prior) {
      return;
    }

    var content = ['<div style="font-weight:600;">Prior assignment</div>'];

    if (!state.context) {
      content.push('<div style="margin-top:4px;color:#64748b;">Open a panel to inspect existing source-region decisions.</div>');
      els.prior.innerHTML = content.join('');
      return;
    }

    state.priorDecision = getDecisionForCurrentContext();

    if (!state.priorDecision) {
      content.push('<div style="margin-top:4px;color:#64748b;">No previous source-region assignment for this speaker/concept.</div>');
      els.prior.innerHTML = content.join('');
      return;
    }

    content.push('<div style="margin-top:4px;">' + escapeHtml(formatTimeRange(state.priorDecision.start_sec, state.priorDecision.end_sec)) + '</div>');
    content.push('<div style="margin-top:2px;color:#475569;">Source: ' + escapeHtml(basename(state.priorDecision.source_wav || state.context.sourceWav || 'unknown')) + '</div>');

    var metaBits = [];
    if (state.priorDecision.ai_suggestion_used != null) {
      metaBits.push('AI #' + state.priorDecision.ai_suggestion_used);
    }
    if (state.priorDecision.ai_suggestion_confidence) {
      metaBits.push(String(state.priorDecision.ai_suggestion_confidence).toUpperCase());
    }
    if (state.priorDecision.ai_suggestion_score != null) {
      metaBits.push(Number(state.priorDecision.ai_suggestion_score).toFixed(2));
    }
    if (metaBits.length) {
      content.push('<div style="margin-top:2px;color:#475569;">' + escapeHtml(metaBits.join(' · ')) + '</div>');
    }

    els.prior.innerHTML = content.join('');
  }

  function renderButtons() {
    if (els.assign) {
      var canAssign = !!(state.context && state.region && isValidRegion(state.region.startSec, state.region.endSec));
      els.assign.disabled = !canAssign;
      els.assign.style.opacity = canAssign ? '1' : '0.55';
      els.assign.style.cursor = canAssign ? 'pointer' : 'not-allowed';
    }

    if (els.loadPrior) {
      var canLoadPrior = !!(state.priorDecision && isValidRegion(state.priorDecision.start_sec, state.priorDecision.end_sec));
      els.loadPrior.disabled = !canLoadPrior;
      els.loadPrior.style.opacity = canLoadPrior ? '1' : '0.55';
      els.loadPrior.style.cursor = canLoadPrior ? 'pointer' : 'not-allowed';
    }
  }

  function setFeedback(message, isError) {
    if (!els.feedback) {
      return;
    }
    els.feedback.textContent = message || '';
    els.feedback.style.color = isError ? '#b91c1c' : '#475569';
  }

  function resetState() {
    state.context = null;
    state.region = null;
    state.priorDecision = null;
    state.activeSuggestion = null;
  }

  function ensureDecisionsStore() {
    if (!SE.decisions || typeof SE.decisions !== 'object') {
      SE.decisions = {};
    }
  }

  function persistDecisions() {
    try {
      localStorage.setItem(DECISIONS_LS_KEY, JSON.stringify(SE.decisions || {}));
    } catch (error) {
      console.warn('[region-manager] Failed to persist decisions:', error);
    }
  }

  function getDecisionForCurrentContext() {
    if (!state.context || !state.context.conceptId || !state.context.speaker) {
      return null;
    }

    ensureDecisionsStore();

    var concept = SE.decisions[String(state.context.conceptId)];
    if (!concept || !concept.source_regions) {
      return null;
    }

    var region = concept.source_regions[state.context.speaker];
    if (!region || !isValidRegion(region.start_sec, region.end_sec)) {
      return null;
    }

    return clone(region);
  }

  function resolveSourceWav(speaker, conceptId, explicitSourceWav) {
    if (explicitSourceWav) {
      return explicitSourceWav;
    }

    ensureDecisionsStore();
    var conceptKey = conceptId != null ? String(conceptId) : null;
    if (conceptKey && SE.decisions[conceptKey] && SE.decisions[conceptKey].source_regions) {
      var existing = SE.decisions[conceptKey].source_regions[speaker];
      if (existing && existing.source_wav) {
        return existing.source_wav;
      }
    }

    if (
      SE.sourceIndex &&
      SE.sourceIndex.speakers &&
      speaker &&
      SE.sourceIndex.speakers[speaker] &&
      Array.isArray(SE.sourceIndex.speakers[speaker].source_wavs)
    ) {
      var wavs = SE.sourceIndex.speakers[speaker].source_wavs;
      for (var i = 0; i < wavs.length; i += 1) {
        if (wavs[i] && wavs[i].is_primary) {
          return wavs[i].filename || null;
        }
      }
      return wavs[0] && wavs[0].filename ? wavs[0].filename : null;
    }

    return null;
  }

  function resolveSuggestionMeta(conceptId, speaker, suggestionIndex, segmentStartSec, segmentEndSec) {
    if (
      !SE.suggestions ||
      !SE.suggestions.suggestions ||
      !conceptId ||
      !speaker
    ) {
      return null;
    }

    var conceptSuggestions = SE.suggestions.suggestions[String(conceptId)];
    if (!conceptSuggestions || !conceptSuggestions.speakers || !Array.isArray(conceptSuggestions.speakers[speaker])) {
      return null;
    }

    var items = conceptSuggestions.speakers[speaker];
    var targetStart = toFiniteNumber(segmentStartSec);
    var targetEnd = toFiniteNumber(segmentEndSec);
    var i;

    for (i = 0; i < items.length; i += 1) {
      if (!items[i]) {
        continue;
      }
      if (nearlyEqual(items[i].segment_start_sec, targetStart) && nearlyEqual(items[i].segment_end_sec, targetEnd)) {
        return clone(items[i]);
      }
    }

    if (typeof suggestionIndex === 'number') {
      if (items[suggestionIndex]) {
        return clone(items[suggestionIndex]);
      }
      if (suggestionIndex > 0 && items[suggestionIndex - 1]) {
        return clone(items[suggestionIndex - 1]);
      }
    }

    return null;
  }

  function decisionToSuggestionContext(decision) {
    if (!decision) {
      return null;
    }

    var hasMeta = (
      decision.ai_suggestion_used != null ||
      decision.ai_suggestion_confidence != null ||
      decision.ai_suggestion_score != null
    );

    if (!hasMeta) {
      return null;
    }

    return {
      suggestionIndex: decision.ai_suggestion_used,
      segmentStartSec: decision.start_sec,
      segmentEndSec: decision.end_sec,
      meta: {
        confidence: decision.ai_suggestion_confidence,
        confidence_score: decision.ai_suggestion_score,
      }
    };
  }

  function regionStillMatchesSuggestion(region, suggestionCtx) {
    if (!region || !suggestionCtx) {
      return false;
    }

    var s0 = toFiniteNumber(suggestionCtx.segmentStartSec);
    var s1 = toFiniteNumber(suggestionCtx.segmentEndSec);
    if (!isValidRegion(s0, s1)) {
      return true;
    }

    if (rangesOverlap(region.startSec, region.endSec, s0, s1)) {
      return true;
    }

    return Math.abs(region.startSec - s0) <= 10 || Math.abs(region.endSec - s1) <= 10;
  }

  function buildSuggestionPayload() {
    var payload = {
      aiSuggestionUsed: null,
      aiSuggestionConfidence: null,
      aiSuggestionScore: null,
    };

    if (!state.activeSuggestion) {
      return payload;
    }

    payload.aiSuggestionUsed = state.activeSuggestion.suggestionIndex;

    var meta = state.activeSuggestion.meta || {};
    if (meta.confidence != null) {
      payload.aiSuggestionConfidence = meta.confidence;
    }
    if (meta.confidence_score != null && isFiniteNumber(meta.confidence_score)) {
      payload.aiSuggestionScore = roundScore(meta.confidence_score);
    }

    return payload;
  }

  function getExportState() {
    ensureDecisionsStore();

    var concepts = {};
    var conceptIds = Object.keys(SE.decisions || {});
    for (var i = 0; i < conceptIds.length; i += 1) {
      var conceptId = conceptIds[i];
      var concept = SE.decisions[conceptId];
      if (!concept || !concept.source_regions || typeof concept.source_regions !== 'object') {
        continue;
      }

      var speakerIds = Object.keys(concept.source_regions);
      var filtered = {};
      for (var j = 0; j < speakerIds.length; j += 1) {
        var speakerId = speakerIds[j];
        var region = concept.source_regions[speakerId];
        if (!region || !region.assigned || !isValidRegion(region.start_sec, region.end_sec)) {
          continue;
        }
        filtered[speakerId] = clone(region);
      }

      if (Object.keys(filtered).length > 0) {
        concepts[conceptId] = {
          source_regions: filtered,
        };
      }
    }

    return {
      decisions: concepts,
      currentContext: state.context ? clone(state.context) : null,
      currentRegion: state.region ? clone(state.region) : null,
    };
  }

  function getCurrentDecision() {
    return state.priorDecision ? clone(state.priorDecision) : getDecisionForCurrentContext();
  }

  function getCurrentRegion() {
    return state.region ? clone(state.region) : null;
  }

  function getContext() {
    return state.context ? clone(state.context) : null;
  }

  function isValidRegion(startSec, endSec) {
    return isFiniteNumber(startSec) && isFiniteNumber(endSec) && endSec > startSec;
  }

  function isFiniteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function toFiniteNumber(value) {
    if (typeof value === 'number' && isFinite(value)) {
      return value;
    }
    if (typeof value === 'string' && value.trim() !== '') {
      var parsed = Number(value);
      return isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function roundSec(value) {
    return Math.round(Number(value) * 1000) / 1000;
  }

  function roundScore(value) {
    return Math.round(Number(value) * 1000) / 1000;
  }

  function nearlyEqual(a, b) {
    var aa = toFiniteNumber(a);
    var bb = toFiniteNumber(b);
    if (aa == null || bb == null) {
      return false;
    }
    return Math.abs(aa - bb) < 0.001;
  }

  function rangesOverlap(a0, a1, b0, b1) {
    return Math.max(a0, b0) <= Math.min(a1, b1);
  }

  function formatTimeRange(startSec, endSec) {
    if (!isValidRegion(startSec, endSec)) {
      return '';
    }
    return formatTime(startSec) + ' → ' + formatTime(endSec);
  }

  function formatDuration(durationSec) {
    var secs = toFiniteNumber(durationSec);
    if (secs == null) {
      return '—';
    }
    if (secs < 1) {
      return secs.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + 's';
    }
    if (secs < 10) {
      return secs.toFixed(2).replace(/0+$/, '').replace(/\.$/, '') + 's';
    }
    return secs.toFixed(1).replace(/0+$/, '').replace(/\.$/, '') + 's';
  }

  function formatTime(value) {
    var sec = toFiniteNumber(value);
    if (sec == null) {
      return '—';
    }

    var whole = Math.floor(sec);
    var hours = Math.floor(whole / 3600);
    var minutes = Math.floor((whole % 3600) / 60);
    var seconds = whole % 60;
    var millis = Math.round((sec - whole) * 1000);

    if (millis === 1000) {
      millis = 0;
      seconds += 1;
      if (seconds === 60) {
        seconds = 0;
        minutes += 1;
        if (minutes === 60) {
          minutes = 0;
          hours += 1;
        }
      }
    }

    var head = hours > 0
      ? hours + ':' + pad2(minutes) + ':' + pad2(seconds)
      : minutes + ':' + pad2(seconds);

    return head + '.' + pad3(millis);
  }

  function pad2(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function pad3(value) {
    if (value < 10) return '00' + value;
    if (value < 100) return '0' + value;
    return String(value);
  }

  function basename(path) {
    if (!path) {
      return '';
    }
    return String(path).split('/').pop();
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  var api = {
    init: init,
    destroy: destroy,
    getContext: getContext,
    getCurrentRegion: getCurrentRegion,
    getCurrentDecision: getCurrentDecision,
    getExportState: getExportState,
    assignCurrentRegion: onAssignClick,
    loadPriorRegion: onLoadPriorClick,
  };

  SE.modules.regions = api;
})();
