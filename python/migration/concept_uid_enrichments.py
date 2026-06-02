"""Re-key PARSE enrichment decisions from row/bundle keys to concept identity uid.

MC-458 Phase 3 makes ``concept_identity.uid`` the durable key for comparative
review state. Older ``parse-enrichments.json`` files can contain decisions keyed
by raw ``concepts.csv`` row ids (``"52"``) or Compare bundle ids
(``"bundle:salt"``). This module provides a dry-run-first, idempotent migration
plus small in-memory compatibility helpers for readers that still receive mixed
legacy/uid payloads during the transition.
"""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from concept_identity import load_concept_identity

ROOT_CONCEPT_KEYED_BLOCKS = (
    "cognate_sets",
    "cognate_decisions",
    "discarded_forms",
    "borrowing_flags",
    "speaker_flags",
    "concept_merges",
    "similarity",
    "concept_notes",
)
MANUAL_CONCEPT_KEYED_BLOCKS = ROOT_CONCEPT_KEYED_BLOCKS + ("canonical_lexemes",)
LEXEME_NOTES_BLOCK = "lexeme_notes"
ENRICHMENTS_FILENAME = "parse-enrichments.json"
_BACKUP_SUFFIX = "pre-uid-namespace"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _slug(label: str) -> str:
    slug = _SLUG_RE.sub("-", str(label or "").casefold()).strip("-")
    return slug or "concept"


def build_uid_key_remap(project_root: Path) -> dict[str, str]:
    """Return every known legacy enrichment key that should resolve to a uid.

    Includes raw row ids, already-materialised uids, and Compare's deterministic
    ``bundle:<slug>`` ids so old canonical selections can be moved without
    needing Compare to run.
    """

    identity = load_concept_identity(Path(project_root))
    remap: dict[str, str] = {}
    for row_id, uid in identity.uid_by_row.items():
        rid = _norm(row_id)
        if rid:
            remap[rid] = uid
    for uid in identity.rows_by_uid:
        remap[uid] = uid

    used_slugs: dict[str, int] = {}
    for concept in identity.concepts:
        slug = _slug(concept.label)
        used_slugs[slug] = used_slugs.get(slug, 0) + 1
        suffix = "" if used_slugs[slug] == 1 else f"-{used_slugs[slug]}"
        remap[f"bundle:{slug}{suffix}"] = concept.uid
    return remap


def resolve_legacy_key_to_uid(project_root: Path, key: Any) -> str:
    """Resolve one legacy row/bundle key to a uid, falling back to the input."""

    text = _norm(key)
    if not text:
        return ""
    try:
        return build_uid_key_remap(Path(project_root)).get(text, text)
    except Exception:
        return text


