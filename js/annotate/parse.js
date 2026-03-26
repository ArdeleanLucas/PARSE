/**
 * parse.js — PARSE Panel Orchestrator
 *
 * Singleton panel manager for the PARSE feature.
 * Attaches to window.PARSE.modules.panel.
 *
 * Responsibilities:
 *  - Singleton enforcement: only one panel open at a time
 *  - Context management: speaker, conceptId, sourceWav, lexiconStartSec
 *  - Panel show/hide and header population
 *  - Fullscreen reparenting (parse:fullscreen-toggle)
 *  - Concept navigation (parse:navigate-concept)
 *  - Region assignment indicator (parse:region-assigned)
 *  - localStorage persistence for lightweight UI state
 */
(function () {
  'use strict';

  // ── Namespace guard ─────────────────────────────────────────────────────────
  if (!window.PARSE) {
    window.PARSE = {};
  }
  if (!window.PARSE.modules) {
    window.PARSE.modules = {};
  }

  const SE = window.PARSE;

  // ── Constants ───────────────────────────────────────────────────────────────
  const LS_KEY = 'se-panel-state';

  // DOM IDs defined by the HTML shell (INTERFACES.md §DOM Contract)
  const PANEL_ID          = 'parse-panel';
  const HEADER_ID         = 'parse-header';
  const FULLSCREEN_OVL_ID = 'parse-fullscreen-overlay';

  // CSS classes
  const CLS_HIDDEN     = 'hidden';
  const CLS_FULLSCREEN = 'se-panel--fullscreen';

  // ── Module state ────────────────────────────────────────────────────────────
  let _containerEl    = null;   // element passed to init()
  let _panelEl        = null;   // #parse-panel
  let _headerEl       = null;   // #parse-header
  let _overlayEl      = null;   // #parse-fullscreen-overlay
  let _inlineParent   = null;   // original parent of _panelEl (for reparent restore)
  let _inlineNextSib  = null;   // original next sibling (for insertion order restore)
  let _isFullscreen   = false;
  let _isOpen         = false;
  let _pendingOpenDetail = null;

  // Current open context
  let _ctx = {
    speaker:        null,
    conceptId:      null,
    sourceWav:      null,
    lexiconStartSec: null,
  };

  // Bound event handler references (for removeEventListener)
  let _boundOnPanelOpen        = null;
  let _boundOnPanelClose       = null;
  let _boundOnFullscreenToggle = null;
  let _boundOnNavigateConcept  = null;
  let _boundOnRegionAssigned   = null;
  let _boundOnAnnotationsChanged = null;

  // ── localStorage helpers ────────────────────────────────────────────────────

  function _loadState() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function _saveState(patch) {
    try {
      const current = _loadState();
      const next = Object.assign({}, current, patch);
      localStorage.setItem(LS_KEY, JSON.stringify(next));
    } catch (_) {
      // Storage unavailable — silently ignore
    }
  }

  function _mergePersistedDecisions() {
    try {
      const rawDec = localStorage.getItem('se-decisions');
      if (!rawDec) return;

      const persisted = JSON.parse(rawDec);
      if (!persisted || typeof persisted !== 'object') return;

      if (!SE.decisions || typeof SE.decisions !== 'object') {
        SE.decisions = {};
      }

      Object.keys(persisted).forEach(function (conceptId) {
        const persistedEntry = persisted[conceptId];
        if (!persistedEntry || typeof persistedEntry !== 'object') return;

        if (!SE.decisions[conceptId] || typeof SE.decisions[conceptId] !== 'object') {
          SE.decisions[conceptId] = persistedEntry;
          return;
        }

        const targetEntry = SE.decisions[conceptId];
        const persistedRegions = persistedEntry.source_regions;
        if (!persistedRegions || typeof persistedRegions !== 'object') return;

        if (!targetEntry.source_regions || typeof targetEntry.source_regions !== 'object') {
          targetEntry.source_regions = {};
        }

        Object.keys(persistedRegions).forEach(function (speaker) {
          targetEntry.source_regions[speaker] = Object.assign(
            {},
            targetEntry.source_regions[speaker] || {},
            persistedRegions[speaker]
          );
        });
      });
    } catch (_) {
      // Invalid persisted decisions — silently ignore
    }
  }

  // ── DOM helpers ─────────────────────────────────────────────────────────────

  function _getPanelEl() {
    return document.getElementById(PANEL_ID);
  }

  function _getHeaderEl() {
    return document.getElementById(HEADER_ID);
  }

  function _getOverlayEl() {
    return document.getElementById(FULLSCREEN_OVL_ID);
  }

  /**
   * Build/refresh the header HTML for the current context.
   * Shows: speaker name, concept label, source WAV filename, lexicon start.
   */
  function _populateHeader(ctx) {
    if (!_headerEl) return;

    const SE_data = window.PARSE;

    // Resolve concept label from suggestions data (if available)
    let conceptLabel = ctx.conceptId ? '#' + ctx.conceptId : '';
    if (SE_data && SE_data.suggestions && SE_data.suggestions.suggestions) {
      const sugConcept = SE_data.suggestions.suggestions[ctx.conceptId];
      if (sugConcept && sugConcept.concept_en) {
        conceptLabel = '"' + sugConcept.concept_en + '" (#' + ctx.conceptId + ')';
      }
    }

    // Determine missing status for this concept/speaker
    let missingBadge = '';
    if (SE_data && SE_data.decisions) {
      const dec = SE_data.decisions[ctx.conceptId];
      const hasAssignment =
        dec &&
        dec.source_regions &&
        dec.source_regions[ctx.speaker] &&
        dec.source_regions[ctx.speaker].assigned;
      if (hasAssignment) {
        missingBadge =
          '<span class="se-badge se-badge--assigned" title="Already assigned">✓ Assigned</span>';
      } else {
        missingBadge =
          '<span class="se-badge se-badge--missing" title="No source region assigned yet">? Missing</span>';
      }
    }

    // Short filename for display
    const wavBasename = ctx.sourceWav
      ? ctx.sourceWav.split('/').pop()
      : '(unknown)';

    // Lexicon start
    const lexStart =
      ctx.lexiconStartSec != null
        ? _formatTimeSec(ctx.lexiconStartSec)
        : '—';

    _headerEl.innerHTML =
      '<div class="se-header__title">' +
        '<span class="se-header__speaker">' + _escHtml(ctx.speaker || '—') + '</span>' +
        ' — Concept ' + _escHtml(conceptLabel) +
        ' ' + missingBadge +
      '</div>' +
      '<div class="se-header__meta">' +
        '<span class="se-header__source-wav" title="' + _escHtml(ctx.sourceWav || '') + '">' +
          'Source: ' + _escHtml(wavBasename) +
        '</span>' +
        '<span class="se-header__lexicon-start">' +
          'Lexicon starts: ' + lexStart +
        '</span>' +
      '</div>' +
      '<div class="se-header__controls">' +
        '<button class="se-btn se-btn--collapse" id="parse-btn-collapse" title="Collapse panel" aria-label="Collapse PARSE panel">▼ Collapse</button>' +
        '<button class="se-btn se-btn--fullscreen" id="parse-btn-fullscreen" title="Toggle fullscreen" aria-label="Toggle fullscreen mode">⛶ Full</button>' +
      '</div>';

    // Wire up header buttons
    const collapseBtn = document.getElementById('parse-btn-collapse');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', function () {
        _dispatchClose(ctx.speaker);
      });
    }

    const fullscreenBtn = document.getElementById('parse-btn-fullscreen');
    if (fullscreenBtn) {
      fullscreenBtn.addEventListener('click', function () {
        document.dispatchEvent(
          new CustomEvent('parse:fullscreen-toggle', {
            detail: { active: !_isFullscreen },
          })
        );
      });
    }
  }

  // ── Event dispatchers ───────────────────────────────────────────────────────

  function _dispatchOpen(detail) {
    document.dispatchEvent(new CustomEvent('parse:panel-open', { detail: detail }));
  }

  function _dispatchClose(speaker) {
    document.dispatchEvent(
      new CustomEvent('parse:panel-close', { detail: { speaker: speaker } })
    );
  }

  // ── Internal open / close ───────────────────────────────────────────────────

  /**
   * Actually show the panel and populate it with context.
   * Called from the parse:panel-open handler AFTER singleton teardown.
   */
  function _openPanel(detail) {
    if (!_panelEl) return;

    _ctx = {
      speaker:         detail.speaker        || null,
      conceptId:       detail.conceptId      || null,
      sourceWav:       detail.sourceWav      || null,
      lexiconStartSec: detail.lexiconStartSec != null ? detail.lexiconStartSec : null,
    };

    _isOpen = true;

    // Restore inline position if currently in fullscreen overlay
    if (_isFullscreen) {
      _exitFullscreen();
    }

    _panelEl.classList.remove(CLS_HIDDEN);
    _panelEl.setAttribute('aria-hidden', 'false');

    _populateHeader(_ctx);

    // Persist last-open context
    _saveState({
      lastSpeaker:   _ctx.speaker,
      lastConceptId: _ctx.conceptId,
    });

    // Scroll panel into view if inline
    if (!_isFullscreen && _panelEl.scrollIntoView) {
      _panelEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * Hide the panel and clear context.
   * Called from the parse:panel-close handler.
   */
  function _closePanel() {
    if (!_panelEl) return;

    _isOpen = false;

    if (_isFullscreen) {
      _exitFullscreen();
    }

    _panelEl.classList.add(CLS_HIDDEN);
    _panelEl.setAttribute('aria-hidden', 'true');

    // Clear header
    if (_headerEl) {
      _headerEl.innerHTML = '';
    }

    // Clear context
    _ctx = {
      speaker:         null,
      conceptId:       null,
      sourceWav:       null,
      lexiconStartSec: null,
    };
  }

  // ── Fullscreen reparenting ──────────────────────────────────────────────────

  function _enterFullscreen() {
    if (_isFullscreen || !_panelEl || !_overlayEl) return;

    // Remember inline position so we can restore it
    _inlineParent  = _panelEl.parentNode;
    _inlineNextSib = _panelEl.nextSibling;

    _overlayEl.appendChild(_panelEl);
    _overlayEl.classList.remove(CLS_HIDDEN);
    _panelEl.classList.add(CLS_FULLSCREEN);

    _isFullscreen = true;

    // Update fullscreen button label
    const btn = document.getElementById('parse-btn-fullscreen');
    if (btn) btn.textContent = '✕ Exit Full';
  }

  function _exitFullscreen() {
    if (!_isFullscreen || !_panelEl) return;

    // Reparent back to original inline position
    if (_inlineParent) {
      if (_inlineNextSib && _inlineNextSib.parentNode === _inlineParent) {
        _inlineParent.insertBefore(_panelEl, _inlineNextSib);
      } else {
        _inlineParent.appendChild(_panelEl);
      }
    }

    if (_overlayEl) {
      _overlayEl.classList.add(CLS_HIDDEN);
    }

    _panelEl.classList.remove(CLS_FULLSCREEN);
    _isFullscreen = false;

    _inlineParent  = null;
    _inlineNextSib = null;

    // Restore fullscreen button label
    const btn = document.getElementById('parse-btn-fullscreen');
    if (btn) btn.textContent = '⛶ Full';
  }

  // ── Concept navigation ──────────────────────────────────────────────────────

  /**
   * Find the next or previous concept that is missing for the current speaker.
   * Returns the conceptId string or null if none found.
   *
   * @param {string} currentConceptId
   * @param {'prev'|'next'} direction
   * @param {boolean} missingOnly  — if true, skip concepts that already have an assignment
   * @returns {string|null}
   */
  function _findAdjacentConcept(currentConceptId, direction, missingOnly) {
    const SE_data = window.PARSE;
    const speaker = _ctx.speaker;

    if (!speaker) return null;

    // Collect ordered concept IDs.
    // Priority: from suggestions data (has concept_en labels, ordered by key)
    //           fallback: from decisions JSON keys
    //           fallback: numeric range 1..82 (known JBIL list length)
    let conceptIds = [];

    if (SE_data && SE_data.suggestions && SE_data.suggestions.suggestions) {
      conceptIds = Object.keys(SE_data.suggestions.suggestions);
    } else if (SE_data && SE_data.decisions) {
      conceptIds = Object.keys(SE_data.decisions);
    }

    if (conceptIds.length === 0) {
      // Fallback: generate 1..82
      for (let i = 1; i <= 82; i++) {
        conceptIds.push(String(i));
      }
    }

    // Sort numerically (concept IDs are numeric strings)
    conceptIds = conceptIds.slice().sort(function (a, b) {
      return parseInt(a, 10) - parseInt(b, 10);
    });

    const currentIdx = conceptIds.indexOf(String(currentConceptId));
    if (currentIdx === -1) return null;

    const step = direction === 'next' ? 1 : -1;
    let idx = currentIdx + step;

    while (idx >= 0 && idx < conceptIds.length) {
      const candidateId = conceptIds[idx];

      if (!missingOnly) {
        return candidateId;
      }

      // Check if this concept/speaker is already assigned
      const dec = SE_data && SE_data.decisions && SE_data.decisions[candidateId];
      const isAssigned =
        dec &&
        dec.source_regions &&
        dec.source_regions[speaker] &&
        dec.source_regions[speaker].assigned;

      if (!isAssigned) {
        return candidateId;
      }

      idx += step;
    }

    return null; // no suitable concept found
  }

  /**
   * Resolve the source WAV and lexiconStartSec for a given speaker/concept.
   * Falls back to the primary source WAV from sourceIndex if no specific
   * assignment exists for this concept.
   */
  function _resolveSourceWav(speaker, conceptId) {
    const SE_data = window.PARSE;

    // Check if there's an existing decision for this concept/speaker
    const dec = SE_data && SE_data.decisions && SE_data.decisions[conceptId];
    if (
      dec &&
      dec.source_regions &&
      dec.source_regions[speaker] &&
      dec.source_regions[speaker].source_wav
    ) {
      return dec.source_regions[speaker].source_wav;
    }

    // Fall back to primary source WAV from sourceIndex
    if (SE_data && SE_data.sourceIndex && SE_data.sourceIndex.speakers) {
      const spkData = SE_data.sourceIndex.speakers[speaker];
      if (spkData && spkData.source_wavs && spkData.source_wavs.length > 0) {
        const primary =
          spkData.source_wavs.find(function (w) { return w.is_primary; }) ||
          spkData.source_wavs[0];
        return primary.filename || null;
      }
    }

    return null;
  }

  function _resolveLexiconStart(speaker, sourceWav) {
    const SE_data = window.PARSE;
    if (SE_data && SE_data.sourceIndex && SE_data.sourceIndex.speakers) {
      const spkData = SE_data.sourceIndex.speakers[speaker];
      if (spkData && spkData.source_wavs) {
        const wav = sourceWav
          ? spkData.source_wavs.find(function (w) { return w.filename === sourceWav; })
          : spkData.source_wavs.find(function (w) { return w.is_primary; });
        if (wav != null && wav.lexicon_start_sec != null) {
          return wav.lexicon_start_sec;
        }
      }
    }
    return null;
  }

  // ── Event handlers ──────────────────────────────────────────────────────────

  function _onPanelOpen(evt) {
    const detail = (evt && evt.detail) || {};

    // Singleton: if a panel is already open for a DIFFERENT context, emit the
    // documented cleanup event first and then reopen on the next frame.
    if (_isOpen) {
      const sameContext =
        _ctx.speaker    === detail.speaker &&
        _ctx.conceptId  === detail.conceptId &&
        _ctx.sourceWav  === detail.sourceWav;

      if (sameContext) {
        // Already showing this exact context — no-op
        return;
      }

      _pendingOpenDetail = {
        speaker: detail.speaker || null,
        conceptId: detail.conceptId || null,
        sourceWav: detail.sourceWav || null,
        lexiconStartSec: detail.lexiconStartSec != null ? detail.lexiconStartSec : null,
      };

      const closeSpeaker = _ctx.speaker;
      requestAnimationFrame(function () {
        if (_pendingOpenDetail && _isOpen && _ctx.speaker === closeSpeaker) {
          _dispatchClose(closeSpeaker);
        } else if (!_isOpen || _ctx.speaker !== closeSpeaker) {
          _pendingOpenDetail = null;
        }
      });
      return;
    }

    _openPanel(detail);

    // Notify annotation-panel of the new context
    const context = _ctx;
    const annotPanel = SE.modules && SE.modules.annotationPanel;
    if (annotPanel && typeof annotPanel.setContext === 'function') {
      annotPanel.setContext({
        speaker: context.speaker,
        conceptId: context.conceptId,
        sourceWav: context.sourceWav,
      });
    }
  }

  function _onPanelClose(evt) {
    // Only act if this close is for our currently-open speaker
    // (or if no speaker context is specified — close regardless)
    const detail = (evt && evt.detail) || {};
    if (detail.speaker && _ctx.speaker && detail.speaker !== _ctx.speaker) {
      return;
    }
    _closePanel();

    // Clear annotation-panel context
    const annotPanel = SE.modules && SE.modules.annotationPanel;
    if (annotPanel && typeof annotPanel.clearContext === 'function') {
      annotPanel.clearContext();
    }

    if (_pendingOpenDetail) {
      const nextDetail = _pendingOpenDetail;
      _pendingOpenDetail = null;
      requestAnimationFrame(function () {
        _dispatchOpen(nextDetail);
      });
    }
  }

  function _onFullscreenToggle(evt) {
    const detail = (evt && evt.detail) || {};
    // detail.active === true → enter fullscreen
    // detail.active === false → exit fullscreen
    // If active is undefined, toggle
    const wantFullscreen = detail.active != null ? !!detail.active : !_isFullscreen;

    if (wantFullscreen && !_isFullscreen) {
      _enterFullscreen();
    } else if (!wantFullscreen && _isFullscreen) {
      _exitFullscreen();
    }
  }

  function _onNavigateConcept(evt) {
    const detail = (evt && evt.detail) || {};
    const direction   = detail.direction   || 'next';
    const missingOnly = detail.missingOnly != null ? !!detail.missingOnly : true;

    if (!_ctx.speaker || !_ctx.conceptId) return;

    const nextConceptId = _findAdjacentConcept(_ctx.conceptId, direction, missingOnly);
    if (!nextConceptId) {
      // Nothing found — could notify UI here
      console.warn('[PARSE] No adjacent concept found in direction:', direction);
      return;
    }

    const prevSpeaker = _ctx.speaker;
    const nextSourceWav   = _resolveSourceWav(prevSpeaker, nextConceptId);
    const nextLexiconStart = _resolveLexiconStart(prevSpeaker, nextSourceWav);

    // Close current panel (fires parse:panel-close so other modules clean up)
    _dispatchClose(prevSpeaker);

    // Open the next concept in a new animation frame to allow teardown
    requestAnimationFrame(function () {
      _dispatchOpen({
        speaker:         prevSpeaker,
        conceptId:       nextConceptId,
        sourceWav:       nextSourceWav,
        lexiconStartSec: nextLexiconStart,
      });
    });
  }

  function _onRegionAssigned(evt) {
    const detail = (evt && evt.detail) || {};
    const { speaker, conceptId, startSec, endSec, sourceWav } = detail;

    if (!speaker || !conceptId) return;

    // Update the decisions store
    _applyDecision(detail);

    // Update the form row indicator in the main RT table
    _updateFormRowIndicator(speaker, conceptId);

    // If this is the currently open context, refresh the header badge
    if (_ctx.speaker === speaker && _ctx.conceptId === conceptId) {
      _populateHeader(_ctx);
    }
  }

  function _onAnnotationsChanged(evt) {
    // Update any annotation count indicator in the panel header if present
    const detail = evt && evt.detail ? evt.detail : {};
    // Best-effort: try to update a badge or header text if the element exists
    const badge = document.getElementById('parse-annotation-count');
    if (badge) badge.textContent = detail.totalAnnotations || '';
  }

  // ── Decisions store helper ──────────────────────────────────────────────────

  /**
   * Write a region assignment into SE.decisions and persist to localStorage.
   */
  function _applyDecision(assignDetail) {
    const SE_data = window.PARSE;
    if (!SE_data) return;

    const { speaker, conceptId, startSec, endSec, sourceWav } = assignDetail;

    if (!SE_data.decisions) {
      SE_data.decisions = {};
    }
    if (!SE_data.decisions[conceptId]) {
      SE_data.decisions[conceptId] = { source_regions: {} };
    }
    if (!SE_data.decisions[conceptId].source_regions) {
      SE_data.decisions[conceptId].source_regions = {};
    }

    const region = {
      source_wav:   sourceWav   || null,
      start_sec:    startSec    != null ? startSec : null,
      end_sec:      endSec      != null ? endSec   : null,
      assigned:     true,
      replaces_segment: true,
    };

    // Carry over optional AI suggestion metadata
    if (assignDetail.aiSuggestionUsed      != null) region.ai_suggestion_used       = assignDetail.aiSuggestionUsed;
    if (assignDetail.aiSuggestionConfidence != null) region.ai_suggestion_confidence = assignDetail.aiSuggestionConfidence;
    if (assignDetail.aiSuggestionScore      != null) region.ai_suggestion_score      = assignDetail.aiSuggestionScore;

    SE_data.decisions[conceptId].source_regions[speaker] = region;

    // Persist full decisions to localStorage
    try {
      localStorage.setItem('se-decisions', JSON.stringify(SE_data.decisions));
    } catch (_) {
      // Quota exceeded or unavailable — silently ignore
    }
  }

  // ── Form row indicator ──────────────────────────────────────────────────────

  /**
   * Find the form row for concept × speaker in the main RT table and
   * insert (or update) a "✓ re-assigned" badge next to the 🔍 button.
   *
   * The existing RT marks rows with data attributes:
   *   data-concept-id="1"  and  data-speaker="Fail02"
   * (or similar — we search by both attributes).
   *
   * Falls back gracefully if the row isn't found.
   */
  function _updateFormRowIndicator(speaker, conceptId) {
    // Try to find the cell via data attributes (most reliable)
    const rows = document.querySelectorAll(
      '[data-concept-id="' + conceptId + '"][data-speaker="' + speaker + '"],' +
      '[data-conceptid="' + conceptId + '"][data-speaker="' + speaker + '"]'
    );

    rows.forEach(function (rowEl) {
      _insertOrUpdateBadge(rowEl, speaker, conceptId);
    });

    // Also search by the 🔍 button's data attributes (some layouts use button-level attrs)
    const btns = document.querySelectorAll(
      'button[data-concept-id="' + conceptId + '"][data-speaker="' + speaker + '"],' +
      'button[data-conceptid="' + conceptId + '"][data-speaker="' + speaker + '"]'
    );

    btns.forEach(function (btn) {
      const container = btn.closest('td') || btn.closest('li') || btn.parentNode;
      if (container) {
        _insertOrUpdateBadge(container, speaker, conceptId);
      }
    });
  }

  function _insertOrUpdateBadge(containerEl, speaker, conceptId) {
    const BADGE_CLASS = 'se-assigned-badge';
    const BADGE_ATTR  = 'data-se-assigned';

    let badge = containerEl.querySelector('.' + BADGE_CLASS);
    if (!badge) {
      badge = document.createElement('span');
      badge.className = BADGE_CLASS;
      badge.setAttribute(BADGE_ATTR, speaker + '|' + conceptId);
      badge.setAttribute('title', 'Source region assigned from PARSE');
      containerEl.appendChild(badge);
    }
    badge.textContent = '✓ re-assigned';
    badge.style.cssText =
      'display:inline-block;' +
      'margin-left:4px;' +
      'padding:1px 5px;' +
      'background:#2ecc71;' +
      'color:#fff;' +
      'border-radius:3px;' +
      'font-size:0.75em;' +
      'font-weight:bold;' +
      'vertical-align:middle;';
  }

  // ── Utility ─────────────────────────────────────────────────────────────────

  function _escHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _formatTimeSec(sec) {
    if (sec == null || isNaN(sec)) return '—';
    const s = Math.floor(sec);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (h > 0) {
      return h + ':' + _pad2(m) + ':' + _pad2(ss);
    }
    return m + ':' + _pad2(ss) + ' (' + s + 's)';
  }

  function _pad2(n) {
    return n < 10 ? '0' + n : String(n);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * init — called by the HTML shell after DOM ready.
   * @param {HTMLElement} containerEl  — the element to use as panel scope anchor
   */
  function init(containerEl) {
    _containerEl = containerEl || document.body;

    // Resolve DOM elements
    _panelEl   = _getPanelEl();
    _headerEl  = _getHeaderEl();
    _overlayEl = _getOverlayEl();

    if (!_panelEl) {
      console.warn('[PARSE] #' + PANEL_ID + ' not found in DOM. init() aborted.');
      return;
    }

    // Ensure panel starts hidden
    _panelEl.classList.add(CLS_HIDDEN);
    _panelEl.setAttribute('aria-hidden', 'true');

    // Restore persisted UI state (informational only — don't auto-reopen)
    const saved = _loadState();
    if (saved.lastSpeaker) {
      _panelEl.dataset.lastSpeaker   = saved.lastSpeaker;
      _panelEl.dataset.lastConceptId = saved.lastConceptId || '';
    }

    // Merge persisted decisions from localStorage into any shell-preloaded
    // decisions state so source-region assignments survive reloads regardless
    // of initialization order.
    _mergePersistedDecisions();

    // Register event listeners
    _boundOnPanelOpen         = _onPanelOpen;
    _boundOnPanelClose        = _onPanelClose;
    _boundOnFullscreenToggle  = _onFullscreenToggle;
    _boundOnNavigateConcept   = _onNavigateConcept;
    _boundOnRegionAssigned    = _onRegionAssigned;
    _boundOnAnnotationsChanged = _onAnnotationsChanged;

    document.addEventListener('parse:panel-open',          _boundOnPanelOpen);
    document.addEventListener('parse:panel-close',         _boundOnPanelClose);
    document.addEventListener('parse:fullscreen-toggle',   _boundOnFullscreenToggle);
    document.addEventListener('parse:navigate-concept',    _boundOnNavigateConcept);
    document.addEventListener('parse:region-assigned',     _boundOnRegionAssigned);
    document.addEventListener('parse:annotations-changed', _boundOnAnnotationsChanged);

    // Keyboard shortcut: Escape closes the panel
    document.addEventListener('keydown', _onKeyDown);
  }

  /**
   * Keyboard shortcuts handler
   */
  function _onKeyDown(evt) {
    if (!_isOpen) return;

    switch (evt.key) {
      case 'Escape':
        if (_isFullscreen) {
          // First Escape exits fullscreen; second closes panel
          document.dispatchEvent(
            new CustomEvent('parse:fullscreen-toggle', { detail: { active: false } })
          );
        } else {
          _dispatchClose(_ctx.speaker);
        }
        evt.preventDefault();
        break;
    }
  }

  /**
   * destroy — clean up all listeners and internal state.
   * Called if the host page tears down PARSE.
   */
  function destroy() {
    if (_boundOnPanelOpen)         document.removeEventListener('parse:panel-open',          _boundOnPanelOpen);
    if (_boundOnPanelClose)        document.removeEventListener('parse:panel-close',         _boundOnPanelClose);
    if (_boundOnFullscreenToggle)  document.removeEventListener('parse:fullscreen-toggle',   _boundOnFullscreenToggle);
    if (_boundOnNavigateConcept)   document.removeEventListener('parse:navigate-concept',    _boundOnNavigateConcept);
    if (_boundOnRegionAssigned)    document.removeEventListener('parse:region-assigned',     _boundOnRegionAssigned);
    if (_boundOnAnnotationsChanged) document.removeEventListener('parse:annotations-changed', _boundOnAnnotationsChanged);
    document.removeEventListener('keydown', _onKeyDown);

    // If in fullscreen, restore DOM structure
    if (_isFullscreen) {
      _exitFullscreen();
    }

    _closePanel();
    _pendingOpenDetail = null;

    _containerEl = null;
    _panelEl     = null;
    _headerEl    = null;
    _overlayEl   = null;

    _boundOnPanelOpen         = null;
    _boundOnPanelClose        = null;
    _boundOnFullscreenToggle  = null;
    _boundOnNavigateConcept   = null;
    _boundOnRegionAssigned    = null;
    _boundOnAnnotationsChanged = null;
  }

  /**
   * Programmatically open a panel for a given context.
   * Other modules can call this directly instead of dispatching events.
   *
   * @param {object} opts
   * @param {string} opts.speaker
   * @param {string} opts.conceptId
   * @param {string} [opts.sourceWav]
   * @param {number} [opts.lexiconStartSec]
   */
  function open(opts) {
    // Resolve sourceWav and lexiconStartSec from sourceIndex if not supplied
    const sourceWav = opts.sourceWav || _resolveSourceWav(opts.speaker, opts.conceptId);
    const lexiconStartSec =
      opts.lexiconStartSec != null
        ? opts.lexiconStartSec
        : _resolveLexiconStart(opts.speaker, sourceWav);

    const nextDetail = {
      speaker:         opts.speaker,
      conceptId:       opts.conceptId,
      sourceWav:       sourceWav,
      lexiconStartSec: lexiconStartSec,
    };

    if (_isOpen) {
      const sameContext =
        _ctx.speaker   === nextDetail.speaker &&
        _ctx.conceptId === nextDetail.conceptId &&
        _ctx.sourceWav === nextDetail.sourceWav;

      if (sameContext) {
        return;
      }

      _pendingOpenDetail = nextDetail;
      _dispatchClose(_ctx.speaker);
      return;
    }

    _dispatchOpen(nextDetail);
  }

  /**
   * Programmatically close the panel.
   */
  function close() {
    if (_isOpen) {
      _dispatchClose(_ctx.speaker);
    }
  }

  /**
   * Returns a snapshot of the current open context (or null if closed).
   */
  function getContext() {
    if (!_isOpen) return null;
    return Object.assign({}, _ctx);
  }

  /**
   * Returns true if the panel is currently open.
   */
  function isOpen() {
    return _isOpen;
  }

  // ── Register module ─────────────────────────────────────────────────────────
  SE.modules.panel = {
    init:       init,
    destroy:    destroy,
    open:       open,
    close:      close,
    getContext: getContext,
    isOpen:     isOpen,
  };

})();
