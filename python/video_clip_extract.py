#!/usr/bin/env python3
"""
video_clip_extract.py - Extract video clips for annotated IPA segments.

This script reads PARSE annotation files (annotations/<Speaker>.parse.json), maps
WAV timestamps to drift-corrected video timestamps using sync metadata
(sync/<Speaker>_sync.json), and extracts MP4 clips with ffmpeg.

Examples:
    # Single speaker
    python video_clip_extract.py \
        --annotations annotations/Khan01.parse.json \
        --sync sync/Khan01_sync.json \
        --output exports/clips/

    # All speakers (auto-discover from annotations dir)
    python video_clip_extract.py \
        --annotations-dir annotations/ \
        --sync-dir sync/ \
        --output exports/clips/

    # Dry run (print ffmpeg commands only)
    python video_clip_extract.py \
        --annotations annotations/Khan01.parse.json \
        --sync sync/Khan01_sync.json \
        --output exports/clips/ \
        --dry-run
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path


_FORCE_OVERWRITE = False
_VIDEO_DURATION_CACHE = {}


def _eprint(message: str) -> None:
    """Print a message to stderr."""
    print(message, file=sys.stderr)


def _safe_float(value: object, default: float = 0.0) -> float:
    """Convert value to finite float; return default on failure."""
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(converted):
        return default
    return converted


def _safe_filename_token(value: str) -> str:
    """Replace unsafe filename characters with underscores."""
    if not value:
        return ""
    chars = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars).strip("_")


def _format_seconds_for_filename(value: float) -> str:
    """Format seconds into a compact, filesystem-safe string."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    if not text:
        return "0"
    return text.replace("-", "neg")


def _format_seconds_for_ffmpeg(value: float) -> str:
    """Format seconds for ffmpeg command arguments."""
    return f"{value:.6f}"


def _format_command(command: list) -> str:
    """Format subprocess arg list as display-friendly shell string."""
    parts = []
    for arg in command:
        if any(char in arg for char in (' ', '"', "'", "\\", "$", "`")):
            escaped = arg.replace('"', '\\"')
            parts.append(f'"{escaped}"')
        else:
            parts.append(arg)
    return " ".join(parts)


def _load_json(path: Path) -> dict:
    """Load JSON file and return dict; on failure prints error and returns {}."""
    if not path.exists():
        _eprint(f"ERROR: File not found: {path}")
        return {}
    if not path.is_file():
        _eprint(f"ERROR: Not a file: {path}")
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except json.JSONDecodeError as exc:
        _eprint(f"ERROR: Invalid JSON in {path}: {exc}")
        return {}
    except OSError as exc:
        _eprint(f"ERROR: Could not read {path}: {exc}")
        return {}

    if not isinstance(loaded, dict):
        _eprint(f"ERROR: Expected JSON object in {path}")
        return {}
    return loaded


def _speaker_from_annotation_path(annotation_path: Path) -> str:
    """Infer speaker id from annotation filename."""
    name = annotation_path.name
    suffix = ".parse.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return annotation_path.stem


def _normalize_concept_id(text: str) -> str:
    """Normalize concept tier text into a concept id token."""
    cleaned = str(text).strip()
    if not cleaned:
        return "unknown"

    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0].strip()
    elif " " in cleaned:
        cleaned = cleaned.split(None, 1)[0].strip()

    token = _safe_filename_token(cleaned)
    if token:
        return token
    return "unknown"


def _extract_tier_intervals(annotation_data: dict, tier_name: str) -> list:
    """Return interval list for a tier, or empty list if missing/invalid."""
    tiers = annotation_data.get("tiers", {})
    if not isinstance(tiers, dict):
        return []
    tier = tiers.get(tier_name, {})
    if not isinstance(tier, dict):
        return []
    intervals = tier.get("intervals", [])
    if not isinstance(intervals, list):
        return []
    return intervals


def _extract_target_segments(annotation_data: dict) -> list:
    """Extract non-empty IPA intervals as candidate clip segments."""
    segments = []
    ipa_intervals = _extract_tier_intervals(annotation_data, "ipa")
    for index, interval in enumerate(ipa_intervals):
        if not isinstance(interval, dict):
            _eprint(f"WARNING: ipa interval #{index} is not an object; skipping")
            continue

        text = str(interval.get("text", "")).strip()
        if not text:
            continue

        start_sec = _safe_float(interval.get("start"), default=float("nan"))
        end_sec = _safe_float(interval.get("end"), default=float("nan"))

        if not math.isfinite(start_sec) or not math.isfinite(end_sec):
            _eprint(
                f"WARNING: ipa interval #{index} has non-numeric start/end; skipping"
            )
            continue

        if end_sec <= start_sec:
            _eprint(
                f"WARNING: ipa interval #{index} has end <= start "
                f"({end_sec:.3f} <= {start_sec:.3f}); skipping"
            )
            continue

        segments.append(
            {
                "start": start_sec,
                "end": end_sec,
                "text": text,
            }
        )
    return segments


