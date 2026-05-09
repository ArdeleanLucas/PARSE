"""Pipeline audio-path resolution shared by the HTTP route and chat tools.

The HTTP route's ``_pipeline_audio_path_for_speaker`` (in
``server_routes/annotate.py``) is the source of truth for "given a speaker
id, where on disk is the WAV the model should read?"  The MCP/chat-tool
shim that drives ``rerun_lexemes_by_tag`` previously hardcoded
``audio/working/<speaker>/working.wav``, which silently failed for the
thesis corpus's per-speaker filename convention (e.g. ``Saha01.wav``).

This module extracts the resolution rule into a pure helper so both
callers share the same fallback chain:

1. ``record["source_audio"]`` (or ``source_wav``) — relative path under
   the project root.
2. ``primary_source_wav_for_speaker(speaker)`` if supplied — the HTTP
   route reads this from the source-index payload; chat tools do not
   have access to that index, so they pass ``None``.
3. Build the normalized working-copy path via
   ``audio_pipeline_paths.build_normalized_output_path`` and prefer it
   if it exists; otherwise return the source path; otherwise raise.

The resolver is dependency-injected (no ``server.*`` imports here) so
test cases can wire any record loader they like.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from audio_pipeline_paths import build_normalized_output_path


AnnotationRecordReader = Callable[[str], Optional[Mapping[str, Any]]]
PrimarySourceWavLookup = Callable[[str], str]


def _record_source_relpath(record: Mapping[str, Any]) -> str:
    """Read ``source_audio`` / ``source_wav`` from a record, returning ``""``."""
    if not isinstance(record, Mapping):
        return ""
    raw = record.get("source_audio") or record.get("source_wav") or ""
    return str(raw or "").strip()


def _resolve_under_root(rel_or_abs: str, project_root: Path) -> Path:
    """Resolve a path under ``project_root`` and reject traversal escapes.

    Mirrors ``server._resolve_project_path`` (cwd-independent — the
    project_root is passed in explicitly). Empty input raises ValueError.
    """
    value = str(rel_or_abs or "").strip()
    if not value:
        raise ValueError("Path value is required")
    candidate = Path(value).expanduser()
    root = project_root.resolve()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Path escapes project root: {0}".format(resolved)
        ) from exc
    return resolved


def pipeline_audio_path_for_speaker(
    speaker: str,
    project_root: Path,
    *,
    read_annotation_record: AnnotationRecordReader,
    primary_source_wav_for_speaker: Optional[PrimarySourceWavLookup] = None,
) -> Path:
    """Resolve the audio path the rerun pipeline should use for ``speaker``.

    See ``server_routes/annotate.py::_pipeline_audio_path_for_speaker`` —
    this helper preserves the same fallback order and the same exception
    types so HTTP and MCP callers behave identically.

    ``read_annotation_record(speaker)`` returns:
      * ``None`` when no annotation file exists for the speaker — the
        helper raises ``RuntimeError("No annotation found for ...")``.
      * a ``dict`` (possibly empty) when the file exists but parsing
        produced no usable record. The helper continues with the source
        lookup chain and may still raise if no source path resolves.

    ``primary_source_wav_for_speaker`` is an optional secondary lookup
    consulted only when the annotation record itself has no
    ``source_audio``/``source_wav``. The HTTP route passes
    ``server._annotation_primary_source_wav``; chat tools pass ``None``.
    """
    record = read_annotation_record(speaker)
    if record is None:
        raise RuntimeError(
            "No annotation found for speaker {0!r}".format(speaker)
        )

    source_rel = _record_source_relpath(record)
    if not source_rel and primary_source_wav_for_speaker is not None:
        source_rel = str(primary_source_wav_for_speaker(speaker) or "").strip()

    if not source_rel:
        raise RuntimeError(
            "No source_audio on annotation for {0!r}; import or onboard the speaker first".format(
                speaker
            )
        )

    source_path = _resolve_under_root(source_rel, project_root)
    working_dir = project_root.resolve() / "audio" / "working" / speaker
    normalized_path = build_normalized_output_path(source_path, working_dir)
    if normalized_path.exists():
        return normalized_path
    if source_path.exists():
        return source_path
    raise FileNotFoundError(
        "Neither normalized ({0}) nor source audio ({1}) exists for {2!r}".format(
            normalized_path, source_path, speaker
        )
    )


__all__ = [
    "AnnotationRecordReader",
    "PrimarySourceWavLookup",
    "pipeline_audio_path_for_speaker",
]
