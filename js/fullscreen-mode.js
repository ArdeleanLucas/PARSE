/**
 * fullscreen-mode.js — fullscreen controls + concept navigation UI
 *
 * Attaches to window.SourceExplorer.modules.fullscreen.
 * Manages UI/state for:
 *  - fullscreen toggle button
 *  - Escape-to-exit while fullscreen is active
 *  - prev/next concept navigation
 *  - missing-only navigation toggle
 *
 * This module does NOT reparent/open panels itself.
 * It only emits:
 *  - se:fullscreen-toggle { active: boolean }
 *  - se:navigate-concept { direction: 'prev'|'next', missingOnly: boolean }
 */
(function () {
  'use strict';

  if (!window.SourceExplorer) {
    window.SourceExplorer = {};
  }
  if (!window.SourceExplorer.modules) {
    window.SourceExplorer.modules = {};
  }

  const SE = window.SourceExplorer;

  const STORAGE_KEY = 'se-fullscreen-mode-state';
  const STYLE_ID = 'se-fullscreen-mode-style';
  const PANEL_ID = 'se-panel';
  const OVERLAY_ID = 'se-fullscreen-overlay';
  const DEFAULT_CONTAINER_ID = 'se-controls';
  const ROOT_CLASS = 'se-fullscreen-controls';
  const ROOT_ATTR = 'data-se-fullscreen-controls';
  const HIDDEN_CLASS = 'se-fullscreen-controls--hidden';

  let containerEl = null;
  let rootEl = null;
  let initialized = false;

  let isPanelOpen = false;
  let isFullscreen = false;
  let missingOnly = true;
  let currentContext = null;

  let onPanelOpenBound = null;
  let onPanelCloseBound = null;
  let onFullscreenToggleBound = null;
  let onKeyDownBound = null;
  let onRootClickBound = null;
  let onRootChangeBound = null;
  let keydownAttached = false;

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { missingOnly: true };
      }

      const parsed = JSON.parse(raw);
      return {
        missingOnly: parsed && typeof parsed.missingOnly === 'boolean' ? parsed.missingOnly : true,
      };
    } catch (_) {
      return { missingOnly: true };
    }
  }

  function saveState() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          missingOnly: !!missingOnly,
        })
      );
    } catch (_) {
      // localStorage unavailable/quota exceeded; ignore
    }
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const styleEl = document.createElement('style');
    styleEl.id = STYLE_ID;
    styleEl.textContent = [
      '.' + ROOT_CLASS + ' {',
      '  display: flex;',
      '  flex-wrap: wrap;',
      '  align-items: center;',
      '  justify-content: space-between;',
      '  gap: 12px;',
      '  margin-top: 12px;',
      '  padding: 10px 12px;',
      '  border: 1px solid rgba(0, 0, 0, 0.12);',
      '  border-radius: 10px;',
      '  background: rgba(255, 255, 255, 0.92);',
      '}',
      '.' + ROOT_CLASS + '--hidden {',
      '  display: none !important;',
      '}',
      '.' + ROOT_CLASS + '__group {',
      '  display: flex;',
      '  flex-wrap: wrap;',
      '  align-items: center;',
      '  gap: 8px;',
      '}',
      '.' + ROOT_CLASS + '__button {',
      '  appearance: none;',
      '  border: 1px solid rgba(0, 0, 0, 0.18);',
      '  border-radius: 8px;',
      '  background: #fff;',
      '  color: inherit;',
      '  cursor: pointer;',
      '  font: inherit;',
      '  line-height: 1.2;',
      '  padding: 8px 12px;',
      '}',
      '.' + ROOT_CLASS + '__button:hover:not(:disabled) {',
      '  background: rgba(0, 0, 0, 0.04);',
      '}',
      '.' + ROOT_CLASS + '__button:disabled {',
      '  cursor: not-allowed;',
      '  opacity: 0.55;',
      '}',
      '.' + ROOT_CLASS + '__button--primary {',
      '  font-weight: 600;',
      '}',
      '.' + ROOT_CLASS + '__button--active {',
      '  border-color: #2c7be5;',
      '  box-shadow: inset 0 0 0 1px rgba(44, 123, 229, 0.25);',
      '  background: rgba(44, 123, 229, 0.08);',
      '}',
      '.' + ROOT_CLASS + '__toggle {',
      '  display: inline-flex;',
      '  align-items: center;',
      '  gap: 6px;',
      '  font-size: 0.92rem;',
      '  user-select: none;',
      '}',
      '.' + ROOT_CLASS + '__toggle input {',
      '  margin: 0;',
      '}',
      '.' + ROOT_CLASS + '__meta {',
      '  display: flex;',
      '  flex-wrap: wrap;',
      '  align-items: center;',
      '  gap: 8px 12px;',
      '  font-size: 0.86rem;',
      '  color: rgba(0, 0, 0, 0.72);',
      '}',
      '.' + ROOT_CLASS + '__context {',
      '  font-weight: 600;',
      '  color: rgba(0, 0, 0, 0.82);',
      '}',
      '.' + ROOT_CLASS + '__hint {',
      '  white-space: nowrap;',
      '}',
      '@media (max-width: 720px) {',
      '  .' + ROOT_CLASS + ' {',
      '    align-items: flex-start;',
      '    flex-direction: column;',
      '  }',
      '  .' + ROOT_CLASS + '__meta {',
      '    white-space: normal;',
      '  }',
      '  .' + ROOT_CLASS + '__hint {',
      '    white-space: normal;',
      '  }',
      '}',
    ].join('\n');

    document.head.appendChild(styleEl);
  }

  function resolveContainer(preferredContainer) {
    if (preferredContainer && preferredContainer.nodeType === 1) {
      return preferredContainer;
    }

    return document.getElementById(DEFAULT_CONTAINER_ID) || document.getElementById(PANEL_ID) || document.body;
  }

  function ensureRoot() {
    if (rootEl && rootEl.isConnected) {
      return rootEl;
    }

    rootEl = document.createElement('div');
    rootEl.className = ROOT_CLASS + ' ' + HIDDEN_CLASS;
    rootEl.setAttribute(ROOT_ATTR, 'true');
    rootEl.setAttribute('aria-label', 'Fullscreen and concept navigation controls');

    rootEl.innerHTML = [
      '<div class="' + ROOT_CLASS + '__group">',
      '  <button type="button" class="' + ROOT_CLASS + '__button ' + ROOT_CLASS + '__button--primary" data-action="toggle-fullscreen" aria-pressed="false">⛶ Fullscreen</button>',
      '  <label class="' + ROOT_CLASS + '__toggle" title="When enabled, prev/next skips concepts that already have an assigned source region.">',
      '    <input type="checkbox" data-action="missing-only" checked />',
      '    <span>Missing only</span>',
      '  </label>',
      '</div>',
      '<div class="' + ROOT_CLASS + '__group">',
      '  <button type="button" class="' + ROOT_CLASS + '__button" data-action="prev-concept">← Prev</button>',
      '  <button type="button" class="' + ROOT_CLASS + '__button" data-action="next-concept">Next →</button>',
      '</div>',
      '<div class="' + ROOT_CLASS + '__meta" aria-live="polite">',
      '  <span class="' + ROOT_CLASS + '__context" data-role="context"></span>',
      '  <span class="' + ROOT_CLASS + '__hint" data-role="hint"></span>',
      '</div>',
    ].join('');

    containerEl.appendChild(rootEl);
    return rootEl;
  }

  function isTextEditingElement(el) {
    if (!el || el === document.body || el === document.documentElement) {
      return false;
    }

    if (el.isContentEditable) {
      return true;
    }

    const tagName = (el.tagName || '').toLowerCase();
    if (!tagName) {
      return false;
    }

    if (tagName === 'textarea' || tagName === 'select') {
      return true;
    }

    if (tagName !== 'input') {
      return false;
    }

    const type = String(el.getAttribute('type') || 'text').toLowerCase();
    return [
      'text',
      'search',
      'email',
      'password',
      'url',
      'tel',
      'number',
      'date',
      'datetime-local',
      'month',
      'time',
      'week',
    ].indexOf(type) !== -1;
  }

  function isWithinPanelScope(target) {
    const panelEl = document.getElementById(PANEL_ID);
    const overlayEl = document.getElementById(OVERLAY_ID);
    const activeEl = document.activeElement;

    if (target === document.body || target === document.documentElement) {
      return true;
    }

    return !!(
      (panelEl && target && panelEl.contains(target)) ||
      (overlayEl && target && overlayEl.contains(target)) ||
      (rootEl && target && rootEl.contains(target)) ||
      activeEl === document.body
    );
  }

  function escapeHtml(value) {
    if (value == null) {
      return '';
    }

    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getConceptLabel(conceptId) {
    if (conceptId == null) {
      return 'No concept selected';
    }

    const suggestions = SE && SE.suggestions && SE.suggestions.suggestions;
    const concept = suggestions && suggestions[String(conceptId)];
    if (concept && concept.concept_en) {
      return '#' + conceptId + ' — ' + concept.concept_en;
    }

    return 'Concept #' + conceptId;
  }

  function render() {
    if (!rootEl) {
      return;
    }

    const toggleBtn = rootEl.querySelector('[data-action="toggle-fullscreen"]');
    const prevBtn = rootEl.querySelector('[data-action="prev-concept"]');
    const nextBtn = rootEl.querySelector('[data-action="next-concept"]');
    const missingOnlyInput = rootEl.querySelector('[data-action="missing-only"]');
    const contextEl = rootEl.querySelector('[data-role="context"]');
    const hintEl = rootEl.querySelector('[data-role="hint"]');

    rootEl.classList.toggle(HIDDEN_CLASS, !isPanelOpen);

    if (missingOnlyInput) {
      missingOnlyInput.checked = !!missingOnly;
      missingOnlyInput.disabled = !isPanelOpen;
    }

    if (toggleBtn) {
      toggleBtn.disabled = !isPanelOpen;
      toggleBtn.setAttribute('aria-pressed', isFullscreen ? 'true' : 'false');
      toggleBtn.classList.toggle(ROOT_CLASS + '__button--active', isFullscreen);
      toggleBtn.textContent = isFullscreen ? '🡼 Exit fullscreen' : '⛶ Fullscreen';
      toggleBtn.setAttribute('title', isFullscreen ? 'Exit fullscreen mode' : 'Enter fullscreen mode');
    }

    if (prevBtn) {
      prevBtn.disabled = !isPanelOpen;
    }

    if (nextBtn) {
      nextBtn.disabled = !isPanelOpen;
    }

    if (contextEl) {
      if (isPanelOpen && currentContext) {
        const speaker = currentContext.speaker ? escapeHtml(currentContext.speaker) : 'Unknown speaker';
        const concept = escapeHtml(getConceptLabel(currentContext.conceptId));
        contextEl.innerHTML = speaker + ' · ' + concept;
      } else {
        contextEl.textContent = '';
      }
    }

    if (hintEl) {
      if (!isPanelOpen) {
        hintEl.textContent = '';
      } else if (isFullscreen) {
        hintEl.textContent = 'Esc exits fullscreen.';
      } else {
        hintEl.textContent = missingOnly ? 'Prev/next will skip already assigned concepts.' : 'Prev/next will visit every concept.';
      }
    }
  }

  function emitFullscreenToggle(active) {
    if (!isPanelOpen) {
      return;
    }

    document.dispatchEvent(
      new CustomEvent('se:fullscreen-toggle', {
        detail: { active: !!active },
      })
    );
  }

  function emitNavigate(direction) {
    if (!isPanelOpen) {
      return;
    }

    document.dispatchEvent(
      new CustomEvent('se:navigate-concept', {
        detail: {
          direction: direction === 'prev' ? 'prev' : 'next',
          missingOnly: !!missingOnly,
        },
      })
    );
  }

  function handleRootClick(event) {
    const actionEl = event.target && event.target.closest('[data-action]');
    if (!actionEl || !rootEl || !rootEl.contains(actionEl)) {
      return;
    }

    const action = actionEl.getAttribute('data-action');
    if (!action) {
      return;
    }

    if (action === 'toggle-fullscreen') {
      emitFullscreenToggle(!isFullscreen);
      return;
    }

    if (action === 'prev-concept') {
      emitNavigate('prev');
      return;
    }

    if (action === 'next-concept') {
      emitNavigate('next');
    }
  }

  function handleRootChange(event) {
    const target = event.target;
    if (!target || !rootEl || !rootEl.contains(target)) {
      return;
    }

    const action = target.getAttribute('data-action');
    if (action !== 'missing-only') {
      return;
    }

    missingOnly = !!target.checked;
    saveState();
    render();
  }

  function handlePanelOpen(event) {
    const detail = (event && event.detail) || {};

    isPanelOpen = true;
    currentContext = {
      speaker: detail.speaker || null,
      conceptId: detail.conceptId || null,
      sourceWav: detail.sourceWav || null,
      lexiconStartSec: detail.lexiconStartSec != null ? detail.lexiconStartSec : null,
    };

    setKeydownListener(true);
    render();
  }

  function handlePanelClose(event) {
    const detail = (event && event.detail) || {};

    if (currentContext && detail.speaker && currentContext.speaker && detail.speaker !== currentContext.speaker) {
      return;
    }

    isPanelOpen = false;
    isFullscreen = false;
    currentContext = null;

    setKeydownListener(false);
    render();
  }

  function handleFullscreenToggle(event) {
    if (!isPanelOpen) {
      return;
    }

    const detail = (event && event.detail) || {};
    isFullscreen = detail.active != null ? !!detail.active : !isFullscreen;
    render();
  }

  function handleKeyDown(event) {
    if (!isPanelOpen || !isFullscreen) {
      return;
    }

    if (event.key !== 'Escape') {
      return;
    }

    const target = event.target || document.activeElement;
    if (isTextEditingElement(target)) {
      return;
    }

    if (!isWithinPanelScope(target)) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    emitFullscreenToggle(false);
  }

  function syncInitialState() {
    const saved = loadState();
    missingOnly = saved.missingOnly;

    const panelModule = SE && SE.modules && SE.modules.panel;
    if (panelModule && typeof panelModule.isOpen === 'function' && panelModule.isOpen()) {
      isPanelOpen = true;
      currentContext = typeof panelModule.getContext === 'function' ? panelModule.getContext() : null;
    }

    const panelEl = document.getElementById(PANEL_ID);
    if (panelEl && panelEl.classList.contains('se-panel--fullscreen')) {
      isFullscreen = true;
    }
  }

  function setKeydownListener(active) {
    if (!onKeyDownBound) {
      return;
    }

    if (active && !keydownAttached) {
      document.addEventListener('keydown', onKeyDownBound, true);
      keydownAttached = true;
      return;
    }

    if (!active && keydownAttached) {
      document.removeEventListener('keydown', onKeyDownBound, true);
      keydownAttached = false;
    }
  }

  function init(preferredContainer) {
    if (initialized) {
      return SE.modules.fullscreen;
    }

    containerEl = resolveContainer(preferredContainer);
    ensureStyles();
    ensureRoot();
    syncInitialState();

    onPanelOpenBound = handlePanelOpen;
    onPanelCloseBound = handlePanelClose;
    onFullscreenToggleBound = handleFullscreenToggle;
    onKeyDownBound = handleKeyDown;
    onRootClickBound = handleRootClick;
    onRootChangeBound = handleRootChange;

    document.addEventListener('se:panel-open', onPanelOpenBound);
    document.addEventListener('se:panel-close', onPanelCloseBound);
    document.addEventListener('se:fullscreen-toggle', onFullscreenToggleBound);

    rootEl.addEventListener('click', onRootClickBound);
    rootEl.addEventListener('change', onRootChangeBound);

    initialized = true;
    setKeydownListener(isPanelOpen);
    render();

    return SE.modules.fullscreen;
  }

  function destroy() {
    if (onPanelOpenBound) {
      document.removeEventListener('se:panel-open', onPanelOpenBound);
    }
    if (onPanelCloseBound) {
      document.removeEventListener('se:panel-close', onPanelCloseBound);
    }
    if (onFullscreenToggleBound) {
      document.removeEventListener('se:fullscreen-toggle', onFullscreenToggleBound);
    }
    setKeydownListener(false);

    if (rootEl && onRootClickBound) {
      rootEl.removeEventListener('click', onRootClickBound);
    }
    if (rootEl && onRootChangeBound) {
      rootEl.removeEventListener('change', onRootChangeBound);
    }

    if (rootEl && rootEl.parentNode) {
      rootEl.parentNode.removeChild(rootEl);
    }

    containerEl = null;
    rootEl = null;
    initialized = false;
    isPanelOpen = false;
    isFullscreen = false;
    currentContext = null;

    onPanelOpenBound = null;
    onPanelCloseBound = null;
    onFullscreenToggleBound = null;
    onKeyDownBound = null;
    onRootClickBound = null;
    onRootChangeBound = null;
    keydownAttached = false;
  }

  function getState() {
    return {
      open: isPanelOpen,
      fullscreen: isFullscreen,
      missingOnly: missingOnly,
      context: currentContext ? Object.assign({}, currentContext) : null,
    };
  }

  function setMissingOnly(value) {
    missingOnly = !!value;
    saveState();
    render();
  }

  function toggleFullscreen() {
    emitFullscreenToggle(!isFullscreen);
  }

  SE.modules.fullscreen = {
    init: init,
    destroy: destroy,
    getState: getState,
    setMissingOnly: setMissingOnly,
    toggleFullscreen: toggleFullscreen,
  };
})();
