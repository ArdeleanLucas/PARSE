"""Pure tag/concept resolver helpers.

Shared by the HTTP routes (``/api/concepts/by-tag``,
``/api/lexemes/rerun-by-tag``) and the MCP wrappers, so this module must
have no HTTP coupling.

A *tag* lives in the global tag vocabulary (``~/.parse/tags.json`` —
``storage.tags_store``); concept membership is per-speaker and stored on
the annotation record under ``concept_tags: {conceptId: [tagId, ...]}``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANNOTATION_FILENAME_SUFFIX = ".parse.json"
ANNOTATION_LEGACY_FILENAME_SUFFIX = ".json"


@dataclass(frozen=True)
class ResolvedTags:
    ids_by_label: dict[str, str] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ConceptHit:
    conceptId: str
    name: str
    start: float
    end: float
    tags: list[str]


class SpeakerExpansionError(ValueError):
    """Raised when ``expand_speakers`` cannot resolve a requested speaker id."""


def _normalize_label(label: Any) -> str:
    return str(label or "").strip().casefold()


def resolve_tag_labels(
    labels: Sequence[str],
    vocab: Iterable[Mapping[str, Any]],
) -> ResolvedTags:
    """Match user-supplied tag labels against the global tag vocabulary.

    Matching is whitespace-trimmed and case-insensitive. If two vocabulary
    entries share a normalized label, the lookup is *ambiguous*: the input
    label is reported in ``ambiguous`` and is NOT included in
    ``ids_by_label``. Unknown labels (including empty strings) appear in
    ``unknown`` in the same order they were supplied.
    """
    by_norm: dict[str, list[str]] = {}
    for entry in vocab:
        if not isinstance(entry, Mapping):
            continue
        tag_id = entry.get("id")
        label = entry.get("label")
        if not isinstance(tag_id, str) or not isinstance(label, str):
            continue
        key = _normalize_label(label)
        if not key:
            continue
        by_norm.setdefault(key, []).append(tag_id)

    ids_by_label: dict[str, str] = {}
    unknown: list[str] = []
    ambiguous: dict[str, list[str]] = {}

    for raw in labels:
        label = str(raw) if raw is not None else ""
        key = _normalize_label(label)
        candidates = by_norm.get(key, [])
        if not candidates:
            unknown.append(label)
            continue
        if len(candidates) > 1:
            ambiguous[label] = list(candidates)
            continue
        ids_by_label[label] = candidates[0]

    return ResolvedTags(ids_by_label=ids_by_label, unknown=unknown, ambiguous=ambiguous)


def _interval_concept_id(interval: Mapping[str, Any]) -> str:
    raw = interval.get("concept_id")
    if raw is None:
        raw = interval.get("conceptId")
    if raw is None:
        return ""
    return str(raw).strip()


def select_concepts_by_tag(
    annotation_record: Mapping[str, Any],
    tag_ids: Sequence[str],
    match: str = "any",
) -> list[ConceptHit]:
    """Return the concept-tier intervals whose conceptId carries the requested tags.

    Empty ``tag_ids`` returns ``[]`` regardless of ``match`` — matching nothing
    is safer than the alternative match-all interpretation, which would pull
    every concept on the speaker.
    """
    if not tag_ids:
        return []
    if match not in ("any", "all"):
        raise ValueError("match must be 'any' or 'all'")

    requested = set(tag_ids)

    raw_concept_tags = annotation_record.get("concept_tags") if isinstance(annotation_record, Mapping) else None
    concept_tags: dict[str, set[str]] = {}
    if isinstance(raw_concept_tags, Mapping):
        for raw_concept_id, raw_tag_ids in raw_concept_tags.items():
            if not isinstance(raw_tag_ids, list):
                continue
            ids = {str(t) for t in raw_tag_ids if isinstance(t, str)}
            if ids:
                concept_tags[str(raw_concept_id)] = ids

    tiers = annotation_record.get("tiers") if isinstance(annotation_record, Mapping) else None
    concept_tier = tiers.get("concept") if isinstance(tiers, Mapping) else None
    intervals = concept_tier.get("intervals") if isinstance(concept_tier, Mapping) else None
    if not isinstance(intervals, list):
        return []

    hits: list[ConceptHit] = []
    for raw_interval in intervals:
        if not isinstance(raw_interval, Mapping):
            continue
        concept_id = _interval_concept_id(raw_interval)
        if not concept_id:
            continue
        concept_tag_ids = concept_tags.get(concept_id, set())
        if not concept_tag_ids:
            continue
        if match == "any":
            if not (requested & concept_tag_ids):
                continue
        else:  # all
            if not requested.issubset(concept_tag_ids):
                continue
        try:
            start = float(raw_interval.get("start"))
            end = float(raw_interval.get("end"))
        except (TypeError, ValueError):
            continue
        hits.append(
            ConceptHit(
                conceptId=concept_id,
                name=str(raw_interval.get("text") or "").strip(),
                start=start,
                end=end,
                tags=sorted(concept_tag_ids),
            )
        )
    return hits


def _looks_like_speaker_file(name: str) -> tuple[bool, str]:
    if name.endswith(ANNOTATION_FILENAME_SUFFIX):
        return True, name[: -len(ANNOTATION_FILENAME_SUFFIX)]
    if name.endswith(ANNOTATION_LEGACY_FILENAME_SUFFIX):
        return True, name[: -len(ANNOTATION_LEGACY_FILENAME_SUFFIX)]
    return False, ""


def _list_workspace_speakers(project_root: Path) -> list[str]:
    annotations_dir = Path(project_root) / "annotations"
    if not annotations_dir.is_dir():
        return []
    speakers: set[str] = set()
    for entry in annotations_dir.iterdir():
        if not entry.is_file():
            continue
        ok, speaker = _looks_like_speaker_file(entry.name)
        if ok and speaker:
            speakers.add(speaker)
    return sorted(speakers)


def expand_speakers(speakers_arg: Any, project_root: Path) -> list[str]:
    """Resolve the ``speakers`` request field to a concrete list of speaker ids.

    Accepts the literal string ``"all"`` (returns every speaker discovered in
    ``<project_root>/annotations/``) or a list of speaker ids (preserves
    caller order, raises ``SpeakerExpansionError`` on the first unknown id).
    """
    if isinstance(speakers_arg, str):
        if speakers_arg.strip().lower() == "all":
            return _list_workspace_speakers(Path(project_root))
        raise SpeakerExpansionError(
            "speakers must be a list of speaker ids or the literal string 'all'"
        )
    if not isinstance(speakers_arg, list):
        raise SpeakerExpansionError(
            "speakers must be a list of speaker ids or the literal string 'all'"
        )

    workspace = set(_list_workspace_speakers(Path(project_root)))
    out: list[str] = []
    for raw in speakers_arg:
        speaker = str(raw or "").strip()
        if not speaker:
            raise SpeakerExpansionError("speaker id must be a non-empty string")
        if speaker not in workspace:
            raise SpeakerExpansionError("unknown speaker: {0}".format(speaker))
        out.append(speaker)
    return out


__all__ = [
    "ConceptHit",
    "ResolvedTags",
    "SpeakerExpansionError",
    "expand_speakers",
    "resolve_tag_labels",
    "select_concepts_by_tag",
]
