# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — freeze the PARSE Python backend into a self-contained bundle.

Gate B (macOS-first). This spec turns ``python/server.py`` and its heavy ML
stack into a **onedir** bundle named ``parse-backend``. onedir (NOT onefile) is a
deliberate choice: onefile unpacks to a temp dir on every launch (slow, and it
routinely breaks torch/ctranslate2 dynamic-library resolution), whereas onedir
ships a real directory tree that the Electron app can spawn directly.

The frozen executable lands at ``dist/parse-backend/parse-backend`` and is
launched exactly like the source entry point, e.g.::

    PARSE_DESKTOP=1 PARSE_API_PORT=8766 ./dist/parse-backend/parse-backend

``python/server.py`` reads ``PARSE_API_PORT`` / ``PARSE_PORT`` for the bind port
and serves ``GET /api/health`` for the readiness handshake. ``_project_root()``
is ``cwd``, so the packaged app should ``chdir`` into the project/workspace
before spawn (a follow-up main.js change owns that; not this spec).

--------------------------------------------------------------------------------
Assumptions / notes for future maintainers
--------------------------------------------------------------------------------
* Python 3.10-3.12 only. ``server.py`` imports the stdlib ``cgi`` module, which
  was removed in 3.13, so freezing on 3.13+ will fail at runtime. CI pins 3.12.
* This spec is EXPECTED to reveal missing hidden imports on the first real
  macOS CI run (dynamically imported provider modules, lazy torch backends,
  ctranslate2 / faster-whisper data files, phonemizer backends, etc.). The
  structure below is built so those are cheap to add:
    - add a package name to ``COLLECT_ALL_PACKAGES`` to pull *everything*
      (submodules + data + dynamic libs) for it, or
    - append a module string to ``EXTRA_HIDDEN_IMPORTS`` for a single lazy import.
* Models are NOT bundled here. STT (Whisper) + IPA (wav2vec2) weights are a later
  increment; this spec only freezes the code + runtime libraries.
