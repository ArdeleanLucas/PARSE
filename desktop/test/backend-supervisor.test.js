'use strict';

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const net = require('node:net');

const {
  createBackendSupervisor,
  pickFreePort,
  HEALTH_PATH,
} = require('../backend-supervisor');

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

test('waitForReady resolves once the stub starts answering /api/health with 200', async () => {
  const stub = await startStubHealthServer({ initialStatus: 404 });
  const supervisor = createBackendSupervisor({
    pollIntervalMs: 100,
    readinessTimeoutMs: 5000,
  });

  // Flip to healthy after ~1s; waitForReady must wait, then resolve.
  const flipTimer = setTimeout(() => stub.setStatus(200), 1000);

  const started = Date.now();
  await supervisor.waitForReady(stub.port);
  const elapsed = Date.now() - started;

  clearTimeout(flipTimer);
  assert.ok(elapsed >= 900, `should have waited for the flip (waited ${elapsed}ms)`);

  await stub.close();
});

test('waitForReady rejects on timeout when the stub never returns 200', async () => {
  const stub = await startStubHealthServer({ initialStatus: 404 });
  const supervisor = createBackendSupervisor({
    pollIntervalMs: 100,
    readinessTimeoutMs: 500,
  });

  await assert.rejects(
    () => supervisor.waitForReady(stub.port),
    /did not become ready/
  );

  await stub.close();
});

test('stop() on a never-started supervisor is a no-op', async () => {
  const supervisor = createBackendSupervisor({});
  await supervisor.stop();
  // Second call must also be safe (idempotent).
  await supervisor.stop();
  assert.equal(supervisor.isRunning, false);
});

test('start() resolves with the right url and stop() terminates the backend', async () => {
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

  const result = await supervisor.start();

  assert.ok(result.url.startsWith('http://127.0.0.1:'), 'url should be loopback');
  assert.equal(result.url, `http://127.0.0.1:${result.port}/`);
  assert.equal(supervisor.isReady, true);

  // The backend must actually be listening on the assigned port while up.
  assert.equal(await isPortListening(result.port), true, 'backend should be listening');

  await supervisor.stop();
  assert.equal(supervisor.isRunning, false);

  // The backend bound the supervisor-assigned port; it must be free now.
  const stillListening = await isPortListening(result.port);
  assert.equal(stillListening, false, 'backend port should be closed after stop()');
});
