'use strict';

// electron-builder `afterPack` hook — guarantee the frozen backend executable
// keeps its +x bit inside the packed app.
//
// Why: electron-builder copies the PyInstaller onedir output into the app via
// `extraResources` (see electron-builder.yml: `from: ../dist/parse-backend,
// to: backend/parse-backend`). If that copy drops the executable bit on the frozen backend
// entry binary, the shipped `.app` trips the supervisor's missing-exe guard
// (backend-supervisor.js `_resolveSpawn` → `fs.accessSync(exe, X_OK)`) and the
// backend never launches. Rather than hope the bit survives, we chmod it here.
//
// This is a build-time hook; it runs in Node from the config directory
// (`desktop/`). Keep it dependency-free (Node `fs`/`path` only).

const fs = require('fs');
const path = require('path');

// Frozen backend directory + entry-executable name produced by the PyInstaller
// onedir freeze (packaging/parse-backend.spec: COLLECT/EXE name="parse-backend").
// Must stay in sync with electron-builder.yml `extraResources: to:
// backend/parse-backend` and backend-launcher.js's FROZEN_BACKEND_DIR /
// frozenBackendExeName.
const FROZEN_BACKEND_DIR = 'parse-backend';

function frozenBackendExeName(platform) {
  return platform === 'win32' ? 'parse-backend.exe' : 'parse-backend';
}

// Pure path derivation for the packed frozen-backend executable. Split out so it
// can be unit-tested without invoking electron-builder.
//
//   macOS: the app is a bundle; extraResources land under
//     <appOutDir>/<productFilename>.app/Contents/Resources/backend/...
//   other platforms: extraResources land under
//     <appOutDir>/resources/backend/...
//
// The `backend/parse-backend/parse-backend(.exe)` tail matches
// electron-builder.yml (`to: backend/parse-backend`) + the PyInstaller onedir
// layout, and is the same path backend-launcher.js resolves at runtime.
function resolvePackedBackendExe({ platformName, appOutDir, productFilename }) {
  const exeName = frozenBackendExeName(platformName);

  if (platformName === 'mac' || platformName === 'darwin') {
    return path.join(
      appOutDir,
      `${productFilename}.app`,
      'Contents',
      'Resources',
      'backend',
      FROZEN_BACKEND_DIR,
      exeName
    );
  }

  return path.join(
    appOutDir,
    'resources',
    'backend',
    FROZEN_BACKEND_DIR,
    exeName
  );
}

async function afterPack(context) {
  const platformName = context.electronPlatformName;

  // The executable bit is not a concept on Windows; nothing to do.
  if (platformName === 'win32') {
    return;
  }

  const appOutDir = context.appOutDir;
  const productFilename = context.packager.appInfo.productFilename;
  const exePath = resolvePackedBackendExe({ platformName, appOutDir, productFilename });

  // Fail the build loudly if the frozen backend is not where we expect — better
  // to break packaging than to ship a `.app` whose backend can never launch.
  if (!fs.existsSync(exePath)) {
    // Dump the actual on-disk layout of the backend resource dir(s) so any
    // residual path mismatch is visible directly in the CI log — otherwise a
    // wrong `to:` in electron-builder.yml costs another blind macOS build to
    // diagnose. `exePath` ends with `backend/parse-backend/parse-backend`, so
    // walk two levels up to reach `Resources/backend`.
    const parseBackendDir = path.dirname(exePath); // .../backend/parse-backend
    const backendDir = path.dirname(parseBackendDir); // .../backend

    const listDir = (dir) => {
      try {
        return fs.readdirSync(dir).join(', ') || '(empty)';
      } catch (error) {
        return `(unreadable: ${error.code || error.message})`;
      }
    };

    const diagnostics = [
      `contents of ${backendDir}: [${listDir(backendDir)}]`,
    ];
    if (fs.existsSync(parseBackendDir)) {
      diagnostics.push(
        `contents of ${parseBackendDir}: [${listDir(parseBackendDir)}]`
      );
    }

    throw new Error(
      `[afterPack] frozen PARSE backend not found at ${exePath}. ` +
        `Expected electron-builder extraResources (from ../dist/parse-backend, ` +
        `to backend/parse-backend) to have copied the PyInstaller onedir output. ` +
        `Did the freeze step run before packaging? ` +
        diagnostics.join('; ')
    );
  }

  fs.chmodSync(exePath, 0o755);
  // eslint-disable-next-line no-console
  console.log(`[afterPack] ensured +x on frozen backend: ${exePath}`);
}

module.exports = afterPack;
module.exports.afterPack = afterPack;
module.exports.resolvePackedBackendExe = resolvePackedBackendExe;
module.exports.frozenBackendExeName = frozenBackendExeName;
module.exports.FROZEN_BACKEND_DIR = FROZEN_BACKEND_DIR;
