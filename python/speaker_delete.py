"""Whole-speaker deletion for PARSE.

Moves every artifact owned by one speaker into a timestamped ``.trash/``
directory (recoverable by an operator) and prunes the speaker's keys from the
shared registry/sidecar JSON files. The action is presented to users as
irreversible; the ``.trash`` copy is an operator safety net, not in-app undo.

The core is intentionally dependency-free (stdlib only) so it can be unit
tested without a running server. Live job-in-flight guarding is supplied by the
caller via ``active_job_check`` because that state lives in the server runtime,
not on disk.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

TRASH_DIRNAME = ".trash"
_REGISTRY_BACKUP_DIRNAME = "_registry_backup"


class SpeakerDeleteError(Exception):
    """Raised when a speaker cannot be deleted safely."""

    def __init__(
        self,
        status: HTTPStatus,
        message: str,
        *,
        holder: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.holder = holder


def _safe_speaker(speaker: object) -> str:
    name = str(speaker or "").strip()
    if not name:
        raise SpeakerDeleteError(HTTPStatus.BAD_REQUEST, "speaker is required")
    if "/" in name or "\\" in name or "\x00" in name or name in {".", ".."}:
        raise SpeakerDeleteError(
            HTTPStatus.BAD_REQUEST, "speaker contains invalid path characters"
        )
    return name


def _timestamp(now: Optional[datetime] = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)


def _speaker_artifacts(root: Path, speaker: str) -> List[Path]:
    """Return existing on-disk paths owned exclusively by ``speaker``."""

    candidates: List[Path] = [
        root / "annotations" / "{0}.parse.json".format(speaker),
        root / "annotations" / "{0}.json".format(speaker),
        root / "audio" / "original" / speaker,
        root / "audio" / "working" / speaker,
    ]
    for sub in ("peaks", "coarse_transcripts"):
        directory = root / sub
        if not directory.is_dir():
            continue
        exact = "{0}.json".format(speaker)
        multi_prefix = "{0}_".format(speaker)
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            if entry.name == exact or (
                entry.name.startswith(multi_prefix) and entry.name.endswith(".json")
            ):
                candidates.append(entry)
    seen: set = set()
    artifacts: List[Path] = []
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        artifacts.append(path)
    return artifacts


def _registry_has_speaker(root: Path, speaker: str) -> bool:
    for name in ("project.json", "source_index.json"):
        data = _read_json(root / name)
        block = data.get("speakers") if isinstance(data, Mapping) else None
        if isinstance(block, Mapping) and speaker in block:
            return True
    return False


def speaker_exists(project_root: Path, speaker: str) -> bool:
    root = Path(project_root)
    return bool(_speaker_artifacts(root, speaker)) or _registry_has_speaker(root, speaker)


def _backup_once(path: Path, backup_dir: Optional[Path], backed_up: set) -> None:
    if backup_dir is None or path in backed_up:
        return
    if path.exists():
        dest = backup_dir / _REGISTRY_BACKUP_DIRNAME / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    backed_up.add(path)


def _prune_registries(
    root: Path, speaker: str, *, apply: bool, backup_dir: Optional[Path]
) -> List[str]:
    """Detect (and, when ``apply``, remove) the speaker's keys in shared files.

    Returns a list of human-readable descriptions of each pruned key. Detection
    is identical for dry-run and apply; side effects only happen when ``apply``.
    """

    pruned: List[str] = []
    backed_up: set = set()

    for name in ("project.json", "source_index.json"):
        path = root / name
        data = _read_json(path)
        block = data.get("speakers") if isinstance(data, dict) else None
        if isinstance(block, dict) and speaker in block:
            pruned.append("{0}:speakers[{1}]".format(name, speaker))
            if apply:
                _backup_once(path, backup_dir, backed_up)
                del block[speaker]
                _write_json(path, data)

    so_path = root / "survey-overlap.json"
    survey = _read_json(so_path)
    if isinstance(survey, dict):
        so_changed = False
        for key in ("speaker_choices", "speaker_concept_survey_links"):
            block = survey.get(key)
            if isinstance(block, dict) and speaker in block:
                pruned.append("survey-overlap.json:{0}[{1}]".format(key, speaker))
                if apply:
                    if not so_changed:
                        _backup_once(so_path, backup_dir, backed_up)
                    del block[speaker]
                    so_changed = True
        if apply and so_changed:
            _write_json(so_path, survey)

    enr_path = root / "parse-enrichments.json"
    enrichments = _read_json(enr_path)
    if isinstance(enrichments, dict):
        enr_changed = False
        notes = enrichments.get("lexeme_notes")
        if isinstance(notes, dict) and speaker in notes:
            pruned.append("parse-enrichments.json:lexeme_notes[{0}]".format(speaker))
            if apply:
                _backup_once(enr_path, backup_dir, backed_up)
                del notes[speaker]
                enr_changed = True
        overrides = enrichments.get("manual_overrides")
        canonical = overrides.get("canonical_lexemes") if isinstance(overrides, dict) else None
        if isinstance(canonical, dict):
            emptied: List[str] = []
            for bundle_id, speaker_map in canonical.items():
                if isinstance(speaker_map, dict) and speaker in speaker_map:
                    pruned.append(
                        "parse-enrichments.json:canonical_lexemes[{0}][{1}]".format(
                            bundle_id, speaker
                        )
                    )
                    if apply:
                        if not enr_changed:
                            _backup_once(enr_path, backup_dir, backed_up)
                        del speaker_map[speaker]
                        enr_changed = True
                        if not speaker_map:
                            emptied.append(bundle_id)
            for bundle_id in emptied:
                del canonical[bundle_id]
        if apply and enr_changed:
            _write_json(enr_path, enrichments)

    return pruned


def delete_speaker(
    project_root: Path,
    speaker: str,
    *,
    dry_run: bool = False,
    active_job_check: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Delete one speaker by moving its files to ``.trash`` and pruning registries.

    ``active_job_check`` is an optional no-arg callable returning a description of
    a blocking job (truthy) when the speaker is busy; deletion then fails with
    409. It is injected so the pure core stays decoupled from server runtime
    state and is trivially testable.
    """

    speaker = _safe_speaker(speaker)
    root = Path(project_root)

    if not speaker_exists(root, speaker):
        raise SpeakerDeleteError(
            HTTPStatus.NOT_FOUND, "speaker not found: {0}".format(speaker)
        )

    if active_job_check is not None:
        holder = active_job_check()
        if holder:
            raise SpeakerDeleteError(
                HTTPStatus.CONFLICT,
                "speaker has an active job; cannot delete while it runs",
                holder=holder,
            )

    artifacts = _speaker_artifacts(root, speaker)
    planned_files = [str(path.relative_to(root)) for path in artifacts]

    if dry_run:
        planned_registry = _prune_registries(root, speaker, apply=False, backup_dir=None)
        return {
            "ok": True,
            "dryRun": True,
            "speaker": speaker,
            "plannedFiles": planned_files,
            "plannedRegistry": planned_registry,
        }

    trash_dir = root / TRASH_DIRNAME / "{0}-{1}".format(speaker, _timestamp(now))
    trash_dir.mkdir(parents=True, exist_ok=True)

    moved: List[str] = []
    try:
        for path in artifacts:
            rel = path.relative_to(root)
            dest = trash_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            moved.append(str(rel))
    except OSError as exc:
        raise SpeakerDeleteError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "failed to move speaker files: {0}".format(exc),
        ) from exc

    pruned_registry = _prune_registries(root, speaker, apply=True, backup_dir=trash_dir)

    return {
        "ok": True,
        "dryRun": False,
        "speaker": speaker,
        "trashDir": str(trash_dir.relative_to(root)),
        "movedFiles": moved,
        "prunedRegistry": pruned_registry,
    }


__all__ = [
    "SpeakerDeleteError",
    "TRASH_DIRNAME",
    "delete_speaker",
    "speaker_exists",
]
