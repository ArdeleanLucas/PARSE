"""Survey-overlap sidecar helpers for PARSE workspaces.

The durable concepts.csv contract remains the five-column CSV. This module adds
an optional JSON sidecar for the many-to-many concept<->survey links and the
per-speaker elicitation survey choices needed by the Annotate UI.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from concept_source_item import row_value

SURVEY_OVERLAP_FILENAME = "survey-overlap.json"
SURVEY_COLOR_KEYS: tuple[str, ...] = (
    "indigo",
    "violet",
    "blue",
    "sky",
    "teal",
    "emerald",
    "amber",
    "orange",
    "rose",
    "pink",
    "slate",
)
DEFAULT_SURVEY_COLOR = "slate"

SurveyOverlapState = dict[str, Any]


def normalize_survey_id(value: object) -> str:
    """Return the canonical sidecar survey id for a CSV/API value."""

    text = str(value or "").strip().casefold()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_.-]+", "", text)
    return text


def _default_state() -> SurveyOverlapState:
    return {
        "version": 1,
        "color_coding_enabled": False,
        "surveys": {},
        "concept_survey_links": {},
        "speaker_choices": {},
    }


def _clean_color(value: object) -> str:
    color = str(value or "").strip().casefold()
    return color if color in SURVEY_COLOR_KEYS else DEFAULT_SURVEY_COLOR


def default_survey_settings(survey_id: str) -> dict[str, str]:
    sid = normalize_survey_id(survey_id)
    return {"display_label": sid.upper() if sid else "", "display_color": DEFAULT_SURVEY_COLOR}


def _clean_survey_settings(survey_id: str, raw: object) -> dict[str, str]:
    sid = normalize_survey_id(survey_id)
    defaults = default_survey_settings(sid)
    if not isinstance(raw, Mapping):
        return defaults
    label = str(raw.get("display_label") or raw.get("label") or defaults["display_label"]).strip()
    return {
        "display_label": label or defaults["display_label"],
        "display_color": _clean_color(raw.get("display_color") or raw.get("color")),
    }


def _clean_links(raw: object) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, Mapping):
        return out
    for concept_id, links in raw.items():
        cid = str(concept_id or "").strip()
        if not cid or not isinstance(links, Mapping):
            continue
        clean_links: dict[str, str] = {}
        for survey_id, source_item in links.items():
            sid = normalize_survey_id(survey_id)
            item = str(source_item or "").strip()
            if sid and item:
                clean_links[sid] = item
        if clean_links:
            out[cid] = clean_links
    return out


def _clean_speaker_choices(raw: object) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, Mapping):
        return out
    for speaker, choices in raw.items():
        speaker_id = str(speaker or "").strip()
        if not speaker_id or not isinstance(choices, Mapping):
            continue
        clean_choices: dict[str, str] = {}
        for concept_id, survey_id in choices.items():
            cid = str(concept_id or "").strip()
            sid = normalize_survey_id(survey_id)
            if cid and sid:
                clean_choices[cid] = sid
        if clean_choices:
            out[speaker_id] = clean_choices
    return out


def normalize_survey_overlap_state(raw: object) -> SurveyOverlapState:
    state = _default_state()
    if not isinstance(raw, Mapping):
        return state
    state["color_coding_enabled"] = bool(raw.get("color_coding_enabled"))

    surveys: dict[str, dict[str, str]] = {}
    raw_surveys = raw.get("surveys")
    if isinstance(raw_surveys, Mapping):
        for survey_id, settings in raw_surveys.items():
            sid = normalize_survey_id(survey_id)
            if sid:
                surveys[sid] = _clean_survey_settings(sid, settings)
    state["surveys"] = surveys
    state["concept_survey_links"] = _clean_links(raw.get("concept_survey_links"))
    state["speaker_choices"] = _clean_speaker_choices(raw.get("speaker_choices"))
    return state


def survey_overlap_path(project_root: Path) -> Path:
    return Path(project_root) / SURVEY_OVERLAP_FILENAME


def load_survey_overlap_state(project_root: Path) -> SurveyOverlapState:
    path = survey_overlap_path(project_root)
    if not path.exists():
        return _default_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return _default_state()
    return normalize_survey_overlap_state(payload)


def save_survey_overlap_state(project_root: Path, state: SurveyOverlapState) -> SurveyOverlapState:
    clean = normalize_survey_overlap_state(state)
    path = survey_overlap_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return clean


def update_survey_overlap_state(project_root: Path, patch: Mapping[str, object]) -> SurveyOverlapState:
    current = load_survey_overlap_state(project_root)
    merged: SurveyOverlapState = {
        "version": 1,
        "color_coding_enabled": current["color_coding_enabled"],
        "surveys": dict(current["surveys"]),
        "concept_survey_links": {cid: dict(links) for cid, links in current["concept_survey_links"].items()},
        "speaker_choices": {speaker: dict(choices) for speaker, choices in current["speaker_choices"].items()},
    }
    if "color_coding_enabled" in patch:
        merged["color_coding_enabled"] = bool(patch.get("color_coding_enabled"))
    if isinstance(patch.get("surveys"), Mapping):
        for survey_id, settings in (patch.get("surveys") or {}).items():
            sid = normalize_survey_id(survey_id)
            if sid:
                merged["surveys"][sid] = _clean_survey_settings(sid, settings)
    if isinstance(patch.get("concept_survey_links"), Mapping):
        incoming_links = _clean_links(patch.get("concept_survey_links"))
        for concept_id, links in incoming_links.items():
            merged["concept_survey_links"].setdefault(concept_id, {}).update(links)
    if isinstance(patch.get("speaker_choices"), Mapping):
        incoming_choices = _clean_speaker_choices(patch.get("speaker_choices"))
        for speaker, choices in incoming_choices.items():
            merged["speaker_choices"].setdefault(speaker, {}).update(choices)
    return save_survey_overlap_state(project_root, merged)


def concept_survey_links_for_row(row: Mapping[str, object], state: Mapping[str, object]) -> dict[str, str]:
    concept_id = str(row_value(row, "id") or "").strip()
    links: dict[str, str] = {}
    legacy_item = row_value(row, "source_item", "survey_item")
    legacy_survey = normalize_survey_id(row_value(row, "source_survey"))
    if legacy_item and legacy_survey:
        links[legacy_survey] = legacy_item
    sidecar_root = state.get("concept_survey_links") if isinstance(state, Mapping) else None
    sidecar_links = sidecar_root.get(concept_id) if isinstance(sidecar_root, Mapping) else None
    if isinstance(sidecar_links, Mapping):
        for survey_id, source_item in sidecar_links.items():
            sid = normalize_survey_id(survey_id)
            item = str(source_item or "").strip()
            if sid and item:
                links[sid] = item
    return links


def survey_settings_for_ids(state: Mapping[str, object], survey_ids: set[str]) -> dict[str, dict[str, str]]:
    settings_root = state.get("surveys") if isinstance(state, Mapping) else None
    explicit = settings_root if isinstance(settings_root, Mapping) else {}
    ids = {normalize_survey_id(sid) for sid in survey_ids}
    ids.update(normalize_survey_id(sid) for sid in explicit.keys())
    out: dict[str, dict[str, str]] = {}
    for sid in sorted(value for value in ids if value):
        out[sid] = _clean_survey_settings(sid, explicit.get(sid))
    return out


def resolve_survey_for_speaker(
    concept_id: str,
    speaker: str,
    links: Mapping[str, object],
    state: Mapping[str, object],
    *,
    fallback_survey: object = None,
) -> tuple[str, str]:
    clean_links = {normalize_survey_id(sid): str(item or "").strip() for sid, item in links.items() if normalize_survey_id(sid) and str(item or "").strip()}
    choices_root = state.get("speaker_choices") if isinstance(state, Mapping) else None
    speaker_choices = choices_root.get(str(speaker or "")) if isinstance(choices_root, Mapping) else None
    chosen = ""
    if isinstance(speaker_choices, Mapping):
        chosen = normalize_survey_id(speaker_choices.get(str(concept_id or "").strip()))
    if chosen in clean_links:
        return chosen, clean_links[chosen]
    fallback = normalize_survey_id(fallback_survey)
    if fallback in clean_links:
        return fallback, clean_links[fallback]
    if clean_links:
        first = sorted(clean_links.keys())[0]
        return first, clean_links[first]
    return "", ""


def _tokenize_source_item(value: str) -> tuple[tuple[int, object], ...]:
    tokens: list[tuple[int, object]] = []
    for match in re.finditer(r"([A-Za-z]+)|(\d+)", str(value or "")):
        if match.group(1):
            tokens.append((0, match.group(1).casefold()))
        elif match.group(2):
            tokens.append((1, int(match.group(2))))
    return tuple(tokens)


def survey_sort_key_for_speaker(
    concept_id: str,
    speaker: str,
    links: Mapping[str, object],
    state: Mapping[str, object],
    *,
    fallback_survey: object = None,
) -> tuple[int, tuple[tuple[int, object], ...], str]:
    survey_id, source_item = resolve_survey_for_speaker(concept_id, speaker, links, state, fallback_survey=fallback_survey)
    if not source_item:
        return (1, tuple(), str(concept_id or ""))
    return (0, _tokenize_source_item(source_item), survey_id)
