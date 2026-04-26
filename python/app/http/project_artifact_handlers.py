"""Helpers for PARSE tag and export HTTP endpoints."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Mapping, Tuple

from .job_observability_handlers import JsonResponseSpec


@dataclass(frozen=True)
class BinaryResponseSpec:
    status: HTTPStatus
    content_type: str
    content_disposition: str
    body: bytes


@dataclass(frozen=True)
class ProjectArtifactHandlerError(Exception):
    status: HTTPStatus
    message: str

    def __str__(self) -> str:
        return self.message


ReadJsonFile = Callable[[pathlib.Path, Dict[str, Any]], Dict[str, Any]]
DefaultPayloadFactory = Callable[[], Dict[str, Any]]
ConceptSortKey = Callable[[str], Any]
WordlistExporter = Callable[[pathlib.Path, pathlib.Path, pathlib.Path], None]



def build_get_tags_response(*, project_root: pathlib.Path) -> JsonResponseSpec:
    tags_path = project_root / "parse-tags.json"
    if not tags_path.exists():
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"tags": []})

    try:
        with open(tags_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:  # preserve route-local 500 behavior
        raise ProjectArtifactHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc

    if isinstance(data, list):
        return JsonResponseSpec(status=HTTPStatus.OK, payload={"tags": data})
    return JsonResponseSpec(status=HTTPStatus.OK, payload={"tags": []})



def build_post_tags_merge_response(
    body: Mapping[str, Any],
    *,
    project_root: pathlib.Path,
) -> JsonResponseSpec:
    incoming = body.get("tags")
    if not isinstance(incoming, list):
        raise ProjectArtifactHandlerError(HTTPStatus.BAD_REQUEST, "tags must be an array")

    try:
        tags_path = project_root / "parse-tags.json"
        existing: list[Any] = []
        if tags_path.exists():
            try:
                with open(tags_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if isinstance(raw, list):
                    existing = raw
            except Exception:
                existing = []

        existing_by_id = {entry["id"]: entry for entry in existing if isinstance(entry, dict) and "id" in entry}
        for tag in incoming:
            if not isinstance(tag, dict) or "id" not in tag:
                continue
            tag_id = str(tag["id"])
            if tag_id in existing_by_id:
                prev = existing_by_id[tag_id]
                merged = set(prev.get("concepts") or [])
                merged.update(tag.get("concepts") or [])
                prev["concepts"] = sorted(merged)
                prev["label"] = tag.get("label", prev.get("label", ""))
                prev["color"] = tag.get("color", prev.get("color", "#6b7280"))
            else:
                existing_by_id[tag_id] = {
                    "id": tag_id,
                    "label": str(tag.get("label") or ""),
                    "color": str(tag.get("color") or "#6b7280"),
                    "concepts": sorted(set(tag.get("concepts") or [])),
                }

        merged_list = list(existing_by_id.values())
        with open(tags_path, "w", encoding="utf-8") as handle:
            json.dump(merged_list, handle, indent=2, ensure_ascii=False)
    except ProjectArtifactHandlerError:
        raise
    except Exception as exc:
        raise ProjectArtifactHandlerError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc

    return JsonResponseSpec(status=HTTPStatus.OK, payload={"ok": True, "tagCount": len(merged_list)})



def build_get_export_lingpy_response(
    *,
    export_wordlist_tsv: WordlistExporter,
    enrichments_path: pathlib.Path,
    annotations_dir: pathlib.Path,
    mkstemp: Callable[..., Tuple[int, str]] = tempfile.mkstemp,
    close_fd: Callable[[int], None] = os.close,
    unlink: Callable[[str], None] = os.unlink,
) -> BinaryResponseSpec:
    tmp_fd, tmp_str = mkstemp(suffix=".tsv")
    close_fd(tmp_fd)
    tmp_path = pathlib.Path(tmp_str)
    try:
        export_wordlist_tsv(enrichments_path, annotations_dir, tmp_path)
        content = tmp_path.read_bytes()
    finally:
        try:
            unlink(tmp_str)
        except OSError:
            pass

    return BinaryResponseSpec(
        status=HTTPStatus.OK,
        content_type="text/tab-separated-values; charset=utf-8",
        content_disposition='attachment; filename="parse-wordlist.tsv"',
        body=content,
    )



def build_get_export_nexus_response(
    *,
    enrichments_path: pathlib.Path,
    project_json_path: pathlib.Path,
    read_json_file: ReadJsonFile,
    default_enrichments_payload: DefaultPayloadFactory,
    concept_sort_key: ConceptSortKey,
) -> BinaryResponseSpec:
    enrichments = read_json_file(enrichments_path, default_enrichments_payload())
    overrides = enrichments.get("manual_overrides") or {}
    override_sets = overrides.get("cognate_sets") if isinstance(overrides, dict) else None
    auto_sets = enrichments.get("cognate_sets") if isinstance(enrichments, dict) else None
    override_sets = override_sets if isinstance(override_sets, dict) else {}
    auto_sets = auto_sets if isinstance(auto_sets, dict) else {}

    speakers_set: set[str] = set()
    project_payload = read_json_file(project_json_path, {})
    speakers_block = project_payload.get("speakers") if isinstance(project_payload, dict) else None
    if isinstance(speakers_block, dict):
        speakers_set.update(str(s) for s in speakers_block.keys() if str(s).strip())
    elif isinstance(speakers_block, list):
        speakers_set.update(str(s) for s in speakers_block if str(s).strip())

    concept_keys: List[str] = []
    concept_group_members: Dict[str, Dict[str, List[str]]] = {}
    union_keys: List[str] = []
    seen_keys: set[str] = set()
    for key in list(override_sets.keys()) + list(auto_sets.keys()):
        if key not in seen_keys:
            seen_keys.add(key)
            union_keys.append(key)

    for key in union_keys:
        override_block = override_sets.get(key)
        auto_block = auto_sets.get(key)
        block = override_block if isinstance(override_block, dict) else auto_block
        if not isinstance(block, dict):
            continue
        groups: Dict[str, List[str]] = {}
        for group, members in block.items():
            if not isinstance(members, list):
                continue
            cleaned = [str(member) for member in members if str(member).strip()]
            if cleaned:
                groups[str(group)] = cleaned
                speakers_set.update(cleaned)
        if groups:
            concept_group_members[key] = groups
            concept_keys.append(key)

    speakers = sorted(speakers_set)

    has_form: Dict[str, set[str]] = {}
    for key in concept_keys:
        present: set[str] = set()
        for members in concept_group_members[key].values():
            present.update(members)
        has_form[key] = present

    characters: List[Tuple[str, str, str]] = []
    for key in sorted(concept_keys, key=concept_sort_key):
        for group in sorted(concept_group_members[key].keys()):
            label = "{0}_{1}".format(str(key).replace(" ", "_"), group)
            characters.append((key, group, label))

    def row_for(speaker: str) -> str:
        chars: List[str] = []
        for key, group, _label in characters:
            members = concept_group_members[key].get(group, [])
            if speaker in members:
                chars.append("1")
            elif speaker in has_form.get(key, set()):
                chars.append("0")
            else:
                chars.append("?")
        return "".join(chars)

    lines: List[str] = []
    lines.append("#NEXUS")
    lines.append("")
    lines.append("BEGIN TAXA;")
    lines.append("    DIMENSIONS NTAX={0};".format(len(speakers)))
    if speakers:
        lines.append("    TAXLABELS")
        for speaker in speakers:
            lines.append("        {0}".format(speaker))
        lines.append("    ;")
    lines.append("END;")
    lines.append("")
    lines.append("BEGIN CHARACTERS;")
    lines.append("    DIMENSIONS NCHAR={0};".format(len(characters)))
    lines.append('    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";')
    if characters:
        lines.append("    CHARSTATELABELS")
        label_rows = []
        for idx, (_key, _group, label) in enumerate(characters, start=1):
            label_rows.append("        {0} {1}".format(idx, label))
        lines.append(",\n".join(label_rows))
        lines.append("    ;")
    lines.append("    MATRIX")
    for speaker in speakers:
        lines.append("        {0}    {1}".format(speaker, row_for(speaker)))
    lines.append("    ;")
    lines.append("END;")
    lines.append("")

    nexus_text = "\n".join(lines).encode("utf-8")
    return BinaryResponseSpec(
        status=HTTPStatus.OK,
        content_type="text/plain; charset=utf-8",
        content_disposition='attachment; filename="parse-cognates.nex"',
        body=nexus_text,
    )
