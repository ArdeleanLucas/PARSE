'use strict';

// Tests for the bundled read-only IPA model wiring (§9.4 packaging increment):
//   * backend-launcher.js::resolveBundledModelsDir — decides the read-only
//     models dir the backend should scan (packaged only).
//   * backend-supervisor.js — must put PARSE_BUNDLED_MODELS in the spawn env
//     ONLY when a bundledModelsRoot is provided (packaged), and OMIT the key
//     entirely in dev (never an empty string), matching the backend registry's
//     "unset/blank means no bundled root" contract in
//     python/ai/model_registry.py::bundled_models_root.

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const net = require('node:net');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  resolveBundledModelsDir,
  BUNDLED_MODELS_DIR,
} = require('../backend-launcher');
const { createBackendSupervisor } = require('../backend-supervisor');

const SPAWN_TEST_TIMEOUT_MS = 15000;

// ---- resolveBundledModelsDir (pure, no electron) ------------------------- //

test('resolveBundledModelsDir returns <resourcesPath>/models when packaged', () => {
  const resourcesPath = '/Applications/PARSE.app/Contents/Resources';
  const dir = resolveBundledModelsDir(true, resourcesPath);

  assert.equal(
    dir,
    path.join(resourcesPath, BUNDLED_MODELS_DIR),
    'packaged: must point at Resources/models (matches electron-builder to: models)'
  );
  // Mirror the exact path segments so a drift in electron-builder.yml's
  // `to: models` (or the BUNDLED_MODELS_DIR constant) breaks this test.
  assert.equal(dir, path.join(resourcesPath, 'models'));
});

test('resolveBundledModelsDir returns undefined in dev (NOT packaged)', () => {
  const dir = resolveBundledModelsDir(false, '/does/not/matter');
  assert.equal(
    dir,
    undefined,
    'dev: must be undefined so the supervisor omits PARSE_BUNDLED_MODELS entirely'
  );
});

test('resolveBundledModelsDir is undefined in dev even with a resourcesPath present', () => {
  // Being packaged is the ONLY thing that flips the bundled root on. A stray
  // process.resourcesPath in dev must not accidentally enable it.
  const dir = resolveBundledModelsDir(false, '/Applications/PARSE.app/Contents/Resources');
  assert.equal(dir, undefined);
});

// ---- supervisor spawn env: PARSE_BUNDLED_MODELS presence ----------------- //

// Capture the spawned child's env by running a tiny inline node backend that
// echoes whether PARSE_BUNDLED_MODELS is set (and its value) to a file, then
// answers /api/health so the supervisor's readiness handshake completes. This
// mirrors how the existing supervisor tests spawn a real inline node backend
// (start()/stop() with a node -e command) rather than mocking child_process.
function isPortListening(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port }, () => {
      socket.destroy();
      resolve(true);
    });
    socket.on('error', () => resolve(false));
    socket.setTimeout(500, () => {
      socket.destroy();
      resolve(false);
    });
  });
}

// Build an inline node backend command that writes the observed
// PARSE_BUNDLED_MODELS state to `outPath` on boot, then serves /api/health.
function inlineEnvProbeBackend(outPath) {
  const jsonOut = JSON.stringify(outPath);
  return [
    'const http=require("http");',
    'const fs=require("fs");',
    'const has=Object.prototype.hasOwnProperty.call(process.env,"PARSE_BUNDLED_MODELS");',
    'const val=process.env.PARSE_BUNDLED_MODELS;',
    `fs.writeFileSync(${jsonOut}, JSON.stringify({has, val: val===undefined?null:val}));`,
    'const port=Number(process.env.PARSE_API_PORT);',
    'http.createServer((req,res)=>{',
    '  if(req.url==="/api/health"){res.writeHead(200);res.end("{\\"status\\":\\"ok\\"}");return;}',
    '  res.writeHead(404);res.end();',
    '}).listen(port,"127.0.0.1");',
  ].join('');
}

