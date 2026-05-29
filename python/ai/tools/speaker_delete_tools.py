from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from speaker_delete import SpeakerDeleteError, delete_speaker

from ..chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    _project_loaded_condition,
    _tool_condition,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


SPEAKER_DELETE_TOOL_NAMES = ("delete_speaker",)


SPEAKER_DELETE_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "delete_speaker": ChatToolSpec(
        name="delete_speaker",
        description=(
            "Permanently remove an entire speaker from the current project. Moves all of the "
            "speaker's artifacts (annotations, audio under audio/original|working/<speaker>/, "
            "peaks, coarse transcripts) into a timestamped .trash/ directory and prunes the "
            "speaker's keys from project.json, source_index.json, survey-overlap.json and "
            "parse-enrichments.json. Fails with a conflict if a normalize/STT/onboard/rerun job "
            "is in flight for the speaker. This is not reversible from the app. "
            "Gated by dryRun: call dryRun=true first to preview the files and registry keys that "
            "would be removed, then dryRun=false after the user confirms."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "dryRun"],
            "properties": {
                "speaker": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "description": "Speaker ID to delete from the current project.",
                },
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, preview only — no files moved and no registry writes.",
                },
            },
        },
        mutability="mutating",
        supports_dry_run=True,
        dry_run_parameter="dryRun",
        preconditions=(
            _project_loaded_condition(),
            _tool_condition(
                "speaker_exists",
                "The speaker must exist in the current project.",
                kind="file_presence",
            ),
            _tool_condition(
                "speaker_not_busy",
                "No normalize/STT/onboard/rerun job may be in flight for the speaker.",
                kind="job_state",
            ),
        ),
        postconditions=(
            _tool_condition(
                "speaker_removed",
                "When dryRun=false, the speaker's files are moved to .trash/ and its registry keys are pruned.",
                kind="filesystem_write",
            ),
        ),
    ),
}


def _disk_lock_holder(project_root: Path, speaker: str) -> Optional[Dict[str, Any]]:
    """Best-effort on-disk speaker lock check (covers lexeme/tag rerun jobs)."""
    try:
        from ai.speaker_locks import _lock_path_for_speaker
    except Exception:
        return None
    raw = os.environ.get("PARSE_LOCKS_DIR", "").strip() or ".parse-locks"
    locks_dir = Path(raw)
    if not locks_dir.is_absolute():
        locks_dir = Path(project_root) / locks_dir
    try:
        lock_file = _lock_path_for_speaker(locks_dir, speaker)
    except Exception:
        return None
    if lock_file.exists():
        return {"lock": lock_file.name, "status": "locked"}
    return None


def tool_delete_speaker(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
    dry_run = bool(args.get("dryRun"))
    try:
        return delete_speaker(
            tools.project_root,
            speaker,
            dry_run=dry_run,
            active_job_check=lambda: _disk_lock_holder(tools.project_root, speaker),
        )
    except SpeakerDeleteError as exc:
        if exc.status in (HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST):
            raise ChatToolValidationError(exc.message) from exc
        raise ChatToolExecutionError(exc.message) from exc


__all__ = [
    "SPEAKER_DELETE_TOOL_NAMES",
    "SPEAKER_DELETE_TOOL_SPECS",
    "tool_delete_speaker",
]
