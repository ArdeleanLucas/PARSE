'use strict';

// Project selection persistence for the PARSE desktop shell.
//
// This module manages which project folder the desktop app opens: it reads and
// writes a small JSON settings file, maintains a de-duplicated recent-projects
// list, and validates candidate project directories.
//
// It is intentionally free of any `require('electron')` so it can be unit
// tested under plain `node --test`. The Electron shell (main.js) wires it in,
// passing `path.join(app.getPath('userData'), 'settings.json')` as the
// settings path.

const fs = require('fs');
const path = require('path');

const RECENT_PROJECTS_CAP = 10;

// A NEW project directory does not yet have a project.json; the backend
// initializes it on first launch. An EXISTING PARSE project has this file.
const PROJECT_MANIFEST = 'project.json';

function defaultSettings() {
  return { recentProjects: [], lastProject: null };
}

// Read settings JSON, tolerating a missing or corrupt file by returning
// defaults. Never throws for I/O or parse errors — a broken settings file must
// not prevent the app from launching.
function readSettings(settingsPath) {
  let raw;
  try {
    raw = fs.readFileSync(settingsPath, 'utf8');
  } catch (error) {
    // Missing file (ENOENT) or unreadable: fall back to defaults.
    return defaultSettings();
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    // Corrupt JSON: fall back to defaults rather than crash.
    return defaultSettings();
  }

  return normalizeSettings(parsed);
}

// Coerce an arbitrary parsed object into the expected settings shape.
function normalizeSettings(obj) {
  const base = defaultSettings();

  if (!obj || typeof obj !== 'object') {
    return base;
  }

  if (Array.isArray(obj.recentProjects)) {
    base.recentProjects = obj.recentProjects.filter(
      (entry) => typeof entry === 'string' && entry.length > 0
    );
  }

  if (typeof obj.lastProject === 'string' && obj.lastProject.length > 0) {
    base.lastProject = obj.lastProject;
  }

  return base;
}

// Write settings JSON, creating the parent directory if needed.
function writeSettings(settingsPath, obj) {
  const normalized = normalizeSettings(obj);
  const dir = path.dirname(settingsPath);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(settingsPath, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
  return normalized;
}

// Return a new settings object with `projectPath` moved/added to the front of
// the recent list (deduped, capped) and recorded as lastProject.
//
// The incoming path is normalized with path.resolve() before dedup/storage so
// that equivalent paths that differ only by a trailing separator (or relative
// segments) collapse to a single recent entry instead of duplicating.
function addRecentProject(settings, projectPath) {
  const normalized = normalizeSettings(settings);

  if (typeof projectPath !== 'string' || projectPath.length === 0) {
    return normalized;
  }

  const resolvedPath = path.resolve(projectPath);

  const deduped = normalized.recentProjects.filter((entry) => entry !== resolvedPath);
  const recentProjects = [resolvedPath, ...deduped].slice(0, RECENT_PROJECTS_CAP);

  return {
    recentProjects,
    lastProject: resolvedPath,
  };
}

// Return a new settings object with `projectPath` removed from the recent list.
// If it was the lastProject, lastProject is reset to the next most-recent entry
// (or null when the list becomes empty).
function removeRecentProject(settings, projectPath) {
  const normalized = normalizeSettings(settings);

  const resolvedPath = typeof projectPath === 'string' && projectPath.length > 0
    ? path.resolve(projectPath)
    : projectPath;

  const recentProjects = normalized.recentProjects.filter(
    (entry) => entry !== resolvedPath
  );

  let lastProject = normalized.lastProject;
  if (lastProject === resolvedPath) {
    lastProject = recentProjects.length > 0 ? recentProjects[0] : null;
  }

  return { recentProjects, lastProject };
}

// A directory is a valid project target when it exists and is a directory.
// A brand-new project is just an empty/new dir the backend will initialize, so
// validity here does NOT require project.json — see hasProjectJson for that.
//
// The input is resolved/normalized before the filesystem check so a
// hand-edited or otherwise relative `lastProject` value is still handled
// consistently with the normalized paths written by addRecentProject.
function isValidProjectDir(dirPath) {
  if (typeof dirPath !== 'string' || dirPath.length === 0) {
    return false;
  }
  try {
    return fs.statSync(path.resolve(dirPath)).isDirectory();
  } catch (error) {
    return false;
  }
}

// True when the directory already contains a PARSE project manifest, i.e. it is
// an existing project rather than a fresh folder to initialize.
function hasProjectJson(dirPath) {
  if (typeof dirPath !== 'string' || dirPath.length === 0) {
    return false;
  }
  try {
    return fs.statSync(path.join(dirPath, PROJECT_MANIFEST)).isFile();
  } catch (error) {
    return false;
  }
}

module.exports = {
  readSettings,
  writeSettings,
  addRecentProject,
  removeRecentProject,
  isValidProjectDir,
  hasProjectJson,
  defaultSettings,
  RECENT_PROJECTS_CAP,
  PROJECT_MANIFEST,
};
