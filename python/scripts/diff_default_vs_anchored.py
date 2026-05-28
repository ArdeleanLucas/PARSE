#!/usr/bin/env python3
"""Diff default review export coverage against an anchored review_data.json.

MC-424-A uses this script to enumerate coverage rows that are present in the
anchored review_tool baseline but missing from the default PARSE export, then
classify each row against the live workspace without mutating it.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_PYTHON = Path(__file__).resolve().parents[1]
if str(REPO_PYTHON) not in sys.path:
    sys.path.insert(0, str(REPO_PYTHON))

from concept_canonical import strip_clarifier  # noqa: E402
from export_review_data import (  # noqa: E402
    DEFAULT_TAG_ID,
    _concept_intervals_by_id,
    _crosstier_text,
    _load_json,
    _stem_label,
    _tagged_concept_ids,
)

SURFACE_ORDER = {"ortho": 0, "audio": 1, "arabic": 2, "persian": 3}


@dataclass(frozen=True)
class Gap:
    surface: str
    concept_en: str
    speaker: str
    anchored: str
    default: str
    case: str = "unclassified"
    rationale: str = ""

    def sort_key(self) -> tuple[int, str, str]:
        return (SURFACE_ORDER.get(self.surface, 99), self.concept_en.casefold(), self.speaker.casefold())


def _load_review_data(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _concepts_by_label(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    concepts = data.get("concepts")
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(concepts, list):
        return out
    for concept in concepts:
        if not isinstance(concept, Mapping):
            continue
        label = str(concept.get("concept_en") or "").strip()
        if label:
            out[label] = concept
    return out


def _forms_by_speaker(concept: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    forms = concept.get("forms")
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(forms, list):
        return out
    for form in forms:
        if not isinstance(form, Mapping):
            continue
        speaker = str(form.get("speaker") or "").strip()
        if speaker:
            out[speaker] = form
    return out


def _text_present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _audio_present(value: Any) -> bool:
    return bool(value)


def _contact_form(concept: Mapping[str, Any], legacy_key: str) -> str:
    entry = concept.get(legacy_key)
    if not isinstance(entry, Mapping):
        return ""
    return str(entry.get("form") or "").strip()


def enumerate_anchor_only_gaps(default: Mapping[str, Any], anchored: Mapping[str, Any]) -> list[Gap]:
    """Rows where anchored has coverage but default does not."""

    default_by_label = _concepts_by_label(default)
    anchored_by_label = _concepts_by_label(anchored)
    gaps: list[Gap] = []
    for concept_en in sorted(set(default_by_label) & set(anchored_by_label), key=str.casefold):
        default_concept = default_by_label[concept_en]
        anchored_concept = anchored_by_label[concept_en]
        default_forms = _forms_by_speaker(default_concept)
        anchored_forms = _forms_by_speaker(anchored_concept)
        for speaker in sorted(set(default_forms) & set(anchored_forms), key=str.casefold):
            default_form = default_forms[speaker]
            anchored_form = anchored_forms[speaker]
            anchored_ortho = str(anchored_form.get("ortho") or "").strip()
            default_ortho = str(default_form.get("ortho") or "").strip()
            if anchored_ortho and not default_ortho:
                gaps.append(Gap("ortho", concept_en, speaker, anchored_ortho, default_ortho))
            if _audio_present(anchored_form.get("audio_path")) and not _audio_present(default_form.get("audio_path")):
                gaps.append(Gap("audio", concept_en, speaker, "present", "absent"))
        for surface, legacy_key in (("arabic", "arabic"), ("persian", "persian")):
            anchored_form = _contact_form(anchored_concept, legacy_key)
            default_form = _contact_form(default_concept, legacy_key)
            if anchored_form and not default_form:
                gaps.append(Gap(surface, concept_en, "", anchored_form, default_form))
    return sorted(gaps, key=Gap.sort_key)


def enumerate_default_only_rows(default: Mapping[str, Any], anchored: Mapping[str, Any]) -> list[Gap]:
    """Rows where default has coverage but anchored does not; useful for net deltas."""

    default_by_label = _concepts_by_label(default)
    anchored_by_label = _concepts_by_label(anchored)
    rows: list[Gap] = []
    for concept_en in sorted(set(default_by_label) & set(anchored_by_label), key=str.casefold):
        default_concept = default_by_label[concept_en]
        anchored_concept = anchored_by_label[concept_en]
        default_forms = _forms_by_speaker(default_concept)
        anchored_forms = _forms_by_speaker(anchored_concept)
        for speaker in sorted(set(default_forms) & set(anchored_forms), key=str.casefold):
            default_form = default_forms[speaker]
            anchored_form = anchored_forms[speaker]
            default_ortho = str(default_form.get("ortho") or "").strip()
            anchored_ortho = str(anchored_form.get("ortho") or "").strip()
            if default_ortho and not anchored_ortho:
                rows.append(Gap("ortho", concept_en, speaker, anchored_ortho, default_ortho))
            if _audio_present(default_form.get("audio_path")) and not _audio_present(anchored_form.get("audio_path")):
                rows.append(Gap("audio", concept_en, speaker, "absent", "present"))
        for surface, legacy_key in (("arabic", "arabic"), ("persian", "persian")):
            default_form = _contact_form(default_concept, legacy_key)
            anchored_form = _contact_form(anchored_concept, legacy_key)
            if default_form and not anchored_form:
                rows.append(Gap(surface, concept_en, "", anchored_form, default_form))
    return sorted(rows, key=Gap.sort_key)


def _base_label(label: str) -> str:
    return (strip_clarifier(label).strip() or _stem_label(label).strip() or label.strip()).casefold()


class WorkspaceClassifier:
    def __init__(self, workspace: Path, speakers: Iterable[str]) -> None:
        self.workspace = workspace
        self.rows_by_base = self._load_concept_rows(workspace / "concepts.csv")
        self.annotations = self._load_annotations(workspace, speakers)
        self.contact_langs = self._load_contact_langs(workspace / "config" / "sil_contact_languages.json")

    @staticmethod
    def _load_concept_rows(path: Path) -> dict[str, list[Mapping[str, str]]]:
        rows_by_base: dict[str, list[Mapping[str, str]]] = {}
        if not path.exists():
            return rows_by_base
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                label = str(row.get("concept_en") or "")
                rows_by_base.setdefault(_base_label(label), []).append(row)
        return rows_by_base

    @staticmethod
    def _load_annotations(workspace: Path, speakers: Iterable[str]) -> dict[str, Mapping[str, Any]]:
        annotations: dict[str, Mapping[str, Any]] = {}
        for speaker in speakers:
            if not speaker:
                continue
            path = workspace / "annotations" / f"{speaker}.parse.json"
            if not path.exists():
                path = workspace / "annotations" / f"{speaker}.json"
            if path.exists():
                annotations[speaker] = _load_json(path)
        return annotations

    @staticmethod
    def _load_contact_langs(path: Path) -> dict[str, Mapping[str, Any]]:
        if not path.exists():
            return {}
        data = _load_json(path)
        out: dict[str, Mapping[str, Any]] = {}
        for code, entry in data.items():
            if isinstance(code, str) and not code.startswith("_") and isinstance(entry, Mapping):
                concepts = entry.get("concepts")
                out[code] = concepts if isinstance(concepts, Mapping) else {}
        return out

    def classify(self, gap: Gap) -> Gap:
        if gap.surface in {"ortho", "audio"}:
            return self._classify_speaker_gap(gap)
        return self._classify_contact_gap(gap)

    def _classify_speaker_gap(self, gap: Gap) -> Gap:
        payload = self.annotations.get(gap.speaker, {})
        rows = self.rows_by_base.get(_base_label(gap.concept_en), [])
        if not payload or not rows:
            return self._with_case(gap, "case 3", "no matching workspace annotation/concepts.csv row")
        tagged = _tagged_concept_ids(payload, DEFAULT_TAG_ID)
        intervals_by_id = _concept_intervals_by_id(payload)
        evidence: list[str] = []
        untagged_evidence = False
        for row in rows:
            concept_id = str(row.get("id") or "").strip()
            source_item = str(row.get("source_item") or "").strip()
            label = str(row.get("concept_en") or "").strip()
            for interval in intervals_by_id.get(concept_id, []):
                start = float(interval.get("start") or interval.get("start_sec") or 0.0)
                end = float(interval.get("end") or interval.get("end_sec") or 0.0)
                concept_ids = {value for value in (concept_id, source_item) if value}
                ortho = _crosstier_text(payload, "ortho", concept_ids, start, end)
                has_surface = gap.surface == "audio" or _text_present(ortho)
                if not has_surface:
                    continue
                if concept_id not in tagged:
                    untagged_evidence = True
                evidence.append(f"{label or concept_id}@{start:.3f}-{end:.3f}")
        if not evidence:
            return self._with_case(gap, "case 3", "no overlapping workspace interval with the missing surface")
        if untagged_evidence:
            return self._with_case(
                gap,
                "case 1",
                "workspace interval exists but default export required a speaker-local thesis tag",
            )
        return self._with_case(gap, "case 1", "workspace interval exists but default export emitted an empty form")

    def _classify_contact_gap(self, gap: Gap) -> Gap:
        lang_code = "ar" if gap.surface == "arabic" else "fa"
        concepts = self.contact_langs.get(lang_code, {})
        if not isinstance(concepts, Mapping):
            concepts = {}
        base = _base_label(gap.concept_en)
        matches = sorted(str(key) for key in concepts if _base_label(str(key)) == base)
        if not matches:
            return self._with_case(gap, "case 3", f"no {lang_code} contact-cache key with matching canonical label")
        return self._with_case(
            gap,
            "case 2",
            f"contact cache has {lang_code} key(s) {matches}; default lookup missed the canonicalized label",
        )

    @staticmethod
    def _with_case(gap: Gap, case: str, rationale: str) -> Gap:
        return Gap(gap.surface, gap.concept_en, gap.speaker, gap.anchored, gap.default, case, rationale)


def _speakers(default: Mapping[str, Any], anchored: Mapping[str, Any]) -> list[str]:
    speakers: list[str] = []
    for data in (default, anchored):
        metadata = data.get("metadata")
        values = metadata.get("speakers") if isinstance(metadata, Mapping) else []
        if isinstance(values, list):
            for speaker in values:
                text = str(speaker or "").strip()
                if text and text not in speakers:
                    speakers.append(text)
    return speakers


def _counts(rows: Iterable[Gap]) -> dict[str, int]:
    counts = {surface: 0 for surface in SURFACE_ORDER}
    for row in rows:
        counts[row.surface] = counts.get(row.surface, 0) + 1
    return counts


def _case_counts(rows: Iterable[Gap]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.case] = counts.get(row.case, 0) + 1
    return counts


def _markdown_table(rows: list[Gap]) -> str:
    lines = ["| Surface | Concept | Speaker | Anchored | Default | Case | Rationale |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        speaker = row.speaker or "—"
        anchored = str(row.anchored).replace("|", "\\|") or "—"
        default = str(row.default).replace("|", "\\|") or "—"
        rationale = row.rationale.replace("|", "\\|")
        lines.append(
            f"| {row.surface} | {row.concept_en} | {speaker} | {anchored} | {default} | {row.case} | {rationale} |"
        )
    return "\n".join(lines)


def render_report(anchor_only: list[Gap], default_only: list[Gap]) -> str:
    lines: list[str] = []
    lines.append("# Default vs anchored coverage diff")
    lines.append("")
    lines.append(f"Anchored-present/default-missing rows: {len(anchor_only)}")
    lines.append(f"Default-present/anchored-missing offset rows: {len(default_only)}")
    lines.append("")
    lines.append("## Anchored-present/default-missing counts")
    for surface, count in _counts(anchor_only).items():
        lines.append(f"- {surface}: {count}")
    if any(row.case != "unclassified" for row in anchor_only):
        lines.append("")
        lines.append("## Classification counts")
        for case, count in sorted(_case_counts(anchor_only).items()):
            lines.append(f"- {case}: {count}")
    lines.append("")
    lines.append("## Anchored-present/default-missing rows")
    lines.append(_markdown_table(anchor_only))
    if default_only:
        lines.append("")
        lines.append("## Default-present/anchored-missing offset rows")
        lines.append(_markdown_table(default_only))
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default", required=True, type=Path, help="Default-mode review_data.json")
    parser.add_argument("--anchored", required=True, type=Path, help="Anchored review_data.json")
    parser.add_argument("--workspace", type=Path, help="PARSE workspace for case classification")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    default = _load_review_data(args.default)
    anchored = _load_review_data(args.anchored)
    anchor_only = enumerate_anchor_only_gaps(default, anchored)
    default_only = enumerate_default_only_rows(default, anchored)
    if args.workspace:
        classifier = WorkspaceClassifier(args.workspace, _speakers(default, anchored))
        anchor_only = [classifier.classify(row) for row in anchor_only]
    print(render_report(anchor_only, default_only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
