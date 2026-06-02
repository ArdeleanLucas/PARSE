#!/usr/bin/env python3
"""export_review_data.py — Export a PARSE workspace to the legacy review_tool format.

Inverse of ``python/import_review_data.py``. Reads a PARSE workspace, filters
concepts by a tag (default: ``custom-sk-concept-list`` — the thesis tag), and
emits a ``review_data.json`` plus pre-clipped per-form WAVs in the layout the
archived ``ArdeleanLucas/review_tool_archived`` HTML expects:

    <out>/review_data.json
    <out>/audio/<Speaker>/<survey>_<source_item>_<variant>_<gloss>_<Speaker>.wav
    <out>/timestamps/<Speaker>_timestamps.csv

Analytical fields (``cognate_class``, ``arabic_similarity`` / ``persian_similarity``,
``borrowing_flag``, plus concept-level ``arabic`` / ``persian`` reference forms)
are populated from ``<workspace>/parse-enrichments.json`` and
``<repo>/config/sil_contact_languages.json`` when those data sources have been
populated by PARSE's compute pipelines. When the enrichments or contact-language
sources are missing or empty, the exporter falls back to the legacy null / zero
/ ``"?"`` defaults (matching the legacy importer's shape for unscored forms) so
the viewer still renders. ``phonetic_flags`` / ``verification`` / ``variants``
are intentionally NOT populated — they require a separate detector pipeline that
is explicitly out of scope for this exporter.

Usage::

    python python/export_review_data.py \\
        --workspace /home/lucas/parse-workspace \\
        --out /tmp/review_tool_export

    # Schema-only run (no ffmpeg, for fast iteration / CI):
    python python/export_review_data.py --workspace ... --out ... --skip-audio
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from concept_canonical import strip_clarifier
from concept_source_item import (
    parse_cue_name,
    read_concepts_csv_rows,
    row_value,
)

DEFAULT_TAG_ID = "custom-sk-concept-list"
DEFAULT_PROJECT_AUDIO_ROOT = "audio/working"
LEGACY_SCHEMA_VERSION = 4.1
EXCLUDED_ANNOTATION_NAMES = {"manifest.json", "parse-enrichments.json"}
ENRICHMENTS_FILENAME = "parse-enrichments.json"
DEFAULT_CONTACT_CONFIG_RELATIVE = "config/sil_contact_languages.json"


def _empty_enrichments() -> dict[str, dict[str, Any]]:
    """Fresh, mutation-safe shape for ``_load_enrichments`` fallbacks.

    Returns a new dict on every call so concurrent / sequential callers can
    write through their copy without aliasing a module-level constant.
    """
    return {"cognate_sets": {}, "similarity": {}, "borrowing_flags": {}}

_REVIEW_VARIANT_CODE_RE = re.compile(r"\s*\(([A-Za-z0-9]+)\)\s*$")
_PAREN_CONTENT_RE = re.compile(r"\(([^)]*)\)")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _stem_label(label: str) -> str:
    """Return the review-tool gloss stem of ``label`` with parens stripped.

    PARSE's migrated ``concepts.csv`` now carries canonical labels with leaked
    Audition cue prefixes removed centrally by ``concept_canonical`` and the
    MC-418 migration. The exporter intentionally no longer owns a second
    leading-number cleanup pass; that MC-415-C workaround is retired.

    Review-tool stemming still strips trailing parentheticals before matching
    or writing legacy-compatible labels:

    1. **Variant suffix** — alphanumeric token at end, e.g. ``"dog (A)"``,
       ``"big (F)"``.
    2. **Meaning qualifier** — free text at end, e.g. ``"egg (e.g., chicken)"``,
       ``"fly (n.)"``, ``"you (sg.)"``, ``"to knock (at the door)"``.

    Trailing parentheticals are stripped iteratively so chained suffixes like
    ``"egg (e.g., chicken) (A)"`` collapse to ``"egg"`` and combined cases like
    ``"stomach (organ) (A)"`` collapse to ``"stomach"``. Returns the input
    unchanged when no trailing parenthetical matches.
    """
    text = str(label or "").strip()
    while True:
        stripped = _TRAILING_PAREN_RE.sub("", text).strip()
        if not stripped or stripped == text:
            break
        text = stripped
    return text


def _variant_letter(label: str) -> str:
    """Return the variant code ``A``/``B``/``F`` from ``"big (A)"`` etc.

    Deliberately uses the narrow alphanumeric-only regex so meaning qualifiers
    (``"egg (e.g., chicken)"``) are NOT mistaken for a variant code.
    """
    match = _REVIEW_VARIANT_CODE_RE.search(str(label or "").strip())
    return match.group(1) if match else ""


def _clarifier_notes(label: str) -> list[str]:
    """Return semantic parenthetical clarifiers as review notes.

    Export-time dedup needs to preserve ``(men)`` / ``(women)`` while ignoring
    variant-only suffixes like ``(A)``. The public stripping primitive remains
    :func:`concept_canonical.strip_clarifier`; this helper only decides which
    stripped chunks are human-review notes rather than variant codes.
    """

    notes: list[str] = []
    for match in _PAREN_CONTENT_RE.finditer(str(label or "")):
        token = match.group(1).strip()
        if not token or re.fullmatch(r"(?:[A-Z]|\d+)", token):
            continue
        note = f"clarifier_variant: ({token})"
        if note not in notes:
            notes.append(note)
    return notes


def _append_note(target: dict[str, Any], note: str) -> None:
    if not note:
        return
    current = target.get("notes")
    if current is None:
        target["notes"] = [note]
        return
    if isinstance(current, list):
        if note not in current:
            current.append(note)
        return
    existing = str(current).strip()
    target["notes"] = [value for value in (existing, note) if value]


def _form_ipa_length(form: Mapping[str, Any]) -> int:
    ipa = str(form.get("ipa") or "").strip()
    if ipa in {"", "?"}:
        return 0
    return len(ipa)


def _entry_ipa_length(entry: Mapping[str, Any]) -> int:
    return sum(_form_ipa_length(form) for form in entry.get("forms", []) if isinstance(form, Mapping))


def _entry_has_semantic_clarifier(entry: Mapping[str, Any]) -> bool:
    return bool(_clarifier_notes(str(entry.get("_source_full_label") or entry.get("concept_en") or "")))


def _clip_plan_by_speaker(entry: Mapping[str, Any]) -> Mapping[str, tuple[str, dict[str, Any]]]:
    clips = entry.get("_clip_plan_by_speaker")
    return clips if isinstance(clips, Mapping) else {}


def _collapse_clarifier_siblings(
    concept_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, dict[str, Any]]]]:
    """Collapse default-export duplicate gloss siblings without touching anchored mode."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in concept_entries:
        label = str(entry.get("_source_full_label") or entry.get("concept_en") or "")
        base = strip_clarifier(label).casefold() or str(entry.get("concept_en") or "").casefold()
        groups.setdefault(base, []).append(entry)

    collapsed: list[dict[str, Any]] = []
    clip_plan: list[tuple[str, dict[str, Any]]] = []
    for siblings in groups.values():
        if len(siblings) == 1:
            for entry in siblings:
                collapsed.append(_public_concept_entry(entry))
                clip_plan.extend(entry.get("_clip_plan", []))
            continue

        winner = max(
            siblings,
            key=lambda entry: (
                _entry_ipa_length(entry),
                not _entry_has_semantic_clarifier(entry),
                -int(entry.get("_source_index") or 0),
            ),
        )
        merged = dict(winner)
        merged["concept_en"] = strip_clarifier(str(winner.get("_source_full_label") or winner.get("concept_en") or "")) or str(
            winner.get("concept_en") or ""
        )

        for sibling in siblings:
            for note in _clarifier_notes(str(sibling.get("_source_full_label") or sibling.get("concept_en") or "")):
                _append_note(merged, note)

        speaker_order = [str(form.get("speaker") or "") for form in winner.get("forms", []) if isinstance(form, Mapping)]
        for sibling in siblings:
            for form in sibling.get("forms", []) or []:
                if not isinstance(form, Mapping):
                    continue
                speaker = str(form.get("speaker") or "")
                if speaker and speaker not in speaker_order:
                    speaker_order.append(speaker)

        merged_forms: list[dict[str, Any]] = []
        merged_clips: list[tuple[str, dict[str, Any]]] = []
        for speaker in speaker_order:
            candidates: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
            for sibling in siblings:
                for form in sibling.get("forms", []) or []:
                    if isinstance(form, Mapping) and str(form.get("speaker") or "") == speaker:
                        candidates.append((sibling, form))
            if not candidates:
                continue
            chosen_entry, chosen_form = max(
                candidates,
                key=lambda item: (
                    _form_ipa_length(item[1]),
                    bool(item[1].get("audio_path")),
                    bool(str(item[1].get("ortho") or "").strip()),
                    not _entry_has_semantic_clarifier(item[0]),
                    item[0] is winner,
                    -int(item[0].get("_source_index") or 0),
                ),
            )
            public_form = dict(chosen_form)
            for note in _clarifier_notes(str(chosen_entry.get("_source_full_label") or chosen_entry.get("concept_en") or "")):
                _append_note(public_form, note)
            merged_forms.append(public_form)
            chosen_clip = _clip_plan_by_speaker(chosen_entry).get(speaker)
            if chosen_clip is not None:
                merged_clips.append(chosen_clip)

        merged["forms"] = merged_forms
        merged["_clip_plan"] = merged_clips
        collapsed.append(_public_concept_entry(merged))
        clip_plan.extend(merged_clips)

    return collapsed, clip_plan