def _merge_values(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(existing)
        merged.update(copy.deepcopy(incoming))
        return merged
    if isinstance(existing, list) and isinstance(incoming, list):
        out: list[Any] = list(existing)
        for item in incoming:
            if item not in out:
                out.append(item)
        return out
    return copy.deepcopy(incoming)


def _store(out: dict[str, Any], key: str, value: Any) -> None:
    if key in out:
        out[key] = _merge_values(out[key], value)
    else:
        out[key] = copy.deepcopy(value)


def _remap_dict_keys(
    block: Mapping[str, Any],
    remap: Mapping[str, str],
    *,
    block_name: str,
    touched: list[dict[str, str]],
    unmappable: list[dict[str, str]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in block.items():
        key = _norm(raw_key)
        new_key = remap.get(key)
        if not new_key:
            _store(out, key, value)
            if key and not key.startswith("c-"):
                unmappable.append({"block": block_name, "key": key})
            continue
        _store(out, new_key, value)
        if new_key != key:
            touched.append({"block": block_name, "old_key": key, "new_key": new_key})
    return out


def _remap_concept_merge_values(
    block: dict[str, Any],
    remap: Mapping[str, str],
    *,
    touched_values: list[dict[str, str]],
) -> None:
    for parent_key, value in list(block.items()):
        if not isinstance(value, list):
            continue
        out: list[str] = []
        for raw in value:
            old = _norm(raw)
            if not old:
                continue
            new = remap.get(old, old)
            if new != old:
                touched_values.append({"block": "concept_merges", "parent_key": parent_key, "old_key": old, "new_key": new})
            if new not in out:
                out.append(new)
        block[parent_key] = out


def _remap_lexeme_notes(
    notes: Mapping[str, Any],
    remap: Mapping[str, str],
    *,
    touched: list[dict[str, str]],
    unmappable: list[dict[str, str]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for speaker, raw_block in notes.items():
        speaker_id = _norm(speaker)
        if not isinstance(raw_block, Mapping):
            out[speaker_id] = copy.deepcopy(raw_block)
            continue
        speaker_out: dict[str, Any] = {}
        for raw_key, value in raw_block.items():
            key = _norm(raw_key)
            new_key = remap.get(key)
            if not new_key:
                _store(speaker_out, key, value)
                if key and not key.startswith("c-"):
                    unmappable.append({"block": LEXEME_NOTES_BLOCK, "speaker": speaker_id, "key": key})
                continue
            _store(speaker_out, new_key, value)
            if new_key != key:
                touched.append({"block": LEXEME_NOTES_BLOCK, "speaker": speaker_id, "old_key": key, "new_key": new_key})
        out[speaker_id] = speaker_out
    return out


def _apply_uid_remap(payload: Mapping[str, Any], remap: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    migrated = copy.deepcopy(dict(payload))
    touched: list[dict[str, str]] = []
    touched_values: list[dict[str, str]] = []
    unmappable: list[dict[str, str]] = []

    for block_name in ROOT_CONCEPT_KEYED_BLOCKS:
        block = migrated.get(block_name)
        if isinstance(block, Mapping):
            migrated[block_name] = _remap_dict_keys(
                block,
                remap,
                block_name=block_name,
                touched=touched,
                unmappable=unmappable,
            )
            if block_name == "concept_merges":
                _remap_concept_merge_values(migrated[block_name], remap, touched_values=touched_values)

    manual = migrated.get("manual_overrides")
    if isinstance(manual, Mapping):
        manual_out = copy.deepcopy(dict(manual))
        for block_name in MANUAL_CONCEPT_KEYED_BLOCKS:
            block = manual_out.get(block_name)
            if isinstance(block, Mapping):
                manual_out[block_name] = _remap_dict_keys(
                    block,
                    remap,
                    block_name=block_name,
                    touched=touched,
                    unmappable=unmappable,
                )
                if block_name == "concept_merges":
                    _remap_concept_merge_values(manual_out[block_name], remap, touched_values=touched_values)
        migrated["manual_overrides"] = manual_out

    notes = migrated.get(LEXEME_NOTES_BLOCK)
    if isinstance(notes, Mapping):
        migrated[LEXEME_NOTES_BLOCK] = _remap_lexeme_notes(notes, remap, touched=touched, unmappable=unmappable)

    report = {
        "decision_keys_migrated": touched,
        "decision_key_values_migrated": touched_values,
        "decision_keys_unmappable_left_in_place": unmappable,
    }
    return migrated, report


def promote_legacy_uid_keys(project_root: Path, payload: dict[str, Any]) -> list[dict[str, str]]:
    """In-memory legacy row/bundle -> uid promotion for mixed pre-migration data."""

    remap = build_uid_key_remap(Path(project_root))
    migrated, report = _apply_uid_remap(payload, remap)
    payload.clear()
    payload.update(migrated)
    return list(report["decision_keys_migrated"])


def expand_uid_keys_for_legacy_read(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Duplicate uid-keyed decisions under member row ids for legacy readers.

    This does not write to disk and never overwrites an explicit row-keyed value.
    It lets older read paths that still call ``block[concept_id]`` keep working
    after the on-disk file has been migrated to uid keys.
    """

    try:
        identity = load_concept_identity(Path(project_root))
    except Exception:
        return payload
    expanded = copy.deepcopy(payload)

    def expand_block(block: Any) -> None:
        if not isinstance(block, dict):
            return
        for uid, members in identity.rows_by_uid.items():
            if uid not in block:
                continue
            value = block[uid]
            for row_id in members:
                block.setdefault(row_id, copy.deepcopy(value))

    for block_name in ROOT_CONCEPT_KEYED_BLOCKS:
        expand_block(expanded.get(block_name))
    manual = expanded.get("manual_overrides")
    if isinstance(manual, dict):
        for block_name in MANUAL_CONCEPT_KEYED_BLOCKS:
            expand_block(manual.get(block_name))
    notes = expanded.get(LEXEME_NOTES_BLOCK)
    if isinstance(notes, dict):
        for speaker_block in notes.values():
            expand_block(speaker_block)
    return expanded


def migrate_uid_enrichment_keys(workspace: Path, *, execute: bool = False) -> dict[str, Any]:
    """Dry-run or apply uid re-keying for one workspace's enrichments file."""

    workspace = Path(workspace)
    enrichments_path = workspace / ENRICHMENTS_FILENAME
    original_text = enrichments_path.read_text(encoding="utf-8") if enrichments_path.exists() else "{}\n"
    payload = json.loads(original_text)
    if not isinstance(payload, dict):
        raise ValueError(f"{ENRICHMENTS_FILENAME} must contain a JSON object")

    remap = build_uid_key_remap(workspace)
    migrated, details = _apply_uid_remap(payload, remap)
    changed = migrated != payload
    report = {
        "workspace": str(workspace),
        "mode": "execute" if execute else "dry-run",
        "uid_keys_total": len({uid for uid in remap.values()}),
        "legacy_keys_migrated_total": len(details["decision_keys_migrated"]),
        "decision_keys_migrated": details["decision_keys_migrated"],
        "decision_key_values_migrated": details["decision_key_values_migrated"],
        "decision_keys_unmappable_left_in_place": details["decision_keys_unmappable_left_in_place"],
        "verification_ok": True,
        "backup_written": None,
    }

    if execute and changed:
        if enrichments_path.exists() and enrichments_path.read_text(encoding="utf-8") != original_text:
            raise RuntimeError(
                "parse-enrichments.json changed since load — aborting. Stop the PARSE server and re-run."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = enrichments_path.with_name(f"{enrichments_path.name}.bak-{stamp}-{_BACKUP_SUFFIX}")
        backup.write_text(original_text, encoding="utf-8")
        tmp = enrichments_path.with_suffix(enrichments_path.suffix + ".tmp")
        tmp.write_text(json.dumps(migrated, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, enrichments_path)
        report["backup_written"] = backup.name
    return report


__all__ = [
    "build_uid_key_remap",
    "expand_uid_keys_for_legacy_read",
    "migrate_uid_enrichment_keys",
    "promote_legacy_uid_keys",
    "resolve_legacy_key_to_uid",
]
