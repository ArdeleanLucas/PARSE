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

    this._options = {
      projectRoot: options.projectRoot || process.cwd(),
      userDataRoot: options.userDataRoot || '',
      backendCommand: options.backendCommand || defaultBackendCommand(),
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

    const command = this._options.backendCommand;

    this._log(`starting backend on 127.0.0.1:${port}: ${command}\n`, 'stdout');

    const child = spawn(command, {
      cwd: this._options.projectRoot,
      shell: true,
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

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

  // Graceful shutdown: SIGTERM (taskkill on win32), wait, then SIGKILL.
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
      try {
        child.kill('SIGTERM');
      } catch (error) {
        this._log(`SIGTERM failed: ${error.message}\n`, 'stderr');
      }
    }

    const timedOut = await Promise.race([
      exited.then(() => false),
      delay(this._options.shutdownTimeoutMs).then(() => true),
    ]);

    if (timedOut && this._child) {
      this._log('graceful shutdown timed out; sending SIGKILL\n', 'stderr');
      try {
        this._child.kill('SIGKILL');
      } catch (error) {
        this._log(`SIGKILL failed: ${error.message}\n`, 'stderr');
      }
      await exited;
    }

    this._child = null;
    this._stopping = false;
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
