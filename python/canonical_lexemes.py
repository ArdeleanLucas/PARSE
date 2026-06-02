"""Canonical lexeme storage for PARSE compare bundles.

Selections live in parse-enrichments.json under
``manual_overrides.canonical_lexemes`` because they are review decisions, not
survey metadata. Writes use a temp+rename pattern to avoid torn decisions files.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping

ENRICHMENTS_FILENAME = "parse-enrichments.json"


@dataclass(frozen=True)
class CanonicalLexemeError(Exception):
    status: HTTPStatus
    message: str
    repair_hint: str | None = None

    def __str__(self) -> str:
        if self.repair_hint:
            return json.dumps({"message": self.message, "repair_hint": self.repair_hint}, ensure_ascii=False)
        return self.message


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def enrichments_path(project_root: Path) -> Path:
    return Path(project_root) / ENRICHMENTS_FILENAME


def load_enrichments(project_root: Path) -> dict[str, Any]:
    path = enrichments_path(project_root)
    if not path.exists():
        return {"manual_overrides": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"manual_overrides": {}}
    if not isinstance(payload, dict):
        return {"manual_overrides": {}}
    _promote_safe_legacy_concept_keys(project_root, payload)
    return payload


def _promote_safe_legacy_concept_keys(project_root: Path, payload: dict[str, Any]) -> None:
    """Read-time safety net: promote decision data from SAFE legacy concept keys
    (grouped concepts' old ``source_item`` keys) to their canonical csv-id keys,
    so safe data stays visible even if the on-disk migration has not run. Never
    touches the 9 ambiguous/collided keys, and never raises — a failure here must
    not break enrichment loading. See python/migration/concept_key_namespace.py.
    """
    try:
        try:
            from migration.concept_key_namespace import (
                build_remap_for_workspace,
                promote_safe_legacy_keys,
                scan_legacy_keys,
            )
        except ImportError:
            from python.migration.concept_key_namespace import (  # type: ignore
                build_remap_for_workspace,
                promote_safe_legacy_keys,
                scan_legacy_keys,
            )
        remap = build_remap_for_workspace(project_root)
        if not remap:
            return
        promote_safe_legacy_keys(payload, remap)
        pending = [e for e in scan_legacy_keys(payload, remap) if e["classification"] == "AMBIGUOUS"]
        if pending:
            logging.getLogger(__name__).warning(
                "parse-enrichments.json has %d ambiguous legacy concept key(s) needing "
                "migration triage (run python/scripts/migrate_concept_key_namespace.py): %s",
                len(pending), pending,
            )
    except Exception:  # pragma: no cover - defensive: loading must never fail here
        return


def save_enrichments_atomic(project_root: Path, payload: Mapping[str, Any]) -> None:
    path = enrichments_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _manual_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    overrides = payload.get("manual_overrides")
    if not isinstance(overrides, dict):
        overrides = {}
        payload["manual_overrides"] = overrides
    return overrides


def normalize_canonical_lexemes(raw: object) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    if not isinstance(raw, Mapping):
        return out
    for bundle_id, speaker_map in raw.items():
        bid = str(bundle_id or "").strip()
        if not bid or not isinstance(speaker_map, Mapping):
            continue
        clean_speakers: dict[str, dict[str, Any]] = {}
        for speaker, selection in speaker_map.items():
            speaker_id = str(speaker or "").strip()
            if not speaker_id or not isinstance(selection, Mapping):
                continue
            row_id = str(selection.get("csv_row_id") or "").strip()
            if not row_id:
                continue
            clean: dict[str, Any] = {"csv_row_id": row_id}
            for key in ("survey_id", "source_item", "bucket_key", "variant_label", "source", "selected_at"):
                value = selection.get(key)
                if value is not None and str(value).strip():
                    clean[key] = str(value).strip()
            if "realization_index" in selection and selection.get("realization_index") is not None:
                try:
                    idx = int(selection.get("realization_index"))
                    if idx >= 0:
                        clean["realization_index"] = idx
                except (TypeError, ValueError):
                    pass
            clean_speakers[speaker_id] = clean
        if clean_speakers:
            out[bid] = clean_speakers
    return out


def load_canonical_lexemes(project_root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    payload = load_enrichments(project_root)
    try:
        from migration.concept_uid_enrichments import promote_legacy_uid_keys

        promote_legacy_uid_keys(project_root, payload)
    except Exception:
        pass
    overrides = payload.get("manual_overrides") if isinstance(payload, Mapping) else None
    raw = overrides.get("canonical_lexemes") if isinstance(overrides, Mapping) else None
    return normalize_canonical_lexemes(raw)


def store_canonical_selection(
    project_root: Path,
    *,
    bundle_id: str,
    speaker: str,
    selection: Mapping[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    payload = load_enrichments(project_root)
    payload = copy.deepcopy(payload)
    overrides = _manual_overrides(payload)
    canonical = normalize_canonical_lexemes(overrides.get("canonical_lexemes"))
    speaker_id = str(speaker or "").strip()
    bid = str(bundle_id or "").strip()
    if not bid or not speaker_id:
        raise CanonicalLexemeError(HTTPStatus.BAD_REQUEST, "bundle_id and speaker are required")
    try:
        from migration.concept_uid_enrichments import resolve_legacy_key_to_uid

        storage_key = resolve_legacy_key_to_uid(project_root, bid) or bid
    except Exception:
        storage_key = bid
    clean = normalize_canonical_lexemes({storage_key: {speaker_id: selection}}).get(storage_key, {}).get(speaker_id)
    if not clean:
        raise CanonicalLexemeError(HTTPStatus.BAD_REQUEST, "csv_row_id is required")
    clean.setdefault("source", "manual")
    clean.setdefault("selected_at", utc_now_iso())
    canonical.setdefault(storage_key, {})[speaker_id] = clean
    overrides["canonical_lexemes"] = canonical
    save_enrichments_atomic(project_root, payload)
    return canonical


def delete_canonical_selection(project_root: Path, *, bundle_id: str, speaker: str) -> dict[str, dict[str, dict[str, Any]]]:
    payload = load_enrichments(project_root)
    payload = copy.deepcopy(payload)
    overrides = _manual_overrides(payload)
    canonical = normalize_canonical_lexemes(overrides.get("canonical_lexemes"))
    bid = str(bundle_id or "").strip()
    speaker_id = str(speaker or "").strip()
    try:
        from migration.concept_uid_enrichments import resolve_legacy_key_to_uid

        storage_key = resolve_legacy_key_to_uid(project_root, bid) or bid
    except Exception:
        storage_key = bid
    for key in {bid, storage_key}:
        if key in canonical:
            canonical[key].pop(speaker_id, None)
            if not canonical[key]:
                canonical.pop(key, None)
    overrides["canonical_lexemes"] = canonical
    save_enrichments_atomic(project_root, payload)
    return canonical


def copy_canonical_references(project_root: Path, *, source_row_id: str, sibling_row_id: str) -> bool:
    """Mirror selections that referenced ``source_row_id`` to the new sibling row."""

    payload = load_enrichments(project_root)
    payload = copy.deepcopy(payload)
    overrides = _manual_overrides(payload)
    canonical = normalize_canonical_lexemes(overrides.get("canonical_lexemes"))
    changed = False
    for speaker_map in canonical.values():
        for speaker, selection in list(speaker_map.items()):
            if selection.get("csv_row_id") == str(source_row_id):
                clone = dict(selection)
                clone["csv_row_id"] = str(sibling_row_id)
                speaker_map[speaker] = clone
                changed = True
    if changed:
        overrides["canonical_lexemes"] = canonical
        save_enrichments_atomic(project_root, payload)
    return changed


def drop_canonical_references_for(project_root: Path, *, row_id: str) -> bool:
    """Remove canonical lexeme selections that reference one deleted CSV row."""

    payload = load_enrichments(project_root)
    payload = copy.deepcopy(payload)
    overrides = _manual_overrides(payload)
    canonical = normalize_canonical_lexemes(overrides.get("canonical_lexemes"))
    target_id = str(row_id)
    changed = False
    for bundle_id, speaker_map in list(canonical.items()):
        for speaker, selection in list(speaker_map.items()):
            if selection.get("csv_row_id") == target_id:
                speaker_map.pop(speaker, None)
                changed = True
        if not speaker_map:
            canonical.pop(bundle_id, None)
    if changed:
        overrides["canonical_lexemes"] = canonical
        save_enrichments_atomic(project_root, payload)
    return changed
