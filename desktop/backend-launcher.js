'use strict';

// Backend launcher resolution for the PARSE desktop shell.
//
// This module decides HOW the local PARSE backend is spawned:
//   * dev / scaffold: the `python3 python/server.py` shell command, and
//   * packaged: the PyInstaller-frozen executable shipped inside the .app.
//
// It is intentionally free of any `require('electron')` so it can be unit
// tested under plain `node --test`. main.js passes in `app.isPackaged` and
// `process.resourcesPath` explicitly.

const path = require('path');

// Name of the frozen backend directory + executable produced by the PyInstaller
// onedir freeze (packaging/parse-backend.spec: COLLECT name="parse-backend",
// EXE name="parse-backend"). electron-builder.yml copies the CONTENTS of
// `../dist/parse-backend` to `backend/parse-backend`, so the packaged layout is:
//   <resourcesPath>/backend/parse-backend/parse-backend
const FROZEN_BACKEND_DIR = 'parse-backend';

function frozenBackendExeName(platform) {
  return platform === 'win32' ? 'parse-backend.exe' : 'parse-backend';
}

// The dev backend command (shell string). Mirrors main.js's getBackendCommand()
// default, and honors the same PARSE_BACKEND_CMD override.
function devBackendCommand(platform, env) {
  const environment = env || process.env;
  if (environment.PARSE_BACKEND_CMD) {
    return environment.PARSE_BACKEND_CMD;
  }
  return platform === 'win32'
    ? 'python python/server.py'
    : 'python3 python/server.py';
}

// Decide how the supervisor should spawn the backend. Pure function — takes the
// packaged flag and Electron's resourcesPath explicitly so it is testable
// without requiring `electron`.
//
//   packaged  -> { executable, args: [] }  (direct frozen exe, NO shell)
//   dev       -> { command, shell: true }   (python3 python/server.py, unchanged)
//
// The packaged executable path matches electron-builder.yml's
// `extraResources: { from: ../dist/parse-backend, to: backend/parse-backend }`,
// so at runtime the frozen onedir lives at `<resourcesPath>/backend/parse-backend`
// and its entry executable is `<resourcesPath>/backend/parse-backend/parse-backend`.
function resolveBackendLauncher(isPackaged, resourcesPath, options = {}) {
  const platform = options.platform || process.platform;

  if (isPackaged) {
    const executable = path.join(
      resourcesPath,
      'backend',
      FROZEN_BACKEND_DIR,
      frozenBackendExeName(platform)
    );
    return { executable, args: [] };
  }

  return { command: devBackendCommand(platform, options.env), shell: true };
}

module.exports = {
  resolveBackendLauncher,
  devBackendCommand,
  frozenBackendExeName,
  FROZEN_BACKEND_DIR,
};
