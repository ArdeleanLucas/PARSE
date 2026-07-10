'use strict';

// Backend supervisor for the PARSE desktop shell.
//
// This module owns the lifecycle of the PARSE Python backend when running in
// desktop-runtime mode: pick an ephemeral loopback port, spawn the backend,
// health-check it, watch for unexpected exits, and shut it down cleanly.
//
// It is intentionally free of any `require('electron')` so it can be unit
// tested under plain `node --test`. The Electron shell (main.js) wires it in.

const net = require('net');
const http = require('http');
const fs = require('fs');
const { spawn } = require('child_process');
const { EventEmitter } = require('events');

const DEFAULT_POLL_INTERVAL_MS = 300;
const DEFAULT_READINESS_TIMEOUT_MS = 30000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 5000;
const HEALTH_PATH = '/api/health';

function defaultBackendCommand() {
  return process.platform === 'win32'
    ? 'python python/server.py'
    : 'python3 python/server.py';
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

// Bind a throwaway server to 127.0.0.1:0 so the OS assigns a free port, read it
// back, close the server, and resolve the port number.
function pickFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();

    server.on('error', (error) => {
      reject(error);
    });

    server.listen(0, '127.0.0.1', () => {
      const address = server.address();

      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('Failed to resolve an ephemeral port from the OS.'));
        return;
      }

      const { port } = address;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(port);
      });
    });
  });
}

function probeHealthOnce(port) {
  return new Promise((resolve) => {
    const request = http.request(
      {
        host: '127.0.0.1',
        port,
        path: HEALTH_PATH,
        method: 'GET',
        timeout: 2000,
      },
      (response) => {
        // Drain the body so the socket can be reused/freed.
        response.resume();
        resolve(response.statusCode === 200);
      }
    );

    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });

    request.on('error', () => {
      resolve(false);
    });

    request.end();
  });
}

class BackendSupervisor extends EventEmitter {
  constructor(options = {}) {
    super();

    // The backend can be spawned two ways:
    //   1. Dev / scaffold: a shell command STRING (`python3 python/server.py`),
    //      spawned via `shell: true`. This is `backendCommand`.
    //   2. Packaged: a DIRECT executable path plus argv, spawned WITHOUT a shell
    //      (no `python`). This is `backendExecutable` + `backendArgs`.
    // When `backendExecutable` is set it takes precedence over `backendCommand`.
    this._options = {
      projectRoot: options.projectRoot || process.cwd(),
      userDataRoot: options.userDataRoot || '',
      // Read-only bundled-models root (packaged: `<resourcesPath>/models`).
      // Undefined in dev — the backend registry treats an absent
      // PARSE_BUNDLED_MODELS as "no bundled root", so we omit the env var
      // entirely (never set an empty string) when this is not provided.
      bundledModelsRoot: options.bundledModelsRoot || undefined,
      backendCommand: options.backendCommand || defaultBackendCommand(),
      backendExecutable: options.backendExecutable || null,
      backendArgs: options.backendArgs || [],
      pollIntervalMs: options.pollIntervalMs || DEFAULT_POLL_INTERVAL_MS,
      readinessTimeoutMs: options.readinessTimeoutMs || DEFAULT_READINESS_TIMEOUT_MS,
      shutdownTimeoutMs: options.shutdownTimeoutMs || DEFAULT_SHUTDOWN_TIMEOUT_MS,
      env: options.env || {},
      onLog: options.onLog || null,
    };

    this._child = null;
    this._port = null;
    this._url = null;
    this._ready = false;
    this._stopping = false;
    // True when the child was spawned as a POSIX process-group leader
    // (`detached: true`). This happens only for the dev/shell-spawn form, where
    // the immediate child is a shell wrapper and the real server is its
    // grandchild. `stop()` must signal the whole group (negative pid) so the
    // grandchild dies with it instead of orphaning and holding the port.
    this._spawnedDetached = false;
    // Records the last child exit so late `stop()` calls stay idempotent and
    // waitForReady can react to a child that dies mid-handshake.
    this._lastExit = null;
  }

  get port() {
    return this._port;
  }

  get url() {
    return this._url;
  }

  get isRunning() {
    return Boolean(this._child) && this._lastExit === null;
  }

  get isReady() {
    return this._ready;
  }

  _log(chunk, stream) {
    if (typeof this._options.onLog === 'function') {
      this._options.onLog(chunk, stream);
      return;
    }

    const target = stream === 'stderr' ? process.stderr : process.stdout;
    target.write(`[parse-backend] ${chunk}`);
  }