def _public_concept_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in entry.items() if not str(key).startswith("_")}


def _slug_for_filename(value: str) -> str:
    cleaned = _FILENAME_SAFE_RE.sub("_", str(value or "").strip())
    return cleaned.strip("_") or "concept"


def _iter_annotation_files(annotations_dir: Path) -> Iterable[Path]:
    """Yield speaker annotation files, preferring ``.parse.json`` over legacy ``.json``."""
    if not annotations_dir.is_dir():
        return []
    candidates = sorted(
        path
        for path in annotations_dir.glob("*.json")
        if path.name not in EXCLUDED_ANNOTATION_NAMES
        and not path.name.endswith(".tmp")
        and ".bak" not in path.name
    )
    parse_speakers = {
        path.name[: -len(".parse.json")]
        for path in candidates
        if path.name.endswith(".parse.json")
    }
    selected: list[Path] = []
    for path in candidates:
        if path.name.endswith(".parse.json"):
            selected.append(path)
            continue
        speaker = path.stem
        if speaker in parse_speakers:
            continue
        selected.append(path)
    return selected


def _speaker_for_annotation(path: Path) -> str:
    if path.name.endswith(".parse.json"):
        return path.name[: -len(".parse.json")]
    return path.stem


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _project_speakers(project_root: Path) -> list[str]:
    payload = _load_json(project_root / "project.json")
    speakers = payload.get("speakers")
    if isinstance(speakers, Mapping):
        return [str(k) for k in speakers.keys() if str(k).strip()]
    if isinstance(speakers, list):
        return [str(s) for s in speakers if str(s).strip()]
    return []


def _apply_speaker_filter(
    project_speakers: list[str],
    speaker_filter: Iterable[str],
) -> list[str]:
    """Restrict ``project_speakers`` to entries in ``speaker_filter``.

    Order from ``project.json`` is preserved (downstream metadata.speakers,
    annotation iteration, and form emission all key off the returned list).
    Raises ``ValueError`` if any requested speaker is not in the workspace —
    callers ship curated subsets and a typo should fail loudly rather than
    silently produce a wrong export.
    """
    requested = [str(s).strip() for s in speaker_filter if str(s).strip()]
    if not requested:
        return list(project_speakers)
    project_set = set(project_speakers)
    missing = [s for s in requested if s not in project_set]
    if missing:
        raise ValueError(
            f"--speakers includes entries not in project.json: {missing}. "
            f"Workspace speakers: {sorted(project_set)}"
        )
    requested_set = set(requested)
    return [s for s in project_speakers if s in requested_set]


def _tagged_concept_ids(payload: Mapping[str, Any], tag_id: str) -> set[str]:
    concept_tags = payload.get("concept_tags")
    if not isinstance(concept_tags, Mapping):
        return set()
    matches: set[str] = set()
    for concept_id, tag_ids in concept_tags.items():
        if not isinstance(tag_ids, list):
            continue
        if tag_id in {str(t) for t in tag_ids}:
            matches.add(str(concept_id))
    return matches


def _source_wav_relative(payload: Mapping[str, Any], speaker: str) -> str:
    raw = str(payload.get("source_audio") or payload.get("source_wav") or "").strip()
    audio = payload.get("audio")
    if not raw and isinstance(audio, Mapping):
        raw = str(
            audio.get("source_audio") or audio.get("source_wav") or audio.get("path") or ""
        ).strip()
    source = raw.replace("\\", "/").strip()
    if not source:
        return f"{DEFAULT_PROJECT_AUDIO_ROOT}/{speaker}/{speaker}.wav"
    if "/" in source or Path(source).is_absolute():
        return source
    return f"{DEFAULT_PROJECT_AUDIO_ROOT}/{speaker}/{source}"


def _resolve_source_wav(project_root: Path, relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    if path.is_absolute():
        return path
    return project_root / relative_or_absolute


def _load_enrichments(workspace: Path) -> dict[str, Any]:
    """Read ``<workspace>/parse-enrichments.json``, tolerating missing file or keys.

    Always returns at minimum the three analytical sub-dicts the exporter
    consults (``cognate_sets``, ``similarity``, ``borrowing_flags``) so callers
    can index without guarding each access. The live workspace currently emits
    only ``lexeme_notes`` post-CSV-re-import; this function bridges that gap.
    Each call returns a fresh dict, so callers can mutate without aliasing.
    """
    path = workspace / ENRICHMENTS_FILENAME
    if not path.exists():
        return _empty_enrichments()
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"warning: failed to read {path}: {exc}; treating as empty enrichments",
            file=sys.stderr,
        )
        return _empty_enrichments()
    if not isinstance(data, Mapping):
        return _empty_enrichments()
    out = _empty_enrichments()
    for key in ("cognate_sets", "similarity", "borrowing_flags"):
        value = data.get(key)
        if isinstance(value, Mapping):
            out[key] = dict(value)
    try:
        from migration.concept_uid_enrichments import expand_uid_keys_for_legacy_read

        out = expand_uid_keys_for_legacy_read(workspace, out)
    except Exception:
        pass
    return out


