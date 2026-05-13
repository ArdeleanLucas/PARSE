"""Backfill stale ``source_audio_duration_sec`` values for existing speakers.

Usage:
    PYTHONPATH=python python3 -m scripts.backfill_source_audio_duration \
        --workspace /home/lucas/parse-workspace [--dry-run] [--speaker Fail01]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import soundfile as sf

import server as _server
from server_routes.annotate import _normalize_speaker_id
from server_routes.media import _refresh_source_audio_duration

logger = logging.getLogger("backfill_duration")


def _json_record(
    *,
    speaker: str,
    status: str,
    old_duration: float | None,
    new_duration: float | None,
    drift_sec: float | None,
    would_write: bool,
) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "status": status,
        "old_duration": old_duration,
        "new_duration": new_duration,
        "drift_sec": drift_sec,
        "would_write": would_write,
    }


@contextlib.contextmanager
def _workspace_project_root(workspace: Path) -> Iterator[None]:
    """Point server helpers at ``workspace`` without changing process CWD."""
    original_project_root = _server._project_root
    resolved_workspace = workspace.resolve()
    _server._project_root = lambda: resolved_workspace  # type: ignore[assignment]
    try:
        yield
    finally:
        _server._project_root = original_project_root  # type: ignore[assignment]


def _annotation_path(workspace: Path, speaker: str) -> Path:
    canonical = workspace / "annotations" / f"{speaker}{_server.ANNOTATION_FILENAME_SUFFIX}"
    if canonical.is_file():
        return canonical
    return workspace / "annotations" / f"{speaker}{_server.ANNOTATION_LEGACY_FILENAME_SUFFIX}"


def _read_old_duration(annotation_path: Path) -> float | None:
    try:
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return float(payload.get("source_audio_duration_sec"))
    except (TypeError, ValueError):
        return None


def _discover_speakers(annotations_dir: Path) -> list[str]:
    speakers: set[str] = set()
    canonical_suffix = _server.ANNOTATION_FILENAME_SUFFIX
    legacy_suffix = _server.ANNOTATION_LEGACY_FILENAME_SUFFIX
    for path in sorted(annotations_dir.glob(f"*{legacy_suffix}")):
        name = path.name
        if name.endswith(canonical_suffix):
            speakers.add(name[: -len(canonical_suffix)])
        elif name.endswith(legacy_suffix):
            speaker = name[: -len(legacy_suffix)]
            if speaker and speaker != "parse-enrichments":
                speakers.add(speaker)
    return [_normalize_speaker_id(speaker) for speaker in sorted(speakers)]


def _working_wav_path(workspace: Path, speaker: str) -> Path:
    source_wav = str(_server._annotation_primary_source_wav(speaker) or "").strip()
    if not source_wav:
        return workspace / "audio" / "working" / speaker / ""
    source_path = Path(source_wav)
    if source_path.is_absolute():
        return source_path
    if len(source_path.parts) >= 3 and source_path.parts[0] == "audio" and source_path.parts[1] == "working":
        return workspace / source_path
    return workspace / "audio" / "working" / speaker / source_path


def _per_speaker(workspace: Path, speaker: str, tolerance_sec: float, dry_run: bool) -> dict[str, Any]:
    annotation_path = _annotation_path(workspace, speaker)
    old_duration = _read_old_duration(annotation_path)
    wav_path = _working_wav_path(workspace, speaker)
    if not wav_path.is_file():
        logger.info("speaker=%s status=missing_wav path=%s", speaker, wav_path)
        return _json_record(
            speaker=speaker,
            status="missing_wav",
            old_duration=old_duration,
            new_duration=None,
            drift_sec=None,
            would_write=False,
        )

    try:
        new_duration = round(float(sf.info(str(wav_path)).duration), 6)
        drift_sec = None if old_duration is None else round(abs(float(old_duration) - new_duration), 6)
        if drift_sec is not None and drift_sec < tolerance_sec:
            logger.info("speaker=%s status=skipped drift_sec=%s", speaker, drift_sec)
            return _json_record(
                speaker=speaker,
                status="skipped",
                old_duration=old_duration,
                new_duration=new_duration,
                drift_sec=drift_sec,
                would_write=False,
            )
        if dry_run:
            logger.info("speaker=%s status=ok dry_run=true drift_sec=%s", speaker, drift_sec)
            return _json_record(
                speaker=speaker,
                status="ok",
                old_duration=old_duration,
                new_duration=new_duration,
                drift_sec=drift_sec,
                would_write=True,
            )
        refreshed = _refresh_source_audio_duration(speaker, wav_path)
        if not refreshed:
            raise RuntimeError("_refresh_source_audio_duration did not update annotation")
        logger.info("speaker=%s status=ok dry_run=false drift_sec=%s", speaker, drift_sec)
        return _json_record(
            speaker=speaker,
            status="ok",
            old_duration=old_duration,
            new_duration=new_duration,
            drift_sec=drift_sec,
            would_write=False,
        )
    except Exception as exc:
        logger.exception("speaker=%s status=error", speaker)
        return _json_record(
            speaker=speaker,
            status="error",
            old_duration=old_duration,
            new_duration=None,
            drift_sec=None,
            would_write=False,
        ) | {"error": str(exc)}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="Workspace root containing annotations/ and audio/working/.")
    parser.add_argument("--dry-run", action="store_true", help="Report stale speakers without writing annotations.")
    parser.add_argument("--speaker", action="append", default=None, help="Speaker id to process; repeat to process multiple speakers.")
    parser.add_argument("--tolerance-sec", type=float, default=1.0, help="Skip updates whose absolute drift is below this tolerance.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    annotations_dir = workspace / "annotations"
    if not annotations_dir.is_dir():
        logger.error("annotations dir missing: %s", annotations_dir)
        return 1
    if args.tolerance_sec < 0.0:
        logger.error("--tolerance-sec must be non-negative: %s", args.tolerance_sec)
        return 1

    _server._install_route_bindings()
    with _workspace_project_root(workspace):
        speakers = [_normalize_speaker_id(speaker) for speaker in args.speaker] if args.speaker else _discover_speakers(annotations_dir)
        any_error = False
        for speaker in speakers:
            record = _per_speaker(workspace, speaker, float(args.tolerance_sec), bool(args.dry_run))
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if record.get("status") == "error":
                any_error = True
    return 1 if any_error else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(main(sys.argv[1:]))
