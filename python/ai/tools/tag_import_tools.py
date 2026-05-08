from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Set

from ..chat_tools import ChatToolSpec

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


TAG_IMPORT_TOOL_NAMES = (
    "import_tag_csv",
    "prepare_tag_import",
)


TAG_IMPORT_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "import_tag_csv": ChatToolSpec(
        name="import_tag_csv",
        description=(
            "Import a CSV file as a custom tag list. Matches CSV rows to project concept IDs "
            "by label (case-insensitive), numeric ID, or fuzzy match (edit distance <= 1). "
            "When dryRun=true returns a preview of matched/unmatched rows and asks for tag name. "
            "When dryRun=false and tagName is provided, creates the tag and writes parse-tags.json. "
            "Always use dryRun=true first, then dryRun=false after explicit user confirmation."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["dryRun"],
            "properties": {
                "csvPath": {"type": "string", "maxLength": 512},
                "tagName": {"type": "string", "minLength": 1, "maxLength": 100},
                "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                "labelColumn": {"type": "string", "maxLength": 64},
                "dryRun": {"type": "boolean"},
                "matchAllVariants": {"type": "boolean", "default": True},
                "propagateToSpeakers": {"type": "boolean", "default": True},
            },
        },
    ),
    "prepare_tag_import": ChatToolSpec(
        name="prepare_tag_import",
        description=(
            "Create or update a tag with a list of concept IDs and write to parse-tags.json. "
            "Always use dryRun=true first to preview, then dryRun=false after user confirms."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["tagName", "conceptIds", "dryRun"],
            "properties": {
                "tagName": {"type": "string", "minLength": 1, "maxLength": 100},
                "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                "conceptIds": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 500,
                    "items": {"type": "string", "minLength": 1, "maxLength": 64},
                },
                "dryRun": {"type": "boolean"},
                "propagateToSpeakers": {"type": "boolean", "default": True},
            },
        },
    ),
}


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    deduped: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _base_concept_label(label: str) -> str:
    return str(label or "").split(" (")[0].strip().lower()


def _annotation_file_is_tag_import_target(path: Path) -> bool:
    name = path.name
    if not name.endswith(".json"):
        return False
    if name.endswith(".parse.json"):
        return False
    if ".bak" in name or name.endswith(".tmp"):
        return False
    if name in {"manifest.json", "parse-enrichments.json"}:
        return False
    return True


def _collect_annotation_concept_ids(value: Any) -> Set[str]:
    concept_ids: Set[str] = set()
    if isinstance(value, dict):
        for key in ("concept_id", "conceptId"):
            raw_id = value.get(key)
            if raw_id is not None and str(raw_id).strip():
                concept_ids.add(str(raw_id).strip())
        for nested in value.values():
            concept_ids.update(_collect_annotation_concept_ids(nested))
    elif isinstance(value, list):
        for item in value:
            concept_ids.update(_collect_annotation_concept_ids(item))
    return concept_ids


def _write_json_atomic(path: Path, payload: Any) -> None:
    import json as _json
    import os as _os

    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        _json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        _os.fsync(handle.fileno())
    _os.replace(tmp_path, path)


