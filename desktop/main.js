'use strict';

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { app, BrowserWindow, ipcMain, shell } = require('electron');

const { createBackendSupervisor } = require('./backend-supervisor');

const DEFAULT_APP_URL = 'http://127.0.0.1:5173/';

let mainWindow = null;
let backendProcess = null;

// Desktop-runtime supervisor state (only used when PARSE_DESKTOP === '1').
let supervisor = null;
let supervisorUrl = null;
let backendLogStream = null;

function isDesktopRuntime() {
  return process.env.PARSE_DESKTOP === '1';
}

function getAppUrl() {
  // In desktop-runtime mode the supervisor decides the URL (ephemeral port).
  if (supervisorUrl) {
    return supervisorUrl;
  }
  return process.env.PARSE_APP_URL || DEFAULT_APP_URL;
}

function getBackendCwd() {
  return process.env.PARSE_PROJECT_ROOT || path.resolve(__dirname, '..');
}

function getBackendCommand() {
  if (process.env.PARSE_BACKEND_CMD) {
    return process.env.PARSE_BACKEND_CMD;
  }

  return process.platform === 'win32'
    ? 'python python/server.py'
    : 'python3 python/server.py';
}

function shouldAutoLaunchBackend() {
  return process.env.PARSE_AUTO_BACKEND === '1';
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function isAllowedAppNavigation(targetUrl) {
  try {
    const configured = new URL(getAppUrl());
    const requested = new URL(targetUrl);
    return requested.origin === configured.origin;
  } catch (error) {
    return false;
  }
}

function buildLoadFailurePage(url, errorMessage) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PARSE Desktop Shell</title>
  <style>
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0b1320;
      color: #d7e3ff;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
    }
    .card {
      width: min(760px, 100%);
      background: #121d30;
      border: 1px solid #294066;
      border-radius: 14px;
      padding: 24px;
      box-sizing: border-box;
    }
    h1 { margin-top: 0; }
    code {
      display: block;
      margin: 8px 0;
      padding: 10px;
      border-radius: 8px;
      background: #0a101b;
      border: 1px solid #233755;
      overflow-wrap: anywhere;
    }
    ul { line-height: 1.45; }
  </style>
</head>
<body>
  <div class="card">
    <h1>PARSE desktop shell is running</h1>
    <p>But it could not load the target app URL:</p>
    <code>${escapeHtml(url)}</code>
    <p><strong>Error:</strong> ${escapeHtml(errorMessage)}</p>
    <ul>
      <li>For the current React UI, start the PARSE backend and Vite first, then set <code>PARSE_APP_URL</code> to <code>http://127.0.0.1:5173/</code> or <code>/compare</code>.</li>
      <li>If you have already run <code>npm run build</code>, you can point <code>PARSE_APP_URL</code> to <code>http://127.0.0.1:8766/</code> or <code>/compare</code> to use the Python-served built UI.</li>
      <li>If your server uses a different host/port/path, set <code>PARSE_APP_URL</code> before launch.</li>
      <li>This is scaffold behavior only; production packaging and backend supervision are not wired yet.</li>
    </ul>
  </div>
</body>
</html>`;
}

function buildSplashPage(message) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PARSE Desktop</title>
  <style>
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0b1320;
      color: #d7e3ff;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
    }
    .card {
      text-align: center;
    }
    h1 { margin: 0 0 12px; font-size: 20px; }
    p { margin: 0; opacity: 0.8; }
    .spinner {
      margin: 24px auto 0;
      width: 32px;
      height: 32px;
      border: 3px solid #294066;
      border-top-color: #6ea8ff;
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <h1>Starting PARSE</h1>
    <p>${escapeHtml(message)}</p>
    <div class="spinner"></div>
  </div>
</body>
</html>`;
}

