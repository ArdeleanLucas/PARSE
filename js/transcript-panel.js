/**
 * transcript-panel.js — Source Explorer transcript panel
 *
 * Responsibilities:
 *  - Attach to window.SourceExplorer.modules.transcript
 *  - Render the current speaker's coarse transcript into #se-transcript
 *  - Support search/filter across transcript text
 *  - Keep rendering efficient for ~800 segments via simple windowing
 *  - Highlight the active segment from se:playback-position updates
 *  - Dispatch se:transcript-click and se:seek on row click
 *  - Fully clean up per-panel UI/listeners/state on se:panel-close
 */
(function () {
  'use strict';

  // ───────────────────────────────────────────────────────────────────────────
  // Namespace guard
  // ───────────────────────────────────────────────────────────────────────────

  window.SourceExplorer = window.SourceExplorer || {};
  window.SourceExplorer.modules = window.SourceExplorer.modules || {};

  const SE = window.SourceExplorer;

  // ───────────────────────────────────────────────────────────────────────────
  // Constants
  // ───────────────────────────────────────────────────────────────────────────

  const STYLE_ID = 'se-transcript-panel-styles';
  const DEFAULT_VIEWPORT_HEIGHT = 360;
  const ROW_HEIGHT = 68;
  const OVERSCAN_ROWS = 6;
  const AUTO_REVEAL_SCROLL_GRACE_MS = 2500;

  // ───────────────────────────────────────────────────────────────────────────
  // Module state
  // ───────────────────────────────────────────────────────────────────────────

  const state = {
    containerEl: null,
    rootEl: null,
    searchInputEl: null,
    clearBtnEl: null,
    summaryEl: null,
    hintEl: null,
    viewportEl: null,
    listEl: null,
    emptyEl: null,

    currentSpeaker: null,
    currentSourceWav: null,
    currentTimeSec: null,
    isOpen: false,

    allSegments: [],
    filteredSegments: [],
    filteredIndexByOriginal: new Map(),

    searchQuery: '',
    activeOriginalIndex: -1,
    activeFilteredIndex: -1,

    renderQueued: false,
    rafId: 0,
    suppressManualScrollTracking: false,
    manualScrollUntil: 0,

    uiListenersAttached: false,
    onSearchInput: null,
    onClearClick: null,
    onViewportScroll: null,
    onViewportClick: null,
  };

  // ───────────────────────────────────────────────────────────────────────────
  // Utilities
  // ───────────────────────────────────────────────────────────────────────────

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.se-transcript-panel{display:flex;flex-direction:column;gap:10px;min-height:180px;color:#1f2937;}',
      '.se-transcript-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;}',
      '.se-transcript-search-wrap{display:flex;align-items:center;gap:8px;flex:1 1 320px;min-width:220px;}',
      '.se-transcript-search-label{font-size:12px;font-weight:600;color:#4b5563;white-space:nowrap;}',
      '.se-transcript-search{flex:1 1 auto;min-width:0;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;font:inherit;}',
      '.se-transcript-search:focus{outline:none;border-color:#4a9eff;box-shadow:0 0 0 3px rgba(74,158,255,0.18);}',
      '.se-transcript-clear{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:7px 10px;cursor:pointer;font:inherit;color:#374151;}',
      '.se-transcript-clear[hidden]{display:none !important;}',
      '.se-transcript-summary{font-size:12px;color:#4b5563;white-space:nowrap;}',
      '.se-transcript-hint{font-size:12px;color:#6b7280;}',
      '.se-transcript-viewport{position:relative;height:' + DEFAULT_VIEWPORT_HEIGHT + 'px;overflow:auto;border:1px solid #dbe4f0;border-radius:10px;background:#fff;box-shadow:inset 0 1px 2px rgba(15,23,42,0.04);}',
      '.se-transcript-list{position:relative;width:100%;min-height:100%;}',
      '.se-transcript-empty{display:flex;align-items:center;justify-content:center;min-height:160px;padding:20px;text-align:center;color:#6b7280;font-size:14px;}',
      '.se-transcript-row{position:absolute;left:0;right:0;height:' + ROW_HEIGHT + 'px;padding:6px 8px;box-sizing:border-box;}',
      '.se-transcript-row-btn{display:grid;grid-template-columns:92px minmax(0,1fr);align-items:start;gap:12px;width:100%;height:100%;padding:10px 12px;border:1px solid transparent;border-radius:10px;background:transparent;text-align:left;cursor:pointer;color:inherit;}',
      '.se-transcript-row-btn:hover{background:#f8fbff;border-color:#d6e8ff;}',
      '.se-transcript-row-btn:focus{outline:none;border-color:#4a9eff;box-shadow:0 0 0 3px rgba(74,158,255,0.18);}',
      '.se-transcript-row.is-match .se-transcript-row-btn{background:#fbfdff;}',
      '.se-transcript-row.is-active .se-transcript-row-btn{background:#eaf4ff;border-color:#7bb8ff;box-shadow:inset 3px 0 0 #1d78d6;}',
      '.se-transcript-row.is-active .se-transcript-time{color:#155b9e;font-weight:700;}',
      '.se-transcript-time{font-variant-numeric:tabular-nums;font-size:12px;font-weight:600;color:#4b5563;padding-top:2px;}',
      '.se-transcript-text{font-size:14px;line-height:1.35;color:#111827;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word;overflow-wrap:anywhere;}',
      '.se-transcript-text.is-muted{color:#6b7280;font-style:italic;}',
      '.se-transcript-current-hidden{color:#9a3412;}',
      '@media (max-width: 720px){',
      '  .se-transcript-row-btn{grid-template-columns:78px minmax(0,1fr);gap:10px;padding:10px;}',
      '  .se-transcript-viewport{height:300px;}',
      '}'
    ].join('');
    document.head.appendChild(style);
  }

  function formatTime(sec) {
    if (!Number.isFinite(sec)) return '—';

    const whole = Math.max(0, Math.floor(sec));
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const seconds = whole % 60;

    if (hours > 0) {
      return hours + ':' + pad2(minutes) + ':' + pad2(seconds);
    }
    return minutes + ':' + pad2(seconds);
  }

  function pad2(num) {
    return num < 10 ? '0' + num : String(num);
  }

  function safeNumber(value, fallback) {
    return Number.isFinite(value) ? value : fallback;
  }

  function normalizeText(value) {
    if (value == null) return '';
    let text = String(value);

    try {
      text = text.normalize('NFC');
    } catch (_) {
      // Some environments can throw on malformed surrogate pairs; ignore.
    }

    return text
      .toLocaleLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  function cancelScheduledRender() {
    state.renderQueued = false;
    if (state.rafId) {
      cancelAnimationFrame(state.rafId);
      state.rafId = 0;
    }
  }

  function scheduleRender() {
    if (!state.isOpen || state.renderQueued) return;

    state.renderQueued = true;
    state.rafId = requestAnimationFrame(function () {
      state.renderQueued = false;
      state.rafId = 0;
      renderRows();
    });
  }

  function getTranscriptForSpeaker(speaker) {
    if (!speaker || !SE.transcripts || typeof SE.transcripts !== 'object') {
      return null;
    }
    return SE.transcripts[speaker] || null;
  }

  function normalizeSegments(transcript) {
    const rawSegments = Array.isArray(transcript)
      ? transcript
      : (transcript && Array.isArray(transcript.segments) ? transcript.segments : []);

    return rawSegments
      .map(function (segment, index) {
        const start = safeNumber(Number(segment && segment.start), 0);
        const rawEnd = safeNumber(Number(segment && segment.end), start);
        const end = rawEnd >= start ? rawEnd : start;
        const text = segment && segment.text != null ? String(segment.text) : '';

        return {
          originalIndex: index,
          start: start,
          end: end,
          text: text,
          normalizedText: normalizeText(text),
        };
      })
      .sort(function (a, b) {
        return (a.start - b.start) || (a.end - b.end) || (a.originalIndex - b.originalIndex);
      });
  }

  function findActiveSegmentIndex(timeSec) {
    if (!Number.isFinite(timeSec) || state.allSegments.length === 0) {
      return -1;
    }

    let low = 0;
    let high = state.allSegments.length - 1;
    let found = -1;

    // We treat the "active" transcript row as the most recent coarse segment
    // whose start time is <= playback time. This works better than strict
    // [start,end] matching because coarse transcripts are often sparse windows.
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      if (state.allSegments[mid].start <= timeSec) {
        found = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    return found;
  }

  function updateActiveIndex(nextOriginalIndex, opts) {
    const options = opts || {};
    if (state.activeOriginalIndex === nextOriginalIndex) return;

    state.activeOriginalIndex = nextOriginalIndex;
    state.activeFilteredIndex = state.filteredIndexByOriginal.has(nextOriginalIndex)
      ? state.filteredIndexByOriginal.get(nextOriginalIndex)
      : -1;

    updateSummary();
    scheduleRender();

    if (options.reveal !== false) {
      maybeRevealActiveRow();
    }
  }

  function maybeRevealActiveRow() {
    if (!state.isOpen) return;
    if (state.searchQuery) return;
    if (!state.viewportEl) return;
    if (state.activeFilteredIndex < 0) return;
    if (Date.now() < state.manualScrollUntil) return;

    const viewport = state.viewportEl;
    const rowTop = state.activeFilteredIndex * ROW_HEIGHT;
    const rowBottom = rowTop + ROW_HEIGHT;
    const viewTop = viewport.scrollTop;
    const viewBottom = viewTop + viewport.clientHeight;
    const cushion = ROW_HEIGHT * 1.5;

    if (rowTop >= viewTop + cushion && rowBottom <= viewBottom - cushion) {
      return;
    }

    const targetTop = Math.max(0, rowTop - Math.max(0, (viewport.clientHeight - ROW_HEIGHT) / 2));
    state.suppressManualScrollTracking = true;
    viewport.scrollTop = targetTop;

    requestAnimationFrame(function () {
      state.suppressManualScrollTracking = false;
      scheduleRender();
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // DOM construction and cleanup
  // ───────────────────────────────────────────────────────────────────────────

  function buildShell() {
    if (!state.containerEl) {
      state.containerEl = document.getElementById('se-transcript');
    }
    if (!state.containerEl) return;

    state.containerEl.innerHTML = '';

    const root = document.createElement('section');
    root.className = 'se-transcript-panel';

    const toolbar = document.createElement('div');
    toolbar.className = 'se-transcript-toolbar';

    const searchWrap = document.createElement('div');
    searchWrap.className = 'se-transcript-search-wrap';

    const searchLabel = document.createElement('label');
    searchLabel.className = 'se-transcript-search-label';
    searchLabel.textContent = 'Transcript';
    searchLabel.setAttribute('for', 'se-transcript-search-input');

    const searchInput = document.createElement('input');
    searchInput.id = 'se-transcript-search-input';
    searchInput.className = 'se-transcript-search';
    searchInput.type = 'search';
    searchInput.placeholder = 'Search transcript text…';
    searchInput.autocomplete = 'off';
    searchInput.spellcheck = false;
    searchInput.value = state.searchQuery;
    searchInput.setAttribute('aria-label', 'Search transcript text');

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'se-transcript-clear';
    clearBtn.textContent = 'Clear';
    clearBtn.hidden = !state.searchQuery;
    clearBtn.setAttribute('aria-label', 'Clear transcript search');

    searchWrap.appendChild(searchLabel);
    searchWrap.appendChild(searchInput);
    searchWrap.appendChild(clearBtn);

    const summary = document.createElement('div');
    summary.className = 'se-transcript-summary';

    toolbar.appendChild(searchWrap);
    toolbar.appendChild(summary);

    const hint = document.createElement('div');
    hint.className = 'se-transcript-hint';
    hint.textContent = 'Click any segment to seek the audio. The active row follows playback.';

    const viewport = document.createElement('div');
    viewport.className = 'se-transcript-viewport';
    viewport.setAttribute('role', 'list');
    viewport.setAttribute('aria-label', 'Transcript segments');

    const list = document.createElement('div');
    list.className = 'se-transcript-list';
    viewport.appendChild(list);

    const empty = document.createElement('div');
    empty.className = 'se-transcript-empty';
    empty.hidden = true;

    root.appendChild(toolbar);
    root.appendChild(hint);
    root.appendChild(viewport);
    root.appendChild(empty);

    state.containerEl.appendChild(root);

    state.rootEl = root;
    state.searchInputEl = searchInput;
    state.clearBtnEl = clearBtn;
    state.summaryEl = summary;
    state.hintEl = hint;
    state.viewportEl = viewport;
    state.listEl = list;
    state.emptyEl = empty;
  }

  function attachUiListeners() {
    if (state.uiListenersAttached || !state.searchInputEl || !state.viewportEl) return;

    state.onSearchInput = function (event) {
      state.searchQuery = event.target.value || '';
      applyFilter();
    };

    state.onClearClick = function () {
      state.searchQuery = '';
      if (state.searchInputEl) {
        state.searchInputEl.value = '';
        state.searchInputEl.focus();
      }
      applyFilter();
    };

    state.onViewportScroll = function () {
      if (!state.suppressManualScrollTracking) {
        state.manualScrollUntil = Date.now() + AUTO_REVEAL_SCROLL_GRACE_MS;
      }
      scheduleRender();
    };

    state.onViewportClick = function (event) {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;

      const button = target.closest('[data-se-transcript-index]');
      if (!button || !state.viewportEl.contains(button)) return;

      const filteredIndex = Number(button.getAttribute('data-se-transcript-index'));
      if (!Number.isInteger(filteredIndex)) return;

      const segment = state.filteredSegments[filteredIndex];
      if (!segment) return;

      updateActiveIndex(segment.originalIndex, { reveal: true });

      emit('se:transcript-click', {
        segmentIndex: segment.originalIndex,
        startSec: segment.start,
      });

      emit('se:seek', {
        timeSec: segment.start,
      });
    };

    state.searchInputEl.addEventListener('input', state.onSearchInput);
    state.clearBtnEl.addEventListener('click', state.onClearClick);
    state.viewportEl.addEventListener('scroll', state.onViewportScroll, { passive: true });
    state.viewportEl.addEventListener('click', state.onViewportClick);

    state.uiListenersAttached = true;
  }

  function detachUiListeners() {
    if (!state.uiListenersAttached) return;

    if (state.searchInputEl && state.onSearchInput) {
      state.searchInputEl.removeEventListener('input', state.onSearchInput);
    }
    if (state.clearBtnEl && state.onClearClick) {
      state.clearBtnEl.removeEventListener('click', state.onClearClick);
    }
    if (state.viewportEl && state.onViewportScroll) {
      state.viewportEl.removeEventListener('scroll', state.onViewportScroll);
    }
    if (state.viewportEl && state.onViewportClick) {
      state.viewportEl.removeEventListener('click', state.onViewportClick);
    }

    state.onSearchInput = null;
    state.onClearClick = null;
    state.onViewportScroll = null;
    state.onViewportClick = null;
    state.uiListenersAttached = false;
  }

  function resetPanelState() {
    cancelScheduledRender();
    detachUiListeners();

    state.currentSpeaker = null;
    state.currentSourceWav = null;
    state.currentTimeSec = null;
    state.isOpen = false;

    state.allSegments = [];
    state.filteredSegments = [];
    state.filteredIndexByOriginal = new Map();

    state.searchQuery = '';
    state.activeOriginalIndex = -1;
    state.activeFilteredIndex = -1;

    state.suppressManualScrollTracking = false;
    state.manualScrollUntil = 0;

    if (state.containerEl) {
      state.containerEl.innerHTML = '';
    }

    state.rootEl = null;
    state.searchInputEl = null;
    state.clearBtnEl = null;
    state.summaryEl = null;
    state.hintEl = null;
    state.viewportEl = null;
    state.listEl = null;
    state.emptyEl = null;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Rendering
  // ───────────────────────────────────────────────────────────────────────────

  function updateSummary() {
    if (!state.summaryEl || !state.hintEl) return;

    if (!state.currentSpeaker) {
      state.summaryEl.textContent = 'No transcript loaded';
      state.hintEl.textContent = 'Open a Source Explorer panel to load a speaker transcript.';
      return;
    }

    const total = state.allSegments.length;
    const filtered = state.filteredSegments.length;

    if (!total) {
      state.summaryEl.textContent = 'No transcript data';
      state.hintEl.textContent = 'This speaker has no coarse transcript loaded in window.SourceExplorer.transcripts.';
      return;
    }

    let summary = state.currentSpeaker + ' · ';
    summary += state.searchQuery
      ? (filtered + ' / ' + total + ' matching segments')
      : (total + ' segments');

    if (state.activeOriginalIndex >= 0) {
      const active = state.allSegments[state.activeOriginalIndex];
      if (active) {
        summary += ' · current ' + formatTime(active.start);
      }
    }

    state.summaryEl.textContent = summary;

    if (!state.searchQuery) {
      state.hintEl.textContent = 'Click any segment to seek the audio. The active row follows playback.';
      return;
    }

    if (filtered === 0) {
      state.hintEl.textContent = 'No transcript segments match the current search.';
      return;
    }

    if (state.activeOriginalIndex >= 0 && state.activeFilteredIndex < 0) {
      state.hintEl.innerHTML = 'Showing filtered matches only. <span class="se-transcript-current-hidden">Current playback row is hidden by search.</span>';
      return;
    }

    state.hintEl.textContent = 'Showing only transcript rows matching the current search.';
  }

  function updateEmptyState() {
    if (!state.emptyEl || !state.viewportEl || !state.listEl) return;

    const hasRows = state.filteredSegments.length > 0;
    state.emptyEl.hidden = hasRows;
    state.viewportEl.hidden = !hasRows;

    if (hasRows) {
      state.emptyEl.textContent = '';
      return;
    }

    if (!state.currentSpeaker) {
      state.emptyEl.textContent = 'Open a Source Explorer panel to view transcript segments.';
      return;
    }

    if (state.allSegments.length === 0) {
      state.emptyEl.textContent = 'No transcript is available for ' + state.currentSpeaker + '.';
      return;
    }

    state.emptyEl.textContent = 'No transcript segments match “' + state.searchQuery + '”.';
  }

  function renderRows() {
    if (!state.listEl || !state.viewportEl) return;

    updateEmptyState();
    if (state.filteredSegments.length === 0) {
      state.listEl.innerHTML = '';
      state.listEl.style.height = '0px';
      return;
    }

    const total = state.filteredSegments.length;
    const viewportHeight = state.viewportEl.clientHeight || DEFAULT_VIEWPORT_HEIGHT;
    const scrollTop = state.viewportEl.scrollTop || 0;

    let startIndex = Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_ROWS;
    let endIndex = Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN_ROWS;

    if (startIndex < 0) startIndex = 0;
    if (endIndex > total - 1) endIndex = total - 1;

    state.listEl.style.height = String(total * ROW_HEIGHT) + 'px';
    state.listEl.innerHTML = '';

    const fragment = document.createDocumentFragment();

    for (let filteredIndex = startIndex; filteredIndex <= endIndex; filteredIndex += 1) {
      const segment = state.filteredSegments[filteredIndex];
      if (!segment) continue;

      const row = document.createElement('div');
      row.className = 'se-transcript-row';
      if (state.searchQuery) row.classList.add('is-match');
      if (segment.originalIndex === state.activeOriginalIndex) row.classList.add('is-active');
      row.style.transform = 'translateY(' + (filteredIndex * ROW_HEIGHT) + 'px)';

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'se-transcript-row-btn';
      button.setAttribute('data-se-transcript-index', String(filteredIndex));
      button.setAttribute('role', 'listitem');
      button.setAttribute(
        'aria-label',
        'Seek to transcript segment at ' + formatTime(segment.start)
      );

      const timeEl = document.createElement('div');
      timeEl.className = 'se-transcript-time';
      timeEl.textContent = formatTime(segment.start);

      const textEl = document.createElement('div');
      textEl.className = 'se-transcript-text';
      if (segment.text) {
        textEl.textContent = segment.text;
      } else {
        textEl.textContent = '(No transcript text)';
        textEl.classList.add('is-muted');
      }

      button.appendChild(timeEl);
      button.appendChild(textEl);
      row.appendChild(button);
      fragment.appendChild(row);
    }

    state.listEl.appendChild(fragment);
  }

  function applyFilter() {
    const query = normalizeText(state.searchQuery);

    if (state.clearBtnEl) {
      state.clearBtnEl.hidden = !query;
    }

    if (!query) {
      state.filteredSegments = state.allSegments.slice();
    } else {
      state.filteredSegments = state.allSegments.filter(function (segment) {
        return segment.normalizedText.indexOf(query) !== -1;
      });
    }

    state.filteredIndexByOriginal = new Map();
    state.filteredSegments.forEach(function (segment, filteredIndex) {
      state.filteredIndexByOriginal.set(segment.originalIndex, filteredIndex);
    });

    state.activeFilteredIndex = state.filteredIndexByOriginal.has(state.activeOriginalIndex)
      ? state.filteredIndexByOriginal.get(state.activeOriginalIndex)
      : -1;

    if (state.viewportEl) {
      state.suppressManualScrollTracking = true;
      state.viewportEl.scrollTop = 0;
      requestAnimationFrame(function () {
        state.suppressManualScrollTracking = false;
      });
    }

    updateSummary();
    scheduleRender();
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Event handlers
  // ───────────────────────────────────────────────────────────────────────────

  function onPanelOpen(event) {
    const detail = (event && event.detail) || {};
    const speaker = detail.speaker || null;

    resetPanelState();
    state.isOpen = true;
    state.currentSpeaker = speaker;
    state.currentSourceWav = detail.sourceWav || null;
    state.currentTimeSec = Number.isFinite(detail.lexiconStartSec) ? detail.lexiconStartSec : null;

    buildShell();
    if (!state.rootEl) {
      return;
    }

    attachUiListeners();

    const transcript = getTranscriptForSpeaker(speaker);
    state.allSegments = normalizeSegments(transcript);

    updateSummary();
    applyFilter();

    if (Number.isFinite(state.currentTimeSec)) {
      updateActiveIndex(findActiveSegmentIndex(state.currentTimeSec), { reveal: true });
    } else {
      updateActiveIndex(-1, { reveal: false });
    }
  }

  function onPanelClose(event) {
    const detail = (event && event.detail) || {};
    if (detail.speaker && state.currentSpeaker && detail.speaker !== state.currentSpeaker) {
      return;
    }

    resetPanelState();
  }

  function onPlaybackPosition(event) {
    if (!state.isOpen) return;

    const detail = (event && event.detail) || {};
    const timeSec = Number(detail.timeSec);
    if (!Number.isFinite(timeSec)) return;

    state.currentTimeSec = timeSec;
    updateActiveIndex(findActiveSegmentIndex(timeSec), { reveal: true });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Public API
  // ───────────────────────────────────────────────────────────────────────────

  function init(containerEl) {
    ensureStyles();
    state.containerEl = containerEl || document.getElementById('se-transcript');

    document.addEventListener('se:panel-open', onPanelOpen);
    document.addEventListener('se:panel-close', onPanelClose);
    document.addEventListener('se:playback-position', onPlaybackPosition);

    return {
      refresh: function () {
        if (!state.isOpen || !state.currentSpeaker) return;
        const transcript = getTranscriptForSpeaker(state.currentSpeaker);
        state.allSegments = normalizeSegments(transcript);
        applyFilter();
        updateActiveIndex(findActiveSegmentIndex(state.currentTimeSec), { reveal: false });
      },
      getState: function () {
        return {
          speaker: state.currentSpeaker,
          sourceWav: state.currentSourceWav,
          searchQuery: state.searchQuery,
          totalSegments: state.allSegments.length,
          filteredSegments: state.filteredSegments.length,
          activeOriginalIndex: state.activeOriginalIndex,
          activeFilteredIndex: state.activeFilteredIndex,
        };
      }
    };
  }

  function destroy() {
    document.removeEventListener('se:panel-open', onPanelOpen);
    document.removeEventListener('se:panel-close', onPanelClose);
    document.removeEventListener('se:playback-position', onPlaybackPosition);

    resetPanelState();
    state.containerEl = null;
  }

  SE.modules.transcript = {
    init: init,
    destroy: destroy,
  };

}());
