"""JSON-backed global concept-tag storage for PARSE.

The tags file is intentionally outside the per-workspace project tree by
default: concept tag vocabulary and attachments are global across workspaces.
Set ``PARSE_TAGS_PATH`` in tests or isolated runtimes to redirect storage.

Current on-disk version 2 matches the React ``useTagStore`` model:
``{"version": 2, "tags": [{id, label, color, concepts, lexemeTargets}]}``.
Version 1 files from the short-lived split ``{tags, attachments}`` shape are
migrated on load by folding concept attachments back into each tag.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, TypedDict


class Tag(TypedDict):
    id: str
    label: str
    color: str
    concepts: list[str]
    lexemeTargets: list[str]


class TagsData(TypedDict):
    version: int
    tags: list[Tag]


class TagValidationError(ValueError):
    """Raised when a full-list tag payload fails validation."""


DEFAULT_PATH = Path.home() / ".parse" / "tags.json"
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_LEXEME_KEY_RE = re.compile(r"^[^:]+::[^:]+$")
_LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()


def _path() -> Path:
    return Path(os.environ.get("PARSE_TAGS_PATH", str(DEFAULT_PATH)))


def _empty() -> TagsData:
    return {"version": 2, "tags": []}


def _warn_dropped(reason: str) -> None:
    _LOGGER.warning("Dropped malformed tags-store entry: %s", reason)


def _migrate_v1_to_v2(raw: dict[str, Any]) -> TagsData:
    tags_in = raw.get("tags", [])
    attachments = raw.get("attachments", {})
    by_tag: dict[str, list[str]] = {}

    if isinstance(attachments, dict):
        for concept_id, tag_ids in attachments.items():
            if not isinstance(concept_id, str) or not isinstance(tag_ids, list):
                continue
            for tag_id in tag_ids:
                if isinstance(tag_id, str):
                    by_tag.setdefault(tag_id, []).append(concept_id)

    out_tags: list[Tag] = []
    if not isinstance(tags_in, list):
        return _empty()

    for entry in tags_in:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        tag_id = entry["id"]
        label = entry.get("name") or entry.get("label") or "Untitled"
        color = entry.get("color") or "#6b7280"
        out_tags.append(
            {
                "id": tag_id,
                "label": label,
                "color": color,
                "concepts": list(by_tag.get(tag_id, [])),
                "lexemeTargets": [],
            }
        )
    return {"version": 2, "tags": out_tags}


def _validate_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TagValidationError("Tag id must be a non-empty string")
    return value.strip()


def _validate_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TagValidationError("Tag label must be a non-empty string")
    return value.strip()


def _validate_color(value: Any) -> str:
    if not isinstance(value, str) or not _COLOR_RE.fullmatch(value):
        raise TagValidationError("Tag color must be a six-digit hex color like #3554B8")
    return value


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise TagValidationError(f"Tag {field} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TagValidationError(f"Tag {field} must be a list of strings")
    return list(value)


def _validate_lexeme_targets(value: Any) -> list[str]:
    targets = _validate_string_list(value, "lexemeTargets")
    if not all(_LEXEME_KEY_RE.fullmatch(target) for target in targets):
        raise TagValidationError("Tag lexemeTargets must use '<speaker>::<conceptId>' keys")
    return targets


def _clean_tag(entry: Any, seen_ids: set[str], seen_labels: set[str]) -> Tag:
    if not isinstance(entry, dict):
        raise TagValidationError("Tag entry must be an object")

    tag_id = _validate_id(entry.get("id"))
    if tag_id in seen_ids:
        raise TagValidationError(f"duplicate tag id '{tag_id}'")

    label = _validate_label(entry.get("label"))
    label_key = label.casefold()
    if label_key in seen_labels:
        raise TagValidationError(f"duplicate label '{label}'")

    tag = {
        "id": tag_id,
        "label": label,
        "color": _validate_color(entry.get("color")),
        "concepts": _validate_string_list(entry.get("concepts", []), "concepts"),
        "lexemeTargets": _validate_lexeme_targets(entry.get("lexemeTargets", [])),
    }
    seen_ids.add(tag_id)
    seen_labels.add(label_key)
    return tag


def _normalize_data(raw: Any) -> TagsData:
    if not isinstance(raw, dict):
        _warn_dropped("root payload is not an object")
        return _empty()

    if raw.get("version") == 1 and "attachments" in raw:
        raw = _migrate_v1_to_v2(raw)

    raw_tags = raw.get("tags", [])
    if not isinstance(raw_tags, list):
        _warn_dropped("tags payload is not a list")
        return _empty()

    tags: list[Tag] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for entry in raw_tags:
        try:
            tags.append(_clean_tag(entry, seen_ids, seen_labels))
        except TagValidationError as exc:
            _warn_dropped(str(exc))
    return {"version": 2, "tags": tags}


def _load() -> TagsData:
    p = _path()
    if not p.exists():
        return _empty()
    return _normalize_data(json.loads(p.read_text(encoding="utf-8")))


def _save(data: TagsData) -> None:
    normalized = _normalize_data(data)
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)  # atomic on POSIX


def fetch_all() -> TagsData:
    with _LOCK:
        return _load()


def replace_all(tags: list[Tag]) -> TagsData:
    """Atomically replace the full tag list with a validated version-2 payload."""
    with _LOCK:
        if not isinstance(tags, list):
            raise TagValidationError("tags must be a list")

        seen_ids: set[str] = set()
        seen_labels: set[str] = set()
        normalized_tags = [_clean_tag(entry, seen_ids, seen_labels) for entry in tags]
        normalized: TagsData = {"version": 2, "tags": normalized_tags}
        _save(normalized)
        return normalized
