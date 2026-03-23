#!/usr/bin/env python3
"""
batch_reextract.py — Batch re-extraction of WAV segments from source recordings.

Reads a decisions JSON file (exported by the Source Explorer UI) and generates
ffmpeg commands to cut each assigned source region into a standalone WAV clip.

Usage:
    # Dry-run (default): print all planned ffmpeg commands
    python batch_reextract.py --decisions decisions.json --output-dir clips/

    # Execute mode: actually run the extractions
    python batch_reextract.py --decisions decisions.json --output-dir clips/ --execute

    # Use a specific ffmpeg binary
    python batch_reextract.py --decisions decisions.json --output-dir clips/ \
        --execute --ffmpeg-bin "C:/ffmpeg/bin/ffmpeg.exe"

Decisions JSON format (Record<conceptId, { source_regions: Record<speaker, SourceRegion> }>):
    {
      "1": {
        "source_regions": {
          "Fail02": {
            "source_wav": "Audio_Original/Fail02/SK_Faili_F_1968.wav",
            "start_sec": 337.2,
            "end_sec": 338.1,
            "assigned": true,
            "replaces_segment": true,
            "ai_suggestion_used": 1,
            "ai_suggestion_confidence": "high",
            "ai_suggestion_score": 0.92
          }
        }
      }
    }

Output filename pattern:
    {speaker}_{concept_id}_{start_sec:.1f}-{end_sec:.1f}.wav
    e.g. Fail02_1_337.2-338.1.wav
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Batch re-extract WAV segments from source recordings using ffmpeg.\n\n"
            "By default runs in DRY-RUN mode — prints all planned ffmpeg commands "
            "without executing them. Add --execute to actually run the extractions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--decisions",
        required=True,
        metavar="FILE",
        help=(
            "Path to the decisions JSON file exported by the Source Explorer UI. "
            "Expected format: Record<conceptId, { source_regions: Record<speaker, SourceRegion> }>."
        ),
    )
    p.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help="Directory where extracted WAV clips will be written. Created if it does not exist.",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help=(
            "Actually run the ffmpeg commands. Without this flag the script runs in "
            "dry-run mode: commands are printed but not executed."
        ),
    )
    p.add_argument(
        "--ffmpeg-bin",
        metavar="PATH",
        default="ffmpeg",
        help=(
            "Path (or name) of the ffmpeg binary. Defaults to 'ffmpeg' (must be on PATH). "
            "Example: --ffmpeg-bin C:/ffmpeg/bin/ffmpeg.exe"
        ),
    )
    p.add_argument(
        "--source-root",
        metavar="DIR",
        default=None,
        help=(
            "Optional root directory to prepend to relative source_wav paths found in "
            "the decisions file. Useful when the decisions were exported on one machine "
            "but you are extracting on another. "
            "Example: --source-root C:/Users/Lucas/Thesis"
        ),
    )
    p.add_argument(
        "--only-assigned",
        action="store_true",
        default=True,
        help=(
            "Skip source regions where assigned=false. Enabled by default — use "
            "--no-only-assigned to include unassigned regions as well."
        ),
    )
    p.add_argument(
        "--no-only-assigned",
        action="store_false",
        dest="only_assigned",
        help="Include source regions even if assigned=false.",
    )
    return p


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_decisions(path: str) -> dict:
    """Load and lightly validate the decisions JSON."""
    fpath = Path(path)
    if not fpath.exists():
        sys.exit(f"ERROR: decisions file not found: {path}")
    if not fpath.is_file():
        sys.exit(f"ERROR: decisions path is not a file: {path}")

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: failed to parse decisions JSON: {e}")
    except UnicodeDecodeError as e:
        sys.exit(f"ERROR: decisions file is not valid UTF-8 text: {e}")
    except OSError as e:
        sys.exit(f"ERROR: could not read decisions file: {e}")

    if not isinstance(data, dict):
        sys.exit(
            f"ERROR: decisions JSON must be a top-level object (got {type(data).__name__}). "
            "Expected format: Record<conceptId, { source_regions: ... }>"
        )
    return data


# ---------------------------------------------------------------------------
# Extraction plan building
# ---------------------------------------------------------------------------

class ExtractionJob:
    """One ffmpeg extraction job."""

    __slots__ = (
        "concept_id",
        "speaker",
        "source_wav",
        "start_sec",
        "end_sec",
        "output_filename",
        "output_path",
        "region",
    )

    def __init__(
        self,
        concept_id: str,
        speaker: str,
        source_wav: str,
        start_sec: float,
        end_sec: float,
        output_dir: Path,
        region: dict,
    ):
        self.concept_id = concept_id
        self.speaker = speaker
        self.source_wav = source_wav
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.region = region

        # Sanitise speaker/concept_id for use in filenames
        safe_speaker = _safe_filename(speaker)
        safe_concept = _safe_filename(concept_id)
        self.output_filename = (
            f"{safe_speaker}_{safe_concept}_{start_sec:.1f}-{end_sec:.1f}.wav"
        )
        self.output_path = output_dir / self.output_filename

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def _safe_filename(s: str) -> str:
    """Replace characters unsafe in filenames with underscores."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s)


