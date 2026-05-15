#!/usr/bin/env python3
"""export_review_data.py — Export a PARSE workspace to the legacy review_tool format.

Inverse of ``python/import_review_data.py``. Reads a PARSE workspace, filters
concepts by a tag (default: ``custom-sk-concept-list`` — the thesis tag), and
emits a ``review_data.json`` plus pre-clipped per-form WAVs in the layout the
archived ``ArdeleanLucas/review_tool_archived`` HTML expects:

    <out>/review_data.json
    <out>/audio/<Speaker>/<survey>_<source_item>_<variant>_<gloss>_<Speaker>.wav
    <out>/timestamps/<Speaker>_timestamps.csv

Analytical fields that the legacy schema carried (cognate_class, contact-
language similarity scores, phonetic_flags) are emitted with the same null
defaults the legacy importer wrote for unscored forms. The viewer renders
forms with these fields empty; populating them later is an additive change.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from concept_source_item import (
    parse_cue_name,
    read_concepts_csv_rows,
    row_value,
)

DEFAULT_TAG_ID = "custom-sk-concept-list"
DEFAULT_PROJECT_AUDIO_ROOT = "audio/working"
LEGACY_SCHEMA_VERSION = 4.1
EXCLUDED_ANNOTATION_NAMES = {"manifest.json", "parse-enrichments.json"}

_VARIANT_SUFFIX_RE = re.compile(r"\s*\(([A-Za-z0-9]+)\)\s*$")
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _stem_label(label: str) -> str:
    return _VARIANT_SUFFIX_RE.sub("", str(label or "").strip()).strip()


def _variant_letter(label: str) -> str:
    match = _VARIANT_SUFFIX_RE.search(str(label or "").strip())
    return match.group(1) if match else ""


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


def _empty_form(speaker: str) -> dict[str, Any]:
    """Form record for a speaker that did not produce the concept (matches legacy nulls)."""
    return {
        "speaker": speaker,
        "ipa": "?",
        "ortho": "",
        "cognate_class": "?",
        "arabic_similarity": 0.0,
        "persian_similarity": 0.0,
        "borrowing_flag": None,
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
) -> dict[str, Any]:
    ipa = _interval_field(interval, "ipa", "ipa_text")
    ortho = _interval_field(interval, "ortho", "orthography", "text")
    return {
        "speaker": speaker,
        "ipa": "" if ipa is None else str(ipa),
        "ortho": "" if ortho is None else str(ortho),
        "cognate_class": "?",
        "arabic_similarity": 0.0,
        "persian_similarity": 0.0,
        "borrowing_flag": None,
        "audio_path": audio_relpath,
        "spectrogram_path": None,
        "variants": None,
        "source": row_value(concept_row, "source_survey") or None,
        "verification": None,
        "start_sec": float(start_sec),
        "duration_sec": float(duration_sec),
    }


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
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Return ``(review_data_payload, clip_plan)``.

    ``clip_plan`` is a list of ``(source_wav_relpath, clip_spec)`` tuples. Each
    ``clip_spec`` carries the keys ``speaker``, ``audio_path``, ``start_sec``,
    ``duration_sec``, plus the timestamps-CSV row fields. The caller decides
    whether to materialize the clips via ffmpeg.
    """
    speakers = _project_speakers(workspace)
    concepts_csv = workspace / "concepts.csv"
    if not concepts_csv.exists():
        raise FileNotFoundError(f"concepts.csv not found at {concepts_csv}")
    concept_rows = read_concepts_csv_rows(concepts_csv)
    concept_by_id = {str(row.get("id") or "").strip(): row for row in concept_rows}

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
    ordered_concept_ids = [
        str(row.get("id") or "").strip()
        for row in concept_rows
        if str(row.get("id") or "").strip() in tagged_union
    ]
    # Fallback: if no tags found, exporter still emits an empty schema so the
    # caller sees a valid output rather than a crash. Stays explicit in logs.
    if not ordered_concept_ids and tagged_union:
        ordered_concept_ids = sorted(tagged_union)

    clip_plan: list[tuple[str, dict[str, Any]]] = []
    concept_entries: list[dict[str, Any]] = []
    for concept_id in ordered_concept_ids:
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
        for speaker in speakers:
            payload = annotation_payloads.get(speaker, {})
            tagged_for_speaker = thesis_ids_by_speaker.get(speaker, set())
            intervals = _concept_intervals_by_id(payload).get(concept_id, [])

            if concept_id not in tagged_for_speaker or not intervals:
                forms.append(_empty_form(speaker))
                continue

            interval = intervals[0]
            start_sec = float(_interval_field(interval, "start", "start_sec") or 0.0)
            end_sec = float(_interval_field(interval, "end", "end_sec") or 0.0)
            duration_sec = max(0.0, end_sec - start_sec)

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
            )
            forms.append(form)

            clip_plan.append(
                (
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
            )

        concept_entries.append(
            {
                "concept_id": source_item or concept_id,
                "concept_en": gloss,
                "arabic": {"form": "", "ipa": ""},
                "persian": {"form": "", "ipa": ""},
                "forms": forms,
            }
        )

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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = args.workspace.resolve()
    out_dir = args.out.resolve()

    if not workspace.exists():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 2

    review_data, clip_plan = build_review_data(workspace=workspace, tag_id=args.tag_id)
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
