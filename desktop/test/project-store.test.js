'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  readSettings,
  writeSettings,
  addRecentProject,
  removeRecentProject,
  isValidProjectDir,
  hasProjectJson,
  defaultSettings,
  RECENT_PROJECTS_CAP,
  PROJECT_MANIFEST,
} = require('../project-store');

function makeTmpDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

test('writeSettings/readSettings round-trip a settings object', () => {
  const dir = makeTmpDir('parse-settings-');
  const settingsPath = path.join(dir, 'nested', 'settings.json');

  const input = {
    recentProjects: ['/a/one', '/b/two'],
    lastProject: '/a/one',
  };

  writeSettings(settingsPath, input);
  const read = readSettings(settingsPath);

  assert.deepEqual(read, input);
  // The nested parent directory should have been created.
  assert.ok(fs.existsSync(settingsPath), 'settings file should exist on disk');

  fs.rmSync(dir, { recursive: true, force: true });
});

test('readSettings returns defaults when the file is missing', () => {
  const dir = makeTmpDir('parse-settings-');
  const settingsPath = path.join(dir, 'does-not-exist.json');

  assert.deepEqual(readSettings(settingsPath), defaultSettings());
  assert.deepEqual(defaultSettings(), { recentProjects: [], lastProject: null });

  fs.rmSync(dir, { recursive: true, force: true });
});

test('readSettings returns defaults when the file is corrupt', () => {
  const dir = makeTmpDir('parse-settings-');
  const settingsPath = path.join(dir, 'settings.json');
  fs.writeFileSync(settingsPath, '{ this is not valid json ]', 'utf8');

  assert.deepEqual(readSettings(settingsPath), defaultSettings());

  fs.rmSync(dir, { recursive: true, force: true });
});

test('readSettings coerces a partial/wrong-shaped object into defaults', () => {
  const dir = makeTmpDir('parse-settings-');
  const settingsPath = path.join(dir, 'settings.json');
  // recentProjects wrong type; lastProject a number; extra junk key.
  fs.writeFileSync(
    settingsPath,
    JSON.stringify({ recentProjects: 'nope', lastProject: 42, junk: true }),
    'utf8'
  );

  assert.deepEqual(readSettings(settingsPath), defaultSettings());

  fs.rmSync(dir, { recursive: true, force: true });
});

test('addRecentProject prepends, sets lastProject, and dedups', () => {
  let settings = defaultSettings();

  settings = addRecentProject(settings, '/proj/alpha');
  assert.deepEqual(settings.recentProjects, ['/proj/alpha']);
  assert.equal(settings.lastProject, '/proj/alpha');

  settings = addRecentProject(settings, '/proj/beta');
  assert.deepEqual(settings.recentProjects, ['/proj/beta', '/proj/alpha']);
  assert.equal(settings.lastProject, '/proj/beta');

  // Re-adding an existing project moves it to the front without duplicating.
  settings = addRecentProject(settings, '/proj/alpha');
  assert.deepEqual(settings.recentProjects, ['/proj/alpha', '/proj/beta']);
  assert.equal(settings.lastProject, '/proj/alpha');
});

test('addRecentProject caps the recent list at RECENT_PROJECTS_CAP', () => {
  let settings = defaultSettings();

  for (let i = 0; i < RECENT_PROJECTS_CAP + 5; i += 1) {
    settings = addRecentProject(settings, `/proj/${i}`);
  }

  assert.equal(settings.recentProjects.length, RECENT_PROJECTS_CAP);
  // Most recent addition is at the front; oldest ones are dropped.
  assert.equal(settings.recentProjects[0], `/proj/${RECENT_PROJECTS_CAP + 4}`);
  assert.equal(settings.lastProject, `/proj/${RECENT_PROJECTS_CAP + 4}`);
  assert.ok(!settings.recentProjects.includes('/proj/0'), 'oldest entry dropped');
});

test('addRecentProject ignores empty/non-string paths', () => {
  const settings = addRecentProject(defaultSettings(), '');
  assert.deepEqual(settings, defaultSettings());
});

test('addRecentProject normalizes paths so trailing-slash variants dedup', () => {
  let settings = defaultSettings();

  settings = addRecentProject(settings, '/foo');
  assert.deepEqual(settings.recentProjects, ['/foo']);
  assert.equal(settings.lastProject, '/foo');

  // Same directory, trailing slash: should collapse to the single normalized
  // entry rather than duplicating.
  settings = addRecentProject(settings, '/foo/');
  assert.deepEqual(settings.recentProjects, ['/foo']);
  assert.equal(settings.lastProject, '/foo');
  assert.equal(settings.recentProjects.length, 1);
});

test('addRecentProject stores a resolved/normalized path, not the raw input', () => {
  const settings = addRecentProject(defaultSettings(), '/foo/bar/../baz/');

  assert.deepEqual(settings.recentProjects, [path.resolve('/foo/bar/../baz/')]);
  assert.equal(settings.recentProjects[0], '/foo/baz');
  assert.equal(settings.lastProject, '/foo/baz');
});

test('removeRecentProject drops the entry and resets lastProject when needed', () => {
  let settings = defaultSettings();
  settings = addRecentProject(settings, '/proj/a');
  settings = addRecentProject(settings, '/proj/b');
  settings = addRecentProject(settings, '/proj/c');
  // recentProjects: [c, b, a], lastProject: c

  const afterRemoveC = removeRecentProject(settings, '/proj/c');
  assert.deepEqual(afterRemoveC.recentProjects, ['/proj/b', '/proj/a']);
  // lastProject was the removed one, so it falls back to the new front.
  assert.equal(afterRemoveC.lastProject, '/proj/b');

  // Removing a non-lastProject entry leaves lastProject untouched.
  const afterRemoveA = removeRecentProject(settings, '/proj/a');
  assert.deepEqual(afterRemoveA.recentProjects, ['/proj/c', '/proj/b']);
  assert.equal(afterRemoveA.lastProject, '/proj/c');
});

test('removeRecentProject resets lastProject to null when list empties', () => {
  let settings = addRecentProject(defaultSettings(), '/proj/only');
  settings = removeRecentProject(settings, '/proj/only');

  assert.deepEqual(settings.recentProjects, []);
  assert.equal(settings.lastProject, null);
});

test('isValidProjectDir is true for an existing directory, false otherwise', () => {
  const dir = makeTmpDir('parse-projdir-');

  assert.equal(isValidProjectDir(dir), true);
  assert.equal(isValidProjectDir(path.join(dir, 'missing')), false);
  assert.equal(isValidProjectDir(''), false);
  assert.equal(isValidProjectDir(null), false);

  // A file path is not a valid project directory.
  const filePath = path.join(dir, 'a-file.txt');
  fs.writeFileSync(filePath, 'x', 'utf8');
  assert.equal(isValidProjectDir(filePath), false);

  fs.rmSync(dir, { recursive: true, force: true });
});

test('hasProjectJson distinguishes existing projects from fresh dirs', () => {
  const dir = makeTmpDir('parse-projdir-');

  // Fresh dir: valid target, but no manifest yet.
  assert.equal(isValidProjectDir(dir), true);
  assert.equal(hasProjectJson(dir), false);

  // Add the manifest -> now it reads as an existing project.
  fs.writeFileSync(path.join(dir, PROJECT_MANIFEST), '{}', 'utf8');
  assert.equal(hasProjectJson(dir), true);

  assert.equal(hasProjectJson(path.join(dir, 'missing')), false);
  assert.equal(hasProjectJson(''), false);

  fs.rmSync(dir, { recursive: true, force: true });
});
