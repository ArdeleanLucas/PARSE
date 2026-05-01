"""JSON-backed global concept-tag storage for PARSE.

The tags file is intentionally outside the per-workspace project tree by
default: concept tag vocabulary and attachments are global across workspaces.
Set ``PARSE_TAGS_PATH`` in tests or isolated runtimes to redirect storage.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict


class Tag(TypedDict):
    id: str
    name: str
    color: str
    createdAt: str


class TagsData(TypedDict):
    version: int
    tags: list[Tag]
    attachments: dict[str, list[str]]


class TagValidationError(ValueError):
    """Raised when a tag payload fails validation."""


class TagNameConflictError(ValueError):
    """Raised when a tag name already exists case-insensitively."""


class UnknownTagError(KeyError):
    """Raised when attaching a concept to a tag that is not in vocabulary."""


DEFAULT_PATH = Path.home() / ".parse" / "tags.json"
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_LOCK = threading.RLock()


def _path() -> Path:
    return Path(os.environ.get("PARSE_TAGS_PATH", str(DEFAULT_PATH)))


def _empty() -> TagsData:
    return {"version": 1, "tags": [], "attachments": {}}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_name(name: Any) -> str:
    if not isinstance(name, str):
        raise TagValidationError("Tag name must be a non-empty string")
    cleaned = name.strip()
    if not cleaned:
        raise TagValidationError("Tag name must be a non-empty string")
    return cleaned


def _validate_color(color: Any) -> str:
    if not isinstance(color, str) or not _COLOR_RE.fullmatch(color):
        raise TagValidationError("Tag color must be a six-digit hex color like #3554B8")
    return color


def _validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TagValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _normalize_data(raw: Any) -> TagsData:
    if not isinstance(raw, dict):
        return _empty()

    tags: list[Tag] = []
    seen_tag_ids: set[str] = set()
    for entry in raw.get("tags", []):
        if not isinstance(entry, dict):
            continue
        tag_id = entry.get("id")
        name = entry.get("name")
        color = entry.get("color")
        created_at = entry.get("createdAt")
        if not isinstance(tag_id, str) or not tag_id or tag_id in seen_tag_ids:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(color, str) or not _COLOR_RE.fullmatch(color):
            continue
        if not isinstance(created_at, str) or not created_at.strip():
            continue
        seen_tag_ids.add(tag_id)
        tags.append({"id": tag_id, "name": name, "color": color, "createdAt": created_at})

    attachments: dict[str, list[str]] = {}
    raw_attachments = raw.get("attachments", {})
    if isinstance(raw_attachments, dict):
        for concept_id, tag_ids in raw_attachments.items():
            if not isinstance(concept_id, str) or not concept_id.strip() or not isinstance(tag_ids, list):
                continue
            cleaned_ids: list[str] = []
            for tag_id in tag_ids:
                if isinstance(tag_id, str) and tag_id in seen_tag_ids and tag_id not in cleaned_ids:
                    cleaned_ids.append(tag_id)
            if cleaned_ids:
                attachments[concept_id] = cleaned_ids

    return {"version": 1, "tags": tags, "attachments": attachments}


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


def create_tag(name: Any, color: Any) -> Tag:
    with _LOCK:
        clean_name = _validate_name(name)
        clean_color = _validate_color(color)
        data = _load()
        if any(t["name"].casefold() == clean_name.casefold() for t in data["tags"]):
            raise TagNameConflictError(f"Tag '{clean_name}' already exists")
        tag: Tag = {
            "id": f"tag_{uuid.uuid4().hex[:12]}",
            "name": clean_name,
            "color": clean_color,
            "createdAt": _utc_now_iso(),
        }
        data["tags"].append(tag)
        _save(data)
        return tag


def delete_tag(tag_id: str) -> None:
    with _LOCK:
        clean_tag_id = _validate_id(tag_id, "tag_id")
        data = _load()
        data["tags"] = [t for t in data["tags"] if t["id"] != clean_tag_id]
        for concept_id in list(data["attachments"]):
            data["attachments"][concept_id] = [t for t in data["attachments"][concept_id] if t != clean_tag_id]
            if not data["attachments"][concept_id]:
                del data["attachments"][concept_id]
        _save(data)


def attach(concept_id: str, tag_id: str) -> None:
    with _LOCK:
        clean_concept_id = _validate_id(concept_id, "concept_id")
        clean_tag_id = _validate_id(tag_id, "tag_id")
        data = _load()
        if not any(tag["id"] == clean_tag_id for tag in data["tags"]):
            raise UnknownTagError(clean_tag_id)
        ids = data["attachments"].setdefault(clean_concept_id, [])
        if clean_tag_id not in ids:
            ids.append(clean_tag_id)
        _save(data)


def detach(concept_id: str, tag_id: str) -> None:
    with _LOCK:
        clean_concept_id = _validate_id(concept_id, "concept_id")
        clean_tag_id = _validate_id(tag_id, "tag_id")
        data = _load()
        if clean_concept_id in data["attachments"]:
            data["attachments"][clean_concept_id] = [
                t for t in data["attachments"][clean_concept_id] if t != clean_tag_id
            ]
            if not data["attachments"][clean_concept_id]:
                del data["attachments"][clean_concept_id]
        _save(data)
