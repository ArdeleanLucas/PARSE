"""Project-folder lifecycle helpers (Stage 2 / Gate A).

Ordinary project-folder bootstrap plus a small read summary, factored out of
``server.py`` so the thin HTTP orchestrator stays thin and this logic is
unit-testable on its own.

Everything here is intentionally dependency-free (stdlib ``pathlib``/``json``/
``os`` only). It must NOT import ``server`` or any heavy runtime deps (torch,
faster-whisper, ...) so the bootstrap/describe logic can be exercised from a
plain ``tmp_path`` in tests.

``bootstrap_project`` is idempotent and non-destructive: it only ever creates a
missing ``project.json`` (and the standard subdirectories from the desktop
architecture doc §6.1); it never overwrites an existing ``project.json`` (even a
corrupt one — reporting it invalid via ``describe_project`` is the signal, since
a corrupt file may still be manually recoverable). That makes it safe to call on
every desktop-mode startup, and it never raises on an unwritable picked folder —
it returns a status dict with an ``error`` instead so the server can log and keep
starting.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, Optional, Tuple

# Schema version stamped into freshly-created project.json files.
PROJECT_JSON_VERSION = 1

# Standard project subdirectories (desktop architecture doc §6.1). Nested paths
# are created with ``parents=True`` so ``audio/`` is materialized implicitly.
STANDARD_SUBDIRS = (
    "annotations",
    "transcripts",
    "peaks",
    "exports",
    "sync",
    "logs",
    "audio/original",
    "audio/working",
)

# Well-known OS cruft that must not make a freshly-picked folder look "non-empty"
# (and therefore un-initializable). A folder containing only these is still a
# valid, initializable project location.
_OS_CRUFT = frozenset({".DS_Store", "Thumbs.db", ".localized"})


def _project_json_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / "project.json"


def _parse_project_json(project_root: pathlib.Path) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Parse ``project.json`` into ``(payload, corrupt)``.

    ``payload`` is the parsed ``dict`` when the file exists and parses to a dict.
    ``corrupt`` is ``True`` only when the file EXISTS but does not parse to a
    ``dict`` (truncated/garbage/non-object JSON). A missing file is not corrupt
    (``(None, False)``).
    """
    path = _project_json_path(project_root)
    if not path.exists():
        return None, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, True
    if not isinstance(payload, dict):
        return None, True
    return payload, False


def _resolve_name(project_root: pathlib.Path, payload: Optional[Dict[str, Any]]) -> str:
    """Resolve the project name, tolerating a missing/non-dict/corrupt payload."""
    if isinstance(payload, dict):
        name = str(payload.get("name") or "").strip()
        if name:
            return name
    return project_root.name


def bootstrap_project(project_root: pathlib.Path) -> Dict[str, Any]:
    """Ensure ``project_root`` is a valid PARSE project folder.

    Idempotent, non-destructive, and defensive (never raises on an unwritable
    folder — see below):

    * If ``project.json`` is MISSING, atomically write a minimal valid one
      (``{"name": <dir name>, "version": 1, "speakers": {}}``) and create the
      standard subdirectories from architecture doc §6.1.
    * If ``project.json`` already EXISTS (including a corrupt one), do nothing to
      it (never overwrite); the standard subdirectories are still ensured
      (``mkdir`` is a no-op when they already exist), so a partially-created
      project heals forward. A corrupt existing file is left in place — it may be
      manually recoverable, and ``describe_project`` reports it invalid.

    Safe to call on every startup. Returns a small summary::

        {"created": bool, "project_json_path": str, "name": str, "error": str|None}

    ``created`` reports whether this call wrote a new ``project.json``. ``error``
    is ``None`` on success; on an ``OSError``/``PermissionError`` (mkdir or write)
    it is a one-line human-readable message and ``created`` is ``False`` — the
    caller logs it and keeps starting rather than crashing on a bad picked folder.
    """
    project_root = pathlib.Path(project_root)
    path = _project_json_path(project_root)

    def _fail(exc: OSError) -> Dict[str, Any]:
        return {
            "created": False,
            "project_json_path": str(path),
            "name": project_root.name,
            "error": "{0}: {1}".format(type(exc).__name__, exc),
        }

    try:
        project_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(exc)

    created = False
    if path.exists():
        payload, _corrupt = _parse_project_json(project_root)
        name = _resolve_name(project_root, payload)
    else:
        name = project_root.name
        new_payload: Dict[str, Any] = {
            "name": name,
            "version": PROJECT_JSON_VERSION,
            "speakers": {},
        }
        try:
            _atomic_write_json(path, new_payload)
        except OSError as exc:
            return _fail(exc)
        created = True

    try:
        for subdir in STANDARD_SUBDIRS:
            (project_root / subdir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(exc)

    return {
        "created": created,
        "project_json_path": str(path),
        "name": name,
        "error": None,
    }


def _atomic_write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    """Atomically write ``payload`` as pretty JSON to ``path``.

    Writes to a temp file in the SAME directory, ``flush()`` + ``os.fsync()``,
    then ``os.replace(tmp, path)`` so a crash can never leave a truncated
    ``project.json``. Stdlib only (MC-463-B atomic-write convention). Cleans up
    the temp file if the replace never happens.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def describe_project(project_root: pathlib.Path) -> Dict[str, Any]:
    """Describe ``project_root`` for the ``GET /api/project`` read endpoint.

    Returns::

        {"root": str, "name": str, "hasProjectJson": bool,
         "valid": bool, "corrupt": bool}

    ``valid`` is true when the directory exists and is either already a project
    (has a well-formed ``project.json``) or an empty/new directory the app can
    still initialize (a folder containing only OS cruft like ``.DS_Store`` still
    counts as empty). A ``project.json`` that exists but does not parse to a dict
    is ``corrupt: True`` and ``valid: False``. ``name`` is read from
    ``project.json`` when present and well-formed, otherwise the directory name.
    """
    project_root = pathlib.Path(project_root)
    has_project_json = _project_json_path(project_root).exists()
    payload, corrupt = _parse_project_json(project_root)
    name = _resolve_name(project_root, payload)

    exists = project_root.exists() and project_root.is_dir()
    if not exists:
        valid = False
    elif has_project_json:
        # A present-but-corrupt project.json is not a valid project.
        valid = not corrupt
    else:
        # An existing directory with no project.json is still valid as long as
        # it is empty (a freshly-picked folder the app can initialize). Ignore
        # well-known OS cruft so a bare macOS/Windows folder still counts as
        # empty. A genuinely non-empty directory is not a PARSE project.
        try:
            valid = not any(
                entry.name not in _OS_CRUFT for entry in project_root.iterdir()
            )
        except OSError:
            valid = False

    return {
        "root": str(project_root),
        "name": name,
        "hasProjectJson": has_project_json,
        "valid": valid,
        "corrupt": corrupt,
    }
