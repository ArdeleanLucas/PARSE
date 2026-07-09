'use strict';

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const net = require('node:net');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  createBackendSupervisor,
  pickFreePort,
  HEALTH_PATH,
} = require('../backend-supervisor');

// Per-test timeout for anything that spawns a child or polls a stub. Any test
// that hangs (e.g. a never-torn-down child keeping the event loop alive, or a
// supervisor waiting out its default 30s readiness timeout) fails fast here
// instead of stacking up toward the 5-minute CI job timeout.
const SPAWN_TEST_TIMEOUT_MS = 15000;

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

// After stop() kills the child, the OS releases the listening port
// asynchronously (SIGTERM -> process exit -> socket teardown is not
// synchronous). On Linux this lag is occasionally long enough that a single
// immediate isPortListening() check still observes the port as open, even
// though the backend is genuinely gone. Poll instead of checking once so the
// assertion tolerates that lag without weakening what it proves: the port
// must still end up closed within a bounded window after stop().
async function waitForPortClosed(port, timeoutMs = 3000) {
  const pollIntervalMs = 100;
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const listening = await isPortListening(port);
    if (!listening) {
      return true;
    }
    if (Date.now() >= deadline) {
      return false;
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }
}

// A tiny stub backend that can flip its /api/health response at runtime.
function startStubHealthServer({ initialStatus = 404 } = {}) {
  const state = { status: initialStatus };

  const server = http.createServer((req, res) => {
    if (req.url === HEALTH_PATH && state.status === 200) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{"status":"ok"}');
      return;
    }
    res.writeHead(state.status);
    res.end();
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({
        port,
        setStatus(status) {
          state.status = status;
        },
        close() {
          return new Promise((r) => server.close(() => r()));
        },
      });
    });
  });
}

test('pickFreePort returns a usable integer port on 127.0.0.1', async () => {
  const port = await pickFreePort();
  assert.ok(Number.isInteger(port), 'port should be an integer');
  assert.ok(port > 0 && port < 65536, 'port should be in the valid range');

  // The port should be free/usable: we can bind to it right after.
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      server.close(() => resolve());
    });
  });
});

test(
  'waitForReady resolves once the stub starts answering /api/health with 200',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const stub = await startStubHealthServer({ initialStatus: 404 });
    // Guarantee the stub server is closed even if an assertion below throws —
    // an open server keeps the event loop alive and hangs the whole suite.
    t.after(() => stub.close());

    const supervisor = createBackendSupervisor({
      pollIntervalMs: 100,
      readinessTimeoutMs: 5000,
    });

    // Flip to healthy after ~1s; waitForReady must wait, then resolve.
    const flipTimer = setTimeout(() => stub.setStatus(200), 1000);
    t.after(() => clearTimeout(flipTimer));

    const started = Date.now();
    await supervisor.waitForReady(stub.port);
    const elapsed = Date.now() - started;

    clearTimeout(flipTimer);
    assert.ok(elapsed >= 900, `should have waited for the flip (waited ${elapsed}ms)`);
  }
);

test(
  'waitForReady rejects on timeout when the stub never returns 200',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const stub = await startStubHealthServer({ initialStatus: 404 });
    t.after(() => stub.close());

    const supervisor = createBackendSupervisor({
      pollIntervalMs: 100,
      readinessTimeoutMs: 500,
    });

    await assert.rejects(
      () => supervisor.waitForReady(stub.port),
      /did not become ready/
    );
  }
);

test('stop() on a never-started supervisor is a no-op', async () => {
  const supervisor = createBackendSupervisor({});
  await supervisor.stop();
  // Second call must also be safe (idempotent).
  await supervisor.stop();
  assert.equal(supervisor.isRunning, false);
});

test(
  'start() resolves with the right url and stop() terminates the backend',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    // A tiny fake backend: a Node http server that serves /api/health with 200.
    // It binds the port the supervisor assigns via PARSE_API_PORT, exactly like
    // the real shell<->backend contract.
    const inlineServer = [
      'const http=require("http");',
      'const port=Number(process.env.PARSE_API_PORT);',
      'http.createServer((req,res)=>{',
      '  if(req.url==="/api/health"){res.writeHead(200);res.end("{\\"status\\":\\"ok\\"}");return;}',
      '  res.writeHead(404);res.end();',
      '}).listen(port,"127.0.0.1");',
    ].join('');

    const supervisor = createBackendSupervisor({
      backendCommand: `node -e '${inlineServer}'`,
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    // Belt-and-suspenders teardown: even if an assertion throws before the
    // explicit stop() below, tear the child down so it can't keep the event
    // loop alive and hang the suite. stop() is idempotent.
    t.after(() => supervisor.stop());

    const result = await supervisor.start();

    assert.ok(result.url.startsWith('http://127.0.0.1:'), 'url should be loopback');
    assert.equal(result.url, `http://127.0.0.1:${result.port}/`);
    assert.equal(supervisor.isReady, true);

    // The backend must actually be listening on the assigned port while up.
    assert.equal(await isPortListening(result.port), true, 'backend should be listening');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);

    // The backend bound the supervisor-assigned port; it must become free
    // shortly after stop() (poll to tolerate OS-level socket teardown lag).
    const closed = await waitForPortClosed(result.port);
    assert.equal(closed, true, 'backend port should be closed after stop()');
  }
);