def _default_contact_config() -> Path:
    return Path(__file__).resolve().parent.parent / DEFAULT_CONTACT_CONFIG_RELATIVE


def _resolve_contact_config(workspace: Path, contact_config: Path | None) -> Path:
    """Resolve contact refs with workspace cache precedence for every caller.

    The populated post-MC-418 cache lives at
    ``<workspace>/config/sil_contact_languages.json``. Keeping this resolution
    beside the loader rather than only in the shell wrapper makes the CLI,
    chat tool, and MCP adapter share the same default behavior.
    """
    if contact_config is not None:
        return contact_config
    workspace_cache = workspace / DEFAULT_CONTACT_CONFIG_RELATIVE
    if workspace_cache.exists():
        return workspace_cache
    return _default_contact_config()


def _load_contact_languages(contact_config: Path | None) -> dict[str, dict[str, Any]]:
    """Read ``sil_contact_languages.json``; return ``{lang_code: {"concepts": {...}}}``.

    Tolerates a missing path, missing file, malformed JSON, and metadata
    underscore-prefixed top-level keys (these are skipped — they mirror the
    fetcher's own behaviour). When the file is absent the caller gets an empty
    dict; lookups then fall through to the empty-form-and-ipa defaults.
    """
    if contact_config is None:
        return {}
    if not contact_config.exists():
        print(
            f"warning: contact-language config not found at {contact_config}; "
            f"Arabic/Persian reference forms will be empty in the export",
            file=sys.stderr,
        )
        return {}
    try:
        with contact_config.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"warning: failed to read {contact_config}: {exc}; "
            f"Arabic/Persian reference forms will be empty",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, Mapping):
        return {}
    languages_value = data.get("languages")
    language_entries: Mapping[str, Any] = languages_value if isinstance(languages_value, Mapping) else data
    out: dict[str, dict[str, Any]] = {}
    for code, entry in language_entries.items():
        if not isinstance(code, str) or code.startswith("_") or not isinstance(entry, Mapping):
            continue
        out[code] = {"concepts": entry.get("concepts") if isinstance(entry.get("concepts"), Mapping) else {}}
    return out


def _extract_form_from_contact_entry(entry: Any) -> str:
    """Pick the orthographic form from a sil_contact_languages concept entry.

    The fetcher writes either a bare list of strings (legacy, ``["ma:ʔ"]``) or a
    list of provenance dicts (modern, ``[{"form": str, "sources": [...]}]``).
    Wikidata-backed entries use ``script`` for the orthographic form; keep
    ``form > script > orthography`` priority so provider-native forms win when
    multiple keys are present.
    """
    if isinstance(entry, list):
        for item in entry:
            if isinstance(item, Mapping):
                for key in ("form", "script", "orthography"):
                    form = item.get(key)
                    if form and str(form).strip():
                        return str(form).strip()
            elif item:
                return str(item).strip()
    elif isinstance(entry, str) and entry.strip():
        return entry.strip()
    return ""


def _contact_lookup_keys(concept_id: str, label: str) -> tuple[str, ...]:
    """Ordered direct keys for contact-language concept maps.

    Live caches have appeared under both full labels (``"egg (e.g., chicken)"``)
    and canonical bare labels (``"egg"``). Try the explicit id/label first for
    backward compatibility, then the exporter canonicalizers before falling back
    to a map scan by canonical equality.
    """

    seen: set[str] = set()
    keys: list[str] = []
    for candidate in (concept_id, label, strip_clarifier(label), _stem_label(label)):
        key = str(candidate or "").strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return tuple(keys)


def _contact_fallback_key(concepts: Mapping[str, Any], label: str) -> str | None:
    """Find a deterministic same-canonical-label cache key, avoiding substrings."""

    base = (
        strip_clarifier(label).strip()
        or _stem_label(label).strip()
        or str(label or "").strip()
    ).casefold()
    if not base:
        return None
    matches = [
        str(key)
        for key in concepts
        if (
            strip_clarifier(str(key)).strip()
            or _stem_label(str(key)).strip()
            or str(key).strip()
        ).casefold()
        == base
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda key: (-len(key), key))[0]


def _contact_forms_for_concept(
    contact_langs: Mapping[str, Mapping[str, Any]],
    concept_id: str,
    label: str,
) -> dict[str, dict[str, str]]:
    """Return ``{"arabic": {form, ipa}, "persian": {form, ipa}}`` for the concept.

    PARSE's contact-lexeme fetcher keys ``concepts`` by ``concept_en`` label
    (confirmed by ``python/compare/contact_lexeme_fetcher.py``'s ``_load_concepts``
    + merge loop). We still try ``concept_id`` first as a defensive fallback in
    case a future provider keys by id. Live post-MC-418 caches can also key a
    concept by a canonical bare label while ``concepts.csv`` carries a semantic
    clarifier (or vice versa), so direct lookup falls back to canonical-label
    equality rather than substring matching. PARSE does not currently store a
    separate IPA for contact-language forms, so ``ipa`` stays empty — populating
    it is a fetcher-side change, not an export change.
    """
    out: dict[str, dict[str, str]] = {
        "arabic": {"form": "", "ipa": ""},
        "persian": {"form": "", "ipa": ""},
    }
    pairs = (("arabic", "ar"), ("persian", "fa"))
    for legacy_key, lang_code in pairs:
        lang_entry = contact_langs.get(lang_code)
        if not isinstance(lang_entry, Mapping):
            continue
        concepts = lang_entry.get("concepts")
        if not isinstance(concepts, Mapping):
            continue
        lookup_keys = list(_contact_lookup_keys(concept_id, label))
        fallback_key = _contact_fallback_key(concepts, label)
        if fallback_key and fallback_key not in lookup_keys:
            lookup_keys.append(fallback_key)
        for key in lookup_keys:
            form = _extract_form_from_contact_entry(concepts.get(key))
            if form:
                out[legacy_key] = {"form": form, "ipa": ""}
                break
    return out


