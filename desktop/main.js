'use strict';

const path = require('path');
const { spawn } = require('child_process');
const { app, BrowserWindow, ipcMain, shell } = require('electron');

const DEFAULT_APP_URL = 'http://127.0.0.1:8766/parse.html';

let mainWindow = null;
let backendProcess = null;

function getAppUrl() {
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
      <li>The default desktop shell target still points at <code>http://127.0.0.1:8766/parse.html</code>, which is a legacy fallback path retained only until C7 cleanup.</li>
      <li>If your server uses a different host/port/path, set <code>PARSE_APP_URL</code> before launch.</li>
      <li>This is scaffold behavior only; production packaging and backend supervision are not wired yet.</li>
    </ul>
  </div>
</body>
</html>`;
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
  const appUrl = getAppUrl();

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

    const failedUrl = validatedUrl || appUrl;
    const errorLabel = `${errorDescription} (${errorCode})`;
    const html = buildLoadFailurePage(failedUrl, errorLabel);

    mainWindow
      .loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
      .catch(() => {
        // Ignore fallback rendering failures in this scaffold.
      });
  });

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

app.whenReady().then(() => {
  startBackendProcess();
  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('before-quit', () => {
  stopBackendProcess();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
