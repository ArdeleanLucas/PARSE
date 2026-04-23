#!/usr/bin/env python3
"""Full-file STT pipeline for PARSE using configured AI provider.

CLI example:
    python stt_pipeline.py --input audio.wav --speaker Khan04 --output stt.json --language sd
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

try:
    from .provider import Segment, WordSpan, get_provider, load_ai_config
except ImportError:
    from provider import Segment, WordSpan, get_provider, load_ai_config  # type: ignore


LONG_FILE_WARNING_SECONDS = 20.0 * 60.0


class _STTOutputSegmentRequired(Segment):
    """Required keys for speaker-import STT segments."""

    ortho: str
    ipa: str


class STTOutputSegment(_STTOutputSegmentRequired, total=False):
    """Output STT segment used by speaker import flows.

    ``words`` is populated when Tier 1 word-level STT is active
    (word_timestamps=True). Legacy consumers that only read start/end/text/
    ortho/ipa keep working because ``words`` is structurally optional.
    """

    words: List[WordSpan]


class STTArtifact(TypedDict):
    """Serialized STT artifact payload for speaker import."""

    speaker: str
    source_wav: str
    duration_sec: float
    processed_at: str
    model: str
    segments: List[STTOutputSegment]


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 with Z suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def model_name_from_config(config: Dict[str, Any]) -> str:
    """Resolve model name for output payload from provider config."""
    stt_config = config.get("stt", {})
    if not isinstance(stt_config, dict):
        return "unknown"

    model_name = str(stt_config.get("model", "") or "").strip()
    if model_name:
        return model_name

    model_path = str(stt_config.get("model_path", "") or "").strip()
    if model_path:
        return model_path

    provider_name = str(stt_config.get("provider", "") or "").strip()
    if provider_name:
        return provider_name

    return "unknown"


def build_provider_config(
    config_path: Optional[Path] = None,
    language: Optional[str] = None,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Load provider config and apply CLI overrides."""
    config = load_ai_config(config_path)
    stt_config = config.get("stt")
    if not isinstance(stt_config, dict):
        stt_config = {}
        config["stt"] = stt_config

    if language:
        stt_config["language"] = str(language)
    if device:
        stt_config["device"] = str(device)
    if compute_type:
        stt_config["compute_type"] = str(compute_type)

    return config


def clamp_confidence(value: float) -> float:
    """Clamp confidence to [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def get_audio_duration_seconds(audio_path: Path) -> float:
    """Read audio duration with soundfile."""
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "soundfile is required for STT pipeline. Install python-soundfile."
        ) from exc

    try:
        info = sf.info(str(audio_path))
    except Exception as exc:
        raise RuntimeError("Failed to read audio metadata with soundfile: {0}".format(exc)) from exc

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    if duration < 0.0:
        return 0.0
    return duration


class ProgressReporter:
    """Progress logger that prints every 10% or every 30 seconds."""

    def __init__(self) -> None:
        self.last_bucket = -1
        self.last_print_monotonic = 0.0
        self.last_progress = 0.0

    def callback(self, progress: float, segments_processed: int) -> None:
        """Progress callback compatible with provider.transcribe."""
        now = time.monotonic()
        bounded = max(0.0, min(float(progress), 100.0))
        bucket = int(bounded // 10)

        should_print = False
        if bucket > self.last_bucket:
            should_print = True
        elif (now - self.last_print_monotonic) >= 30.0 and bounded > self.last_progress:
            should_print = True
        elif bounded >= 100.0 and self.last_progress < 100.0:
            should_print = True

        if not should_print:
            return

        print(
            "[STT] {0:5.1f}% complete ({1} segments)".format(bounded, segments_processed),
            file=sys.stderr,
        )
        self.last_bucket = max(self.last_bucket, bucket)
        self.last_print_monotonic = now
        self.last_progress = bounded


def run_stt_pipeline(
    input_path: Path,
    speaker: str,
    language: Optional[str] = None,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> STTArtifact:
    """Run full-file STT and return speaker-import artifact."""
    speaker_id = str(speaker or "").strip()
    if not speaker_id:
        raise ValueError("Speaker ID is required")

    audio_path = Path(input_path).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError("Input audio does not exist: {0}".format(audio_path))

    duration = get_audio_duration_seconds(audio_path)
    if duration >= LONG_FILE_WARNING_SECONDS:
        print(
            "[WARN] Long file detected ({0:.1f} minutes). STT may take a while.".format(
                duration / 60.0
            ),
            file=sys.stderr,
        )

    config = build_provider_config(
        config_path=config_path,
        language=language,
        device=device,
        compute_type=compute_type,
    )
    provider = get_provider(config)

    reporter = ProgressReporter()
    raw_segments = provider.transcribe(
        audio_path=audio_path,
        language=language,
        progress_callback=reporter.callback,
    )

    cleaned: List[STTOutputSegment] = []
    for segment in raw_segments:
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        text = str(segment.get("text", "") or "").strip()
        confidence = clamp_confidence(float(segment.get("confidence", 0.0) or 0.0))

        out_segment: STTOutputSegment = {
            "start": start,
            "end": end,
            "text": text,
            "ortho": text,
            "ipa": "",
            "confidence": confidence,
        }
        # Tier 1: propagate word-level spans when faster-whisper produced
        # them (word_timestamps=True). Forced-alignment (Tier 2) consumes
        # these; the frontend and legacy MCP tools ignore the extra key.
        raw_words = segment.get("words")
        if isinstance(raw_words, list) and raw_words:
            out_segment["words"] = list(raw_words)
        cleaned.append(out_segment)

    return {
        "speaker": speaker_id,
        "source_wav": str(audio_path),
        "duration_sec": duration,
        "processed_at": utc_now_iso(),
        "model": model_name_from_config(config),
        "segments": cleaned,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run full-file STT and write speaker-import artifact JSON."
    )
    parser.add_argument("--input", required=True, help="Input WAV/audio path")
    parser.add_argument("--speaker", required=True, help="Speaker ID for the STT artifact")
    parser.add_argument("--output", required=True, help="Output JSON path for STT artifact")
    parser.add_argument("--language", default=None, help="Language override (e.g., sd, sdh)")
    parser.add_argument("--device", default=None, help="Inference device override (cuda or cpu)")
    parser.add_argument(
        "--compute-type",
        default=None,
        help="Compute type override (float16, int8, etc.)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to ai_config.json (defaults to config/ai_config.json)",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve() if args.config else None

    try:
        artifact = run_stt_pipeline(
            input_path=input_path,
            speaker=args.speaker,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            config_path=config_path,
        )
    except Exception as exc:
        print("[ERROR] STT pipeline failed: {0}".format(exc), file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "[INFO] Wrote {0} segments for speaker '{1}' to {2}".format(
            len(artifact["segments"]),
            artifact["speaker"],
            output_path,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