def _enrichment_keys(concept_id: str, label: str) -> tuple[str, ...]:
    """Ordered candidate keys for enrichment lookups.

    Two conventions exist in the wild:

    - The current ``python/compare/cognate_compute.py`` writes ``cognate_sets``
      and ``similarity`` keyed by normalized **concept_id** (line 815 / 889 of
      ``cognate_compute.py``: ``output[concept_id] = groups``).
    - Older workspace backups (e.g. ``parse-workspace/annotations/backups/
      20260430T201917Z-*``) store keys as the full concept **label** with any
      variant suffix included (``"ear (A)"``).

    Try ``concept_id`` first to match current compute output, then fall back to
    ``label`` for backup compatibility. Empty / duplicate values are filtered.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in (concept_id, label):
        key = str(candidate or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _cognate_class_for(
    cognate_sets: Mapping[str, Any],
    concept_id: str,
    label: str,
    speaker: str,
) -> str:
    """Return the group letter (A/B/C/…) the speaker is in for this concept.

    ``cognate_sets`` shape per ``python/compare/cognate_compute.py``:
    ``{<concept_id_or_label>: {group_letter: [speaker_or_row_id, ...]}}``.
    Tries ``concept_id`` first (matching current cognate_compute output),
    falls back to ``label`` (backup-compatibility). Returns ``"?"`` when the
    concept is not in the map or the speaker is not in any group.
    """
    if not speaker:
        return "?"
    for key in _enrichment_keys(concept_id, label):
        groups = cognate_sets.get(key)
        if not isinstance(groups, Mapping):
            continue
        for group_letter, members in groups.items():
            if not isinstance(members, list):
                continue
            if speaker in {str(m) for m in members if m is not None}:
                return str(group_letter)
    return "?"


def _similarity_score(
    similarity: Mapping[str, Any],
    concept_id: str,
    label: str,
    speaker: str,
    lang_code: str,
) -> float:
    """Return the per-(concept, speaker, lang) similarity score, or 0.0 if missing.

    Shape: ``similarity[<concept_id_or_label>][speaker][lang_code] =
    {"score": Optional[float], "has_reference_data": bool}``. ``score`` may be
    ``None`` when PARSE has no reference data for the pair (see
    ``python/compare/cognate_compute.py:SimilarityScore``); treat that as 0.0.
    """
    if not speaker or not lang_code:
        return 0.0
    for key in _enrichment_keys(concept_id, label):
        by_speaker = similarity.get(key)
        if not isinstance(by_speaker, Mapping):
            continue
        by_lang = by_speaker.get(speaker)
        if not isinstance(by_lang, Mapping):
            continue
        entry = by_lang.get(lang_code)
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("score")
        if raw is None:
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _borrowing_flag_for(
    borrowing_flags: Mapping[str, Any],
    concept_id: str,
    label: str,
    speaker: str,
) -> Any:
    """Return the borrowing flag value for the (concept, speaker), or None."""
    if not speaker:
        return None
    for key in _enrichment_keys(concept_id, label):
        by_speaker = borrowing_flags.get(key)
        if not isinstance(by_speaker, Mapping):
            continue
        if speaker in by_speaker:
            return by_speaker.get(speaker)
    return None


def _concept_intervals_by_id(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tiers = payload.get("tiers")
    if not isinstance(tiers, Mapping):
        return {}
    concept_tier = tiers.get("concept")
    if not isinstance(concept_tier, Mapping):
        return {}
    intervals = concept_tier.get("intervals")
    if not isinstance(intervals, list):
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in intervals:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("concept_id") or "").strip()
        if not cid:
            # Legacy intervals encode "<id>: <label>" in text; tolerate that shape too.
            text = str(raw.get("text") or "").strip()
            if ":" in text:
                head = text.split(":", 1)[0].strip()
                if head.isdigit():
                    cid = head
        if cid:
            grouped.setdefault(cid, []).append(dict(raw))
    return grouped


def _interval_field(interval: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = interval.get(name)
        if value is not None and value != "":
            return value
    return None


def _audio_filename(
    survey_id: str,
    source_item: str,
    variant: str,
    gloss: str,
    speaker: str,
) -> str:
    survey = _slug_for_filename(survey_id) if survey_id else "SRC"
    item = _slug_for_filename(source_item) if source_item else "0"
    variant_token = _slug_for_filename(variant) if variant else "A"
    gloss_token = _slug_for_filename(gloss) or "concept"
    speaker_token = _slug_for_filename(speaker)
    return f"{survey}_{item}_{variant_token}_{gloss_token}_{speaker_token}.wav"


def _clip_wav(
    source_path: Path,
    start_sec: float,
    duration_sec: float,
    out_path: Path,
    *,
    ffmpeg_bin: str = "ffmpeg",
) -> None:
    """Slice ``[start, start + duration]`` from ``source_path`` into ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, float(start_sec)):.6f}",
        "-t",
        f"{max(0.0, float(duration_sec)):.6f}",
        "-i",
        str(source_path),
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def _empty_form(
    speaker: str,
    *,
    concept_id: str = "",
    label: str = "",
    cognate_sets: Mapping[str, Any] | None = None,
    similarity: Mapping[str, Any] | None = None,
    borrowing_flags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Form record for a speaker that did not produce the concept.

    Even when the speaker has no interval for the concept, PARSE's compute
    pipelines may still have an opinion (e.g. cognate_class via shared
    reconstruction; similarity from a no-form sentinel). Populate those from
    the lookups when available, fall back to the legacy null/zero/"?"
    defaults otherwise.
    """
    cs = cognate_sets or {}
    sim = similarity or {}
    bf = borrowing_flags or {}
    return {
        "speaker": speaker,
        "ipa": "?",
        "ortho": "",
        "cognate_class": _cognate_class_for(cs, concept_id, label, speaker),
        "arabic_similarity": _similarity_score(sim, concept_id, label, speaker, "ar"),
        "persian_similarity": _similarity_score(sim, concept_id, label, speaker, "fa"),
        "borrowing_flag": _borrowing_flag_for(bf, concept_id, label, speaker),
        "audio_path": None,
        "spectrogram_path": None,
        "variants": None,
        "source": None,
        "verification": None,
    }


def _form_from_interval(
    *,
    speaker: str,
    interval: Mapping[str, Any],
    concept_row: Mapping[str, str],
    audio_relpath: str | None,
    start_sec: float,
    duration_sec: float,
    concept_id: str = "",
    label: str = "",
    cognate_sets: Mapping[str, Any] | None = None,
    similarity: Mapping[str, Any] | None = None,
    borrowing_flags: Mapping[str, Any] | None = None,
    ipa_override: str | None = None,
    ortho_override: str | None = None,
) -> dict[str, Any]:
    ipa = ipa_override if ipa_override is not None else _interval_field(interval, "ipa", "ipa_text")
    ortho = (
        ortho_override
        if ortho_override is not None
        else _interval_field(interval, "ortho", "orthography", "text")
    )
    cs = cognate_sets or {}
    sim = similarity or {}
    bf = borrowing_flags or {}
    return {
        "speaker": speaker,
        "ipa": "" if ipa is None else str(ipa),
        "ortho": "" if ortho is None else str(ortho),
        "cognate_class": _cognate_class_for(cs, concept_id, label, speaker),
        "arabic_similarity": _similarity_score(sim, concept_id, label, speaker, "ar"),
        "persian_similarity": _similarity_score(sim, concept_id, label, speaker, "fa"),
        "borrowing_flag": _borrowing_flag_for(bf, concept_id, label, speaker),
        "audio_path": audio_relpath,
        "spectrogram_path": None,
        "variants": None,
        "source": row_value(concept_row, "source_survey") or None,
        "verification": None,
        "start_sec": float(start_sec),
        "duration_sec": float(duration_sec),
    }


def _crosstier_text(
    payload: Mapping[str, Any],
    tier_name: str,
    concept_ids: set[str],
    interval_start: float,
    interval_end: float,
) -> str | None:
    """Return the ``text`` field of a tier interval aligned with the concept window.

    The IPA and ortho tiers are temporally aligned with the concept tier (they
    describe the same audio segment), and may carry an optional ``conceptId``
    link from automated pipelines (e.g. ``concept_window_ipa``). When PARSE's
    ``concepts.csv`` carries multiple polluted rows for one gloss, two
    misalignments arise:

    - Several IPA intervals across the recording may carry ``conceptId`` values
      that are in ``concept_ids`` (one per per-speaker variant row), but only
      one of them overlaps the chosen concept-tier window.
    - Manually-adjusted intervals drop the ``conceptId`` link entirely and can
      only be located by time overlap.

    Strategy: require an overlap with ``[interval_start, interval_end]``; among
    overlapping candidates, prefer ones whose ``conceptId`` is in
    ``concept_ids`` (tiebreak by largest overlap), and otherwise fall back to
    the plain largest-overlap interval. Returns ``None`` when no overlapping
    candidate has a non-empty text.
    """
    tiers = payload.get("tiers")
    if not isinstance(tiers, Mapping):
        return None
    tier = tiers.get(tier_name)
    if not isinstance(tier, Mapping):
        return None
    intervals = tier.get("intervals")
    if not isinstance(intervals, list):
        return None

    overlapping: list[tuple[float, Mapping[str, Any]]] = []
    for raw in intervals:
        if not isinstance(raw, Mapping):
            continue
        try:
            iv_s = float(raw.get("start") or 0.0)
            iv_e = float(raw.get("end") or 0.0)
        except (TypeError, ValueError):
            continue
        overlap = min(iv_e, interval_end) - max(iv_s, interval_start)
        if overlap > 0:
            overlapping.append((overlap, raw))

    if not overlapping:
        return None

    with_cid = [
        (ov, iv)
        for ov, iv in overlapping
        if str(iv.get("conceptId") or iv.get("concept_id") or "").strip() in concept_ids
    ]
    candidates = with_cid if with_cid else overlapping
    candidates.sort(key=lambda pair: -pair[0])
    for _ov, iv in candidates:
        text = iv.get("text")
        if text:
            return str(text)
    return None


def _legacy_audio_filename(
    *,
    source: str,
    legacy_concept_id: str,
    gloss: str,
    speaker: str,
) -> str:
    """Match the legacy review_tool's audio filename scheme.

    Legacy convention (verified against ArdeleanLucas/review_tool's existing
    paths): ``<source>_<concept_id>_A_<gloss>_<speaker>.wav`` — the ``A``
    variant token is hardcoded because the legacy data collapsed every
    speaker's per-variant realizations into a single canonical form.
    """
    survey = _slug_for_filename(source) if source else "JBIL"
    item = _slug_for_filename(legacy_concept_id) if legacy_concept_id else "0"
    gloss_token = _slug_for_filename(gloss) or "concept"
    speaker_token = _slug_for_filename(speaker)
    return f"{survey}_{item}_A_{gloss_token}_{speaker_token}.wav"


def _legacy_concept_source(legacy_concept: Mapping[str, Any]) -> str:
    """Pick the ``source`` to use for audio filenames of a legacy concept.

    The legacy schema carries ``source`` only on per-speaker forms (most are
    ``"JBIL"``, some are ``None`` for empty forms). Take the first non-empty
    form source, or fall back to ``"JBIL"`` to match the deployed audio paths.
    """
    forms = legacy_concept.get("forms") or []
    if isinstance(forms, list):
        for f in forms:
            if isinstance(f, Mapping):
                src = f.get("source")
                if src:
                    return str(src)
    return "JBIL"


def build_review_data_anchored(
    *,
    workspace: Path,
    legacy_anchor: Path,
    tag_id: str = DEFAULT_TAG_ID,
    speaker_filter: Iterable[str] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Build review_data anchored to an existing legacy ``review_data.json``.

    Iterates the legacy file's ``concepts`` list as the canonical concept set,
    and re-derives each speaker's form from the current PARSE workspace:

    - Concept identity (``concept_id``, ``concept_en``, ``arabic``, ``persian``)
      comes from the legacy file unchanged. The thesis tag is consulted only as
      a sanity guard: each legacy concept must match at least one PARSE row
      whose ``concept_en`` shares the legacy gloss stem, otherwise we emit
      empty forms and warn.
    - Per-speaker form data (start_sec / duration_sec / IPA / ortho / audio
      path) comes from the speaker's current concept-tier interval whose
      ``concept_id`` is in the matched PARSE id set. IPA and ortho text come
      via :func:`_crosstier_text` against the speaker's ipa / ortho tiers.
    - Audio filenames match the legacy ``<source>_<id>_A_<gloss>_<speaker>.wav``
      scheme so an in-place push to the review_tool clone keeps WAV references
      coherent.

    This mode is the workaround for PARSE issue #529 — the workspace's
    ``concepts.csv`` carries per-speaker variant suffixes as separate rows
    (e.g. ``big``, ``big (A)``, ``big (B)`` … all sharing ``source_item=4.1``),
    so iterating ``concepts.csv`` produces 8 separate "big" entries with
    spotty coverage. Anchoring to a stable 82-concept list collapses all
    variants per gloss to one entry and recovers full-speaker coverage.
    """
    legacy = _load_json(legacy_anchor)
    legacy_concepts = legacy.get("concepts") if isinstance(legacy.get("concepts"), list) else []

    concepts_csv = workspace / "concepts.csv"
    if not concepts_csv.exists():
        raise FileNotFoundError(f"concepts.csv not found at {concepts_csv}")
    parse_rows = read_concepts_csv_rows(concepts_csv)

    # Index PARSE concepts.csv by stem (lowercase, variant suffix stripped).
    parse_by_stem: dict[str, list[Mapping[str, str]]] = {}
    for row in parse_rows:
        stem = _stem_label(row.get("concept_en") or "").casefold()
        if stem:
            parse_by_stem.setdefault(stem, []).append(row)

    speakers = _project_speakers(workspace)
    if speaker_filter is not None:
        speakers = _apply_speaker_filter(speakers, speaker_filter)

    annotations_dir = workspace / "annotations"
    annotation_payloads: dict[str, dict[str, Any]] = {}
    thesis_ids_by_speaker: dict[str, set[str]] = {}
    for path in _iter_annotation_files(annotations_dir):
        speaker = _speaker_for_annotation(path)
        if speakers and speaker not in speakers:
            continue
        try:
            payload = _load_json(path)
        except json.JSONDecodeError as exc:
            print(f"warning: skipping unparseable annotation {path}: {exc}", file=sys.stderr)
            continue
        annotation_payloads[speaker] = payload
        thesis_ids_by_speaker[speaker] = _tagged_concept_ids(payload, tag_id)

    if not speakers:
        speakers = sorted(annotation_payloads.keys())

    enrichments = _load_enrichments(workspace)
    cognate_sets = enrichments.get("cognate_sets", {})
    similarity = enrichments.get("similarity", {})
    borrowing_flags = enrichments.get("borrowing_flags", {})

    clip_plan: list[tuple[str, dict[str, Any]]] = []
    out_concepts: list[dict[str, Any]] = []
    unmatched_legacy: list[str] = []

    for legacy_c in legacy_concepts:
        if not isinstance(legacy_c, Mapping):
            continue
        legacy_id = str(legacy_c.get("concept_id") or "").strip()
        legacy_en = str(legacy_c.get("concept_en") or "").strip()
        legacy_stem = _stem_label(legacy_en).casefold()
        matched_rows = parse_by_stem.get(legacy_stem, [])
        matched_ids: set[str] = {
            str(r.get("id") or "").strip() for r in matched_rows if r.get("id")
        }
        if not matched_rows:
            unmatched_legacy.append(legacy_en or legacy_id)
        legacy_source = _legacy_concept_source(legacy_c)

        forms: list[dict[str, Any]] = []
        for speaker in speakers:
            payload = annotation_payloads.get(speaker, {})
            concept_tier_by_id = _concept_intervals_by_id(payload)

            speaker_intervals: list[Mapping[str, Any]] = []
            for cid in matched_ids:
                speaker_intervals.extend(concept_tier_by_id.get(cid, []))

            if not speaker_intervals:
                forms.append(
                    _empty_form(
                        speaker,
                        concept_id=legacy_id,
                        label=legacy_en,
                        cognate_sets=cognate_sets,
                        similarity=similarity,
                        borrowing_flags=borrowing_flags,
                    )
                )
                continue

            # PARSE collapses cross-survey readings under a single concept_id
            # (e.g. JBIL 75 "sister" and KLQ 2.5 "sister" both live at
            # concept_id=16, distinguished only by ``audition_prefix``). When
            # multiple candidates exist, prefer the one whose audition_prefix
            # matches the legacy concept_id — that is the survey item the
            # legacy review_tool was built from, so its IPA/ortho match what
            # the committee expects. Fall back to all candidates when no
            # audition_prefix matches (the speaker only annotated via a
            # different survey). Within the chosen pool, longest wins as a
            # representativeness heuristic.
            prefix_matches = [
                iv
                for iv in speaker_intervals
                if legacy_id and str(iv.get("audition_prefix") or "").strip() == legacy_id
            ]
            candidate_pool = prefix_matches if prefix_matches else speaker_intervals
            interval = max(
                candidate_pool,
                key=lambda iv: float(
                    _interval_field(iv, "end", "end_sec") or 0.0
                ) - float(_interval_field(iv, "start", "start_sec") or 0.0),
            )
            start_sec = float(_interval_field(interval, "start", "start_sec") or 0.0)
            end_sec = float(_interval_field(interval, "end", "end_sec") or 0.0)
            duration_sec = max(0.0, end_sec - start_sec)

            ipa_text = _crosstier_text(payload, "ipa", matched_ids, start_sec, end_sec)
            ortho_text = _crosstier_text(payload, "ortho", matched_ids, start_sec, end_sec)

            audio_filename = _legacy_audio_filename(
                source=legacy_source,
                legacy_concept_id=legacy_id,
                gloss=_stem_label(legacy_en) or legacy_en or legacy_id,
                speaker=speaker,
            )
            audio_relpath = f"audio/{speaker}/{audio_filename}"
            source_wav_rel = _source_wav_relative(payload, speaker)

            form = {
                "speaker": speaker,
                "ipa": ipa_text or "",
                "ortho": ortho_text or "",
                "cognate_class": _cognate_class_for(cognate_sets, legacy_id, legacy_en, speaker),
                "arabic_similarity": _similarity_score(similarity, legacy_id, legacy_en, speaker, "ar"),
                "persian_similarity": _similarity_score(similarity, legacy_id, legacy_en, speaker, "fa"),
                "borrowing_flag": _borrowing_flag_for(borrowing_flags, legacy_id, legacy_en, speaker),
                "audio_path": audio_relpath,
                "spectrogram_path": None,
                "variants": None,
                "source": legacy_source,
                "verification": None,
                "start_sec": start_sec,
                "duration_sec": duration_sec,
            }
            forms.append(form)
            clip_plan.append(
                (
                    source_wav_rel,
                    {
                        "speaker": speaker,
                        "audio_path": audio_relpath,
                        "start_sec": start_sec,
                        "duration_sec": duration_sec,
                        "concept_id": legacy_id,
                        "concept_en": _stem_label(legacy_en) or legacy_en,
                        "ipa": form["ipa"],
                        "ortho": form["ortho"],
                    },
                )
            )

        out_concepts.append(
            {
                "concept_id": legacy_id,
                "concept_en": legacy_en,
                "arabic": legacy_c.get("arabic") if isinstance(legacy_c.get("arabic"), Mapping) else {"form": "", "ipa": ""},
                "persian": legacy_c.get("persian") if isinstance(legacy_c.get("persian"), Mapping) else {"form": "", "ipa": ""},
                "forms": forms,
            }
        )

    metadata = {
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "speakers": list(speakers),
        "total_concepts": len(out_concepts),
        "method": "parse_workspace_export_legacy_anchored",
        "threshold": None,
        "audio_linked": True,
        "spectrograms": False,
        "klq_merge": False,
        "noisy_verification": False,
        "version": LEGACY_SCHEMA_VERSION,
        "phonetic_flags": {},
        "source": {
            "workspace": str(workspace),
            "tag_id": tag_id,
            "legacy_anchor": str(legacy_anchor),
            "unmatched_legacy_concepts": unmatched_legacy,
        },
    }
    return {"metadata": metadata, "concepts": out_concepts}, clip_plan


def _write_timestamps_csv(
    out_dir: Path,
    speaker: str,
    rows: list[dict[str, Any]],
) -> None:
    """Emit a legacy-style ``<Speaker>_timestamps.csv`` per speaker."""
    out_path = out_dir / f"{speaker}_timestamps.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "concept_id",
        "concept_en",
        "start_sec",
        "duration_sec",
        "audio_path",
        "ipa",
        "ortho",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def build_review_data(
    *,
    workspace: Path,
    tag_id: str = DEFAULT_TAG_ID,
    contact_config: Path | None = None,
    speaker_filter: Iterable[str] | None = None,
    concept_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Return ``(review_data_payload, clip_plan)``.

    ``clip_plan`` is a list of ``(source_wav_relpath, clip_spec)`` tuples. Each
    ``clip_spec`` carries the keys ``speaker``, ``audio_path``, ``start_sec``,
    ``duration_sec``, plus the timestamps-CSV row fields. The caller decides
    whether to materialize the clips via ffmpeg.

    Analytical fields (cognate_class, arabic/persian similarity, borrowing_flag,
    concept-level arabic/persian reference forms) are populated from
    ``<workspace>/parse-enrichments.json`` and ``contact_config`` when those
    sources carry data; otherwise the exporter falls back to the legacy
    null / zero / "?" defaults.

    When ``speaker_filter`` is non-empty, only those speakers appear in the
    output (project.json order preserved). Used by callers shipping a curated
    subset of speakers to the review_tool without modifying the workspace.
    """
    speakers = _project_speakers(workspace)
    if speaker_filter is not None:
        speakers = _apply_speaker_filter(speakers, speaker_filter)
    concepts_csv = workspace / "concepts.csv"
    if not concepts_csv.exists():
        raise FileNotFoundError(f"concepts.csv not found at {concepts_csv}")
    concept_rows = read_concepts_csv_rows(concepts_csv)
    concept_by_id = {str(row.get("id") or "").strip(): row for row in concept_rows}

    enrichments = _load_enrichments(workspace)
    cognate_sets = enrichments.get("cognate_sets", {})
    similarity = enrichments.get("similarity", {})
    borrowing_flags = enrichments.get("borrowing_flags", {})
    contact_langs = _load_contact_languages(_resolve_contact_config(workspace, contact_config))

    annotations_dir = workspace / "annotations"
    annotation_payloads: dict[str, dict[str, Any]] = {}
    thesis_ids_by_speaker: dict[str, set[str]] = {}
    for path in _iter_annotation_files(annotations_dir):
        speaker = _speaker_for_annotation(path)
        try:
            payload = _load_json(path)
        except json.JSONDecodeError as exc:
            print(f"warning: skipping unparseable annotation {path}: {exc}", file=sys.stderr)
            continue
        annotation_payloads[speaker] = payload
        thesis_ids_by_speaker[speaker] = _tagged_concept_ids(payload, tag_id)

    if not speakers:
        speakers = sorted(annotation_payloads.keys())

    # Union of thesis-tagged concept ids across speakers, in concepts.csv order.
    tagged_union: set[str] = set()
    for ids in thesis_ids_by_speaker.values():
        tagged_union.update(ids)

    if concept_ids is not None:
        # Explicit concept selection (e.g. the caller's currently-filtered concept
        # menu) overrides tag filtering — export exactly these ids, preserving the
        # caller's order (so the export mirrors the concept menu's sort) rather than
        # concepts.csv order. Unknown/duplicate ids are dropped; caller owns the set.
        valid_ids = {str(row.get("id") or "").strip() for row in concept_rows}
        valid_ids.discard("")
        seen_requested: set[str] = set()
        ordered_concept_ids = []
        for raw in concept_ids:
            cid = str(raw).strip()
            if cid and cid in valid_ids and cid not in seen_requested:
                seen_requested.add(cid)
                ordered_concept_ids.append(cid)
    else:
        ordered_concept_ids = [
            str(row.get("id") or "").strip()
            for row in concept_rows
            if str(row.get("id") or "").strip() in tagged_union
        ]
        # Fallback: if no tags found, exporter still emits an empty schema so the
        # caller sees a valid output rather than a crash. Stays explicit in logs.
        if not ordered_concept_ids and tagged_union:
            ordered_concept_ids = sorted(tagged_union)

    concept_entries: list[dict[str, Any]] = []
    for concept_index, concept_id in enumerate(ordered_concept_ids):
        row = concept_by_id.get(concept_id, {})
        full_label = row_value(row, "concept_en") or row_value(row, "label")
        gloss = _stem_label(full_label) or full_label or concept_id
        variant = _variant_letter(full_label) or "A"
        survey = row_value(row, "source_survey")
        source_item = row_value(row, "source_item") or concept_id
        if not survey and full_label:
            # Tolerate Audition-style cue names if source_survey wasn't backfilled.
            cue_item, cue_survey, _ = parse_cue_name(full_label)
            survey = survey or cue_survey or ""
            if cue_item and not source_item:
                source_item = cue_item

        forms: list[dict[str, Any]] = []
        entry_clip_plan_by_speaker: dict[str, tuple[str, dict[str, Any]]] = {}
        for speaker in speakers:
            payload = annotation_payloads.get(speaker, {})
            intervals = _concept_intervals_by_id(payload).get(concept_id, [])

            if not intervals:
                forms.append(
                    _empty_form(
                        speaker,
                        concept_id=concept_id,
                        label=full_label,
                        cognate_sets=cognate_sets,
                        similarity=similarity,
                        borrowing_flags=borrowing_flags,
                    )
                )
                continue

            interval = intervals[0]
            start_sec = float(_interval_field(interval, "start", "start_sec") or 0.0)
            end_sec = float(_interval_field(interval, "end", "end_sec") or 0.0)
            duration_sec = max(0.0, end_sec - start_sec)
            crosstier_ids = {value for value in {concept_id, source_item} if value}
            ipa_text = _crosstier_text(payload, "ipa", crosstier_ids, start_sec, end_sec)
            ortho_text = _crosstier_text(payload, "ortho", crosstier_ids, start_sec, end_sec)

            filename = _audio_filename(survey, source_item, variant, gloss, speaker)
            audio_relpath = f"audio/{speaker}/{filename}"

            source_wav_rel = _source_wav_relative(payload, speaker)
            form = _form_from_interval(
                speaker=speaker,
                interval=interval,
                concept_row=row,
                audio_relpath=audio_relpath,
                start_sec=start_sec,
                duration_sec=duration_sec,
                concept_id=concept_id,
                label=full_label,
                cognate_sets=cognate_sets,
                similarity=similarity,
                borrowing_flags=borrowing_flags,
                ipa_override=ipa_text,
                ortho_override=ortho_text,
            )
            forms.append(form)

            entry_clip_plan_by_speaker[speaker] = (
                source_wav_rel,
                {
                    "speaker": speaker,
                    "audio_path": audio_relpath,
                    "start_sec": start_sec,
                    "duration_sec": duration_sec,
                    "concept_id": concept_id,
                    "concept_en": gloss,
                    "ipa": form["ipa"],
                    "ortho": form["ortho"],
                },
            )

        contact_forms = _contact_forms_for_concept(contact_langs, concept_id, full_label)
        concept_entries.append(
            {
                "concept_id": source_item or concept_id,
                "concept_en": gloss,
                "arabic": contact_forms["arabic"],
                "persian": contact_forms["persian"],
                "forms": forms,
                "_clip_plan": list(entry_clip_plan_by_speaker.values()),
                "_clip_plan_by_speaker": entry_clip_plan_by_speaker,
                "_source_full_label": full_label,
                "_source_index": concept_index,
            }
        )

    concept_entries, clip_plan = _collapse_clarifier_siblings(concept_entries)

    metadata = {
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "speakers": list(speakers),
        "total_concepts": len(concept_entries),
        "method": "parse_workspace_export",
        "threshold": None,
        "audio_linked": True,
        "spectrograms": False,
        "klq_merge": False,
        "noisy_verification": False,
        "version": LEGACY_SCHEMA_VERSION,
        "phonetic_flags": {},
        "source": {
            "workspace": str(workspace),
            "tag_id": tag_id,
            "tagged_concept_count": len(tagged_union),
        },
    }

    return {"metadata": metadata, "concepts": concept_entries}, clip_plan


def materialize_clips(
    *,
    workspace: Path,
    out_dir: Path,
    clip_plan: list[tuple[str, dict[str, Any]]],
    ffmpeg_bin: str = "ffmpeg",
) -> tuple[int, list[str]]:
    """Run ffmpeg over ``clip_plan``. Returns ``(clipped_count, error_messages)``."""
    errors: list[str] = []
    clipped = 0
    for source_rel, spec in clip_plan:
        source_path = _resolve_source_wav(workspace, source_rel)
        if not source_path.exists():
            errors.append(f"missing source WAV: {source_path} (for {spec['audio_path']})")
            continue
        out_path = out_dir / spec["audio_path"]
        try:
            _clip_wav(
                source_path,
                spec["start_sec"],
                spec["duration_sec"],
                out_path,
                ffmpeg_bin=ffmpeg_bin,
            )
            clipped += 1
        except subprocess.CalledProcessError as exc:
            errors.append(f"ffmpeg failed for {spec['audio_path']}: {exc}")
    return clipped, errors


def _analytical_coverage(review_data: Mapping[str, Any]) -> dict[str, int]:
    """Count how many emitted forms/concepts actually carry analytical data.

    "Populated" = not equal to the legacy null/zero/``"?"`` default. Callers
    use this to tell whether PARSE's compute pipelines have been run — a
    summary with all-zero counts means the export is structurally correct but
    the analytical sources (parse-enrichments.json + sil_contact_languages.json)
    have not been populated yet.
    """
    counts = {
        "forms_with_cognate_class": 0,
        "forms_with_arabic_similarity": 0,
        "forms_with_persian_similarity": 0,
        "forms_with_borrowing_flag": 0,
        "concepts_with_arabic_ref": 0,
        "concepts_with_persian_ref": 0,
    }
    for concept in review_data.get("concepts", []) or []:
        if not isinstance(concept, Mapping):
            continue
        arabic = concept.get("arabic") if isinstance(concept.get("arabic"), Mapping) else {}
        if str(arabic.get("form") or "").strip():
            counts["concepts_with_arabic_ref"] += 1
        persian = concept.get("persian") if isinstance(concept.get("persian"), Mapping) else {}
        if str(persian.get("form") or "").strip():
            counts["concepts_with_persian_ref"] += 1
        for form in concept.get("forms", []) or []:
            if not isinstance(form, Mapping):
                continue
            if str(form.get("cognate_class") or "").strip() not in {"", "?"}:
                counts["forms_with_cognate_class"] += 1
            try:
                if float(form.get("arabic_similarity") or 0.0) > 0.0:
                    counts["forms_with_arabic_similarity"] += 1
            except (TypeError, ValueError):
                pass
            try:
                if float(form.get("persian_similarity") or 0.0) > 0.0:
                    counts["forms_with_persian_similarity"] += 1
            except (TypeError, ValueError):
                pass
            if form.get("borrowing_flag") is not None:
                counts["forms_with_borrowing_flag"] += 1
    return counts


def write_outputs(
    *,
    workspace: Path,
    out_dir: Path,
    review_data: dict[str, Any],
    clip_plan: list[tuple[str, dict[str, Any]]],
    skip_audio: bool,
    ffmpeg_bin: str = "ffmpeg",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    review_path = out_dir / "review_data.json"
    review_path.write_text(
        json.dumps(review_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    timestamps_dir = out_dir / "timestamps"
    by_speaker: dict[str, list[dict[str, Any]]] = {}
    for _source_rel, spec in clip_plan:
        by_speaker.setdefault(spec["speaker"], []).append(spec)
    for speaker, rows in by_speaker.items():
        rows.sort(key=lambda r: (r.get("concept_id", ""), r.get("start_sec", 0.0)))
        _write_timestamps_csv(timestamps_dir, speaker, rows)

    summary: dict[str, Any] = {
        "review_data_path": str(review_path),
        "concept_count": len(review_data.get("concepts", [])),
        "speaker_count": len(review_data.get("metadata", {}).get("speakers", [])),
        "clip_plan_count": len(clip_plan),
        "audio_clipped": 0,
        "audio_errors": [],
        "skipped_audio": bool(skip_audio),
        "analytical_coverage": _analytical_coverage(review_data),
    }

    if not skip_audio and clip_plan:
        clipped, errors = materialize_clips(
            workspace=workspace,
            out_dir=out_dir,
            clip_plan=clip_plan,
            ffmpeg_bin=ffmpeg_bin,
        )
        summary["audio_clipped"] = clipped
        summary["audio_errors"] = errors

    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a PARSE workspace to legacy review_tool format.",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="Path to the PARSE workspace root (containing project.json + concepts.csv).",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Destination directory for review_data.json + audio/ + timestamps/.",
    )
    parser.add_argument(
        "--tag-id",
        default=DEFAULT_TAG_ID,
        help="Tag id to filter concepts by (default: %(default)s — the thesis tag).",
    )
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Emit review_data.json + timestamps only; do not run ffmpeg.",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg binary path (default: %(default)s).",
    )
    parser.add_argument(
        "--contact-config",
        type=Path,
        default=None,
        help=(
            "Path to sil_contact_languages.json (Arabic/Persian reference forms). "
            "Defaults to <workspace>/config/sil_contact_languages.json when present, "
            "then <repo>/config/sil_contact_languages.json. Pass an explicit path or "
            "set to /dev/null to skip."
        ),
    )
    parser.add_argument(
        "--speakers",
        nargs="+",
        default=None,
        metavar="SPEAKER",
        help=(
            "Restrict the export to this set of speakers (project.json order is "
            "preserved). Errors if any name is not in the workspace. Omit to "
            "export every speaker. Use to ship a curated review_tool subset "
            "without mutating the workspace."
        ),
    )
    parser.add_argument(
        "--legacy-anchor",
        type=Path,
        default=None,
        help=(
            "DEPRECATED: path to an existing legacy review_data.json to anchor the export "
            "against. When set, the exporter iterates the legacy concepts list "
            "(preserving concept_id / concept_en / arabic / persian) and rebuilds "
            "each speaker's form from current PARSE workspace data, matching by "
            "concept gloss stem. Use this to collapse PARSE issue #529's "
            "duplicate concept rows down to one entry per gloss. Post-MC-418 "
            "canonical workspaces should use the default export path instead."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = args.workspace.resolve()
    out_dir = args.out.resolve()
    contact_config = args.contact_config.resolve() if args.contact_config else None
    legacy_anchor = args.legacy_anchor.resolve() if args.legacy_anchor else None
    if legacy_anchor is not None:
        warnings.warn(
            "--legacy-anchor is deprecated and will be removed in a future release. "
            "The default non-anchored export now produces the canonical review_tool "
            "shape against post-MC-418 workspaces. Concept identity is canonical in "
            "/home/lucas/parse-workspace after the 2026-05-28 migration. Retire "
            "your invocation of --legacy-anchor before 2026-Q3 or the flag will "
            "start failing.",
            DeprecationWarning,
            stacklevel=2,
        )

    if not workspace.exists():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 2
    if legacy_anchor is not None and not legacy_anchor.exists():
        print(f"error: --legacy-anchor file not found: {legacy_anchor}", file=sys.stderr)
        return 2

    try:
        if legacy_anchor is not None:
            review_data, clip_plan = build_review_data_anchored(
                workspace=workspace,
                legacy_anchor=legacy_anchor,
                tag_id=args.tag_id,
                speaker_filter=args.speakers,
            )
        else:
            review_data, clip_plan = build_review_data(
                workspace=workspace,
                tag_id=args.tag_id,
                contact_config=contact_config,
                speaker_filter=args.speakers,
            )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = write_outputs(
        workspace=workspace,
        out_dir=out_dir,
        review_data=review_data,
        clip_plan=clip_plan,
        skip_audio=args.skip_audio,
        ffmpeg_bin=args.ffmpeg,
    )

    print(json.dumps(summary, indent=2))
    return 0 if not summary.get("audio_errors") else 1


if __name__ == "__main__":
    sys.exit(main())
