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
architecture doc §6.1); it never overwrites an existing ``project.json``. That
makes it safe to call on every desktop-mode startup.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict

# Schema version stamped into freshly-created project.json files.
PROJECT_JSON_VERSION = 1

# Standard project subdirectories (desktop architecture doc §6.1). Nested paths
# are created with ``parents=True`` so ``audio/`` is materialized implicitly.
STANDARD_SUBDIRS = (
    "annotations",
    "transcripts",
    "peaks",
    "exports",
    "audio/original",
    "audio/working",
)


def _project_json_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / "project.json"


def _read_project_json(project_root: pathlib.Path) -> Dict[str, Any]:
    """Best-effort read of ``project.json`` as a dict (empty dict on any error)."""
    path = _project_json_path(project_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def bootstrap_project(project_root: pathlib.Path) -> Dict[str, Any]:
    """Ensure ``project_root`` is a valid PARSE project folder.

    Idempotent and non-destructive:

    * If ``project.json`` is MISSING, write a minimal valid one
      (``{"name": <dir name>, "version": 1, "speakers": {}}``) and create the
      standard subdirectories from architecture doc §6.1.
    * If ``project.json`` already EXISTS, do nothing to it (never overwrite);
      the standard subdirectories are still ensured (``mkdir`` is a no-op when
      they already exist), so a partially-created project heals forward.

    Safe to call on every startup. Returns a small summary::

        {"created": bool, "project_json_path": str, "name": str}

    where ``created`` reports whether this call wrote a new ``project.json``.
    """
    project_root = pathlib.Path(project_root)
    project_root.mkdir(parents=True, exist_ok=True)

    path = _project_json_path(project_root)
    created = False
    if path.exists():
        name = str(_read_project_json(project_root).get("name") or project_root.name)
    else:
        name = project_root.name
        payload: Dict[str, Any] = {
            "name": name,
            "version": PROJECT_JSON_VERSION,
            "speakers": {},
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        created = True

    for subdir in STANDARD_SUBDIRS:
        (project_root / subdir).mkdir(parents=True, exist_ok=True)

    return {
        "created": created,
        "project_json_path": str(path),
        "name": name,
    }


def describe_project(project_root: pathlib.Path) -> Dict[str, Any]:
    """Describe ``project_root`` for the ``GET /api/project`` read endpoint.

    Returns::

        {"root": str, "name": str, "hasProjectJson": bool, "valid": bool}

    ``valid`` is true when the directory exists and is either already a project
    (has ``project.json``) or an empty/new directory the app can still
    initialize. ``name`` is read from ``project.json`` when present, otherwise
    the directory name.
    """
    project_root = pathlib.Path(project_root)
    has_project_json = _project_json_path(project_root).exists()

    if has_project_json:
        name = str(_read_project_json(project_root).get("name") or project_root.name)
    else:
        name = project_root.name

    exists = project_root.exists() and project_root.is_dir()
    if not exists:
        valid = False
    elif has_project_json:
        valid = True
    else:
        # An existing directory with no project.json is still valid as long as
        # it is empty (a freshly-picked folder the app can initialize). A
        # non-empty directory without a project.json is not a PARSE project.
        try:
            valid = not any(project_root.iterdir())
        except OSError:
            valid = False

    return {
        "root": str(project_root),
        "name": name,
        "hasProjectJson": has_project_json,
        "valid": valid,
    }
