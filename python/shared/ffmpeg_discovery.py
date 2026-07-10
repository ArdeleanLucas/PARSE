"""
ffmpeg_discovery.py - Cross-platform ffmpeg/ffprobe discovery policy for PARSE.

This module implements the binary-discovery policy required by distribution
readiness Gate B2 ("ffmpeg/ffprobe availability policy is implemented and
documented"). It is stdlib-only so it stays importable in a frozen desktop
build and in hermetic tests, with no dependency on the audio pipeline itself.

Discovery order (first candidate that verifies wins):

  1. Explicit override env var — PARSE_FFMPEG / PARSE_FFPROBE — if set and valid.
  2. A bundled location for the packaged desktop app:
       - PARSE_BUNDLED_BIN directory (the desktop shell sets this), and
       - a path relative to a frozen executable (PyInstaller sys._MEIPASS,
         or the directory of sys.executable when frozen).
     This makes discovery ready for a future packaging step that ships ffmpeg
     alongside the frozen backend; nothing is bundled here.
  3. shutil.which() on PATH (Homebrew / apt / system installs on mac/Linux,
     and Windows PATH).
  4. Common per-OS install locations (macOS: /opt/homebrew/bin, /usr/local/bin;
     Linux: /usr/bin, /usr/local/bin; Windows: Program Files + the Chocolatey
     path as ONE fallback among others, not the primary).

Callers with a higher-priority explicit path (for example the normalize CLI's
`--ffmpeg` flag) should pass it via `explicit=` so it is tried above the env
var. If nothing verifies, `FfmpegNotFoundError` is raised with an actionable
message naming the override env vars and how to install ffmpeg.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional


# Env var names, exported so callers and docs share one source of truth.
FFMPEG_OVERRIDE_ENV = "PARSE_FFMPEG"
FFPROBE_OVERRIDE_ENV = "PARSE_FFPROBE"
BUNDLED_BIN_ENV = "PARSE_BUNDLED_BIN"

# Legacy override honoured by the historical normalize_audio resolver. Kept as a
# lower-priority alias so existing setups keep working.
LEGACY_FFMPEG_ENV = "FFMPEG_PATH"


class FfmpegNotFoundError(RuntimeError):
    """Raised when no working ffmpeg/ffprobe binary can be discovered."""


def _exe_name(tool: str) -> str:
    """Return the platform-appropriate executable filename for a tool."""
    if platform.system() == "Windows":
        return f"{tool}.exe"
    return tool


def _verify_with_version(candidate: str) -> bool:
    """Return True if `candidate -version` runs and exits 0.

    Used as the default validator. Kept small so tests can substitute a stub.
    """
    try:
        probe = subprocess.run(
            [candidate, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _frozen_dirs() -> List[Path]:
    """Directories to search inside a frozen (PyInstaller-style) desktop build."""
    dirs: List[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        dirs.append(base)
        dirs.append(base / "bin")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)
        dirs.append(exe_dir / "bin")
    return dirs


def _bundled_dirs() -> List[Path]:
    """Directories where a packaged desktop app may ship ffmpeg/ffprobe."""
    dirs: List[Path] = []
    bundled = os.environ.get(BUNDLED_BIN_ENV, "").strip()
    if bundled:
        bundled_path = Path(bundled).expanduser()
        dirs.append(bundled_path)
        dirs.append(bundled_path / "bin")
    dirs.extend(_frozen_dirs())
    return dirs


def _common_install_dirs() -> List[Path]:
    """Common per-OS install directories, in preference order."""
    system = platform.system()
    if system == "Darwin":
        return [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/usr/bin")]
    if system == "Windows":
        dirs = []
        for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_key, "").strip()
            if base:
                dirs.append(Path(base) / "ffmpeg" / "bin")
        # Chocolatey is ONE fallback among others, not the primary path.
        dirs.append(Path("C:/ProgramData/chocolatey/bin"))
        return dirs
    # Linux and other POSIX.
    return [Path("/usr/bin"), Path("/usr/local/bin"), Path("/bin")]


def _dedupe(paths: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in paths:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _candidate_paths(tool: str, explicit: Optional[str]) -> List[str]:
    """Build the ordered candidate list for `tool` (``ffmpeg`` or ``ffprobe``)."""
    exe = _exe_name(tool)
    override_env = FFMPEG_OVERRIDE_ENV if tool == "ffmpeg" else FFPROBE_OVERRIDE_ENV

    candidates: List[str] = []

    # 0. Caller-supplied explicit path (e.g. CLI --ffmpeg). Highest priority.
    if explicit and explicit.strip():
        candidates.append(explicit.strip())

    # 1. Explicit override env var.
    env_override = os.environ.get(override_env, "").strip()
    if env_override:
        candidates.append(env_override)

    # Legacy env alias (ffmpeg only), lower priority than the new override.
    if tool == "ffmpeg":
        legacy = os.environ.get(LEGACY_FFMPEG_ENV, "").strip()
        if legacy:
            candidates.append(legacy)

    # 2. Bundled desktop locations.
    for directory in _bundled_dirs():
        candidates.append(str(directory / exe))

    # 3. PATH lookup.
    which_hit = shutil.which(tool)
    if which_hit:
        candidates.append(which_hit)

    # 4. Common per-OS install locations.
    for directory in _common_install_dirs():
        candidates.append(str(directory / exe))

    return _dedupe(candidates)


def _not_found_message(tool: str, override_env: str) -> str:
    return (
        f"Could not find a working {tool} binary.\n"
        "Checked, in order:\n"
        f"  1) explicit path argument (e.g. --ffmpeg)\n"
        f"  2) {override_env} environment variable\n"
        f"  3) {BUNDLED_BIN_ENV} bundled directory / frozen app dir\n"
        f"  4) {tool} on system PATH\n"
        "  5) common per-OS install locations\n"
        "\n"
        f"Install ffmpeg (which provides {tool}) and try one of:\n"
        f"  - set {override_env}=/path/to/{tool}\n"
        f"  - add {tool} to your system PATH\n"
        "  - macOS: brew install ffmpeg\n"
        "  - Debian/Ubuntu: sudo apt install ffmpeg\n"
        "  - Windows: choco install ffmpeg (or download a static build)"
    )


def discover_ffmpeg(
    explicit: Optional[str] = None,
    *,
    verify: Callable[[str], bool] = _verify_with_version,
) -> str:
    """Return the first ffmpeg binary that verifies, following the policy order.

    Args:
        explicit: A caller-supplied path tried above all env/bundled/PATH
            candidates (e.g. the normalize CLI's ``--ffmpeg`` flag).
        verify: Predicate used to validate a candidate. Defaults to a
            ``-version`` probe; tests inject a stub so they stay hermetic.

    Raises:
        FfmpegNotFoundError: when no candidate verifies.
    """
    for candidate in _candidate_paths("ffmpeg", explicit):
        if verify(candidate):
            return candidate
    raise FfmpegNotFoundError(_not_found_message("ffmpeg", FFMPEG_OVERRIDE_ENV))


def discover_ffprobe(
    explicit: Optional[str] = None,
    *,
    ffmpeg_path: Optional[str] = None,
    verify: Callable[[str], bool] = _verify_with_version,
) -> str:
    """Return the first ffprobe binary that verifies, following the policy order.

    Args:
        explicit: A caller-supplied ffprobe path tried above env/bundled/PATH.
        ffmpeg_path: A known-good ffmpeg path. ffprobe usually sits next to
            ffmpeg, so a sibling ``ffprobe`` is tried before PATH/common dirs.
        verify: Candidate validator (see ``discover_ffmpeg``).

    Raises:
        FfmpegNotFoundError: when no candidate verifies.
    """
    candidates = _candidate_paths("ffprobe", explicit)

    # Prefer a sibling of a known-good ffmpeg, tried right after explicit/env.
    if ffmpeg_path and ffmpeg_path.strip():
        sibling = _sibling_ffprobe(ffmpeg_path.strip())
        if sibling:
            # Insert after any explicit/env override but before generic lookups.
            insert_at = _override_count("ffprobe", explicit)
            candidates.insert(insert_at, sibling)
            candidates = _dedupe(candidates)

    for candidate in candidates:
        if verify(candidate):
            return candidate
    raise FfmpegNotFoundError(_not_found_message("ffprobe", FFPROBE_OVERRIDE_ENV))


# ---------------------------------------------------------------------------
# Cached accessors
# ---------------------------------------------------------------------------
#
# The `-version` probe in `_verify_with_version` spawns a subprocess, so callers
# on a hot path (per-request server routes, per-chunk decode loops) must not
# re-run discovery on every call. These module-level lazy singletons resolve the
# binary once and reuse it; `reset_ffmpeg_cache()` clears them (mainly for tests
# and for a future "the bundled binary moved" re-resolve hook).

_CACHED_FFMPEG: Optional[str] = None
_CACHED_FFPROBE: Optional[str] = None


def cached_ffmpeg(
    *,
    verify: Callable[[str], bool] = _verify_with_version,
) -> str:
    """Return a discovered ffmpeg path, resolving at most once per process.

    Long-running / high-frequency callers (server routes, per-chunk decode
    loops) should use this instead of `discover_ffmpeg` so the `-version` probe
    runs once rather than per request/frame. Raises `FfmpegNotFoundError` (once,
    uncached) when nothing verifies, so a later install + `reset_ffmpeg_cache()`
    can recover without a restart.
    """
    global _CACHED_FFMPEG
    if _CACHED_FFMPEG is None:
        _CACHED_FFMPEG = discover_ffmpeg(verify=verify)
    return _CACHED_FFMPEG


def cached_ffprobe(
    *,
    ffmpeg_path: Optional[str] = None,
    verify: Callable[[str], bool] = _verify_with_version,
) -> str:
    """Return a discovered ffprobe path, resolving at most once per process.

    See `cached_ffmpeg`. When `ffmpeg_path` is omitted and ffmpeg has already
    been cached, the cached ffmpeg path seeds the sibling lookup.
    """
    global _CACHED_FFPROBE
    if _CACHED_FFPROBE is None:
        seed = ffmpeg_path if ffmpeg_path is not None else _CACHED_FFMPEG
        _CACHED_FFPROBE = discover_ffprobe(ffmpeg_path=seed, verify=verify)
    return _CACHED_FFPROBE


def reset_ffmpeg_cache() -> None:
    """Clear the cached ffmpeg/ffprobe paths so the next call re-discovers.

    Intended for tests and for a future re-resolve hook (e.g. after a bundled
    binary is installed at runtime).
    """
    global _CACHED_FFMPEG, _CACHED_FFPROBE
    _CACHED_FFMPEG = None
    _CACHED_FFPROBE = None


def _override_count(tool: str, explicit: Optional[str]) -> int:
    """How many leading candidates are explicit/env overrides (for insertion)."""
    count = 0
    if explicit and explicit.strip():
        count += 1
    override_env = FFMPEG_OVERRIDE_ENV if tool == "ffmpeg" else FFPROBE_OVERRIDE_ENV
    if os.environ.get(override_env, "").strip():
        count += 1
    return count


def _sibling_ffprobe(ffmpeg_path: str) -> Optional[str]:
    """Infer an ffprobe path sitting next to a resolved ffmpeg path."""
    name = Path(ffmpeg_path).name.lower()
    if name in ("ffmpeg", "ffmpeg.exe"):
        suffix = ".exe" if name.endswith(".exe") else ""
        return str(Path(ffmpeg_path).with_name("ffprobe" + suffix))
    # Bare "ffmpeg" resolved via PATH -> let ffprobe resolve via PATH too.
    return None
