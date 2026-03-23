#!/usr/bin/env python3
"""
elan_export.py — Export PARSE annotations to ELAN XML (.eaf).

Usage:
    python elan_export.py --input annotations/Fail01.parse.json --output exports/Fail01.eaf
    python elan_export.py --input-dir annotations/ --output-dir exports/
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
ELAN_SCHEMA_LOCATION = "http://www.mpi.nl/tools/elan/EAFv3.0.xsd"

STANDARD_TIER_MAP = {
    "ipa": "IPA",
    "ortho": "Ortho",
    "concept": "Concept",
    "speaker": "Speaker",
}

STANDARD_TIER_ORDER = ["ipa", "ortho", "concept", "speaker"]


def _time_sec_to_ms(time_sec: object, label: str) -> int:
    """Convert seconds to milliseconds using round()."""
    if isinstance(time_sec, bool):
        raise ValueError(f"{label} must be numeric, got boolean")

    try:
        value = float(time_sec)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc

    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be a finite number")

    return int(round(value * 1000.0))


def _normalize_interval_text(value: object) -> str:
    """Normalize interval text for XML output."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _tier_id_for_elan(tier_name: str) -> str:
    """Map PARSE tier names to ELAN tier IDs."""
    mapped = STANDARD_TIER_MAP.get(tier_name.lower())
    if mapped is not None:
        return mapped
    return tier_name


def _ordered_tier_names(tiers: dict) -> list:
    """Return tier names in standard order, then custom tiers."""
    ordered = []
    used = set()

    lower_name_to_original = {}
    for tier_name in tiers.keys():
        if isinstance(tier_name, str):
            key = tier_name.lower()
            if key not in lower_name_to_original:
                lower_name_to_original[key] = tier_name

    for standard_name in STANDARD_TIER_ORDER:
        original_name = lower_name_to_original.get(standard_name)
        if original_name is not None:
            ordered.append(original_name)
            used.add(original_name)

    for tier_name in tiers.keys():
        if tier_name not in used:
            ordered.append(tier_name)

    return ordered


def _collect_tier_entries(annotation_data: dict) -> tuple:
    """Collect exportable annotations and deduplicated time boundaries."""
    tiers = annotation_data.get("tiers")
    if not isinstance(tiers, dict):
        raise ValueError("annotation_data must contain a 'tiers' object")

    tier_entries = []
    time_values_ms = set()

    for tier_name in _ordered_tier_names(tiers):
        if not isinstance(tier_name, str):
            raise ValueError("tier names must be strings")

        tier_data = tiers.get(tier_name)
        if not isinstance(tier_data, dict):
            raise ValueError(f"tier '{tier_name}' must be an object")

        intervals = tier_data.get("intervals", [])
        if intervals is None:
            intervals = []
        if not isinstance(intervals, list):
            raise ValueError(f"tier '{tier_name}' field 'intervals' must be a list")

        tier_annotations = []
        for idx, interval in enumerate(intervals):
            if not isinstance(interval, dict):
                raise ValueError(f"tier '{tier_name}' interval[{idx}] must be an object")

            text = _normalize_interval_text(interval.get("text", ""))
            if text == "":
                continue

            start_ms = _time_sec_to_ms(interval.get("start"), f"tier '{tier_name}' interval[{idx}] start")
            end_ms = _time_sec_to_ms(interval.get("end"), f"tier '{tier_name}' interval[{idx}] end")
            if end_ms < start_ms:
                raise ValueError(
                    f"tier '{tier_name}' interval[{idx}] has end < start ({end_ms} < {start_ms})"
                )

            tier_annotations.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                }
            )

            time_values_ms.add(start_ms)
            time_values_ms.add(end_ms)

        tier_entries.append(
            {
                "tier_name": tier_name,
                "tier_id": _tier_id_for_elan(tier_name),
                "annotations": tier_annotations,
            }
        )

    return tier_entries, sorted(time_values_ms)


