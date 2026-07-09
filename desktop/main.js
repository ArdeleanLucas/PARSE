'use strict';

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');

const { createBackendSupervisor } = require('./backend-supervisor');
const { resolveBackendLauncher } = require('./backend-launcher');
const projectStore = require('./project-store');

// Resolved project root for desktop-runtime mode (the folder passed to the
// backend as PARSE_WORKSPACE_ROOT). Null until the user has chosen one.
let selectedProjectRoot = null;

const DEFAULT_APP_URL = 'http://127.0.0.1:5173/';

let mainWindow = null;
let backendProcess = null;

// Desktop-runtime supervisor state (only used when PARSE_DESKTOP === '1').
let supervisor = null;
let supervisorUrl = null;
let backendLogStream = null;

// Re-entrancy guard for switchProject(). Two quick fires (menu accelerator +
// pick-project IPC, or a double click) can otherwise interleave stop()/start()
// calls on the supervisor and orphan a Python backend process. While a switch
// is in flight, subsequent switch attempts are no-ops, and did-fail-load
// recovery rendering is suppressed so a torn-down backend's in-flight request
// can't flash the failure page over the splash screen.
let switching = false;

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

// Path to the desktop settings file (recent projects + last project).
function getSettingsPath() {
  return path.join(app.getPath('userData'), 'settings.json');
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

function buildNoProjectPage() {
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
      width: min(620px, 100%);
      background: #121d30;
      border: 1px solid #294066;
      border-radius: 14px;
      padding: 28px;
      box-sizing: border-box;
      text-align: center;
    }
    h1 { margin-top: 0; }
    p { line-height: 1.5; opacity: 0.9; }
    button {
      margin-top: 12px;
      padding: 11px 22px;
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
    <h1>Choose a PARSE project</h1>
    <p>PARSE needs a project folder to open. Pick an existing project, or create
       a new empty folder and PARSE will set it up for you.</p>
    <button onclick="window.parseDesktop && window.parseDesktop.pickProject && window.parseDesktop.pickProject()">Open or create a project folder</button>
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

// Show the native folder picker ("Open or create a PARSE project folder").
// Returns the chosen absolute path, or null if the user cancelled.
async function showProjectPicker() {
  const result = await dialog.showOpenDialog({
    title: 'Open or create a PARSE project folder',
    message: 'Choose an existing PARSE project, or create a new empty folder.',
    buttonLabel: 'Open Project',
    properties: ['openDirectory', 'createDirectory'],
  });

  if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
}

// Persist a chosen project into settings (recent + last) and record it as the
// active project root.
function commitSelectedProject(projectPath) {
  selectedProjectRoot = projectPath;
  try {
    const settingsPath = getSettingsPath();
    const settings = projectStore.readSettings(settingsPath);
    const next = projectStore.addRecentProject(settings, projectPath);
    projectStore.writeSettings(settingsPath, next);
  } catch (error) {
    console.error(`[parse-desktop] could not persist project selection: ${error.message}`);
  }
  return projectPath;
}

// Resolve the project root to hand the supervisor. Reuse a valid last project
// when present; otherwise prompt with the native picker. Returns the chosen
// path, or null if the user declined and there is no valid fallback.
async function resolveProjectRoot() {
  const settings = projectStore.readSettings(getSettingsPath());

  if (settings.lastProject && projectStore.isValidProjectDir(settings.lastProject)) {
    return commitSelectedProject(settings.lastProject);
  }

  const chosen = await showProjectPicker();
  if (chosen && projectStore.isValidProjectDir(chosen)) {
    return commitSelectedProject(chosen);
  }

  return null;
}

async function startSupervisedBackend() {
  if (!supervisor) {
    // Packaged builds spawn the frozen backend executable directly (no shell,
    // no python); dev builds keep the existing `python3 python/server.py` shell
    // command. resolveBackendLauncher() encapsulates that choice.
    const launcher = resolveBackendLauncher(app.isPackaged, process.resourcesPath);

    supervisor = createBackendSupervisor({
      projectRoot: selectedProjectRoot || getBackendCwd(),
      userDataRoot: app.getPath('userData'),
      backendCommand: launcher.command || getBackendCommand(),
      backendExecutable: launcher.executable || null,
      backendArgs: launcher.args || [],
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
  // Choose the project folder BEFORE booting the backend so it comes up bound
  // to the right PARSE_WORKSPACE_ROOT.
  const projectRoot = await resolveProjectRoot();
  if (!projectRoot) {
    // User cancelled and there is no valid last project: show the friendly
    // no-project page with a button to re-open the picker.
    await renderHtml(buildNoProjectPage());
    return;
  }

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

// Tear down the running backend, then boot it against `targetPath` and load
// the new URL. Shared by switchProject() (native picker) and the Open Recent
// menu (an explicit already-known path). Callers are responsible for the
// `switching` re-entrancy guard.
async function switchToProjectPath(targetPath) {
  await renderHtml(buildSplashPage('Switching PARSE project...'));

  try {
    if (supervisor) {
      await supervisor.stop();
    }
    // Drop the supervisor so it re-reads the new project root on next create.
    supervisor = null;
    supervisorUrl = null;

    commitSelectedProject(targetPath);
    // Refresh the menu so "Open Recent" reflects the just-updated order.
    installDesktopMenu();

    const url = await startSupervisedBackend();
    if (mainWindow) {
      await mainWindow.loadURL(url);
    }
    return { ok: true, url };
  } catch (error) {
    console.error(`[parse-desktop] switch project failed: ${error.message}`);
    await renderHtml(buildBackendFailurePage(error.message));
    return { ok: false, reason: error.message };
  }
}

// Tear down the running backend, prompt for a new project, then boot the
// backend against it and load the new URL. Used by the Switch Project menu item
// and by the pick-project IPC (recovery / no-project page).
//
// Guarded against re-entrancy: reachable from both the Switch Project menu
// accelerator (CmdOrCtrl+Shift+O) and the parse-desktop:pick-project IPC, with
// no natural mutual exclusion otherwise. Two quick fires could interleave
// supervisor stop()/start() calls and orphan a Python backend process.
async function switchProject() {
  if (!isDesktopRuntime()) {
    return { ok: false, reason: 'not-desktop-runtime' };
  }

  if (switching) {
    return { ok: false, reason: 'switch-in-progress' };
  }

  switching = true;
  try {
    const chosen = await showProjectPicker();
    if (!chosen || !projectStore.isValidProjectDir(chosen)) {
      // Cancelled: leave the current session (if any) untouched.
      return { ok: false, reason: 'cancelled' };
    }

    return await switchToProjectPath(chosen);
  } finally {
    switching = false;
  }
}

// Switch directly to a known, already-validated project path (no picker
// dialog). Used by the Open Recent submenu. Shares the same re-entrancy guard
// as switchProject() since both ultimately tear down/rebuild the supervisor.
async function switchToRecentProject(targetPath) {
  if (!isDesktopRuntime()) {
    return { ok: false, reason: 'not-desktop-runtime' };
  }

  if (switching) {
    return { ok: false, reason: 'switch-in-progress' };
  }

  if (!projectStore.isValidProjectDir(targetPath)) {
    return { ok: false, reason: 'invalid-project-dir' };
  }

  switching = true;
  try {
    return await switchToProjectPath(targetPath);
  } finally {
    switching = false;
  }
}

// Build the "Open Recent" submenu from persisted settings. Each entry
// switches directly to that project path (via switchToRecentProject, which
// shares the switchProject re-entrancy guard). Shown disabled with a
// placeholder item when there are no recent projects yet.
function buildOpenRecentSubmenu() {
  let recentProjects = [];
  try {
    recentProjects = projectStore.readSettings(getSettingsPath()).recentProjects || [];
  } catch (error) {
    console.error(`[parse-desktop] could not read recent projects: ${error.message}`);
  }

  if (recentProjects.length === 0) {
    return [{ label: 'No Recent Projects', enabled: false }];
  }

  return recentProjects.map((projectPath) => ({
    label: projectPath,
    click: () => {
      void switchToRecentProject(projectPath);
    },
  }));
}

// Build a minimal application menu in desktop-runtime mode, adding
// "Switch Project..." and "Open Recent" items. In dev/scaffold mode the menu
// is left untouched.
function installDesktopMenu() {
  if (!isDesktopRuntime()) {
    return;
  }

  const isMac = process.platform === 'darwin';
  const template = [];

  if (isMac) {
    template.push({ role: 'appMenu' });
  }

  template.push({
    label: 'File',
    submenu: [
      {
        label: 'Switch Project...',
        accelerator: 'CmdOrCtrl+Shift+O',
        click: () => {
          void switchProject();
        },
      },
      {
        label: 'Open Recent',
        submenu: buildOpenRecentSubmenu(),
      },
      { type: 'separator' },
      isMac ? { role: 'close' } : { role: 'quit' },
    ],
  });

  template.push({ role: 'editMenu' });
  template.push({ role: 'viewMenu' });
  template.push({ role: 'windowMenu' });

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
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

    // A project switch in progress is already tearing down/rebuilding the
    // backend and driving its own splash/failure rendering. An in-flight
    // request against the old (now-stopped) backend can fail-load right as
    // that happens; without this guard it would flash the generic failure
    // page over the switch's own splash/result UI.
    if (switching) {
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

// Picker affordance for the no-project / recovery page and any renderer that
// wants to switch projects. Mirrors the retry-backend pattern.
ipcMain.handle('parse-desktop:pick-project', async () => {
  return switchProject();
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
  installDesktopMenu();
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