  // Register an unexpected-exit callback (after the backend was ready).
  onExit(callback) {
    if (typeof callback === 'function') {
      this.on('exit', callback);
    }
    return this;
  }

  // Resolve how to spawn the backend for this run. Returns the `child_process`
  // spawn arguments plus a human-readable description for logs.
  //
  // Packaged: a direct executable + argv, NO shell. The executable is verified
  // to exist first; a missing frozen binary throws a clear error instead of
  // letting spawn fall through to something unexpected.
  //
  // Dev: the shell command string, spawned via `shell: true` (unchanged).
  _resolveSpawn(env) {
    const baseOptions = {
      cwd: this._options.projectRoot,
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    };

    const executable = this._options.backendExecutable;

    if (executable) {
      // Guard: fail loudly if the frozen backend is missing so we never quietly
      // spawn `python` as a fallback.
      try {
        fs.accessSync(executable, fs.constants.X_OK);
      } catch (error) {
        throw new Error(
          `Frozen PARSE backend is missing or not executable at ${executable} ` +
            `(${error.code || error.message}).`
        );
      }

      const args = this._options.backendArgs || [];
      return {
        // Direct frozen executable: a single process, no shell wrapper. Its own
        // SIGTERM already reaches the real server, so we do NOT detach it —
        // `child.kill()` in `stop()` is correct and simplest here.
        spawnArg: { file: executable, args },
        spawnOptions: baseOptions,
        detached: false,
        describe: `${executable} ${args.join(' ')}`.trim(),
      };
    }

    const command = this._options.backendCommand;
    // Dev/shell form: the command runs under a shell (`/bin/sh -c ...`), so the
    // immediate child is the shell and the real server is its grandchild. On
    // POSIX, spawn with `detached: true` so the child becomes a new
    // process-group leader; `stop()` then signals the whole group (negative
    // pid) to kill the grandchild too. Windows uses `taskkill /t` for the tree,
    // so detach is POSIX-only.
    const detached = process.platform !== 'win32';
    return {
      spawnArg: { file: command, args: [] },
      spawnOptions: { ...baseOptions, shell: true, detached },
      detached,
      describe: command,
    };
  }

  async start() {
    if (this._child) {
      throw new Error('Backend supervisor is already started.');
    }

    this._stopping = false;
    this._ready = false;
    this._lastExit = null;

    const port = await pickFreePort();
    this._port = port;
    this._url = `http://127.0.0.1:${port}/`;

    const env = {
      ...process.env,
      PARSE_DESKTOP: '1',
      PARSE_API_PORT: String(port),
      PARSE_HOST: '127.0.0.1',
      PARSE_WORKSPACE_ROOT: this._options.projectRoot,
      PARSE_USER_DATA: this._options.userDataRoot,
      ...this._options.env,
    };

    // Point the backend's model registry at the read-only bundled models root
    // ONLY when we actually have one (packaged builds). The registry treats an
    // unset/blank PARSE_BUNDLED_MODELS as "no bundled root", so in dev we omit
    // the key entirely rather than setting an empty string — mirroring how
    // main.js leaves it undefined when not packaged. Set AFTER the spread so a
    // caller-provided `env` cannot accidentally reintroduce a blank value.
    if (this._options.bundledModelsRoot) {
      env.PARSE_BUNDLED_MODELS = this._options.bundledModelsRoot;
    }

    // Choose the spawn form: a direct frozen executable (packaged) or the dev
    // shell command string. `_resolveSpawn` also guards a missing/unusable
    // frozen executable so a failed packaged launch never silently falls back
    // to spawning `python`.
    const { spawnArg, spawnOptions, detached, describe } = this._resolveSpawn(env);

    this._log(`starting backend on 127.0.0.1:${port}: ${describe}\n`, 'stdout');

    const child = spawn(spawnArg.file, spawnArg.args, spawnOptions);

    // Record whether this child leads its own process group so `stop()` can
    // signal the group (negative pid) instead of just the shell wrapper.
    // We intentionally do NOT call `child.unref()` — piped stdio still works
    // when detached, and we want to keep managing/awaiting this child.
    this._spawnedDetached = Boolean(detached);
    this._child = child;

    if (child.stdout) {
      child.stdout.on('data', (chunk) => {
        this._log(chunk, 'stdout');
      });
    }

    if (child.stderr) {
      child.stderr.on('data', (chunk) => {
        this._log(chunk, 'stderr');
      });
    }

    child.on('error', (error) => {
      this._log(`backend launch failed: ${error.message}\n`, 'stderr');
    });

    child.on('exit', (code, signal) => {
      this._handleChildExit(code, signal);
    });

    try {
      await this.waitForReady(port);
    } catch (error) {
      // Health handshake failed (timeout or early exit). Tear down the child
      // so a failed start does not leave an orphaned process behind.
      await this.stop();
      throw error;
    }

    this._ready = true;
    return { port, url: this._url };
  }

