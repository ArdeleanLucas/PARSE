"""Convert review_data.json (old review tool) to PARSE v5 compare-compatible data.

Usage:
    python3 python/import_review_data.py review_data.json --output-dir .

Generates:
    project.json                 — compare-mode project config
    concepts.csv                 — concept list consumed by compare.js
    annotations/<Speaker>.json   — per-speaker tiered annotation records
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from concept_source_item import write_concepts_csv_rows


PROJECT_NAME = "Southern Kurdish Dialect Comparison"
PROJECT_ID = "southern-kurdish-dialect-comparison"


def to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_non_negative_float(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0:
        return None
    return num


def load_json(path: pathlib.Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    return {}


def load_review_data(path: pathlib.Path) -> Dict[str, Any]:
    return load_json(path)


def load_source_index(output_dir: pathlib.Path) -> Dict[str, Any]:
    source_index_path = output_dir / "source_index.json"
    if not source_index_path.exists():
        return {}

    try:
        return load_json(source_index_path)
    except Exception as exc:  # pragma: no cover - defensive path
        print(
            f"Warning: failed to parse {source_index_path}: {exc}",
            file=sys.stderr,
        )
        return {}


def extract_concepts(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    concepts_raw = data.get("concepts", [])
    if not isinstance(concepts_raw, list):
        return []

    concepts: List[Dict[str, Any]] = []
    for idx, concept in enumerate(concepts_raw, start=1):
        if not isinstance(concept, dict):
            continue

        forms = concept.get("forms", [])
        if not isinstance(forms, list):
            forms = []

        concepts.append(
            {
                "id": str(idx),
                "source_id": to_text(concept.get("concept_id")) or str(idx),
                "label": to_text(concept.get("concept_en")),
                "forms": forms,
            }
        )

    return concepts


def extract_speakers(concepts: List[Dict[str, Any]]) -> List[str]:
    speakers: List[str] = []
    seen = set()

    for concept in concepts:
        forms = concept.get("forms", [])
        if not isinstance(forms, list):
            continue

        for form in forms:
            if not isinstance(form, dict):
                continue

            speaker = to_text(form.get("speaker"))
            if not speaker or speaker in seen:
                continue

            seen.add(speaker)
            speakers.append(speaker)

    return speakers


def build_speaker_form_lookup(
    concepts: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return speaker -> concept_id -> selected form dict."""
    lookup: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for concept in concepts:
        concept_id = to_text(concept.get("id"))
        forms = concept.get("forms", [])
        if not concept_id or not isinstance(forms, list):
            continue

        for form in forms:
            if not isinstance(form, dict):
                continue

            speaker = to_text(form.get("speaker"))
            if not speaker:
                continue

            speaker_map = lookup.setdefault(speaker, {})
            # Keep first occurrence for deterministic behavior.
            if concept_id not in speaker_map:
                speaker_map[concept_id] = form

    return lookup


def build_project_json(speakers: List[str], concept_total: int) -> Dict[str, Any]:
    speaker_map = {speaker: {} for speaker in speakers}

    return {
        "name": PROJECT_NAME,
        "sourceIndex": "source_index.json",
        "concepts": {
            "source": "concepts.csv",
            "id_column": "id",
            "label_column": "concept_en",
            "total": concept_total,
        },
        "speakers": speaker_map,
    }