function buildBackendFailurePage(errorMessage) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PARSE Desktop</title>
  <style>
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0b1320;
      color: #d7e3ff;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
    }
    .card {
      width: min(760px, 100%);
      background: #121d30;
      border: 1px solid #294066;
      border-radius: 14px;
      padding: 24px;
      box-sizing: border-box;
    }
    h1 { margin-top: 0; }
    code {
      display: block;
      margin: 8px 0;
      padding: 10px;
      border-radius: 8px;
      background: #0a101b;
      border: 1px solid #233755;
      overflow-wrap: anywhere;
    }
    button {
      margin-top: 12px;
      padding: 10px 18px;
      font-size: 15px;
      color: #0b1320;
      background: #6ea8ff;
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    button:hover { background: #8bbcff; }
  </style>
</head>
<body>
  <div class="card">
    <h1>PARSE backend could not start</h1>
    <p>The desktop shell is running, but the local PARSE backend did not come up.</p>
    <p><strong>Error:</strong> ${escapeHtml(errorMessage)}</p>
    <code>Check the backend log at userData/logs/backend.log for details.</code>
    <button onclick="window.parseDesktop && window.parseDesktop.retryBackend && window.parseDesktop.retryBackend()">Retry</button>
  </div>
</body>
</html>`;
}

function renderHtml(html) {
  if (!mainWindow) {
    return Promise.resolve();
  }
  return mainWindow
    .loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
    .catch(() => {
      // Ignore fallback rendering failures.
    });
}

function getBackendLogPath() {
  return path.join(app.getPath('userData'), 'logs', 'backend.log');
}

function openBackendLogStream() {
  if (backendLogStream) {
    return backendLogStream;
  }
  try {
    const logPath = getBackendLogPath();
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    backendLogStream = fs.createWriteStream(logPath, { flags: 'a' });
  } catch (error) {
    console.error(`[parse-desktop] could not open backend log: ${error.message}`);
    backendLogStream = null;
  }
  return backendLogStream;
}

function desktopBackendLog(chunk, stream) {
  const target = stream === 'stderr' ? process.stderr : process.stdout;
  target.write(`[parse-backend] ${chunk}`);

  const logStream = openBackendLogStream();
  if (logStream) {
    logStream.write(chunk);
  }
}

async function startSupervisedBackend() {
  if (!supervisor) {
    supervisor = createBackendSupervisor({
      projectRoot: getBackendCwd(),
      userDataRoot: app.getPath('userData'),
      backendCommand: getBackendCommand(),
      onLog: desktopBackendLog,
    });

    supervisor.onExit(({ code, signal }) => {
      // Backend died after being ready: show recovery UI.
      supervisorUrl = null;
      const label = `Backend exited unexpectedly (code=${code}, signal=${signal || 'none'}).`;
      void renderHtml(buildBackendFailurePage(label));
    });
  }

  const { url } = await supervisor.start();
  supervisorUrl = url;
  return url;
}

async function launchDesktopRuntime() {
  await renderHtml(buildSplashPage('Launching the local PARSE backend...'));

  try {
    const url = await startSupervisedBackend();
    if (mainWindow) {
      await mainWindow.loadURL(url);
    }
  } catch (error) {
    console.error(`[parse-desktop] backend supervision failed: ${error.message}`);
    await renderHtml(buildBackendFailurePage(error.message));
  }
}

function startBackendProcess() {
  if (!shouldAutoLaunchBackend() || backendProcess) {
    return;
  }

  const command = getBackendCommand();
  const cwd = getBackendCwd();

  console.log(`[parse-desktop] starting backend: ${command} (cwd=${cwd})`);

  backendProcess = spawn(command, {
    cwd,
    shell: true,
    env: process.env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  if (backendProcess.stdout) {
    backendProcess.stdout.on('data', (chunk) => {
      process.stdout.write(`[parse-backend] ${chunk}`);
    });
  }

  if (backendProcess.stderr) {
    backendProcess.stderr.on('data', (chunk) => {
      process.stderr.write(`[parse-backend] ${chunk}`);
    });
  }

  backendProcess.on('error', (error) => {
    console.error(`[parse-desktop] backend launch failed: ${error.message}`);
    backendProcess = null;
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`[parse-desktop] backend exited (code=${code}, signal=${signal || 'none'})`);
    backendProcess = null;
  });
}

function stopBackendProcess() {
  if (!backendProcess) {
    return;
  }

  const pid = backendProcess.pid;

  if (process.platform === 'win32' && pid) {
    spawn('taskkill', ['/pid', String(pid), '/f', '/t'], {
      windowsHide: true,
      stdio: 'ignore',
    });
  } else {
    backendProcess.kill('SIGTERM');
  }

  backendProcess = null;
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1100,
    minHeight: 680,
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (isAllowedAppNavigation(url) || url.startsWith('data:')) {
      return;
    }

    event.preventDefault();
    void shell.openExternal(url);
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedUrl, isMainFrame) => {
    if (!isMainFrame || !mainWindow) {
      return;
    }

    const failedUrl = validatedUrl || getAppUrl();
    const errorLabel = `${errorDescription} (${errorCode})`;
    const html = buildLoadFailurePage(failedUrl, errorLabel);

    mainWindow
      .loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
      .catch(() => {
        // Ignore fallback rendering failures in this scaffold.
      });
  });

  if (isDesktopRuntime()) {
    // Desktop-runtime mode: show a splash, supervise the backend, then load its
    // ephemeral-port URL once the /api/health handshake succeeds.
    void launchDesktopRuntime();
    return;
  }

  // Dev / scaffold mode: preserve the existing behavior exactly — attach to the
  // configured PARSE_APP_URL (Vite dev target or built-UI target).
  const appUrl = getAppUrl();
  mainWindow.loadURL(appUrl).catch((error) => {
    console.error(`[parse-desktop] failed to load ${appUrl}: ${error.message}`);
  });
}

ipcMain.handle('parse-desktop:get-config', () => {
  return {
    appUrl: getAppUrl(),
    autoLaunchBackend: shouldAutoLaunchBackend(),
    backendCommand: getBackendCommand(),
    backendCwd: getBackendCwd(),
    platform: process.platform,
    isPackaged: app.isPackaged,
  };
});

ipcMain.handle('parse-desktop:ping', () => {
  return 'pong';
});

// Retry affordance for the recovery page: re-run supervised backend startup.
ipcMain.handle('parse-desktop:retry-backend', async () => {
  if (!isDesktopRuntime()) {
    return { ok: false, reason: 'not-desktop-runtime' };
  }

  await renderHtml(buildSplashPage('Restarting the local PARSE backend...'));

  try {
    supervisorUrl = null;
    const url = supervisor ? await supervisor.restart() : await startSupervisedBackend();
    const finalUrl = typeof url === 'string' ? url : url && url.url;
    supervisorUrl = finalUrl || supervisorUrl;
    if (mainWindow && supervisorUrl) {
      await mainWindow.loadURL(supervisorUrl);
    }
    return { ok: true, url: supervisorUrl };
  } catch (error) {
    await renderHtml(buildBackendFailurePage(error.message));
    return { ok: false, reason: error.message };
  }
});

async function shutdownBackend() {
  if (supervisor) {
    try {
      await supervisor.stop();
    } catch (error) {
      console.error(`[parse-desktop] supervisor stop failed: ${error.message}`);
    }
  } else {
    stopBackendProcess();
  }

  if (backendLogStream) {
    backendLogStream.end();
    backendLogStream = null;
  }
}

app.whenReady().then(() => {
  // In desktop-runtime mode the supervisor owns the backend lifecycle; the
  // legacy PARSE_AUTO_BACKEND launcher only runs in dev/scaffold mode.
  if (!isDesktopRuntime()) {
    startBackendProcess();
  }
  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

let quitting = false;

app.on('before-quit', (event) => {
  if (quitting) {
    return;
  }

  event.preventDefault();
  quitting = true;

  shutdownBackend().finally(() => {
    app.quit();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
