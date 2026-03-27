#!/usr/bin/env node
'use strict';

const path = require('path');
const { spawn } = require('child_process');

const electronBinary = require('electron');

const DEFAULT_APP_URL = 'http://127.0.0.1:8766/parse.html';
const desktopDir = __dirname;
const repoRoot = path.resolve(desktopDir, '..');

function parseArgs(argv) {
  const parsed = {
    appUrl: process.env.PARSE_APP_URL || DEFAULT_APP_URL,
    withBackend: false,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === '--with-backend') {
      parsed.withBackend = true;
      continue;
    }

    if ((arg === '--url' || arg === '--app-url') && argv[i + 1]) {
      parsed.appUrl = argv[i + 1];
      i += 1;
      continue;
    }

    if (arg === '-h' || arg === '--help') {
      parsed.help = true;
      continue;
    }
  }

  return parsed;
}

function printHelp() {
  console.log(`PARSE desktop scaffold launcher

Usage:
  npm run dev -- [--url <http://127.0.0.1:8766/parse.html>] [--with-backend]

Options:
  --url, --app-url   App URL loaded by Electron
  --with-backend     Starts backend command inside Electron main process
  -h, --help         Show this help
`);
}

function defaultBackendCommand() {
  return process.platform === 'win32'
    ? 'python python/server.py'
    : 'python3 python/server.py';
}

const args = parseArgs(process.argv.slice(2));

if (args.help) {
  printHelp();
  process.exit(0);
}

const env = {
  ...process.env,
  PARSE_APP_URL: args.appUrl,
  PARSE_PROJECT_ROOT: process.env.PARSE_PROJECT_ROOT || repoRoot,
};

if (args.withBackend) {
  env.PARSE_AUTO_BACKEND = '1';
  env.PARSE_BACKEND_CMD = process.env.PARSE_BACKEND_CMD || defaultBackendCommand();
}

console.log(`[parse-desktop] launching shell for ${env.PARSE_APP_URL}`);

if (env.PARSE_AUTO_BACKEND === '1') {
  console.log(`[parse-desktop] backend auto-launch enabled: ${env.PARSE_BACKEND_CMD}`);
  console.log(`[parse-desktop] backend cwd: ${env.PARSE_PROJECT_ROOT}`);
}

const child = spawn(electronBinary, ['.'], {
  cwd: desktopDir,
  env,
  stdio: 'inherit',
});

child.on('error', (error) => {
  console.error(`[parse-desktop] failed to start Electron: ${error.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    console.log(`[parse-desktop] Electron exited via signal ${signal}`);
    process.exit(0);
  }

  process.exit(typeof code === 'number' ? code : 1);
});