def build_concepts_csv_rows(concepts: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for concept in concepts:
        rows.append(
            {
                "id": to_text(concept.get("id")),
                "concept_en": to_text(concept.get("label")),
            }
        )
    return rows


def best_source_for_speaker(source_index: Dict[str, Any], speaker: str) -> Tuple[str, Optional[float]]:
    speakers_map = source_index.get("speakers", {})
    if not isinstance(speakers_map, dict):
        return "", None

    entry = speakers_map.get(speaker)
    if not isinstance(entry, dict):
        return "", None

    source_list = entry.get("source_wavs")
    if not isinstance(source_list, list):
        source_list = entry.get("source_files")
    if not isinstance(source_list, list):
        source_list = []

    selected: Dict[str, Any] = {}
    for candidate in source_list:
        if isinstance(candidate, dict) and candidate.get("is_primary"):
            selected = candidate
            break

    if not selected and source_list and isinstance(source_list[0], dict):
        selected = source_list[0]

    source_audio = ""
    if selected:
        for key in ("filename", "path", "file"):
            value = to_text(selected.get(key))
            if value:
                source_audio = value
                break

    duration = to_non_negative_float(selected.get("duration_sec")) if selected else None
    if duration is None:
        duration = to_non_negative_float(entry.get("duration_sec"))

    return source_audio, duration


def interval(start: float, end: float, text: str) -> Dict[str, Any]:
    return {
        "start": float(start),
        "end": float(end),
        "text": text,
    }


def build_annotations(
    concepts: List[Dict[str, Any]],
    speakers: List[str],
    speaker_forms: Dict[str, Dict[str, Dict[str, Any]]],
    source_index: Dict[str, Any],
    input_name: str,
) -> Dict[str, Dict[str, Any]]:
    annotations: Dict[str, Dict[str, Any]] = {}
    concept_count = len(concepts)
    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for speaker in speakers:
        source_audio, source_duration = best_source_for_speaker(source_index, speaker)
        per_concept_form = speaker_forms.get(speaker, {})

        ipa_intervals: List[Dict[str, Any]] = []
        ortho_intervals: List[Dict[str, Any]] = []
        concept_intervals: List[Dict[str, Any]] = []
        speaker_intervals: List[Dict[str, Any]] = []

        for idx, concept in enumerate(concepts):
            start = float(idx)
            end = float(idx + 1)

            concept_id = to_text(concept.get("id"))
            concept_label = to_text(concept.get("label"))
            concept_text = f"{concept_id}: {concept_label}" if concept_label else concept_id

            form = per_concept_form.get(concept_id, {})
            if not isinstance(form, dict):
                form = {}

            ipa_text = to_text(form.get("ipa"))
            ortho_text = to_text(form.get("ortho"))

            ipa_intervals.append(interval(start, end, ipa_text))
            ortho_intervals.append(interval(start, end, ortho_text))
            concept_intervals.append(interval(start, end, concept_text))
            speaker_intervals.append(interval(start, end, speaker))

        synthetic_duration = float(concept_count)
        resolved_duration = synthetic_duration
        if source_duration is not None:
            resolved_duration = max(source_duration, synthetic_duration)

        annotations[speaker] = {
            "version": 1,
            "project_id": PROJECT_ID,
            "speaker": speaker,
            "source_audio": source_audio,
            "source_audio_duration_sec": resolved_duration,
            "tiers": {
                "ipa": {
                    "display_order": 1,
                    "intervals": ipa_intervals,
                },
                "ortho": {
                    "display_order": 2,
                    "intervals": ortho_intervals,
                },
                "concept": {
                    "display_order": 3,
                    "intervals": concept_intervals,
                },
                "speaker": {
                    "display_order": 4,
                    "intervals": speaker_intervals,
                },
            },
            "metadata": {
                "language_code": "sdh",
                "created": imported_at,
                "modified": imported_at,
                "bridge": {
                    "source": input_name,
                    "synthetic_timings": True,
                    "synthetic_step_sec": 1.0,
                    "concept_count": concept_count,
                },
            },
        }

    return annotations


def main() -> None:
    parser = argparse.ArgumentParser(description="Import review_data.json into compare-compatible PARSE data")
    parser.add_argument("input", type=pathlib.Path, help="Path to review_data.json")
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Output directory (default: same directory as input)",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    output_dir = (args.output_dir or input_path.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {input_path}...")
    data = load_review_data(input_path)

    concepts = extract_concepts(data)
    speakers = extract_speakers(concepts)
    speaker_forms = build_speaker_form_lookup(concepts)
    source_index = load_source_index(output_dir)

    print(f"Found {len(concepts)} concepts, {len(speakers)} speakers: {', '.join(speakers)}")

    # Write project.json
    project_path = output_dir / "project.json"
    project = build_project_json(speakers, len(concepts))
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2, ensure_ascii=False)
    print(f"Wrote {project_path}")

    # Write concepts.csv
    csv_path = output_dir / "concepts.csv"
    csv_rows = build_concepts_csv_rows(concepts)
    write_concepts_csv_rows(csv_path, csv_rows)
    print(f"Wrote {csv_path} ({len(csv_rows)} concepts)")

    # Write per-speaker annotation files
    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)

    annotations = build_annotations(
        concepts=concepts,
        speakers=speakers,
        speaker_forms=speaker_forms,
        source_index=source_index,
        input_name=input_path.name,
    )

    for speaker in speakers:
        annot = annotations[speaker]
        annot_path = annotations_dir / f"{speaker}.json"
        with open(annot_path, "w", encoding="utf-8") as f:
            json.dump(annot, f, indent=2, ensure_ascii=False)

        interval_count = len(annot["tiers"]["concept"]["intervals"])
        print(f"Wrote {annot_path} ({interval_count} concept intervals)")

    print(f"\nDone! Compare-compatible data generated in {output_dir}")


if __name__ == "__main__":
    main()