def _coerce_time_seconds(value, *, field_name: str, concept_id: str, speaker: str) -> float:
    """Coerce a timestamp-like value to a finite, non-negative float."""
    try:
        time_sec = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"concept '{concept_id}' speaker '{speaker}': {field_name} is not numeric"
        )

    if not math.isfinite(time_sec):
        raise ValueError(
            f"concept '{concept_id}' speaker '{speaker}': {field_name} is not finite"
        )
    if time_sec < 0:
        raise ValueError(
            f"concept '{concept_id}' speaker '{speaker}': {field_name} is negative"
        )
    return time_sec


def build_jobs(
    decisions: dict,
    output_dir: Path,
    source_root: str | None,
    only_assigned: bool,
) -> list[ExtractionJob]:
    """Parse decisions dict into a flat list of ExtractionJob objects."""
    jobs: list[ExtractionJob] = []
    skipped_unassigned = 0
    skipped_missing_fields = 0

    for concept_id, concept_entry in decisions.items():
        if not isinstance(concept_entry, dict):
            print(
                f"  WARNING: concept '{concept_id}' entry is not an object — skipping.",
                file=sys.stderr,
            )
            continue

        source_regions = concept_entry.get("source_regions")
        if source_regions is None:
            # Concept has no source regions — fine, just nothing to do.
            continue
        if not isinstance(source_regions, dict):
            print(
                f"  WARNING: concept '{concept_id}'.source_regions is not an object — skipping.",
                file=sys.stderr,
            )
            continue

        for speaker, region in source_regions.items():
            speaker_str = str(speaker)
            concept_id_str = str(concept_id)

            if not isinstance(region, dict):
                print(
                    f"  WARNING: concept '{concept_id_str}' speaker '{speaker_str}' region is not "
                    f"an object — skipping.",
                    file=sys.stderr,
                )
                skipped_missing_fields += 1
                continue

            # Check assigned flag
            assigned = region.get("assigned", False)
            if only_assigned and not assigned:
                skipped_unassigned += 1
                continue

            # Required fields
            source_wav = region.get("source_wav")
            start_sec = region.get("start_sec")
            end_sec = region.get("end_sec")

            missing = [
                f for f, v in [
                    ("source_wav", source_wav),
                    ("start_sec", start_sec),
                    ("end_sec", end_sec),
                ]
                if v is None
            ]
            if missing:
                print(
                    f"  WARNING: concept '{concept_id_str}' speaker '{speaker_str}' region is missing "
                    f"required field(s): {', '.join(missing)} — skipping.",
                    file=sys.stderr,
                )
                skipped_missing_fields += 1
                continue

            if not isinstance(source_wav, str) or not source_wav.strip():
                print(
                    f"  WARNING: concept '{concept_id_str}' speaker '{speaker_str}' region 'source_wav' "
                    f"is not a valid string — skipping.",
                    file=sys.stderr,
                )
                skipped_missing_fields += 1
                continue
            source_wav = source_wav.strip()

            # Type coercion for timestamps (may come in as int or string)
            try:
                start_sec = _coerce_time_seconds(
                    start_sec,
                    field_name="start_sec",
                    concept_id=concept_id_str,
                    speaker=speaker_str,
                )
                end_sec = _coerce_time_seconds(
                    end_sec,
                    field_name="end_sec",
                    concept_id=concept_id_str,
                    speaker=speaker_str,
                )
            except ValueError as exc:
                print(f"  WARNING: {exc} — skipping.", file=sys.stderr)
                skipped_missing_fields += 1
                continue

            if end_sec <= start_sec:
                print(
                    f"  WARNING: concept '{concept_id_str}' speaker '{speaker_str}': "
                    f"end_sec ({end_sec}) <= start_sec ({start_sec}) — skipping.",
                    file=sys.stderr,
                )
                skipped_missing_fields += 1
                continue

            # Resolve source_wav path
            try:
                resolved_wav = _resolve_wav_path(source_wav, source_root)
            except (TypeError, ValueError, OSError) as exc:
                print(
                    f"  WARNING: concept '{concept_id_str}' speaker '{speaker_str}': "
                    f"invalid source_wav path ({exc}) — skipping.",
                    file=sys.stderr,
                )
                skipped_missing_fields += 1
                continue

            jobs.append(
                ExtractionJob(
                    concept_id=concept_id_str,
                    speaker=speaker_str,
                    source_wav=resolved_wav,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    output_dir=output_dir,
                    region=region,
                )
            )

    if skipped_unassigned:
        print(
            f"  (Skipped {skipped_unassigned} unassigned region(s). "
            "Use --no-only-assigned to include them.)",
            file=sys.stderr,
        )
    if skipped_missing_fields:
        print(
            f"  (Skipped {skipped_missing_fields} region(s) due to missing/invalid fields.)",
            file=sys.stderr,
        )

    return jobs


