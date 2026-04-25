"""Workspace/frontend configuration helpers for the PARSE HTTP server."""

from __future__ import annotations

import copy
import csv
import json
import pathlib
from typing import Any, Dict, List, Optional


def _read_json_dict(path: pathlib.Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _collect_speakers(project_payload: Dict[str, Any], source_index_payload: Dict[str, Any]) -> List[str]:
    speakers: List[str] = []

    speakers_value = project_payload.get("speakers")
    if isinstance(speakers_value, dict):
        speakers.extend(str(key).strip() for key in speakers_value.keys() if str(key).strip())
    elif isinstance(speakers_value, list):
        speakers.extend(str(item).strip() for item in speakers_value if str(item).strip())

    source_speakers = source_index_payload.get("speakers")
    if isinstance(source_speakers, dict):
        speakers.extend(str(key).strip() for key in source_speakers.keys() if str(key).strip())

    return sorted(dict.fromkeys(speakers))


def _load_concepts(project_root: pathlib.Path) -> List[Dict[str, Any]]:
    concepts_path = project_root / "concepts.csv"
    concepts: List[Dict[str, Any]] = []
    if not concepts_path.exists():
        return concepts

    with concepts_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cid = str(row.get("id") or "").strip()
            label = str(row.get("concept_en") or "").strip()
            if not (cid and label):
                continue

            entry: Dict[str, Any] = {"id": cid, "label": label}
            survey_item = str(row.get("survey_item") or "").strip()
            if survey_item:
                entry["survey_item"] = survey_item

            custom_order_raw = str(row.get("custom_order") or "").strip()
            if custom_order_raw:
                try:
                    entry["custom_order"] = int(custom_order_raw)
                except ValueError:
                    try:
                        entry["custom_order"] = float(custom_order_raw)
                    except ValueError:
                        pass
            concepts.append(entry)

    return concepts


def build_workspace_frontend_config(
    project_root: pathlib.Path,
    base_config: Optional[Dict[str, Any]] = None,
    *,
    schema_version: int,
) -> Dict[str, Any]:
    root = project_root.resolve()
    config = copy.deepcopy(base_config) if isinstance(base_config, dict) else {}

    project_payload = _read_json_dict(root / "project.json")
    source_index_payload = _read_json_dict(root / "source_index.json")
    speakers = _collect_speakers(project_payload, source_index_payload)
    concepts = _load_concepts(root)

    language_block = project_payload.get("language") if isinstance(project_payload.get("language"), dict) else {}
    language_code = str(
        project_payload.get("language_code")
        or language_block.get("code")
        or config.get("language_code")
        or "und"
    ).strip() or "und"
    project_name = str(
        project_payload.get("project_name")
        or project_payload.get("name")
        or config.get("project_name")
        or "PARSE"
    ).strip() or "PARSE"

    config["project_name"] = project_name
    config["language_code"] = language_code
    config["speakers"] = speakers
    config["concepts"] = concepts
    config["audio_dir"] = str(project_payload.get("audio_dir") or config.get("audio_dir") or "audio")
    config["annotations_dir"] = str(project_payload.get("annotations_dir") or config.get("annotations_dir") or "annotations")
    config["schema_version"] = schema_version
    return config
