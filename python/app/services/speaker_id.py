"""Pure speaker-id normalizer shared by HTTP routes and chat tools.

The HTTP route at ``server_routes/annotate.py::_normalize_speaker_id``
and the chat-tool helper at ``ai/tools/tag_filter_tools.py::_normalize_speaker``
were textbook duplicates with mildly different error wording. Both now
delegate here so future changes (e.g. allowing ``:`` for nested speakers)
land in one place.
"""
from __future__ import annotations

from typing import Any


def normalize_speaker_id(raw_speaker: Any) -> str:
    """Return a sanitized speaker id or raise ValueError.

    Rejects:
      * empty / whitespace-only input        ``"speaker is required"``
      * the literal ``.`` and ``..``         ``"Invalid speaker id"``
      * embedded NUL bytes                   ``"speaker contains an invalid null byte"``
      * path separators (``/`` or ``\\``)    ``"speaker must not contain path separators"``
      * inputs longer than 200 characters    ``"speaker is too long"``

    Error wording matches the HTTP route's previous messages so external
    API consumers see no observable change.
    """
    speaker = str(raw_speaker or "").strip()
    if not speaker:
        raise ValueError("speaker is required")
    if speaker in {".", ".."}:
        raise ValueError("Invalid speaker id")
    if "\x00" in speaker:
        raise ValueError("speaker contains an invalid null byte")
    if "/" in speaker or "\\" in speaker:
        raise ValueError("speaker must not contain path separators")
    if len(speaker) > 200:
        raise ValueError("speaker is too long")
    return speaker


__all__ = ["normalize_speaker_id"]