def _pick_concept_id(start_sec: float, end_sec: float, concept_intervals: list) -> str:
    """Find best matching concept interval for a segment."""
    midpoint = (start_sec + end_sec) / 2.0
    best_text = ""
    best_overlap = 0.0

    for interval in concept_intervals:
        if not isinstance(interval, dict):
            continue

        text = str(interval.get("text", "")).strip()
        if not text:
            continue

        concept_start = _safe_float(interval.get("start"), default=float("nan"))
        concept_end = _safe_float(interval.get("end"), default=float("nan"))
        if not math.isfinite(concept_start) or not math.isfinite(concept_end):
            continue
        if concept_end <= concept_start:
            continue

        if concept_start <= midpoint <= concept_end:
            return _normalize_concept_id(text)

        overlap = min(end_sec, concept_end) - max(start_sec, concept_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = text

    if best_text:
        return _normalize_concept_id(best_text)
    return "unknown"


def _resolve_video_path(
    sync_path: Path,
    annotation_path: Path,
    video_file: str,
) -> Path:
    """Resolve video path with sensible relative-path fallbacks."""
    direct = Path(video_file)
    if direct.is_absolute():
        return direct

    candidates = [
        sync_path.parent / direct,
        sync_path.parent.parent / direct,
        annotation_path.parent.parent / direct,
        Path(video_file),
    ]

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate

    return candidates[0]


def _infer_ffprobe_path(ffmpeg_path: str) -> str:
    """Infer ffprobe executable from ffmpeg path."""
    ffmpeg_name = Path(ffmpeg_path).name
    lower_name = ffmpeg_name.lower()

    if ffmpeg_path == "ffmpeg":
        return "ffprobe"
    if ffmpeg_path == "ffmpeg.exe":
        return "ffprobe.exe"

    if lower_name.startswith("ffmpeg"):
        suffix = ffmpeg_name[6:]
        return str(Path(ffmpeg_path).with_name("ffprobe" + suffix))

    return "ffprobe"


def _probe_video_duration(video_path: Path, ffmpeg_path: str) -> float:
    """Read video duration with ffprobe; returns <=0 when unknown."""
    cache_key = str(video_path.resolve(strict=False))
    if cache_key in _VIDEO_DURATION_CACHE:
        return _VIDEO_DURATION_CACHE[cache_key]

    ffprobe_path = _infer_ffprobe_path(ffmpeg_path)
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        _eprint(
            "WARNING: ffprobe not found; clip bounds cannot be clamped to video duration"
        )
        _VIDEO_DURATION_CACHE[cache_key] = -1.0
        return -1.0
    except OSError as exc:
        _eprint(f"WARNING: failed to run ffprobe: {exc}")
        _VIDEO_DURATION_CACHE[cache_key] = -1.0
        return -1.0

    if result.returncode != 0:
        stderr_text = result.stderr.strip()
        if stderr_text:
            _eprint(f"WARNING: ffprobe failed for {video_path}: {stderr_text}")
        else:
            _eprint(f"WARNING: ffprobe failed for {video_path}")
        _VIDEO_DURATION_CACHE[cache_key] = -1.0
        return -1.0

    output = result.stdout.strip()
    if not output:
        _eprint(f"WARNING: ffprobe returned empty duration for {video_path}")
        _VIDEO_DURATION_CACHE[cache_key] = -1.0
        return -1.0

    duration_sec = _safe_float(output, default=-1.0)
    if duration_sec <= 0.0:
        _eprint(f"WARNING: ffprobe returned invalid duration for {video_path}: {output}")
        _VIDEO_DURATION_CACHE[cache_key] = -1.0
        return -1.0

    _VIDEO_DURATION_CACHE[cache_key] = duration_sec
    return duration_sec


def _compute_clip_window(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    ffmpeg_path: str,
    padding_sec: float,
) -> tuple:
    """Apply padding and clamp clip boundaries to video duration."""
    if end_sec <= start_sec:
        _eprint(
            f"WARNING: invalid clip bounds (end <= start): {end_sec:.6f} <= {start_sec:.6f}"
        )
        return ()

    if padding_sec < 0:
        _eprint("WARNING: negative padding provided; using 0.0 seconds")
        padding_sec = 0.0

    clip_start = start_sec - padding_sec
    clip_end = end_sec + padding_sec

    if clip_start < 0.0:
        _eprint(
            f"WARNING: clip start below 0 for {video_path}; clamping {clip_start:.3f} -> 0.000"
        )
        clip_start = 0.0

    video_duration = _probe_video_duration(video_path, ffmpeg_path)
    if video_duration > 0.0:
        if clip_start > video_duration:
            _eprint(
                "WARNING: clip start past video end for "
                f"{video_path}; clamping {clip_start:.3f} -> {video_duration:.3f}"
            )
            clip_start = video_duration
        if clip_end > video_duration:
            _eprint(
                "WARNING: clip end past video duration for "
                f"{video_path}; clamping {clip_end:.3f} -> {video_duration:.3f}"
            )
            clip_end = video_duration

    if clip_end <= clip_start:
        _eprint(
            "WARNING: clip window collapsed after clamping; "
            f"start={clip_start:.6f}, end={clip_end:.6f}"
        )
        return ()

    return (clip_start, clip_end)


def _build_ffmpeg_command(
    ffmpeg_path: str,
    video_path: Path,
    clip_start: float,
    clip_end: float,
    output_path: Path,
) -> list:
    """Build ffmpeg extraction command for one clip."""
    duration_sec = clip_end - clip_start
    return [
        ffmpeg_path,
        "-ss",
        _format_seconds_for_ffmpeg(clip_start),
        "-i",
        str(video_path),
        "-t",
        _format_seconds_for_ffmpeg(duration_sec),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-y",
        str(output_path),
    ]


def wav_to_video_time(wav_time: float, sync: dict) -> float:
    """Apply drift-corrected mapping from WAV timestamp to video timestamp."""
    if not math.isfinite(wav_time):
        raise ValueError(f"wav_time must be finite, got: {wav_time}")

    sync_values = sync
    nested_sync = sync.get("sync")
    if isinstance(nested_sync, dict):
        sync_values = nested_sync

    drift_rate = _safe_float(sync_values.get("drift_rate"), default=0.0)
    offset_sec = _safe_float(sync_values.get("offset_sec"), default=0.0)
    manual_adjustment_sec = _safe_float(
        sync_values.get("manual_adjustment_sec"),
        default=0.0,
    )

    return (wav_time * (1.0 + drift_rate / 60.0)) + offset_sec + manual_adjustment_sec


def extract_clip(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    output_path: Path,
    ffmpeg_path: str = "ffmpeg",
    padding_sec: float = 0.5,
) -> bool:
    """Extract one video clip. Returns True on success."""
    clip_window = _compute_clip_window(
        video_path=video_path,
        start_sec=start_sec,
        end_sec=end_sec,
        ffmpeg_path=ffmpeg_path,
        padding_sec=padding_sec,
    )
    if not clip_window:
        return False

    clip_start, clip_end = clip_window
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = _build_ffmpeg_command(
        ffmpeg_path=ffmpeg_path,
        video_path=video_path,
        clip_start=clip_start,
        clip_end=clip_end,
        output_path=output_path,
    )

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        _eprint(f"ERROR: ffmpeg not found: {ffmpeg_path}")
        return False
    except OSError as exc:
        _eprint(f"ERROR: failed to run ffmpeg for {output_path}: {exc}")
        return False

    if result.returncode != 0:
        _eprint(
            f"ERROR: ffmpeg failed ({result.returncode}) for {output_path}\n"
            f"{result.stderr.strip()}"
        )
        return False

    return True


def extract_speaker_clips(
    annotation_path: Path,
    sync_path: Path,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg",
    padding_sec: float = 0.5,
    dry_run: bool = False,
) -> dict:
    """
    Extract all annotated clips for a speaker.
    Returns {"extracted": int, "skipped": int, "errors": int}
    """
    results = {
        "extracted": 0,
        "skipped": 0,
        "errors": 0,
    }

    annotation_data = _load_json(annotation_path)
    if not annotation_data:
        results["errors"] += 1
        return results

    sync_data = _load_json(sync_path)
    if not sync_data:
        results["errors"] += 1
        return results

    sync_values = sync_data.get("sync", {})
    if not isinstance(sync_values, dict):
        _eprint(f"WARNING: Invalid sync object in {sync_path}; skipping speaker")
        return results

    sync_status = str(sync_values.get("status", "")).strip().lower()
    if sync_status != "synced":
        _eprint(
            f"WARNING: Sync status is '{sync_status or 'missing'}' in {sync_path}; "
            "skipping speaker"
        )
        return results

    video_file = sync_data.get("video_file")
    if not isinstance(video_file, str) or not video_file.strip():
        _eprint(f"WARNING: Missing 'video_file' in {sync_path}; skipping speaker")
        results["errors"] += 1
        return results
    video_path = _resolve_video_path(sync_path, annotation_path, video_file.strip())

    speaker = str(annotation_data.get("speaker", "")).strip()
    if not speaker:
        speaker = _speaker_from_annotation_path(annotation_path)

    speaker_output_dir = output_dir / speaker
    if not dry_run:
        speaker_output_dir.mkdir(parents=True, exist_ok=True)

    target_segments = _extract_target_segments(annotation_data)
    if not target_segments:
        _eprint(
            f"WARNING: No non-empty IPA intervals in {annotation_path}; skipping speaker"
        )
        return results

    concept_intervals = _extract_tier_intervals(annotation_data, "concept")

    fps = _safe_float(sync_data.get("fps"), default=0.0)
    if fps <= 0.0:
        _eprint(
            f"WARNING: Missing/invalid fps in {sync_path}; clip boundaries will not be frame-rounded"
        )

    for segment in target_segments:
        wav_start = _safe_float(segment.get("start"), default=float("nan"))
        wav_end = _safe_float(segment.get("end"), default=float("nan"))

        if not math.isfinite(wav_start) or not math.isfinite(wav_end):
            results["errors"] += 1
            _eprint(
                f"WARNING: Segment has invalid WAV bounds ({wav_start}, {wav_end}); skipping"
            )
            continue
        if wav_end <= wav_start:
            results["errors"] += 1
            _eprint(
                f"WARNING: Segment has end <= start ({wav_end:.3f} <= {wav_start:.3f}); skipping"
            )
            continue

        concept_id = _pick_concept_id(wav_start, wav_end, concept_intervals)
        clip_name = f"{concept_id}_{_format_seconds_for_filename(wav_start)}.mp4"
        output_path = speaker_output_dir / clip_name

        if output_path.exists() and not _FORCE_OVERWRITE:
            results["skipped"] += 1
            _eprint(f"WARNING: Output exists, skipping (use --force): {output_path}")
            continue

        mapped_start = wav_to_video_time(wav_start, sync_data)
        mapped_end = wav_to_video_time(wav_end, sync_data)

        if fps > 0.0:
            mapped_start = round(mapped_start * fps) / fps
            mapped_end = round(mapped_end * fps) / fps

        if mapped_end <= mapped_start:
            results["errors"] += 1
            _eprint(
                "WARNING: Mapped video interval collapsed "
                f"({mapped_start:.6f} -> {mapped_end:.6f}) for {output_path}; skipping"
            )
            continue

        if dry_run:
            clip_window = _compute_clip_window(
                video_path=video_path,
                start_sec=mapped_start,
                end_sec=mapped_end,
                ffmpeg_path=ffmpeg_path,
                padding_sec=padding_sec,
            )
            if not clip_window:
                results["errors"] += 1
                continue

            clip_start, clip_end = clip_window
            command = _build_ffmpeg_command(
                ffmpeg_path=ffmpeg_path,
                video_path=video_path,
                clip_start=clip_start,
                clip_end=clip_end,
                output_path=output_path,
            )
            print(_format_command(command))
            results["extracted"] += 1
            continue

        if extract_clip(
            video_path=video_path,
            start_sec=mapped_start,
            end_sec=mapped_end,
            output_path=output_path,
            ffmpeg_path=ffmpeg_path,
            padding_sec=padding_sec,
        ):
            results["extracted"] += 1
        else:
            results["errors"] += 1

    return results


def _find_sync_for_speaker(sync_dir: Path, speaker: str) -> Path:
    """Resolve sync json path for a speaker in sync directory."""
    candidates = [
        sync_dir / f"{speaker}_sync.json",
        sync_dir / f"{speaker}.sync.json",
        sync_dir / f"{speaker}.json",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    fuzzy = sorted(sync_dir.glob(f"{speaker}*sync*.json"))
    if fuzzy:
        if len(fuzzy) > 1:
            _eprint(
                f"WARNING: Multiple sync files matched speaker '{speaker}', "
                f"using first: {fuzzy[0]}"
            )
        return fuzzy[0]

    return candidates[0]


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract video clips for PARSE annotations using drift-corrected "
            "audio-to-video timestamp mapping."
        )
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--annotations",
        type=str,
        help="Single annotation file path (e.g., annotations/Khan01.parse.json)",
    )
    mode_group.add_argument(
        "--annotations-dir",
        type=str,
        help="Directory containing annotation files (*.parse.json)",
    )

    parser.add_argument(
        "--sync",
        type=str,
        help="Single speaker sync JSON file path",
    )
    parser.add_argument(
        "--sync-dir",
        type=str,
        help="Directory containing speaker sync JSON files",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=str,
        help="Output clips root directory (speaker subfolders are created)",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.5,
        help="Padding (seconds) added before/after each segment (default: 0.5)",
    )
    parser.add_argument(
        "--ffmpeg",
        type=str,
        default="ffmpeg",
        help="Path to ffmpeg executable (default: ffmpeg)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ffmpeg commands without executing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output clips (default: skip existing)",
    )

    return parser


