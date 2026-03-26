"""Convert review_data.json (old review tool) to PARSE v5.0 annotation format.

Usage:
    python3 python/import_review_data.py review_data.json --output-dir .

Generates:
    project.json          — v5.0 project config
    concepts.csv          — concept list
    annotations/<Speaker>.json  — per-speaker annotation files
"""

import argparse
import csv
import json
import pathlib
import sys
from typing import Any, Dict, List


def load_review_data(path: pathlib.Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_speakers(data: Dict[str, Any]) -> List[str]:
    speakers_set: Dict[str, bool] = {}
    for concept in data.get("concepts", []):
        for form in concept.get("forms", []):
            speaker = form.get("speaker", "")
            if speaker and speaker not in speakers_set:
                speakers_set[speaker] = True
    return list(speakers_set.keys())


def build_project_json(speakers: List[str]) -> Dict[str, Any]:
    return {
        "name": "Southern Kurdish Dialect Comparison",
        "sourceIndex": "source_index.json",
        "annotationsDir": "annotations",
        "conceptList": "concepts.csv",
        "speakers": speakers,
    }


def build_concepts_csv(data: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = []
    seen = set()
    for concept in data.get("concepts", []):
        cid = str(concept.get("concept_id", ""))
        label = concept.get("concept_en", "")
        if cid and cid not in seen:
            rows.append({"id": cid, "concept_en": label})
            seen.add(cid)
    return rows


def build_annotations(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build per-speaker annotation dicts from review_data concepts."""
    annotations: Dict[str, Dict[str, Any]] = {}

    for concept in data.get("concepts", []):
        concept_id = str(concept.get("concept_id", ""))
        concept_en = concept.get("concept_en", "")

        # Reference forms
        arabic = concept.get("arabic", {})
        persian = concept.get("persian", {})

        for form in concept.get("forms", []):
            speaker = form.get("speaker", "")
            if not speaker:
                continue

            if speaker not in annotations:
                annotations[speaker] = {
                    "speaker": speaker,
                    "version": 1,
                    "segments": [],
                    "referenceData": {},
                }

            segment = {
                "id": concept_id,
                "conceptId": concept_id,
                "conceptLabel": concept_en,
                "startSec": None,
                "endSec": None,
                "ipa": form.get("ipa", "?"),
                "ortho": form.get("ortho", ""),
                "cognateClass": form.get("cognate_class", "?"),
                "arabicSimilarity": form.get("arabic_similarity", 0.0),
                "persianSimilarity": form.get("persian_similarity", 0.0),
                "borrowingFlag": form.get("borrowing_flag"),
                "source": form.get("source"),
                "verification": form.get("verification"),
            }

            # Include variants if present
            variants = form.get("variants")
            if variants:
                segment["variants"] = variants

            annotations[speaker]["segments"].append(segment)

            # Store reference forms per concept (once)
            if concept_id not in annotations[speaker].get("referenceData", {}):
                annotations[speaker].setdefault("referenceData", {})[concept_id] = {
                    "arabic": {
                        "form": arabic.get("form", ""),
                        "ipa": arabic.get("ipa", ""),
                    },
                    "persian": {
                        "form": persian.get("form", ""),
                        "ipa": persian.get("ipa", ""),
                    },
                }

    return annotations


def main() -> None:
    parser = argparse.ArgumentParser(description="Import review_data.json to PARSE v5.0 format")
    parser.add_argument("input", type=pathlib.Path, help="Path to review_data.json")
    parser.add_argument("--output-dir", type=pathlib.Path, default=None,
                        help="Output directory (default: same as input file)")
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.exists():
        print("Error: {} not found".format(input_path), file=sys.stderr)
        sys.exit(1)

    output_dir = (args.output_dir or input_path.parent).resolve()

    print("Loading {}...".format(input_path))
    data = load_review_data(input_path)

    concepts = data.get("concepts", [])
    speakers = extract_speakers(data)
    print("Found {} concepts, {} speakers: {}".format(len(concepts), len(speakers), ", ".join(speakers)))

    # Write project.json
    project_path = output_dir / "project.json"
    project = build_project_json(speakers)
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2, ensure_ascii=False)
    print("Wrote {}".format(project_path))

    # Write concepts.csv
    csv_path = output_dir / "concepts.csv"
    csv_rows = build_concepts_csv(data)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerows(csv_rows)
    print("Wrote {} ({} concepts)".format(csv_path, len(csv_rows)))

    # Write per-speaker annotation files
    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(exist_ok=True)
    annotations = build_annotations(data)

    for speaker, annot in annotations.items():
        annot_path = annotations_dir / "{}.json".format(speaker)
        with open(annot_path, "w", encoding="utf-8") as f:
            json.dump(annot, f, indent=2, ensure_ascii=False)
        print("Wrote {} ({} segments)".format(annot_path, len(annot["segments"])))

    print("\nDone! PARSE v5.0 data files generated in {}".format(output_dir))
    print("Start the server and open compare.html to use.")


if __name__ == "__main__":
    main()
