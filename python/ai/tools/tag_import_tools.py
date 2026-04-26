from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

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
            },
        },
    ),
}


def tool_import_tag_csv(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Match CSV rows to project concept IDs and optionally create a tag."""
    import csv as _csv

    raw_path = str(args.get("csvPath") or "").strip()
    tag_name = str(args.get("tagName") or "").strip()
    color = str(args.get("color") or "#4461d4").strip()
    label_column = str(args.get("labelColumn") or "").strip()
    dry_run = bool(args.get("dryRun", True))

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
        a, b = a.lower(), b.lower()
        if len(a) > len(b):
            a, b = b, a
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if ca == cb else 1)))
            prev = curr
        return prev[-1]

    for row in csv_rows:
        raw_label = str(row.get(label_column) or "").strip()
        if not raw_label:
            continue
        concept_id = label_to_id.get(raw_label.lower())
        if not concept_id and raw_label in id_to_label:
            concept_id = raw_label
        if not concept_id:
            for lbl, cid in label_to_id.items():
                if _edit_distance(raw_label, lbl) <= 1:
                    concept_id = cid
                    break
        if concept_id:
            matched.append({"csvLabel": raw_label, "conceptId": concept_id, "conceptLabel": id_to_label.get(concept_id, "")})
        else:
            unmatched.append({"csvLabel": raw_label})

    result: Dict[str, Any] = {
        "ok": True,
        "matchedCount": len(matched),
        "unmatchedCount": len(unmatched),
        "matched": matched,
        "unmatched": unmatched,
        "dryRun": dry_run,
    }

    if not tag_name:
        result["needsTagName"] = True
        result["message"] = "Found {0} matches and {1} unmatched. What should this tag be called?".format(len(matched), len(unmatched))
        return result

    if dry_run:
        result["preview"] = True
        result["message"] = "Will create tag {0!r} with {1} concepts. Call again with dryRun=false to confirm.".format(tag_name, len(matched))
        return result

    concept_ids = [m["conceptId"] for m in matched]
    return tool_prepare_tag_import(
        tools,
        {
            "tagName": tag_name,
            "color": color,
            "conceptIds": concept_ids,
            "dryRun": False,
        },
    )


def tool_prepare_tag_import(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a named tag with concept IDs in parse-tags.json."""
    import json as _json
    import re as _re

    tag_name = str(args.get("tagName") or "").strip()
    color = str(args.get("color") or "#4461d4").strip()
    concept_ids = [str(c).strip() for c in (args.get("conceptIds") or []) if str(c).strip()]
    dry_run = bool(args.get("dryRun", True))

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
    for tag in tags:
        if tag.get("id") == tag_id:
            existing_ids = set(tag.get("concepts") or [])
            existing_ids.update(concept_ids)
            tag["concepts"] = sorted(existing_ids)
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

    return {
        "ok": True,
        "dryRun": False,
        "tagId": tag_id,
        "tagName": tag_name,
        "color": color,
        "assignedCount": len(concept_ids),
        "totalTagsInFile": len(tags),
        "message": "Tag {0!r} created with {1} concepts. Refresh Compare to see it.".format(tag_name, len(concept_ids)),
    }


TAG_IMPORT_TOOL_HANDLERS = {
    "import_tag_csv": tool_import_tag_csv,
    "prepare_tag_import": tool_prepare_tag_import,
}
