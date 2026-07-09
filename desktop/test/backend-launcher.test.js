'use strict';

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const { resolveBackendLauncher } = require('../backend-launcher');

test('resolveBackendLauncher returns the dev shell command when NOT packaged', () => {
  const launcher = resolveBackendLauncher(false, '/does/not/matter', {
    platform: 'darwin',
    env: {},
  });

  assert.equal(launcher.shell, true, 'dev launcher must request a shell');
  assert.equal(
    launcher.command,
    'python3 python/server.py',
    'dev launcher must keep the existing python3 command'
  );
  assert.equal(launcher.executable, undefined, 'dev launcher must not set an executable');
});

test('resolveBackendLauncher returns the win32 dev command when NOT packaged', () => {
  const launcher = resolveBackendLauncher(false, '/x', { platform: 'win32', env: {} });

  assert.equal(launcher.shell, true);
  assert.equal(launcher.command, 'python python/server.py');
});

test('resolveBackendLauncher honors PARSE_BACKEND_CMD override in dev', () => {
  const launcher = resolveBackendLauncher(false, '/x', {
    platform: 'darwin',
    env: { PARSE_BACKEND_CMD: 'my-custom-backend --flag' },
  });

  assert.equal(launcher.shell, true);
  assert.equal(launcher.command, 'my-custom-backend --flag');
});

test('resolveBackendLauncher returns the frozen executable form when packaged', () => {
  const resourcesPath = '/Applications/PARSE.app/Contents/Resources';
  const launcher = resolveBackendLauncher(true, resourcesPath, { platform: 'darwin' });

  const expected = path.join(
    resourcesPath,
    'backend',
    'parse-backend',
    'parse-backend'
  );

  assert.equal(launcher.executable, expected, 'packaged launcher must point at the frozen exe');
  assert.deepEqual(launcher.args, [], 'packaged launcher must pass no args');
  assert.equal(launcher.shell, undefined, 'packaged launcher must NOT request a shell');
  assert.equal(launcher.command, undefined, 'packaged launcher must NOT set a shell command');
});

test('resolveBackendLauncher matches the electron-builder resourcesPath/backend/... layout', () => {
  // Explicitly assert the path segments so a drift in electron-builder.yml's
  // `to: backend` (or the frozen dir/exe name) breaks this test.
  const launcher = resolveBackendLauncher(true, '/RES', { platform: 'darwin' });
  assert.equal(launcher.executable, path.join('/RES', 'backend', 'parse-backend', 'parse-backend'));
});

test('resolveBackendLauncher uses parse-backend.exe on win32 when packaged', () => {
  const launcher = resolveBackendLauncher(true, 'C:\\Res', { platform: 'win32' });
  assert.ok(
    launcher.executable.endsWith('parse-backend.exe'),
    `expected a .exe suffix, got ${launcher.executable}`
  );
});

test('packaged launcher carries no python fallback command (main.js wires backendCommand: null)', () => {
  // main.js computes `backendCommand: launcher.command || null` — so when
  // packaged the supervisor must receive NO python string. Assert the launcher
  // itself never surfaces a python command in packaged mode, on either OS.
  for (const platform of ['darwin', 'win32']) {
    const launcher = resolveBackendLauncher(true, '/RES', { platform });
    assert.equal(launcher.command, undefined, `${platform}: no shell command when packaged`);
    // Mirror the exact expression main.js uses; it must collapse to null.
    assert.equal(launcher.command || null, null, `${platform}: main.js backendCommand resolves to null`);
    assert.ok(launcher.executable, `${platform}: packaged launcher must set an executable`);
    assert.ok(
      !/python/i.test(launcher.executable),
      `${platform}: packaged executable must not be python (${launcher.executable})`
    );
  }
});