def _resolve_wav_path(source_wav: str, source_root: str | None) -> str:
    """Resolve a source WAV path, optionally prepending source_root."""
    if source_root:
        # If source_wav is absolute and source_root is given, source_wav wins.
        # Otherwise join them.
        wav_path = Path(source_wav)
        if wav_path.is_absolute():
            return str(wav_path)
        
        try:
            resolved = (Path(source_root) / wav_path).resolve(strict=False)
            root_resolved = Path(source_root).resolve(strict=False)
            if not str(resolved).startswith(str(root_resolved)):
                print(f"  WARNING: Path traversal detected: {source_wav}", file=sys.stderr)
                return str(Path(source_root) / wav_path.name)
            return str(resolved)
        except Exception:
            return str(Path(source_root) / wav_path)
    return source_wav


# ---------------------------------------------------------------------------
# ffmpeg command building
# ---------------------------------------------------------------------------

def build_ffmpeg_cmd(
    job: ExtractionJob,
    ffmpeg_bin: str,
) -> list[str]:
    """
    Build the ffmpeg command list for a single extraction job.

    Uses:
      -ss <start>  (input seek — fast, before decoding)
      -t <duration> (duration of output)
      -c copy      (stream copy, no re-encoding — preserves original quality)
      -y           (overwrite output without prompting)

    Note: We use -ss before -i (input-side seek) for speed on large files.
    Combined with -t (duration) rather than -to, which avoids any ambiguity
    when input-side seek is used with stream copy mode.
    """
    duration = job.end_sec - job.start_sec

    cmd = [
        ffmpeg_bin,
        "-y",                          # overwrite output if exists
        "-ss", f"{job.start_sec:.6f}", # seek to start (input-side, fast)
        "-t",  f"{duration:.6f}",      # duration of extract
        "-i",  job.source_wav,         # input file
        "-c",  "copy",                 # stream copy (no re-encode)
        str(job.output_path),          # output file
    ]
    return cmd