  _handleChildExit(code, signal) {
    const wasReady = this._ready;
    const stopping = this._stopping;

    this._lastExit = { code, signal };
    this._child = null;
    this._ready = false;

    this._log(
      `backend exited (code=${code}, signal=${signal || 'none'})\n`,
      'stdout'
    );

    // Only surface an unexpected-exit event when the backend had already become
    // ready and we were not the ones asking it to stop.
    if (wasReady && !stopping) {
      this.emit('exit', { code, signal });
    }
  }

  // Poll GET /api/health until a 200 or timeout. Rejects immediately if the
  // child exits before becoming ready.
  waitForReady(port) {
    const targetPort = port || this._port;
    const deadline = Date.now() + this._options.readinessTimeoutMs;

    return new Promise((resolve, reject) => {
      const attempt = async () => {
        if (this._lastExit) {
          const { code, signal } = this._lastExit;
          reject(
            new Error(
              `Backend process exited before becoming ready (code=${code}, signal=${signal || 'none'}).`
            )
          );
          return;
        }

        const healthy = await probeHealthOnce(targetPort);

        if (healthy) {
          resolve();
          return;
        }

        if (Date.now() >= deadline) {
          reject(
            new Error(
              `Backend did not become ready within ${this._options.readinessTimeoutMs}ms ` +
                `(polling http://127.0.0.1:${targetPort}${HEALTH_PATH}).`
            )
          );
          return;
        }

        await delay(this._options.pollIntervalMs);
        attempt();
      };

      attempt();
    });
  }

  // Send `signal` to the backend. For a detached POSIX child (dev/shell form)
  // this targets the whole process GROUP via a negative pid, so the shell
  // wrapper AND its grandchild server both receive the signal. For the direct
  // executable path it targets just the single child. `ESRCH` (no such
  // process) means the target is already gone — treat as success.
  _signalBackend(child, pid, signal) {
    if (this._spawnedDetached && process.platform !== 'win32' && pid) {
      try {
        process.kill(-pid, signal);
        return;
      } catch (error) {
        if (error.code === 'ESRCH') {
          return; // Group already gone.
        }
        this._log(`process-group ${signal} failed: ${error.message}\n`, 'stderr');
        // Fall through to a plain child.kill as a best effort.
      }
    }

    try {
      child.kill(signal);
    } catch (error) {
      if (error.code === 'ESRCH') {
        return;
      }
      this._log(`${signal} failed: ${error.message}\n`, 'stderr');
    }
  }

  // Graceful shutdown: SIGTERM (taskkill on win32; process-group signal for
  // detached dev/shell backends), wait, then SIGKILL.
  // Idempotent: safe to call when never started or already stopped.
  async stop() {
    const child = this._child;

    if (!child) {
      this._ready = false;
      return;
    }

    this._stopping = true;
    this._ready = false;

    const pid = child.pid;

    const exited = new Promise((resolve) => {
      child.once('exit', () => resolve());
    });

    if (process.platform === 'win32' && pid) {
      spawn('taskkill', ['/pid', String(pid), '/f', '/t'], {
        windowsHide: true,
        stdio: 'ignore',
      });
    } else {
      this._signalBackend(child, pid, 'SIGTERM');
    }

    const timedOut = await Promise.race([
      exited.then(() => false),
      delay(this._options.shutdownTimeoutMs).then(() => true),
    ]);

    if (timedOut && this._child) {
      this._log('graceful shutdown timed out; sending SIGKILL\n', 'stderr');
      if (process.platform === 'win32' && pid) {
        spawn('taskkill', ['/pid', String(pid), '/f', '/t'], {
          windowsHide: true,
          stdio: 'ignore',
        });
      } else {
        this._signalBackend(this._child, pid, 'SIGKILL');
      }
      await exited;
    }

    this._child = null;
    this._stopping = false;
    this._spawnedDetached = false;
  }

  async restart() {
    await this.stop();
    return this.start();
  }
}

function createBackendSupervisor(options) {
  return new BackendSupervisor(options);
}

module.exports = {
  createBackendSupervisor,
  BackendSupervisor,
  pickFreePort,
  defaultBackendCommand,
  HEALTH_PATH,
};