def _guess_mime_type(media_url: str) -> str:
    """Guess MIME type from the media URL extension."""
    lowered = media_url.lower()
    if lowered.endswith(".mp3"):
        return "audio/mpeg"
    if lowered.endswith(".wav"):
        return "audio/x-wav"
    return "audio/x-wav"


def _escape_xml_text(value: str) -> str:
    """Escape XML text content, including quotes."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _escape_xml_attr(value: str) -> str:
    """Escape XML attribute values."""
    return _escape_xml_text(value).replace("'", "&apos;")


def _serialize_xml_element(element: ET.Element, level: int = 0) -> str:
    """Serialize an ElementTree node to pretty XML with stable indentation."""
    indent = "    " * level

    attributes = "".join(
        f' {key}="{_escape_xml_attr(str(value))}"' for key, value in element.attrib.items()
    )
    opening = f"{indent}<{element.tag}{attributes}"

    children = list(element)
    text_value = element.text if element.text is not None else ""

    if not children and text_value == "":
        return f"{opening} />"

    if not children:
        return f"{opening}>{_escape_xml_text(text_value)}</{element.tag}>"

    lines = [f"{opening}>"]
    if text_value != "":
        lines.append(f"{'    ' * (level + 1)}{_escape_xml_text(text_value)}")

    for child in children:
        lines.append(_serialize_xml_element(child, level + 1))

    lines.append(f"{indent}</{element.tag}>")
    return "\n".join(lines)


def annotations_to_elan_str(annotation_data: dict, speaker: str) -> str:
    """
    Serialize to ELAN XML string without writing to disk.
    Used by annotation-store.js export via server endpoint.
    """
    if not isinstance(annotation_data, dict):
        raise ValueError("annotation_data must be an object")

    _ = speaker

    tier_entries, time_values_ms = _collect_tier_entries(annotation_data)
    time_slot_lookup = {}
    for idx, time_value in enumerate(time_values_ms, start=1):
        time_slot_lookup[time_value] = f"ts{idx}"

    document = ET.Element(
        "ANNOTATION_DOCUMENT",
        {
            "AUTHOR": "",
            "DATE": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "FORMAT": "3.0",
            "VERSION": "3.0",
            "xmlns:xsi": XSI_NAMESPACE,
            "xsi:noNamespaceSchemaLocation": ELAN_SCHEMA_LOCATION,
        },
    )

    header = ET.SubElement(
        document,
        "HEADER",
        {
            "MEDIA_FILE": "",
            "TIME_UNITS": "milliseconds",
        },
    )

    media_url = annotation_data.get("source_audio", "")
    if media_url is None:
        media_url = ""
    elif not isinstance(media_url, str):
        media_url = str(media_url)

    ET.SubElement(
        header,
        "MEDIA_DESCRIPTOR",
        {
            "MEDIA_URL": media_url,
            "MIME_TYPE": _guess_mime_type(media_url),
            "RELATIVE_MEDIA_URL": "",
        },
    )

    last_id_property = ET.SubElement(header, "PROPERTY", {"NAME": "lastUsedAnnotationId"})
    last_id_property.text = "0"

    time_order = ET.SubElement(document, "TIME_ORDER")
    for time_value in time_values_ms:
        ET.SubElement(
            time_order,
            "TIME_SLOT",
            {
                "TIME_SLOT_ID": time_slot_lookup[time_value],
                "TIME_VALUE": str(time_value),
            },
        )

    annotation_id_counter = 1
    for tier_entry in tier_entries:
        tier_element = ET.SubElement(
            document,
            "TIER",
            {
                "LINGUISTIC_TYPE_REF": "default-lt",
                "TIER_ID": tier_entry["tier_id"],
            },
        )

        for annotation in tier_entry["annotations"]:
            annotation_wrapper = ET.SubElement(tier_element, "ANNOTATION")
            alignable_annotation = ET.SubElement(
                annotation_wrapper,
                "ALIGNABLE_ANNOTATION",
                {
                    "ANNOTATION_ID": f"a{annotation_id_counter}",
                    "TIME_SLOT_REF1": time_slot_lookup[annotation["start_ms"]],
                    "TIME_SLOT_REF2": time_slot_lookup[annotation["end_ms"]],
                },
            )
            value_element = ET.SubElement(alignable_annotation, "ANNOTATION_VALUE")
            value_element.text = annotation["text"]

            annotation_id_counter += 1

    ET.SubElement(
        document,
        "LINGUISTIC_TYPE",
        {
            "GRAPHIC_REFERENCES": "false",
            "LINGUISTIC_TYPE_ID": "default-lt",
            "TIME_ALIGNABLE": "true",
        },
    )

    last_id_property.text = str(annotation_id_counter - 1)

    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + _serialize_xml_element(document) + "\n"


def export_elan(annotation_data: dict, output_path: Path, speaker: str) -> None:
    """
    Export annotation data to ELAN XML .eaf file.
    annotation_data: full annotation file dict with "tiers" key.
    """
    xml_text = annotations_to_elan_str(annotation_data, speaker)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_text, encoding="utf-8")


def _load_annotation_file(input_path: Path) -> dict:
    """Load and parse a single annotation JSON file."""
    try:
        text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read '{input_path}': {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in '{input_path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"annotation file '{input_path}' must contain a JSON object")

    return data


def _infer_speaker(annotation_data: dict, input_path: Path) -> str:
    """Infer speaker from annotation JSON, with filename fallback."""
    speaker_value = annotation_data.get("speaker")
    if isinstance(speaker_value, str) and speaker_value.strip():
        return speaker_value.strip()

    filename = input_path.name
    if filename.endswith(".parse.json"):
        candidate = filename[: -len(".parse.json")]
    else:
        candidate = input_path.stem

    candidate = candidate.strip()
    if not candidate:
        raise ValueError(f"could not infer speaker from '{input_path}'")

    return candidate


def _export_single(input_path: Path, output_path: Path) -> None:
    """Export one annotation file to one EAF file."""
    if not input_path.exists() or not input_path.is_file():
        raise ValueError(f"input file does not exist: {input_path}")

    annotation_data = _load_annotation_file(input_path)
    speaker = _infer_speaker(annotation_data, input_path)

    export_elan(annotation_data, output_path, speaker)
    print(f"Exported: {output_path}")


def _export_batch(input_dir: Path, output_dir: Path) -> None:
    """Export all *.parse.json files in a directory to .eaf files."""
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"input directory does not exist: {input_dir}")

    input_files = sorted(input_dir.glob("*.parse.json"))
    if not input_files:
        raise ValueError(f"no '*.parse.json' files found in: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for input_path in input_files:
        annotation_data = _load_annotation_file(input_path)
        speaker = _infer_speaker(annotation_data, input_path)
        output_path = output_dir / f"{speaker}.eaf"

        export_elan(annotation_data, output_path, speaker)
        print(f"Exported: {output_path}")


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Export PARSE annotation JSON files to ELAN XML (.eaf)."
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=Path,
        help="Path to a single annotation JSON file (e.g., annotations/Fail01.parse.json).",
    )
    input_group.add_argument(
        "--input-dir",
        type=Path,
        help="Path to a directory containing annotation JSON files (*.parse.json).",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output .eaf path (required with --input).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for .eaf files (required with --input-dir).",
    )

    return parser


def main(argv: list) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.input is not None:
            if args.output is None:
                parser.error("--output is required when using --input")
            if args.output_dir is not None:
                parser.error("--output-dir cannot be used with --input")

            _export_single(args.input, args.output)
            return 0

        if args.output_dir is None:
            parser.error("--output-dir is required when using --input-dir")
        if args.output is not None:
            parser.error("--output cannot be used with --input-dir")

        _export_batch(args.input_dir, args.output_dir)
        return 0

    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