async function readEnvProbe(outPath, deadlineMs = 5000) {
  const deadline = Date.now() + deadlineMs;
  for (;;) {
    if (fs.existsSync(outPath)) {
      const text = fs.readFileSync(outPath, 'utf8');
      if (text) {
        return JSON.parse(text);
      }
    }
    if (Date.now() >= deadline) {
      throw new Error(`env probe file never appeared at ${outPath}`);
    }
    await new Promise((r) => setTimeout(r, 50));
  }
}

test(
  'supervisor sets PARSE_BUNDLED_MODELS in the spawn env when packaged (bundledModelsRoot provided)',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'parse-bundled-env-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const outPath = path.join(dir, 'env-probe.json');

    // The value a packaged main.js would compute from resolveBundledModelsDir.
    const bundledRoot = path.join('/Applications/PARSE.app/Contents/Resources', 'models');

    const supervisor = createBackendSupervisor({
      bundledModelsRoot: bundledRoot,
      backendCommand: `node -e '${inlineEnvProbeBackend(outPath)}'`,
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    const result = await supervisor.start();
    assert.equal(await isPortListening(result.port), true, 'backend should be listening');

    const probe = await readEnvProbe(outPath);
    assert.equal(probe.has, true, 'PARSE_BUNDLED_MODELS must be present in the child env when packaged');
    assert.equal(probe.val, bundledRoot, 'PARSE_BUNDLED_MODELS must carry the bundled models root');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);
  }
);

test(
  'supervisor OMITS PARSE_BUNDLED_MODELS from the spawn env in dev (no bundledModelsRoot)',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'parse-bundled-env-dev-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const outPath = path.join(dir, 'env-probe.json');

    const supervisor = createBackendSupervisor({
      // No bundledModelsRoot: dev/web behavior. The key must be absent entirely,
      // not set to an empty string (the registry treats blank as "no root", but
      // omitting the key is the stronger, documented contract).
      backendCommand: `node -e '${inlineEnvProbeBackend(outPath)}'`,
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    // Ensure a leaked PARSE_BUNDLED_MODELS from the test runner's own env can't
    // mask the omission we're asserting: the supervisor spreads process.env, so
    // clear it here for the duration of this spawn.
    const savedEnv = process.env.PARSE_BUNDLED_MODELS;
    delete process.env.PARSE_BUNDLED_MODELS;
    t.after(() => {
      if (savedEnv !== undefined) {
        process.env.PARSE_BUNDLED_MODELS = savedEnv;
      }
    });

    const result = await supervisor.start();
    assert.equal(await isPortListening(result.port), true, 'backend should be listening');

    const probe = await readEnvProbe(outPath);
    assert.equal(
      probe.has,
      false,
      'PARSE_BUNDLED_MODELS must be omitted entirely (not empty string) in dev'
    );
    assert.equal(probe.val, null, 'dev child must observe no PARSE_BUNDLED_MODELS value');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);
  }
);

test(
  'supervisor does not set PARSE_BUNDLED_MODELS from an empty-string bundledModelsRoot',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    // A blank bundledModelsRoot (e.g. a mis-wired caller) must be treated like
    // dev: omit the key, never spawn with PARSE_BUNDLED_MODELS="". The supervisor
    // guards this with `if (this._options.bundledModelsRoot)` after the spread.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'parse-bundled-env-empty-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const outPath = path.join(dir, 'env-probe.json');

    const supervisor = createBackendSupervisor({
      bundledModelsRoot: '',
      backendCommand: `node -e '${inlineEnvProbeBackend(outPath)}'`,
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    const savedEnv = process.env.PARSE_BUNDLED_MODELS;
    delete process.env.PARSE_BUNDLED_MODELS;
    t.after(() => {
      if (savedEnv !== undefined) {
        process.env.PARSE_BUNDLED_MODELS = savedEnv;
      }
    });

    const result = await supervisor.start();
    const probe = await readEnvProbe(outPath);
    assert.equal(probe.has, false, 'empty bundledModelsRoot must omit the env key, not set ""');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);
  }
);