def _propagate_tag_to_speaker_annotations(tools: "ParseChatTools", tag_id: str, concept_ids: List[str]) -> Dict[str, int]:
    import datetime as _datetime
    import json as _json
    import shutil as _shutil

    annotations_dir = tools.project_root / "annotations"
    if not annotations_dir.is_dir():
        return {"propagatedSpeakerCount": 0, "propagatedConceptAssignments": 0}

    target_concept_ids = set(concept_ids)
    timestamp = _datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    modified_speakers = 0
    assignments_added = 0
    for path in sorted(annotations_dir.glob("*.json")):
        if not _annotation_file_is_tag_import_target(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                record = _json.load(handle)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue
        present_concept_ids = _collect_annotation_concept_ids(record) & target_concept_ids
        if not present_concept_ids:
            continue
        concept_tags = record.get("concept_tags")
        if not isinstance(concept_tags, dict):
            concept_tags = {}
        file_assignments_added = 0
        for concept_id in sorted(present_concept_ids):
            raw_tag_ids = concept_tags.get(concept_id)
            tag_ids = [str(raw_tag_id) for raw_tag_id in raw_tag_ids] if isinstance(raw_tag_ids, list) else []
            if tag_id in tag_ids:
                continue
            tag_ids.append(tag_id)
            concept_tags[concept_id] = tag_ids
            file_assignments_added += 1
        if not file_assignments_added:
            continue
        backup_path = path.with_name("{0}.bak-{1}-pre-tag-import".format(path.name, timestamp))
        _shutil.copy2(path, backup_path)
        record["concept_tags"] = concept_tags
        _write_json_atomic(path, record)
        modified_speakers += 1
        assignments_added += file_assignments_added
    return {
        "propagatedSpeakerCount": modified_speakers,
        "propagatedConceptAssignments": assignments_added,
    }


def tool_import_tag_csv(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Match CSV rows to project concept IDs and optionally create a tag."""
    import csv as _csv

    raw_path = str(args.get("csvPath") or "").strip()
    tag_name = str(args.get("tagName") or "").strip()
    color = str(args.get("color") or "#4461d4").strip()
    label_column = str(args.get("labelColumn") or "").strip()
    dry_run = bool(args.get("dryRun", True))
    match_all_variants = bool(args.get("matchAllVariants", True))
    propagate_to_speakers = bool(args.get("propagateToSpeakers", True))

    if raw_path:
        csv_path = Path(raw_path).expanduser()
        if not csv_path.is_absolute():
            csv_path = tools.project_root / csv_path
        csv_path = csv_path.resolve()
    else:
        csv_path = tools.project_root / "concepts.csv"

    if not csv_path.exists():
        return {"ok": False, "error": "CSV file not found: {0}".format(csv_path)}

    project_concepts = tools._load_project_concepts()
    if not project_concepts:
        return {"ok": False, "error": "No project concepts loaded. concepts.csv not found in project root."}

    label_to_id: Dict[str, str] = {c["label"].lower(): c["id"] for c in project_concepts}
    id_to_label: Dict[str, str] = {c["id"]: c["label"] for c in project_concepts}
    base_label_to_ids: Dict[str, List[str]] = {}
    for concept in project_concepts:
        concept_id = str(concept.get("id") or "").strip()
        base_label = _base_concept_label(str(concept.get("label") or ""))
        if concept_id and base_label:
            base_label_to_ids.setdefault(base_label, []).append(concept_id)

    delimiter = ","
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            sample = f.read(8192)
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters=",\t;")
            delimiter = dialect.delimiter
        except Exception:
            pass
    except Exception as exc:
        return {"ok": False, "error": "Could not read CSV: {0}".format(exc)}

    csv_rows: list = []
    fieldnames: list = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f, delimiter=delimiter)
            fieldnames = list(reader.fieldnames or [])
            csv_rows = [dict(row) for row in reader]
    except Exception as exc:
        return {"ok": False, "error": "CSV parse error: {0}".format(exc)}

    if not label_column:
        hints = {"concept", "label", "english", "name", "gloss", "concept_en"}
        for col in fieldnames:
            if col.lower() in hints:
                label_column = col
                break
        if not label_column and fieldnames:
            label_column = fieldnames[0]

    matched: list = []
    unmatched: list = []

    def _edit_distance(a: str, b: str) -> int:
        # Damerau-Levenshtein keeps the one-character fuzzy fallback useful for
        # field-list typos such as adjacent transpositions (for example dgo→dog).
        a, b = a.lower(), b.lower()
        len_a = len(a)
        len_b = len(b)
        distances = [[0] * (len_b + 1) for _ in range(len_a + 1)]
        for i in range(len_a + 1):
            distances[i][0] = i
        for j in range(len_b + 1):
            distances[0][j] = j
        for i in range(1, len_a + 1):
            for j in range(1, len_b + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                distances[i][j] = min(
                    distances[i - 1][j] + 1,
                    distances[i][j - 1] + 1,
                    distances[i - 1][j - 1] + cost,
                )
                if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                    distances[i][j] = min(distances[i][j], distances[i - 2][j - 2] + 1)
        return distances[len_a][len_b]

    for row in csv_rows:
        raw_label = str(row.get(label_column) or "").strip()
        if not raw_label:
            continue
        raw_label_key = raw_label.lower()
        concept_ids: List[str] = []
        numeric_id_hit = raw_label in id_to_label
        if numeric_id_hit:
            concept_ids = [raw_label]
        else:
            exact_label_id = label_to_id.get(raw_label_key)
            base_ids = base_label_to_ids.get(raw_label_key, [])
            if match_all_variants:
                if base_ids:
                    concept_ids = list(base_ids)
                elif exact_label_id:
                    concept_ids = [exact_label_id]
            else:
                if base_ids:
                    concept_ids = [base_ids[0]]
                elif exact_label_id:
                    concept_ids = [exact_label_id]
        if not concept_ids:
            for base_label, candidate_ids in base_label_to_ids.items():
                if _edit_distance(raw_label_key, base_label) <= 1:
                    concept_ids = [candidate_ids[0]]
                    break
        concept_ids = _dedupe_preserve_order(concept_ids)
        if concept_ids:
            primary_id = concept_ids[0]
            matched.append(
                {
                    "csvLabel": raw_label,
                    "conceptId": primary_id,
                    "conceptIds": concept_ids,
                    "conceptLabel": id_to_label.get(primary_id, ""),
                }
            )
        else:
            unmatched.append({"csvLabel": raw_label})

    matched_concept_ids = _dedupe_preserve_order(
        [concept_id for entry in matched for concept_id in entry.get("conceptIds", [entry.get("conceptId", "")]) if concept_id]
    )

    result: Dict[str, Any] = {
        "ok": True,
        "matchedCount": len(matched),
        "unmatchedCount": len(unmatched),
        "matched": matched,
        "unmatched": unmatched,
        "matchedConceptCount": len(matched_concept_ids),
        "dryRun": dry_run,
    }

    if not tag_name:
        result["needsTagName"] = True
        result["message"] = "Found {0} matches and {1} unmatched. What should this tag be called?".format(len(matched), len(unmatched))
        return result

    if dry_run:
        result["preview"] = True
        result["message"] = "Will create tag {0!r} with {1} concepts. Call again with dryRun=false to confirm.".format(
            tag_name, len(matched_concept_ids)
        )
        return result

    return tool_prepare_tag_import(
        tools,
        {
            "tagName": tag_name,
            "color": color,
            "conceptIds": matched_concept_ids,
            "dryRun": False,
            "propagateToSpeakers": propagate_to_speakers,
        },
    )


def tool_prepare_tag_import(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a named tag with concept IDs in parse-tags.json."""
    import json as _json
    import re as _re

    tag_name = str(args.get("tagName") or "").strip()
    color = str(args.get("color") or "#4461d4").strip()
    concept_ids = _dedupe_preserve_order([str(c).strip() for c in (args.get("conceptIds") or []) if str(c).strip()])
    dry_run = bool(args.get("dryRun", True))
    propagate_to_speakers = bool(args.get("propagateToSpeakers", True))

    if not tag_name:
        return {"ok": False, "error": "tagName is required"}
    if not concept_ids:
        return {"ok": False, "error": "conceptIds must not be empty"}

    tag_id = _re.sub(r"[^a-z0-9]+", "-", tag_name.lower()).strip("-") or "tag"

    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "preview": True,
            "tagId": tag_id,
            "tagName": tag_name,
            "color": color,
            "conceptCount": len(concept_ids),
            "message": "Will create tag {0!r} (id={1}) with {2} concepts. Call with dryRun=false to apply.".format(tag_name, tag_id, len(concept_ids)),
        }

    tags: list = []
    if tools.tags_path.exists():
        try:
            with open(tools.tags_path, "r", encoding="utf-8") as f:
                existing = _json.load(f)
            if isinstance(existing, list):
                tags = existing
        except Exception:
            tags = []

    found = False
    assigned_count = len(concept_ids)
    for tag in tags:
        if tag.get("id") == tag_id:
            existing_ids = set(tag.get("concepts") or [])
            existing_ids.update(concept_ids)
            tag["concepts"] = sorted(existing_ids)
            assigned_count = len(tag["concepts"])
            tag["label"] = tag_name
            tag["color"] = color
            found = True
            break
    if not found:
        tags.append(
            {
                "id": tag_id,
                "label": tag_name,
                "color": color,
                "concepts": sorted(set(concept_ids)),
            }
        )

    try:
        with open(tools.tags_path, "w", encoding="utf-8") as f:
            _json.dump(tags, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        return {"ok": False, "error": "Failed to write parse-tags.json: {0}".format(exc)}

    propagation = {"propagatedSpeakerCount": 0, "propagatedConceptAssignments": 0}
    if propagate_to_speakers:
        try:
            propagation = _propagate_tag_to_speaker_annotations(tools, tag_id, concept_ids)
        except Exception as exc:
            return {"ok": False, "error": "Failed to propagate tag to speaker annotations: {0}".format(exc)}

    return {
        "ok": True,
        "dryRun": False,
        "tagId": tag_id,
        "tagName": tag_name,
        "color": color,
        "assignedCount": assigned_count,
        "totalTagsInFile": len(tags),
        **propagation,
        "message": "Tag {0!r} created with {1} concepts. Refresh Compare to see it.".format(tag_name, assigned_count),
    }


TAG_IMPORT_TOOL_HANDLERS = {
    "import_tag_csv": tool_import_tag_csv,
    "prepare_tag_import": tool_prepare_tag_import,
}