"""

import os
import sys

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# ``SPECPATH`` is injected by PyInstaller and points at this file's directory
# (``packaging/``). The repo root is its parent; the backend package is
# ``python/`` under the repo root.
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # noqa: F821 (SPECPATH is a PyInstaller global)
PYTHON_DIR = os.path.join(REPO_ROOT, "python")
ENTRY_SCRIPT = os.path.join(PYTHON_DIR, "server.py")

# CRITICAL: put the backend dir on ``sys.path`` at spec-evaluation time.
# ``collect_submodules`` / ``collect_*`` import the target package via the LIVE
# interpreter's ``sys.path`` while this spec is being evaluated — they do NOT
# honor PyInstaller's ``pathex`` (that only affects the frozen import graph).
# Without this, ``collect_submodules('server_routes')`` (and every other
# first-party package) silently returns an empty list, and dynamically imported
# modules like ``server_routes.progress_ipc`` get dropped from the freeze.
for _p in (PYTHON_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ``pathex`` must include ``python/`` so first-party imports resolve
# (``import server``, ``from ai.chat_tools import ...``, ``app.http.*``,
# ``compare.*``, ``server_routes.*``, ``shared.*``, ``external_api.*``, ...).
pathex = [PYTHON_DIR, REPO_ROOT]

# --------------------------------------------------------------------------- #
# Heavy third-party stack — collect_all pulls submodules + data + dynamic libs.
# --------------------------------------------------------------------------- #
# ``collect_all`` returns (datas, binaries, hiddenimports) for a package. We use
# it for the packages whose runtime behaviour depends on data files and/or
# native shared objects that PyInstaller's static analysis alone would miss.
COLLECT_ALL_PACKAGES = [
    "torch",
    "torchaudio",
    "transformers",
    "faster_whisper",
    "ctranslate2",
    "silero_vad",
    "phonemizer",
    "soundfile",
    "tokenizers",       # transformers backend; ships a native extension
    "sentencepiece",    # some transformers tokenizers require it at runtime
    "regex",            # transformers/tokenizers hard dependency
    "huggingface_hub",  # model resolution used by transformers/faster-whisper
    "safetensors",      # transformers weight loader
]

datas = []
binaries = []
hiddenimports = []

for pkg in COLLECT_ALL_PACKAGES:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception as exc:  # noqa: BLE001 - a missing optional pkg must not abort the freeze.
        # Some packages in the list are optional/transitive; if one is not
        # installed in the freeze environment, skip it rather than aborting.
        # A required-but-missing package will instead surface as a runtime
        # ImportError in the CI smoke test, which is the signal we want.
        print(f"[parse-backend.spec] collect_all skipped {pkg!r}: {exc}", file=sys.stderr)
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# --------------------------------------------------------------------------- #
# First-party backend package: make sure every submodule under python/ is
# available even when it is only reached via dynamic dispatch (route modules,
# provider registries, MCP adapters, chat tools).
# --------------------------------------------------------------------------- #
FIRST_PARTY_PACKAGES = [
    "ai",
    "app",
    "compare",
    "server_routes",
    "shared",
    "external_api",
    "adapters",
    "api",
    "storage",
    "migration",
]

for pkg in FIRST_PARTY_PACKAGES:
    pkg_path = os.path.join(PYTHON_DIR, pkg)
    if not os.path.isdir(pkg_path):
        continue
    try:
        # Exclude test modules: now that collect_submodules actually enumerates
        # submodules (see the sys.path fix above), it would otherwise pull in
        # ``test_*.py`` modules (e.g. ``ai/tools/test_*.py``), which can drag in
        # the excluded ``pytest`` dev dep or fail on test-only imports.
        pkg_submodules = collect_submodules(
            pkg,
            filter=lambda name: not name.rsplit(".", 1)[-1].startswith("test_") and ".tests" not in name,
        )
        if not pkg_submodules:
            # A first-party package that yields zero submodules almost always
            # means the collection silently failed (e.g. sys.path regression) —
            # make it loud so a future silent-miss shows up in the CI freeze log.
            print(
                f"[parse-backend.spec] WARNING: collect_submodules({pkg!r}) returned 0 modules",
                file=sys.stderr,
            )
        hiddenimports += pkg_submodules
    except Exception as exc:  # noqa: BLE001
        print(f"[parse-backend.spec] collect_submodules skipped {pkg!r}: {exc}", file=sys.stderr)

# --------------------------------------------------------------------------- #
# Belt-and-suspenders: top-level single-file first-party modules that live
# directly under ``python/`` (not inside a package). Dynamic imports —
# ``importlib.import_module("<topmodule>")`` — may reference these by bare name,
# and they are not covered by the package-level ``collect_submodules`` above.
# The entry ``server.py`` is frozen as ``__main__`` and is intentionally skipped.
# --------------------------------------------------------------------------- #
try:
    for _fname in os.listdir(PYTHON_DIR):
        if not _fname.endswith(".py"):
            continue
        if _fname.startswith("test_") or _fname.startswith("__") or _fname == "server.py":
            continue
        if not os.path.isfile(os.path.join(PYTHON_DIR, _fname)):
            continue
        hiddenimports.append(_fname[:-3])  # strip ".py" -> bare module name
except Exception as exc:  # noqa: BLE001 - defensive: never let this optional walk abort the freeze.
    print(f"[parse-backend.spec] top-level module walk skipped: {exc}", file=sys.stderr)

# --------------------------------------------------------------------------- #
# Extra data files that ``collect_all`` may not associate with a top-level
# package but that the runtime needs.
# --------------------------------------------------------------------------- #
for data_pkg in ("phonemizer", "silero_vad"):
    try:
        datas += collect_data_files(data_pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"[parse-backend.spec] collect_data_files skipped {data_pkg!r}: {exc}", file=sys.stderr)

# Dynamic libs for the native-heavy packages (belt-and-suspenders alongside
# collect_all, which already gathers most of these).
for lib_pkg in ("ctranslate2", "torch", "torchaudio", "soundfile"):
    try:
        binaries += collect_dynamic_libs(lib_pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"[parse-backend.spec] collect_dynamic_libs skipped {lib_pkg!r}: {exc}", file=sys.stderr)

# --------------------------------------------------------------------------- #
# Hidden imports that are reached only through dynamic import / lazy loading.
# Add to this list whenever a CI run reports a ModuleNotFoundError from the
# frozen binary.
# --------------------------------------------------------------------------- #
EXTRA_HIDDEN_IMPORTS = [
    # stdlib module imported by server.py; present on 3.10-3.12, gone in 3.13+.
    "cgi",
    # Chat providers (openai / anthropic SDKs) — imported lazily by provider.py.
    "openai",
    "anthropic",
    # Web/runtime deps declared in requirements.txt.
    "pydantic",
    "requests",
    "websockets",
    "numpy",
    # MCP stack used by the adapter surface.
    "mcp",
    # faster-whisper / ctranslate2 sometimes need these named explicitly.
    "ctranslate2",
    "onnxruntime",  # silero-vad ONNX backend (optional; skipped if absent at runtime).
]
hiddenimports += EXTRA_HIDDEN_IMPORTS

# De-duplicate while preserving order (PyInstaller tolerates dupes, but a clean
# list keeps warnings readable).
def _dedupe(seq):
    seen = set()
    out = []
    for item in seq:
        key = item if isinstance(item, str) else repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


hiddenimports = _dedupe(hiddenimports)

# --------------------------------------------------------------------------- #
# Analysis / build graph.
# --------------------------------------------------------------------------- #
block_cipher = None

a = Analysis(  # noqa: F821 (Analysis is a PyInstaller global)
    [ENTRY_SCRIPT],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excludes: keep the bundle lean. These are heavy dev/test-only deps that
    # the runtime server does not import. pytest/ruff are dev tooling; tkinter
    # is a GUI toolkit PyInstaller otherwise tries to drag in.
    excludes=[
        "pytest",
        "ruff",
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries live beside the exe, not inside it.
    name="parse-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX corrupts torch/ctranslate2 dylibs on macOS — keep it off.
    console=True,  # headless backend; stdout/stderr are teed to the Electron log.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # electron-builder/CI pins the arch (arm64 for macos-14).
    codesign_identity=None,  # signing is Gate C; unsigned freeze for Gate B.
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="parse-backend",  # -> dist/parse-backend/
)
