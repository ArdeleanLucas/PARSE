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
  const TAG_STYLE_ID = 'se-tag-sidebar-style';
  const TAG_FILTER_BAR_ID = 'se-tag-filter-bar';
  const TAG_DROPDOWN_ID = 'se-tag-dropdown';

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

  // Tags sidebar integration state
  let _tagsModule = null;
  let _tagFilterState = {
    tagId: null,
    showUntagged: false,
  };
  let _tagFilterSignature = null;
  let _tagSidebarRefreshQueued = false;
  let _tagSidebarObserver = null;
  let _activeTagDropdownContext = null;
  let _searchInputEl = null;
  let _boundOnSearchInput = null;

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
  let _boundOnTagFilterChanged = null;
  let _boundOnTagsUpdated = null;
  let _boundOnItemsTagged = null;
  let _boundOnTagCreated = null;
  let _boundOnTagDeleted = null;
  let _boundOnDocumentPointerDown = null;
  let _boundOnDocumentKeyDown = null;

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

  // ── Tag sidebar helpers ─────────────────────────────────────────────────────

  function _normalizeConceptId(value) {
    if (value == null) return null;

    let text = String(value).trim();
    if (!text) return null;

    if (text.charAt(0) === '#') {
      text = text.slice(1).trim();
    }

    const colonIdx = text.indexOf(':');
    if (colonIdx !== -1) {
      text = text.slice(0, colonIdx).trim();
    }

    return text || null;
  }

  function _conceptArg(conceptId) {
    const normalized = _normalizeConceptId(conceptId);
    if (!normalized) return null;
    const num = Number(normalized);
    return Number.isFinite(num) ? num : normalized;
  }

  function _extractConceptIdFromLabelText(labelText) {
    const text = String(labelText || '').trim();
    if (!text) return null;

    const prefixedMatch = text.match(/^#?\s*(\d+)\s*[:\-\.]/);
    if (prefixedMatch && prefixedMatch[1]) {
      return _normalizeConceptId(prefixedMatch[1]);
    }

    const plainNumMatch = text.match(/^#?\s*(\d+)\b/);
    if (plainNumMatch && plainNumMatch[1]) {
      return _normalizeConceptId(plainNumMatch[1]);
    }

    return null;
  }

  function _conceptIdFromItem(itemEl) {
    if (!itemEl) return null;

    if (itemEl.dataset && itemEl.dataset.seConceptId) {
      return _normalizeConceptId(itemEl.dataset.seConceptId);
    }

    let conceptId =
      _normalizeConceptId(itemEl.getAttribute('data-concept-id')) ||
      _normalizeConceptId(itemEl.getAttribute('data-conceptid'));

    if (!conceptId) {
      const labelEl = itemEl.querySelector('.ci-label');
      conceptId = _extractConceptIdFromLabelText(labelEl ? labelEl.textContent : itemEl.textContent);
    }

    if (!conceptId && itemEl.dataset && itemEl.dataset.idx != null) {
      const idx = Number(itemEl.dataset.idx);
      if (Number.isFinite(idx)) {
        conceptId = String(idx + 1);
      }
    }

    if (conceptId && itemEl.dataset) {
      itemEl.dataset.seConceptId = conceptId;
    }

    return conceptId;
  }

  function _normalizeTagFilter(filter) {
    const next = {
      tagId: null,
      showUntagged: false,
    };

    if (!filter || typeof filter !== 'object') {
      return next;
    }

    const tagId = filter.tagId != null ? String(filter.tagId).trim() : '';
    next.tagId = tagId || null;
    next.showUntagged = !!filter.showUntagged;
    return next;
  }

  function _tagFilterSignatureOf(filter) {
    const f = _normalizeTagFilter(filter);
    return (f.tagId || '') + '|' + (f.showUntagged ? '1' : '0');
  }

  function _dispatchTagFilterChanged(source) {
    document.dispatchEvent(
      new CustomEvent('parse:tag-filter-changed', {
        detail: {
          tagId: _tagFilterState.tagId,
          showUntagged: !!_tagFilterState.showUntagged,
          source: source || 'annotate-sidebar',
        },
      })
    );
  }

  function _getTagsModule() {
    if (_tagsModule) return _tagsModule;
    if (SE.modules && SE.modules.tags) {
      _tagsModule = SE.modules.tags;
    }
    return _tagsModule;
  }

  function _safeGetTags() {
    const tagsModule = _getTagsModule();
    if (!tagsModule || typeof tagsModule.getTags !== 'function') {
      return [];
    }

    try {
      const tags = tagsModule.getTags();
      if (!Array.isArray(tags)) return [];
      return tags
        .map(function (tag) {
          if (!tag || typeof tag !== 'object') return null;
          const id = String(tag.id || tag.tagId || '').trim();
          if (!id) return null;
          return {
            id: id,
            name: String(tag.name || id).trim() || id,
            color: String(tag.color || '#64748b').trim() || '#64748b',
          };
        })
        .filter(Boolean);
    } catch (error) {
      console.warn('[PARSE] Failed to read tags:', error);
      return [];
    }
  }

  function _safeGetTagsForConcept(conceptId) {
    const tagsModule = _getTagsModule();
    if (!tagsModule || typeof tagsModule.getTagsForConcept !== 'function') {
      return [];
    }

    const conceptArg = _conceptArg(conceptId);
    if (conceptArg == null) return [];

    try {
      const tags = tagsModule.getTagsForConcept(conceptArg);
      if (!Array.isArray(tags)) return [];
      return tags
        .map(function (tag) {
          if (!tag || typeof tag !== 'object') return null;
          const id = String(tag.id || tag.tagId || '').trim();
          if (!id) return null;
          return {
            id: id,
            name: String(tag.name || id).trim() || id,
            color: String(tag.color || '#64748b').trim() || '#64748b',
          };
        })
        .filter(Boolean);
    } catch (error) {
      console.warn('[PARSE] Failed to read concept tags:', error);
      return [];
    }
  }

  function _conceptMatchesTagFilter(conceptId) {
    const normalizedId = _normalizeConceptId(conceptId);
    if (!normalizedId) return true;

    const tags = _safeGetTagsForConcept(normalizedId);
    const hasTags = tags.length > 0;
    const hasSelectedTag = _tagFilterState.tagId
      ? tags.some(function (tag) { return tag.id === _tagFilterState.tagId; })
      : false;

    if (!_tagFilterState.tagId && !_tagFilterState.showUntagged) {
      return true;
    }

    if (!_tagFilterState.tagId && _tagFilterState.showUntagged) {
      return !hasTags;
    }

    if (_tagFilterState.tagId && !_tagFilterState.showUntagged) {
      return hasSelectedTag;
    }

    return hasSelectedTag || !hasTags;
  }

  function _conceptItemEls() {
    const container = document.getElementById('concept-items');
    if (!container) return [];
    return Array.from(container.querySelectorAll('.concept-item'));
  }

  function _searchQuery() {
    const input = document.getElementById('search-input');
    if (!input) return '';
    return String(input.value || '').trim().toLowerCase();
  }

  function _itemMatchesSearch(itemEl, query) {
    if (!query) return true;
    const labelEl = itemEl ? itemEl.querySelector('.ci-label') : null;
    const text = String(labelEl ? labelEl.textContent : (itemEl ? itemEl.textContent : '')).toLowerCase();
    return text.indexOf(query) !== -1;
  }

  function _applyTagFilterToConceptList() {
    const items = _conceptItemEls();
    if (!items.length) return;

    const query = _searchQuery();

    items.forEach(function (itemEl) {
      const conceptId = _conceptIdFromItem(itemEl);
      const matchesTag = conceptId ? _conceptMatchesTagFilter(conceptId) : true;
      const matchesSearch = _itemMatchesSearch(itemEl, query);
      itemEl.style.display = matchesTag && matchesSearch ? '' : 'none';
    });
  }

  function _onSearchInput() {
    requestAnimationFrame(_applyTagFilterToConceptList);
  }

  function _wireSearchInput() {
    const input = document.getElementById('search-input');
    if (!input) return;

    if (_searchInputEl === input) {
      return;
    }

    if (_searchInputEl && _boundOnSearchInput) {
      _searchInputEl.removeEventListener('input', _boundOnSearchInput);
    }

    _searchInputEl = input;
    _boundOnSearchInput = _onSearchInput;
    _searchInputEl.addEventListener('input', _boundOnSearchInput);
  }

  function _createTagDot(color, title) {
    const dot = document.createElement('span');
    dot.className = 'se-tag-dot';
    dot.style.background = color || '#64748b';
    if (title) {
      dot.title = title;
      dot.setAttribute('aria-label', title);
    }
    return dot;
  }

  function _ensureTagStyles() {
    if (document.getElementById(TAG_STYLE_ID)) return;

    const styleEl = document.createElement('style');
    styleEl.id = TAG_STYLE_ID;
    styleEl.textContent = '' +
      '#' + TAG_FILTER_BAR_ID + '{' +
        'display:flex;flex-wrap:wrap;gap:6px;padding:6px 8px;border-bottom:1px solid var(--border,#334155);' +
        'background:linear-gradient(180deg, rgba(148,163,184,0.08), rgba(148,163,184,0.02));' +
      '}' +
      '.se-tag-filter-pill{' +
        'display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:999px;' +
        'border:1px solid var(--border,#334155);background:rgba(15,23,42,0.55);color:var(--muted,#94a3b8);' +
        'font-size:11px;line-height:1.6;cursor:pointer;' +
      '}' +
      '.se-tag-filter-pill:hover{border-color:var(--accent,#38bdf8);color:var(--text,#f1f5f9);}' +
      '.se-tag-filter-pill.is-active{' +
        'background:rgba(56,189,248,0.18);border-color:var(--accent,#38bdf8);color:var(--text,#f1f5f9);' +
      '}' +
      '.se-filter-empty{font-size:11px;color:var(--muted,#94a3b8);padding:2px 0;}' +
      '.concept-item .ci-label{min-width:0;}' +
      '.se-concept-tags-inline{display:inline-flex;align-items:center;gap:4px;flex-shrink:0;}' +
      '.se-tag-dots{display:inline-flex;align-items:center;gap:3px;max-width:56px;overflow:hidden;}' +
      '.se-tag-dot{width:7px;height:7px;border-radius:50%;display:inline-block;border:1px solid rgba(15,23,42,0.35);}' +
      '.se-tag-more{font-size:10px;color:var(--muted,#94a3b8);margin-left:1px;}' +
      '.se-tag-toggle-btn{' +
        'height:18px;min-width:18px;padding:0 4px;border-radius:5px;border:1px solid transparent;' +
        'background:transparent;color:var(--muted,#94a3b8);font-size:11px;line-height:1;cursor:pointer;' +
      '}' +
      '.se-tag-toggle-btn:hover,.se-tag-toggle-btn.is-open{' +
        'border-color:var(--border,#334155);background:rgba(56,189,248,0.14);color:var(--text,#f1f5f9);' +
      '}' +
      '#'+ TAG_DROPDOWN_ID + '{' +
        'position:fixed;z-index:12000;min-width:200px;max-width:280px;padding:6px;' +
        'border-radius:10px;border:1px solid var(--border,#334155);' +
        'background:var(--surface,#1e293b);box-shadow:0 16px 28px rgba(2,6,23,0.5);' +
      '}' +
      '#'+ TAG_DROPDOWN_ID + '[hidden]{display:none;}' +
      '.se-tag-dd-head{font-size:11px;color:var(--muted,#94a3b8);padding:3px 6px 6px;}' +
      '.se-tag-dd-option{' +
        'width:100%;display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:7px;' +
        'border:1px solid transparent;background:transparent;color:var(--text,#f1f5f9);' +
        'font-size:12px;text-align:left;cursor:pointer;' +
      '}' +
      '.se-tag-dd-option:hover{background:rgba(56,189,248,0.12);}' +
      '.se-tag-dd-option.is-active{border-color:var(--accent,#38bdf8);background:rgba(56,189,248,0.16);}' +
      '.se-tag-dd-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}' +
      '.se-tag-dd-check{font-size:11px;color:var(--accent,#38bdf8);min-width:32px;text-align:right;}' +
      '.se-tag-dd-empty{font-size:12px;color:var(--muted,#94a3b8);padding:8px 6px;}';

    document.head.appendChild(styleEl);
  }

  function _ensureTagFilterBar() {
    const conceptListEl = document.getElementById('concept-list');
    const itemsEl = document.getElementById('concept-items');
    if (!conceptListEl || !itemsEl) return null;

    let barEl = document.getElementById(TAG_FILTER_BAR_ID);
    if (!barEl) {
      barEl = document.createElement('div');
      barEl.id = TAG_FILTER_BAR_ID;
      barEl.addEventListener('click', _onTagFilterBarClick);

      const searchEl = document.getElementById('concept-search');
      if (searchEl && searchEl.parentNode === conceptListEl) {
        conceptListEl.insertBefore(barEl, itemsEl);
      } else {
        conceptListEl.insertBefore(barEl, conceptListEl.firstChild || itemsEl);
      }
    }

    return barEl;
  }

  function _renderTagFilterBar() {
    const barEl = _ensureTagFilterBar();
    if (!barEl) return;

    const tags = _safeGetTags();
    barEl.innerHTML = '';

    function makeButton(label, mode, tag) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'se-tag-filter-pill';
      btn.dataset.seTagFilter = '1';
      btn.dataset.mode = mode;
      if (tag && tag.id) {
        btn.dataset.tagId = tag.id;
      }

      if (tag && tag.color) {
        btn.appendChild(_createTagDot(tag.color, tag.name));
      }

      const textNode = document.createElement('span');
      textNode.textContent = label;
      btn.appendChild(textNode);

      const filter = _tagFilterState;
      const active =
        (mode === 'all' && !filter.tagId && !filter.showUntagged) ||
        (mode === 'untagged' && !!filter.showUntagged) ||
        (mode === 'tag' && filter.tagId === (tag && tag.id));

      if (active) {
        btn.classList.add('is-active');
      }

      return btn;
    }

    barEl.appendChild(makeButton('All', 'all'));
    barEl.appendChild(makeButton('Untagged', 'untagged'));

    if (tags.length === 0) {
      const empty = document.createElement('span');
      empty.className = 'se-filter-empty';
      empty.textContent = 'No tags defined';
      barEl.appendChild(empty);
      return;
    }

    tags.forEach(function (tag) {
      barEl.appendChild(makeButton(tag.name, 'tag', tag));
    });
  }

  function _setTagFilter(nextFilter, source, syncToTags) {
    const normalized = _normalizeTagFilter(nextFilter);
    const nextSignature = _tagFilterSignatureOf(normalized);
    const changed = nextSignature !== _tagFilterSignature;

    _tagFilterState = normalized;
    _tagFilterSignature = nextSignature;

    if (syncToTags !== false) {
      const tagsModule = _getTagsModule();
      if (tagsModule && typeof tagsModule.setFilter === 'function') {
        try {
          tagsModule.setFilter(normalized.tagId, normalized.showUntagged);
        } catch (error) {
          console.warn('[PARSE] Failed to set tag filter:', error);
        }
      }
    }

    _renderTagFilterBar();
    _refreshConceptTagIndicators();
    _applyTagFilterToConceptList();

    if (changed) {
      _dispatchTagFilterChanged(source || 'annotate-sidebar');
    }
  }

  function _onTagFilterBarClick(evt) {
    const btn = evt && evt.target && typeof evt.target.closest === 'function'
      ? evt.target.closest('[data-se-tag-filter="1"]')
      : null;
    if (!btn) return;

    const mode = btn.dataset.mode || 'all';
    if (mode === 'all') {
      _setTagFilter({ tagId: null, showUntagged: false }, 'annotate-sidebar', true);
      return;
    }
    if (mode === 'untagged') {
      _setTagFilter({ tagId: null, showUntagged: true }, 'annotate-sidebar', true);
      return;
    }

    const tagId = String(btn.dataset.tagId || '').trim() || null;
    _setTagFilter({ tagId: tagId, showUntagged: false }, 'annotate-sidebar', true);
  }

  function _ensureConceptTagInline(itemEl, conceptId) {
    if (!itemEl) return null;

    let inlineEl = itemEl.querySelector('.se-concept-tags-inline');
    if (!inlineEl) {
      inlineEl = document.createElement('span');
      inlineEl.className = 'se-concept-tags-inline';

      const dotsEl = document.createElement('span');
      dotsEl.className = 'se-tag-dots';
      inlineEl.appendChild(dotsEl);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'se-tag-toggle-btn';
      btn.setAttribute('aria-haspopup', 'true');
      btn.title = 'Toggle tags';
      btn.textContent = '\uD83C\uDFF7';
      btn.addEventListener('click', function (clickEvt) {
        clickEvt.preventDefault();
        clickEvt.stopPropagation();

        const currentConceptId = _conceptIdFromItem(itemEl);
        if (!currentConceptId) return;
        _toggleTagDropdown(currentConceptId, itemEl, btn);
      });

      inlineEl.appendChild(btn);

      const timeEl = itemEl.querySelector('.ci-time');
      if (timeEl && timeEl.parentNode === itemEl) {
        itemEl.insertBefore(inlineEl, timeEl);
      } else {
        itemEl.appendChild(inlineEl);
      }
    }

    if (conceptId && itemEl.dataset) {
      itemEl.dataset.seConceptId = conceptId;
    }

    return inlineEl;
  }

  function _renderTagDots(itemEl, conceptId) {
    const inlineEl = _ensureConceptTagInline(itemEl, conceptId);
    if (!inlineEl) return;

    const dotsEl = inlineEl.querySelector('.se-tag-dots');
    const btn = inlineEl.querySelector('.se-tag-toggle-btn');
    if (!dotsEl || !btn) return;

    const tags = _safeGetTagsForConcept(conceptId);
    dotsEl.innerHTML = '';

    const maxDots = 3;
    tags.slice(0, maxDots).forEach(function (tag) {
      dotsEl.appendChild(_createTagDot(tag.color, tag.name));
    });

    if (tags.length > maxDots) {
      const more = document.createElement('span');
      more.className = 'se-tag-more';
      more.textContent = '+' + String(tags.length - maxDots);
      dotsEl.appendChild(more);
    }

    btn.classList.toggle('is-tagged', tags.length > 0);
    btn.title = tags.length > 0
      ? 'Tags: ' + tags.map(function (tag) { return tag.name; }).join(', ')
      : 'Toggle tags';
  }

  function _refreshConceptTagIndicators() {
    const items = _conceptItemEls();
    items.forEach(function (itemEl) {
      const conceptId = _conceptIdFromItem(itemEl);
      if (!conceptId) return;
      _renderTagDots(itemEl, conceptId);
    });
  }

  function _ensureTagDropdownEl() {
    let dropdownEl = document.getElementById(TAG_DROPDOWN_ID);
    if (!dropdownEl) {
      dropdownEl = document.createElement('div');
      dropdownEl.id = TAG_DROPDOWN_ID;
      dropdownEl.hidden = true;
      dropdownEl.addEventListener('click', function (evt) {
        const optionEl = evt && evt.target && typeof evt.target.closest === 'function'
          ? evt.target.closest('[data-se-tag-option="1"]')
          : null;
        if (!optionEl || !_activeTagDropdownContext) return;

        evt.preventDefault();
        evt.stopPropagation();

        const tagId = String(optionEl.dataset.tagId || '').trim();
        const conceptId = _activeTagDropdownContext.conceptId;
        if (!tagId || !conceptId) return;
        _toggleTagForConcept(conceptId, tagId);
      });
      document.body.appendChild(dropdownEl);
    }
    return dropdownEl;
  }

  function _positionTagDropdown() {
    const dropdownEl = document.getElementById(TAG_DROPDOWN_ID);
    if (!dropdownEl || !_activeTagDropdownContext || !_activeTagDropdownContext.buttonEl) {
      return;
    }

    const btnRect = _activeTagDropdownContext.buttonEl.getBoundingClientRect();
    const ddRect = dropdownEl.getBoundingClientRect();

    let left = btnRect.left;
    let top = btnRect.bottom + 6;

    if (left + ddRect.width > window.innerWidth - 8) {
      left = window.innerWidth - ddRect.width - 8;
    }
    if (left < 8) {
      left = 8;
    }

    if (top + ddRect.height > window.innerHeight - 8) {
      top = btnRect.top - ddRect.height - 6;
      if (top < 8) {
        top = 8;
      }
    }

    dropdownEl.style.left = Math.round(left) + 'px';
    dropdownEl.style.top = Math.round(top) + 'px';
  }

  function _renderTagDropdown() {
    const dropdownEl = _ensureTagDropdownEl();
    if (!dropdownEl || !_activeTagDropdownContext) return;

    const conceptId = _activeTagDropdownContext.conceptId;
    const tags = _safeGetTags();
    const assigned = new Set(_safeGetTagsForConcept(conceptId).map(function (tag) { return tag.id; }));

    dropdownEl.innerHTML = '';

    const heading = document.createElement('div');
    heading.className = 'se-tag-dd-head';
    heading.textContent = 'Tags for concept #' + conceptId;
    dropdownEl.appendChild(heading);

    if (!tags.length) {
      const empty = document.createElement('div');
      empty.className = 'se-tag-dd-empty';
      empty.textContent = 'No tags are defined yet.';
      dropdownEl.appendChild(empty);
      return;
    }

    tags.forEach(function (tag) {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'se-tag-dd-option';
      option.dataset.seTagOption = '1';
      option.dataset.tagId = tag.id;

      const active = assigned.has(tag.id);
      if (active) {
        option.classList.add('is-active');
      }

      option.appendChild(_createTagDot(tag.color, tag.name));

      const nameEl = document.createElement('span');
      nameEl.className = 'se-tag-dd-name';
      nameEl.textContent = tag.name;
      option.appendChild(nameEl);

      const checkEl = document.createElement('span');
      checkEl.className = 'se-tag-dd-check';
      checkEl.textContent = active ? 'On' : '';
      option.appendChild(checkEl);

      dropdownEl.appendChild(option);
    });
  }

  function _openTagDropdown(conceptId, itemEl, buttonEl) {
    if (!conceptId || !itemEl || !buttonEl) return;

    _closeTagDropdown();

    _activeTagDropdownContext = {
      conceptId: conceptId,
      itemEl: itemEl,
      buttonEl: buttonEl,
    };

    buttonEl.classList.add('is-open');

    const dropdownEl = _ensureTagDropdownEl();
    dropdownEl.hidden = false;
    _renderTagDropdown();
    _positionTagDropdown();
  }

  function _closeTagDropdown() {
    const dropdownEl = document.getElementById(TAG_DROPDOWN_ID);
    if (dropdownEl) {
      dropdownEl.hidden = true;
    }

    if (_activeTagDropdownContext && _activeTagDropdownContext.buttonEl) {
      _activeTagDropdownContext.buttonEl.classList.remove('is-open');
    }

    _activeTagDropdownContext = null;
  }

  function _toggleTagDropdown(conceptId, itemEl, buttonEl) {
    const isSameContext =
      _activeTagDropdownContext &&
      _activeTagDropdownContext.conceptId === conceptId &&
      _activeTagDropdownContext.buttonEl === buttonEl;

    if (isSameContext) {
      _closeTagDropdown();
      return;
    }

    _openTagDropdown(conceptId, itemEl, buttonEl);
  }

  function _toggleTagForConcept(conceptId, tagId) {
    const tagsModule = _getTagsModule();
    if (!tagsModule) return;

    const conceptArg = _conceptArg(conceptId);
    if (conceptArg == null) return;

    const currentlyAssigned = _safeGetTagsForConcept(conceptId).map(function (tag) { return tag.id; });
    const hasTag = currentlyAssigned.indexOf(tagId) !== -1;

    try {
      if (hasTag && typeof tagsModule.removeTagFromConcepts === 'function') {
        tagsModule.removeTagFromConcepts(tagId, [conceptArg]);
      } else if (!hasTag && typeof tagsModule.addTagToConcepts === 'function') {
        tagsModule.addTagToConcepts(tagId, [conceptArg]);
      }

      document.dispatchEvent(
        new CustomEvent('parse:tags-updated', {
          detail: {
            conceptId: conceptArg,
            tagId: tagId,
            action: hasTag ? 'remove' : 'add',
          },
        })
      );
    } catch (error) {
      console.warn('[PARSE] Failed to toggle concept tag:', error);
    }
  }

  function _onDocumentPointerDown(evt) {
    if (!_activeTagDropdownContext) return;

    const dropdownEl = document.getElementById(TAG_DROPDOWN_ID);
    if (!dropdownEl) return;

    const target = evt && evt.target;
    if (!target) return;

    if (dropdownEl.contains(target)) return;
    if (
      _activeTagDropdownContext.buttonEl &&
      _activeTagDropdownContext.buttonEl.contains(target)
    ) {
      return;
    }

    _closeTagDropdown();
  }

  function _onDocumentKeyDown(evt) {
    if (!_activeTagDropdownContext) return;
    if (!evt || evt.key !== 'Escape') return;

    _closeTagDropdown();
    evt.preventDefault();
    evt.stopPropagation();
  }

  function _refreshTagSidebar() {
    _tagSidebarRefreshQueued = false;

    if (!_getTagsModule()) return;

    _attachTagSidebarObserver();

    _ensureTagStyles();
    _wireSearchInput();
    _renderTagFilterBar();
    _refreshConceptTagIndicators();
    _applyTagFilterToConceptList();

    if (_activeTagDropdownContext) {
      if (!_activeTagDropdownContext.itemEl || !document.body.contains(_activeTagDropdownContext.itemEl)) {
        _closeTagDropdown();
      } else {
        _renderTagDropdown();
        _positionTagDropdown();
      }
    }
  }

  function _scheduleTagSidebarRefresh() {
    if (_tagSidebarRefreshQueued) return;
    _tagSidebarRefreshQueued = true;
    requestAnimationFrame(_refreshTagSidebar);
  }

  function _attachTagSidebarObserver() {
    if (_tagSidebarObserver || typeof MutationObserver !== 'function') {
      return;
    }

    const targetEl = document.getElementById('concept-items') || document.getElementById('concept-list');
    if (!targetEl) return;

    _tagSidebarObserver = new MutationObserver(function () {
      _scheduleTagSidebarRefresh();
    });

    _tagSidebarObserver.observe(targetEl, {
      childList: true,
      subtree: true,
    });
  }

  function _detachTagSidebarObserver() {
    if (_tagSidebarObserver) {
      _tagSidebarObserver.disconnect();
      _tagSidebarObserver = null;
    }
  }

  function _initTagSidebarIntegration() {
    const tagsModule = SE.modules && SE.modules.tags;
    if (!tagsModule || typeof tagsModule.init !== 'function') {
      return;
    }

    try {
      const maybeApi = tagsModule.init(document.getElementById('concept-list') || _containerEl || document.body);
      _tagsModule = maybeApi || tagsModule;
    } catch (error) {
      console.warn('[PARSE] tags.init() failed:', error);
      _tagsModule = tagsModule;
    }

    if (_tagsModule && typeof _tagsModule.getFilter === 'function') {
      try {
        _tagFilterState = _normalizeTagFilter(_tagsModule.getFilter());
      } catch (_) {
        _tagFilterState = _normalizeTagFilter(_tagFilterState);
      }
    }

    _tagFilterSignature = _tagFilterSignatureOf(_tagFilterState);
    _attachTagSidebarObserver();
    _scheduleTagSidebarRefresh();
  }

  function _destroyTagSidebarIntegration() {
    _closeTagDropdown();
    _detachTagSidebarObserver();

    if (_searchInputEl && _boundOnSearchInput) {
      _searchInputEl.removeEventListener('input', _boundOnSearchInput);
    }
    _searchInputEl = null;
    _boundOnSearchInput = null;

    const filterBar = document.getElementById(TAG_FILTER_BAR_ID);
    if (filterBar && filterBar.parentNode) {
      filterBar.parentNode.removeChild(filterBar);
    }

    const dropdownEl = document.getElementById(TAG_DROPDOWN_ID);
    if (dropdownEl && dropdownEl.parentNode) {
      dropdownEl.parentNode.removeChild(dropdownEl);
    }

    const tagsModule = _getTagsModule();
    if (tagsModule && typeof tagsModule.destroy === 'function') {
      try {
        tagsModule.destroy();
      } catch (error) {
        console.warn('[PARSE] tags.destroy() failed:', error);
      }
    }

    _tagsModule = null;
    _tagFilterState = { tagId: null, showUntagged: false };
    _tagFilterSignature = null;
    _tagSidebarRefreshQueued = false;
  }

  function _onTagFilterChanged(evt) {
    const detail = (evt && evt.detail) || {};
    _setTagFilter(detail, 'tags-module', false);
  }

  function _onTagsUpdated() {
    _scheduleTagSidebarRefresh();
  }

  function _onItemsTagged() {
    _scheduleTagSidebarRefresh();
  }

  function _onTagDefinitionsChanged() {
    _scheduleTagSidebarRefresh();
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

    _scheduleTagSidebarRefresh();
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

    _closeTagDropdown();

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
    _boundOnTagFilterChanged  = _onTagFilterChanged;
    _boundOnTagsUpdated       = _onTagsUpdated;
    _boundOnItemsTagged       = _onItemsTagged;
    _boundOnTagCreated        = _onTagDefinitionsChanged;
    _boundOnTagDeleted        = _onTagDefinitionsChanged;
    _boundOnDocumentPointerDown = _onDocumentPointerDown;
    _boundOnDocumentKeyDown   = _onDocumentKeyDown;

    document.addEventListener('parse:panel-open',          _boundOnPanelOpen);
    document.addEventListener('parse:panel-close',         _boundOnPanelClose);
    document.addEventListener('parse:fullscreen-toggle',   _boundOnFullscreenToggle);
    document.addEventListener('parse:navigate-concept',    _boundOnNavigateConcept);
    document.addEventListener('parse:region-assigned',     _boundOnRegionAssigned);
    document.addEventListener('parse:annotations-changed', _boundOnAnnotationsChanged);
    document.addEventListener('parse:tag-filter',          _boundOnTagFilterChanged);
    document.addEventListener('parse:tags-updated',        _boundOnTagsUpdated);
    document.addEventListener('parse:items-tagged',        _boundOnItemsTagged);
    document.addEventListener('parse:tag-created',         _boundOnTagCreated);
    document.addEventListener('parse:tag-deleted',         _boundOnTagDeleted);
    document.addEventListener('pointerdown',               _boundOnDocumentPointerDown);
    document.addEventListener('keydown',                   _boundOnDocumentKeyDown, true);

    _initTagSidebarIntegration();

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
    if (_boundOnTagFilterChanged)  document.removeEventListener('parse:tag-filter',          _boundOnTagFilterChanged);
    if (_boundOnTagsUpdated)       document.removeEventListener('parse:tags-updated',        _boundOnTagsUpdated);
    if (_boundOnItemsTagged)       document.removeEventListener('parse:items-tagged',        _boundOnItemsTagged);
    if (_boundOnTagCreated)        document.removeEventListener('parse:tag-created',         _boundOnTagCreated);
    if (_boundOnTagDeleted)        document.removeEventListener('parse:tag-deleted',         _boundOnTagDeleted);
    if (_boundOnDocumentPointerDown) document.removeEventListener('pointerdown',              _boundOnDocumentPointerDown);
    if (_boundOnDocumentKeyDown)   document.removeEventListener('keydown',                   _boundOnDocumentKeyDown, true);
    document.removeEventListener('keydown', _onKeyDown);

    _destroyTagSidebarIntegration();

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
    _boundOnTagFilterChanged  = null;
    _boundOnTagsUpdated       = null;
    _boundOnItemsTagged       = null;
    _boundOnTagCreated        = null;
    _boundOnTagDeleted        = null;
    _boundOnDocumentPointerDown = null;
    _boundOnDocumentKeyDown   = null;
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