// Write a tiny executable "backend" (a node script with a shebang, chmod +x) to
// a temp dir. This stands in for the frozen `parse-backend` binary: the
// supervisor spawns it as a DIRECT executable (no shell, no command string).
function writeStubExecutable() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'parse-frozen-'));
  const exePath = path.join(dir, 'parse-backend');
  const nodeBin = process.execPath;

  const script = [
    `#!${nodeBin}`,
    'const http=require("http");',
    'const port=Number(process.env.PARSE_API_PORT);',
    'http.createServer((req,res)=>{',
    '  if(req.url==="/api/health"){res.writeHead(200);res.end("{\\"status\\":\\"ok\\"}");return;}',
    '  res.writeHead(404);res.end();',
    '}).listen(port,"127.0.0.1");',
    '',
  ].join('\n');

  fs.writeFileSync(exePath, script, { mode: 0o755 });
  return { dir, exePath };
}

test(
  'start() can spawn a DIRECT executable (packaged form) and stop() terminates it',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const { dir, exePath } = writeStubExecutable();
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));

    const supervisor = createBackendSupervisor({
      // No backendCommand: exercise the executable + args path exclusively.
      backendExecutable: exePath,
      backendArgs: [],
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    const result = await supervisor.start();

    assert.ok(result.url.startsWith('http://127.0.0.1:'), 'url should be loopback');
    assert.equal(result.url, `http://127.0.0.1:${result.port}/`);
    assert.equal(supervisor.isReady, true);
    assert.equal(await isPortListening(result.port), true, 'executable backend should be listening');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);

    const closed = await waitForPortClosed(result.port);
    assert.equal(closed, true, 'executable backend port should be closed after stop()');
  }
);

test(
  'start() fails loudly when the packaged executable is missing (no python fallback)',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    const missing = path.join(os.tmpdir(), 'parse-frozen-missing', 'parse-backend');

    const supervisor = createBackendSupervisor({
      backendExecutable: missing,
      backendArgs: [],
      pollIntervalMs: 100,
      readinessTimeoutMs: 2000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    await assert.rejects(
      () => supervisor.start(),
      /Frozen PARSE backend is missing or not executable/
    );
    assert.equal(supervisor.isRunning, false);
  }
);

test(
  'packaged mode with backendCommand:null + a valid executable spawns the exe (no python fallback)',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    // Mirror exactly what main.js passes when packaged: backendCommand is null,
    // and the frozen executable is the only spawn source. This proves the null
    // command never triggers a `python` fallback when an executable is present.
    const { dir, exePath } = writeStubExecutable();
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));

    const supervisor = createBackendSupervisor({
      backendCommand: null,
      backendExecutable: exePath,
      backendArgs: [],
      pollIntervalMs: 100,
      readinessTimeoutMs: 8000,
      shutdownTimeoutMs: 3000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    const result = await supervisor.start();
    assert.equal(supervisor.isReady, true);
    assert.equal(await isPortListening(result.port), true, 'frozen exe should be listening');

    await supervisor.stop();
    assert.equal(supervisor.isRunning, false);
  }
);

test(
  'packaged mode with backendCommand:null + a missing executable fails loudly (no python fallback)',
  { timeout: SPAWN_TEST_TIMEOUT_MS },
  async (t) => {
    // The dangerous case: packaged, null command, and the frozen binary absent.
    // The supervisor must throw the missing-exe guard rather than quietly
    // spawning `python`.
    const missing = path.join(os.tmpdir(), 'parse-frozen-null-cmd-missing', 'parse-backend');

    const supervisor = createBackendSupervisor({
      backendCommand: null,
      backendExecutable: missing,
      backendArgs: [],
      pollIntervalMs: 100,
      readinessTimeoutMs: 2000,
      onLog: () => {},
    });
    t.after(() => supervisor.stop());

    await assert.rejects(
      () => supervisor.start(),
      /Frozen PARSE backend is missing or not executable/
    );
    assert.equal(supervisor.isRunning, false);
  }
);
