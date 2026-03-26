(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.tags = window.PARSE.tags || {};

  const P = window.PARSE;

  const LEGACY_STORAGE_KEY = 'parse-tags-v1';
  const STORAGE_KEY_PREFIX = LEGACY_STORAGE_KEY + '-';
  const STORAGE_VERSION = 1;
  const DEFAULT_COLOR = '#6b7280';
  const DEFAULT_TAGS = [
    { id: 'review-needed', name: 'Review needed', color: '#f59e0b' },
    { id: 'confirmed', name: 'Confirmed', color: '#10b981' },
    { id: 'problematic', name: 'Problematic', color: '#ef4444' },
  ];

  const state = {
    initialized: false,
    containerEl: null,
    storageKey: null,
    tags: [],
    assignments: Object.create(null),
    included: Object.create(null),
    filter: {
      tagId: null,
      showUntagged: false,
    },
  };

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function cloneJson(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeTagId(tagId) {
    if (tagId == null) return null;
    const text = String(tagId).trim();
    return text || null;
  }

  function normalizeConceptId(conceptId) {
    if (conceptId == null) return '';

    let text = String(conceptId).trim();
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

  function conceptIdToNumber(conceptId) {
    const numeric = Number(conceptId);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function normalizeColor(color) {
    if (color == null) return DEFAULT_COLOR;
    const text = String(color).trim();
    if (!text) return DEFAULT_COLOR;

    const hexMatch = text.match(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
    return hexMatch ? text : DEFAULT_COLOR;
  }

  function normalizeTagName(name) {
    const text = name == null ? '' : String(name).trim();
    return text;
  }

  function normalizeStorageSegment(value) {
    const text = value == null ? '' : String(value).trim();
    if (!text) return '';

    return text
      .replace(/\/+/g, '-')
      .replace(/[^a-zA-Z0-9._-]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function getProjectStorageId() {
    const project = P.project && typeof P.project === 'object' ? P.project : null;
    const projectId = normalizeStorageSegment(project && project.id);
    if (projectId) {
      return projectId;
    }

    const pathId = normalizeStorageSegment(window.location && window.location.pathname);
    if (pathId) {
      return pathId;
    }

    return 'default';
  }

  function buildStorageKey() {
    return STORAGE_KEY_PREFIX + getProjectStorageId();
  }

  function getStorageKey() {
    if (!state.storageKey) {
      state.storageKey = buildStorageKey();
    }
    return state.storageKey;
  }

  function migrateLegacyStorage(nextStorageKey) {
    if (!nextStorageKey || nextStorageKey === LEGACY_STORAGE_KEY) {
      return;
    }

    try {
      const namespacedValue = localStorage.getItem(nextStorageKey);
      if (namespacedValue != null) {
        return;
      }

      const legacyValue = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacyValue != null) {
        localStorage.setItem(nextStorageKey, legacyValue);
      }
    } catch (error) {
      console.warn('[tags] Failed to migrate legacy tag state:', error);
    }
  }

  function generateTagId(name) {
    const base = normalizeTagName(name)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 32);

    const safeBase = base || 'tag';
    const suffix = Math.random().toString(36).slice(2, 9);
    return safeBase + '-' + suffix;
  }

  function listTagIdsForConcept(conceptId) {
    const key = normalizeConceptId(conceptId);
    if (!key || !state.assignments[key]) {
      return [];
    }

    return Array.from(state.assignments[key]);
  }

  function getTagIndexById(tagId) {
    const normalized = normalizeTagId(tagId);
    if (!normalized) return -1;

    for (let i = 0; i < state.tags.length; i += 1) {
      if (state.tags[i].id === normalized) {
        return i;
      }
    }

    return -1;
  }

  function hasTag(tagId) {
    return getTagIndexById(tagId) !== -1;
  }

  function serializeState() {
    const assignments = {};
    const assignmentKeys = Object.keys(state.assignments);

    for (let i = 0; i < assignmentKeys.length; i += 1) {
      const conceptId = assignmentKeys[i];
      const tagIdSet = state.assignments[conceptId];
      if (!tagIdSet || !tagIdSet.size) continue;

      const filtered = Array.from(tagIdSet).filter(function (tagId) {
        return hasTag(tagId);
      });

      if (filtered.length) {
        assignments[conceptId] = filtered;
      }
    }

    const included = {};
    const includedKeys = Object.keys(state.included);
    for (let i = 0; i < includedKeys.length; i += 1) {
      const conceptId = includedKeys[i];
      if (state.included[conceptId] === false) {
        included[conceptId] = false;
      }
    }

    return {
      version: STORAGE_VERSION,
      tags: state.tags.map(function (tag) {
        return {
          id: tag.id,
          name: tag.name,
          color: tag.color,
        };
      }),
      assignments: assignments,
      included: included,
      filter: {
        tagId: state.filter.tagId,
        showUntagged: !!state.filter.showUntagged,
      },
    };
  }

  function persistState() {
    try {
      localStorage.setItem(getStorageKey(), JSON.stringify(serializeState()));
    } catch (error) {
      console.warn('[tags] Failed to persist tags to localStorage:', error);
    }
  }

  function normalizeSnapshot(snapshot) {
    const parsed = snapshot && typeof snapshot === 'object' ? snapshot : {};
    const rawTags = Array.isArray(parsed.tags) ? parsed.tags : [];

    const seenTagIds = new Set();
    const tags = [];

    for (let i = 0; i < rawTags.length; i += 1) {
      const rawTag = rawTags[i];
      if (!rawTag || typeof rawTag !== 'object') continue;

      const id = normalizeTagId(rawTag.id);
      const name = normalizeTagName(rawTag.name);

      if (!id || !name || seenTagIds.has(id)) {
        continue;
      }

      seenTagIds.add(id);
      tags.push({
        id: id,
        name: name,
        color: normalizeColor(rawTag.color),
      });
    }

    const assignments = Object.create(null);
    const rawAssignments = parsed.assignments && typeof parsed.assignments === 'object'
      ? parsed.assignments
      : {};
    const assignmentKeys = Object.keys(rawAssignments);

    for (let i = 0; i < assignmentKeys.length; i += 1) {
      const conceptId = normalizeConceptId(assignmentKeys[i]);
      if (!conceptId) continue;

      const rawTagIds = Array.isArray(rawAssignments[assignmentKeys[i]])
        ? rawAssignments[assignmentKeys[i]]
        : [];

      const tagIdSet = new Set();
      for (let j = 0; j < rawTagIds.length; j += 1) {
        const tagId = normalizeTagId(rawTagIds[j]);
        if (tagId && seenTagIds.has(tagId)) {
          tagIdSet.add(tagId);
        }
      }

      if (tagIdSet.size) {
        assignments[conceptId] = tagIdSet;
      }
    }

    const included = Object.create(null);
    const rawIncluded = parsed.included && typeof parsed.included === 'object'
      ? parsed.included
      : {};
    const includedKeys = Object.keys(rawIncluded);

    for (let i = 0; i < includedKeys.length; i += 1) {
      const conceptId = normalizeConceptId(includedKeys[i]);
      if (!conceptId) continue;
      included[conceptId] = rawIncluded[includedKeys[i]] === false ? false : true;
    }

    const rawFilter = parsed.filter && typeof parsed.filter === 'object'
      ? parsed.filter
      : {};
    const filterTagId = normalizeTagId(rawFilter.tagId);

    return {
      tags: tags,
      assignments: assignments,
      included: included,
      filter: {
        tagId: filterTagId && seenTagIds.has(filterTagId) ? filterTagId : null,
        showUntagged: !!rawFilter.showUntagged,
      },
    };
  }

  function restoreState() {
    const storageKey = getStorageKey();
    let snapshot = null;
    let hasStoredValue = false;

    try {
      const raw = localStorage.getItem(storageKey);
      hasStoredValue = raw != null;
      if (raw != null) {
        snapshot = JSON.parse(raw);
      }
    } catch (error) {
      console.warn('[tags] Failed to parse saved tag state. Reinitializing defaults.', error);
      snapshot = null;
      hasStoredValue = false;
    }

    if (!hasStoredValue) {
      state.tags = cloneJson(DEFAULT_TAGS);
      state.assignments = Object.create(null);
      state.included = Object.create(null);
      state.filter = { tagId: null, showUntagged: false };
      persistState();
      return;
    }

    const normalized = normalizeSnapshot(snapshot);
    state.tags = normalized.tags;
    state.assignments = normalized.assignments;
    state.included = normalized.included;
    state.filter = normalized.filter;
  }

  function syncGlobalState() {
    P.tags = {
      tags: state.tags.map(function (tag) {
        return {
          id: tag.id,
          name: tag.name,
          color: tag.color,
        };
      }),
      assignments: Object.keys(state.assignments).reduce(function (acc, conceptId) {
        acc[conceptId] = Array.from(state.assignments[conceptId]);
        return acc;
      }, {}),
      included: Object.keys(state.included).reduce(function (acc, conceptId) {
        acc[conceptId] = state.included[conceptId];
        return acc;
      }, {}),
      filter: {
        tagId: state.filter.tagId,
        showUntagged: !!state.filter.showUntagged,
      },
    };
  }

  function ensureInitialized() {
    if (!state.initialized) {
      init(null);
    }
  }

  function normalizeConceptIdList(conceptIds) {
    const list = Array.isArray(conceptIds) ? conceptIds : [conceptIds];
    const seen = new Set();
    const output = [];

    for (let i = 0; i < list.length; i += 1) {
      const conceptId = normalizeConceptId(list[i]);
      if (!conceptId || seen.has(conceptId)) continue;
      seen.add(conceptId);
      output.push(conceptId);
    }

    return output;
  }

  function mapConceptIdsToNumbers(conceptIds) {
    const out = [];
    for (let i = 0; i < conceptIds.length; i += 1) {
      const numeric = conceptIdToNumber(conceptIds[i]);
      if (numeric != null) {
        out.push(numeric);
      }
    }
    return out;
  }

  /**
   * Initialize the tags module and restore persisted state.
   * @param {HTMLElement|null} containerEl Root element for future UI rendering.
   * @returns {object} Public tags module API.
   */
  function init(containerEl) {
    const nextStorageKey = buildStorageKey();
    state.containerEl = containerEl || state.containerEl || null;

    if (!state.initialized || state.storageKey !== nextStorageKey) {
      state.storageKey = nextStorageKey;
      migrateLegacyStorage(nextStorageKey);
      restoreState();
      syncGlobalState();
    }

    state.initialized = true;
    return P.modules.tags;
  }

  /**
   * Destroy module state references and stop further interaction.
   */
  function destroy() {
    state.containerEl = null;
    state.storageKey = null;
    state.initialized = false;
  }

  /**
   * Get all defined tags.
   * @returns {Array<{id: string, name: string, color: string}>}
   */
  function getTags() {
    ensureInitialized();
    return state.tags.map(function (tag) {
      return {
        id: tag.id,
        name: tag.name,
        color: tag.color,
      };
    });
  }

  /**
   * Create a new tag.
   * @param {string} name Tag display name.
   * @param {string} [color] Optional hex color.
   * @returns {{id: string, name: string, color: string}} The created tag.
   */
  function createTag(name, color) {
    ensureInitialized();

    const normalizedName = normalizeTagName(name);
    if (!normalizedName) {
      throw new Error('Tag name is required.');
    }

    const nextTag = {
      id: generateTagId(normalizedName),
      name: normalizedName,
      color: normalizeColor(color),
    };

    state.tags.push(nextTag);
    persistState();
    syncGlobalState();

    dispatch('parse:tag-created', {
      tagId: nextTag.id,
      name: nextTag.name,
      color: nextTag.color,
    });

    return {
      id: nextTag.id,
      name: nextTag.name,
      color: nextTag.color,
    };
  }

  /**
   * Delete a tag and remove all assignments for it.
   * @param {string} tagId Tag ID.
   * @returns {boolean} True if a tag was deleted.
   */
  function deleteTag(tagId) {
    ensureInitialized();

    const normalizedTagId = normalizeTagId(tagId);
    const index = getTagIndexById(normalizedTagId);
    if (index === -1) {
      return false;
    }

    state.tags.splice(index, 1);

    const affectedConceptIds = [];
    const assignmentKeys = Object.keys(state.assignments);
    for (let i = 0; i < assignmentKeys.length; i += 1) {
      const conceptId = assignmentKeys[i];
      const tagIds = state.assignments[conceptId];
      if (!tagIds || !tagIds.size) continue;

      if (tagIds.delete(normalizedTagId)) {
        affectedConceptIds.push(conceptId);
      }

      if (!tagIds.size) {
        delete state.assignments[conceptId];
      }
    }

    const filterWasUpdated = state.filter.tagId === normalizedTagId;
    if (filterWasUpdated) {
      state.filter.tagId = null;
    }

    persistState();
    syncGlobalState();

    dispatch('parse:tag-deleted', { tagId: normalizedTagId });

    if (affectedConceptIds.length) {
      dispatch('parse:items-tagged', {
        tagId: normalizedTagId,
        conceptIds: mapConceptIdsToNumbers(affectedConceptIds),
        action: 'remove',
      });
    }

    if (filterWasUpdated) {
      dispatch('parse:tag-filter', {
        tagId: null,
        showUntagged: !!state.filter.showUntagged,
      });
    }

    return true;
  }

  /**
   * Rename an existing tag.
   * @param {string} tagId Tag ID.
   * @param {string} name New tag name.
   * @returns {{id: string, name: string, color: string}|null} Updated tag or null when missing.
   */
  function renameTag(tagId, name) {
    ensureInitialized();

    const normalizedTagId = normalizeTagId(tagId);
    const normalizedName = normalizeTagName(name);
    if (!normalizedName) {
      throw new Error('Tag name is required.');
    }

    const index = getTagIndexById(normalizedTagId);
    if (index === -1) {
      return null;
    }

    state.tags[index].name = normalizedName;
    persistState();
    syncGlobalState();

    return {
      id: state.tags[index].id,
      name: state.tags[index].name,
      color: state.tags[index].color,
    };
  }

  /**
   * Add a tag to one or more concepts.
   * @param {string} tagId Tag ID.
   * @param {Array<number|string>|number|string} conceptIds Concept IDs.
   * @returns {number[]} Concept IDs updated by this operation.
   */
  function addTagToConcepts(tagId, conceptIds) {
    ensureInitialized();

    const normalizedTagId = normalizeTagId(tagId);
    if (!hasTag(normalizedTagId)) {
      throw new Error('Unknown tag ID: ' + String(tagId));
    }

    const normalizedConceptIds = normalizeConceptIdList(conceptIds);
    const changed = [];

    for (let i = 0; i < normalizedConceptIds.length; i += 1) {
      const conceptId = normalizedConceptIds[i];
      if (!state.assignments[conceptId]) {
        state.assignments[conceptId] = new Set();
      }

      const tagSet = state.assignments[conceptId];
      const before = tagSet.size;
      tagSet.add(normalizedTagId);

      if (tagSet.size !== before) {
        changed.push(conceptId);
      }
    }

    if (changed.length) {
      persistState();
      syncGlobalState();
      dispatch('parse:items-tagged', {
        tagId: normalizedTagId,
        conceptIds: mapConceptIdsToNumbers(changed),
        action: 'add',
      });
    }

    return mapConceptIdsToNumbers(changed);
  }

  /**
   * Remove a tag from one or more concepts.
   * @param {string} tagId Tag ID.
   * @param {Array<number|string>|number|string} conceptIds Concept IDs.
   * @returns {number[]} Concept IDs updated by this operation.
   */
  function removeTagFromConcepts(tagId, conceptIds) {
    ensureInitialized();

    const normalizedTagId = normalizeTagId(tagId);
    if (!hasTag(normalizedTagId)) {
      throw new Error('Unknown tag ID: ' + String(tagId));
    }

    const normalizedConceptIds = normalizeConceptIdList(conceptIds);
    const changed = [];

    for (let i = 0; i < normalizedConceptIds.length; i += 1) {
      const conceptId = normalizedConceptIds[i];
      const tagSet = state.assignments[conceptId];
      if (!tagSet || !tagSet.size) continue;

      if (tagSet.delete(normalizedTagId)) {
        changed.push(conceptId);
      }

      if (!tagSet.size) {
        delete state.assignments[conceptId];
      }
    }

    if (changed.length) {
      persistState();
      syncGlobalState();
      dispatch('parse:items-tagged', {
        tagId: normalizedTagId,
        conceptIds: mapConceptIdsToNumbers(changed),
        action: 'remove',
      });
    }

    return mapConceptIdsToNumbers(changed);
  }

  /**
   * Get all tags assigned to a concept.
   * @param {number|string} conceptId Concept ID.
   * @returns {Array<{id: string, name: string, color: string}>}
   */
  function getTagsForConcept(conceptId) {
    ensureInitialized();

    const assignedTagIds = listTagIdsForConcept(conceptId);
    if (!assignedTagIds.length) {
      return [];
    }

    const tagsById = state.tags.reduce(function (acc, tag) {
      acc[tag.id] = tag;
      return acc;
    }, {});

    return assignedTagIds
      .map(function (tagId) {
        const tag = tagsById[tagId];
        return tag
          ? {
            id: tag.id,
            name: tag.name,
            color: tag.color,
          }
          : null;
      })
      .filter(function (tag) {
        return !!tag;
      });
  }

  /**
   * Check if a concept is currently included in analysis.
   * @param {number|string} conceptId Concept ID.
   * @returns {boolean} True when included.
   */
  function isIncluded(conceptId) {
    ensureInitialized();

    const key = normalizeConceptId(conceptId);
    if (!key) return true;
    return state.included[key] !== false;
  }

  /**
   * Set include-in-analysis state for a concept.
   * @param {number|string} conceptId Concept ID.
   * @param {boolean} included Inclusion flag.
   * @returns {boolean} The updated inclusion value.
   */
  function setIncluded(conceptId, included) {
    ensureInitialized();

    const key = normalizeConceptId(conceptId);
    if (!key) {
      throw new Error('Concept ID is required.');
    }

    const normalizedIncluded = included !== false;
    const previousIncluded = state.included[key] !== false;

    if (normalizedIncluded) {
      delete state.included[key];
    } else {
      state.included[key] = false;
    }

    if (previousIncluded !== normalizedIncluded) {
      persistState();
      syncGlobalState();
      dispatch('parse:analysis-toggle', {
        conceptId: conceptIdToNumber(key) == null ? key : conceptIdToNumber(key),
        included: normalizedIncluded,
      });
    }

    return normalizedIncluded;
  }

  /**
   * Set the active tag filter.
   * @param {string|null} tagId Active tag ID or null for all tags.
   * @param {boolean} [showUntagged] Whether untagged concepts are also visible.
   * @returns {{tagId: string|null, showUntagged: boolean}} The active filter.
   */
  function setFilter(tagId, showUntagged) {
    ensureInitialized();

    const normalizedTagId = normalizeTagId(tagId);
    if (normalizedTagId && !hasTag(normalizedTagId)) {
      throw new Error('Unknown tag ID: ' + normalizedTagId);
    }

    const nextShowUntagged = showUntagged == null
      ? !!state.filter.showUntagged
      : !!showUntagged;

    const didChange = state.filter.tagId !== normalizedTagId || state.filter.showUntagged !== nextShowUntagged;

    state.filter.tagId = normalizedTagId;
    state.filter.showUntagged = nextShowUntagged;

    if (didChange) {
      persistState();
      syncGlobalState();
      dispatch('parse:tag-filter', {
        tagId: state.filter.tagId,
        showUntagged: !!state.filter.showUntagged,
      });
    }

    return {
      tagId: state.filter.tagId,
      showUntagged: !!state.filter.showUntagged,
    };
  }

  /**
   * Set untagged visibility while preserving the selected tag.
   * @param {boolean} showUntagged Whether untagged concepts should be shown.
   * @returns {{tagId: string|null, showUntagged: boolean}} The active filter.
   */
  function setShowUntagged(showUntagged) {
    return setFilter(state.filter.tagId, showUntagged);
  }

  /**
   * Get the currently active filter state.
   * @returns {{tagId: string|null, showUntagged: boolean}}
   */
  function getFilter() {
    ensureInitialized();
    return {
      tagId: state.filter.tagId,
      showUntagged: !!state.filter.showUntagged,
    };
  }

  /**
   * Determine if a concept is visible under the current filter.
   * @param {number|string} conceptId Concept ID.
   * @returns {boolean} True if concept should be visible.
   */
  function matchesFilter(conceptId) {
    ensureInitialized();

    const assignedTagIds = listTagIdsForConcept(conceptId);
    const isUntagged = assignedTagIds.length === 0;
    const hasActiveTag = !!state.filter.tagId;

    if (!hasActiveTag && !state.filter.showUntagged) {
      return true;
    }

    if (!hasActiveTag && state.filter.showUntagged) {
      return isUntagged;
    }

    const matchesTag = assignedTagIds.indexOf(state.filter.tagId) !== -1;
    return state.filter.showUntagged ? (matchesTag || isUntagged) : matchesTag;
  }

  P.modules.tags = {
    init: init,
    destroy: destroy,
    getTags: getTags,
    createTag: createTag,
    deleteTag: deleteTag,
    renameTag: renameTag,
    addTagToConcepts: addTagToConcepts,
    removeTagFromConcepts: removeTagFromConcepts,
    getTagsForConcept: getTagsForConcept,
    isIncluded: isIncluded,
    setIncluded: setIncluded,
    setFilter: setFilter,
    setShowUntagged: setShowUntagged,
    getFilter: getFilter,
    matchesFilter: matchesFilter,
  };
}());