def format_cmd_for_display(cmd: list[str]) -> str:
    """Format a command list as a human-readable shell string."""
    parts = []
    for arg in cmd:
        # Quote arguments that contain spaces or special chars
        if " " in arg or any(c in arg for c in r'"\$`'):
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_job(job: ExtractionJob, cmd: list[str]) -> tuple[bool, str]:
    """
    Execute a single ffmpeg command.

    Returns:
        (success: bool, message: str)
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return False, f"ffmpeg binary not found: {cmd[0]}"
    except OSError as e:
        return False, f"OS error running ffmpeg: {e}"

    if result.returncode != 0:
        # Extract the last few lines of stderr for a concise error message
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        return False, f"ffmpeg exited with code {result.returncode}:\n{stderr_tail}"

    # Verify output file was actually created and has non-zero size
    if not job.output_path.exists():
        return False, "ffmpeg exited 0 but output file was not created"
    if job.output_path.stat().st_size == 0:
        return False, "ffmpeg exited 0 but output file is empty"

    return True, f"OK ({job.output_path.stat().st_size / 1024:.1f} KB)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    # --- Load decisions ---
    print(f"Loading decisions from: {args.decisions}")
    decisions = load_decisions(args.decisions)
    print(f"  Found {len(decisions)} concept(s) in decisions file.")

    # --- Prepare output directory ---
    output_dir = Path(args.output_dir)
    if args.execute:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {output_dir.resolve()}")
    else:
        print(f"Output directory (dry-run): {output_dir}")

    # --- Build extraction jobs ---
    print()
    jobs = build_jobs(
        decisions,
        output_dir=output_dir,
        source_root=args.source_root,
        only_assigned=args.only_assigned,
    )

    if not jobs:
        print("No extraction jobs found. Nothing to do.")
        print(
            "  Tip: check that your regions have assigned=true, "
            "or use --no-only-assigned to include unassigned regions."
        )
        sys.exit(0)

    print(f"Found {len(jobs)} extraction job(s).\n")

    if not args.execute:
        print("=" * 70)
        print("DRY-RUN MODE — no files will be written.")
        print("Add --execute to actually run these commands.")
        print("=" * 70)
        print()

    # --- Process jobs ---
    succeeded = 0
    failed = 0
    overwritten_existing = 0
    missing_sources = 0

    for i, job in enumerate(jobs, start=1):
        cmd = build_ffmpeg_cmd(job, ffmpeg_bin=args.ffmpeg_bin)
        cmd_str = format_cmd_for_display(cmd)

        # Annotation line
        ai_info = ""
        if job.region.get("ai_suggestion_used") is not None:
            conf = job.region.get("ai_suggestion_confidence", "?")
            score = job.region.get("ai_suggestion_score")
            try:
                score_val = float(score)
                score_str = f" score={score_val:.2f}"
            except (TypeError, ValueError):
                score_str = ""
            ai_info = f" [AI suggestion #{job.region['ai_suggestion_used']}, {conf}{score_str}]"

        notes = job.region.get("notes", "")
        notes_str = f" — {notes}" if notes else ""

        header = (
            f"[{i}/{len(jobs)}] {job.speaker} / concept {job.concept_id} "
            f"({job.start_sec:.1f}s → {job.end_sec:.1f}s, {job.duration_sec:.2f}s)"
            f"{ai_info}{notes_str}"
        )

        print(header)
        print(f"  Source : {job.source_wav}")
        print(f"  Output : {job.output_filename}")
        print(f"  CMD    : {cmd_str}")

        # Verify source file exists before attempting extraction
        source_path = Path(job.source_wav)
        if not source_path.exists():
            print(f"  STATUS : SKIPPED — source file not found: {job.source_wav}")
            missing_sources += 1
            failed += 1
            print()
            continue

        if not args.execute:
            print()
            continue

        # --- Execute ---
        # Skip if output already exists (avoid accidental overwrites in re-runs)
        # Note: ffmpeg -y will overwrite anyway, but we log it clearly.
        if job.output_path.exists():
            overwritten_existing += 1
            print(f"  STATUS : OVERWRITING existing file")

        success, msg = run_job(job, cmd)
        if success:
            print(f"  STATUS : SUCCESS — {msg}")
            succeeded += 1
        else:
            print(f"  STATUS : FAILED — {msg}")
            failed += 1
        print()

    # --- Summary ---
    print("=" * 70)
    if args.execute:
        print(f"DONE. {succeeded} succeeded, {failed} failed out of {len(jobs)} jobs.")
        if overwritten_existing > 0:
            print(f"  ({overwritten_existing} output file(s) were overwritten.)")
        if failed > 0:
            print(
                "\nSome extractions failed. Common causes:\n"
                "  - Source WAV file not found (wrong path or missing --source-root)\n"
                "  - ffmpeg not on PATH (use --ffmpeg-bin to specify the binary)\n"
                "  - Output directory is not writable\n"
                "  - Timestamp out of range for the source recording"
            )
            sys.exit(1)
    else:
        summary = f"DRY-RUN complete. {len(jobs)} command(s) shown above."
        if missing_sources > 0:
            summary += f"\n  WARNING: {missing_sources} job(s) reference missing source WAVs."
        print(summary + "\nRun with --execute to perform the extractions.")


if __name__ == "__main__":
    main()