def main() -> int:
    """CLI entry point."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.padding < 0.0:
        parser.error("--padding must be >= 0")

    if args.annotations and not args.sync:
        parser.error("--sync is required when using --annotations")
    if args.annotations_dir and not args.sync_dir:
        parser.error("--sync-dir is required when using --annotations-dir")
    if args.sync and not args.annotations:
        parser.error("--sync can only be used with --annotations")
    if args.sync_dir and not args.annotations_dir:
        parser.error("--sync-dir can only be used with --annotations-dir")

    global _FORCE_OVERWRITE
    _FORCE_OVERWRITE = bool(args.force)

    output_dir = Path(args.output)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_extracted = 0
    total_skipped = 0
    total_errors = 0
    skipped_speakers = 0

    if args.annotations:
        annotation_path = Path(args.annotations)
        sync_path = Path(args.sync)
        if not sync_path.exists() or not sync_path.is_file():
            _eprint(
                f"WARNING: Sync file missing for speaker annotation '{annotation_path.name}'; "
                "skipping speaker"
            )
            skipped_speakers += 1
        else:
            stats = extract_speaker_clips(
                annotation_path=annotation_path,
                sync_path=sync_path,
                output_dir=output_dir,
                ffmpeg_path=args.ffmpeg,
                padding_sec=args.padding,
                dry_run=args.dry_run,
            )
            total_extracted += stats["extracted"]
            total_skipped += stats["skipped"]
            total_errors += stats["errors"]
    else:
        annotations_dir = Path(args.annotations_dir)
        sync_dir = Path(args.sync_dir)

        if not annotations_dir.exists() or not annotations_dir.is_dir():
            _eprint(f"ERROR: annotations directory not found: {annotations_dir}")
            return 1
        if not sync_dir.exists() or not sync_dir.is_dir():
            _eprint(f"ERROR: sync directory not found: {sync_dir}")
            return 1

        annotation_files = sorted(annotations_dir.glob("*.parse.json"))
        if not annotation_files:
            _eprint(f"WARNING: No annotation files found in {annotations_dir}")
            return 0

        for annotation_path in annotation_files:
            speaker = _speaker_from_annotation_path(annotation_path)
            sync_path = _find_sync_for_speaker(sync_dir, speaker)
            if not sync_path.exists() or not sync_path.is_file():
                skipped_speakers += 1
                _eprint(
                    f"WARNING: Sync file missing for speaker '{speaker}'; skipping speaker"
                )
                continue

            stats = extract_speaker_clips(
                annotation_path=annotation_path,
                sync_path=sync_path,
                output_dir=output_dir,
                ffmpeg_path=args.ffmpeg,
                padding_sec=args.padding,
                dry_run=args.dry_run,
            )
            total_extracted += stats["extracted"]
            total_skipped += stats["skipped"]
            total_errors += stats["errors"]

    mode_label = "DRY-RUN" if args.dry_run else "DONE"
    print(
        f"{mode_label}: extracted={total_extracted} "
        f"skipped={total_skipped} errors={total_errors} "
        f"skipped_speakers={skipped_speakers}"
    )

    if total_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
