'use strict';

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const {
  resolvePackedBackendExe,
  frozenBackendExeName,
  FROZEN_BACKEND_DIR,
} = require('../afterPack');

test('frozenBackendExeName appends .exe only on win32', () => {
  assert.equal(frozenBackendExeName('darwin'), 'parse-backend');
  assert.equal(frozenBackendExeName('mac'), 'parse-backend');
  assert.equal(frozenBackendExeName('linux'), 'parse-backend');
  assert.equal(frozenBackendExeName('win32'), 'parse-backend.exe');
});

test('resolvePackedBackendExe builds the macOS .app Resources/backend layout', () => {
  // Must match electron-builder.yml `extraResources: to: backend` +
  // backend-launcher.js runtime resolution
  //   <resourcesPath>/backend/parse-backend/parse-backend
  const exePath = resolvePackedBackendExe({
    platformName: 'mac',
    appOutDir: '/out/mac-arm64',
    productFilename: 'PARSE',
  });

  assert.equal(
    exePath,
    path.join(
      '/out/mac-arm64',
      'PARSE.app',
      'Contents',
      'Resources',
      'backend',
      FROZEN_BACKEND_DIR,
      'parse-backend'
    )
  );
  // The tail must match what backend-launcher resolves at runtime.
  assert.ok(exePath.endsWith(path.join('backend', 'parse-backend', 'parse-backend')));
});

test('resolvePackedBackendExe honors the productFilename for the .app bundle name', () => {
  const exePath = resolvePackedBackendExe({
    platformName: 'darwin',
    appOutDir: '/out/mac-arm64',
    productFilename: 'PARSE Desktop',
  });
  assert.ok(exePath.includes(path.join('/out/mac-arm64', 'PARSE Desktop.app', 'Contents', 'Resources')));
});

test('resolvePackedBackendExe builds the non-mac resources/backend layout', () => {
  const exePath = resolvePackedBackendExe({
    platformName: 'linux',
    appOutDir: '/out/linux-unpacked',
    productFilename: 'PARSE',
  });

  assert.equal(
    exePath,
    path.join('/out/linux-unpacked', 'resources', 'backend', FROZEN_BACKEND_DIR, 'parse-backend')
  );
});

test('resolvePackedBackendExe uses parse-backend.exe on win32', () => {
  const exePath = resolvePackedBackendExe({
    platformName: 'win32',
    appOutDir: 'C:\\out\\win-unpacked',
    productFilename: 'PARSE',
  });
  assert.ok(exePath.endsWith('parse-backend.exe'), `expected .exe suffix, got ${exePath}`);
  assert.ok(exePath.includes(path.join('resources', 'backend', FROZEN_BACKEND_DIR)));
});
