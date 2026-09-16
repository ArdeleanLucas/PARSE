#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel

DEFAULT_CACHED_MODEL = Path("/home/lucas/.cache/ctranslate2/razhan-whisper-base-sdh-fp16")


def resolve_model(model_arg: str | None) -> str:
    if not model_arg:
        if DEFAULT_CACHED_MODEL.exists():
            return str(DEFAULT_CACHED_MODEL)
        return "base"

    normalized = model_arg.strip()
    if normalized in {"base", "base.en"} and DEFAULT_CACHED_MODEL.exists():
        return str(DEFAULT_CACHED_MODEL)
    return normalized


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Transcribe audio with Faster-Whisper on GPU")
    p.add_argument("--input", required=True, help="Path to input audio/video file")
    p.add_argument("--output-dir", help="Optional output directory for .txt/.json transcript files")
    p.add_argument("--model", default="base", help="Model name or CTranslate2 model path (default: base -> local cached model if present)")
    p.add_argument("--language", default=None, help="Optional language code (e.g. en, ku, de)")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu", "auto"], help="Execution device")
    p.add_argument("--compute-type", default="float16", help="CTranslate2 compute type (recommended on this machine: float16 or float32)")
    p.add_argument("--beam-size", type=int, default=5, help="Beam size")
    p.add_argument("--no-vad", action="store_true", help="Disable VAD filtering")
    p.add_argument("--json", action="store_true", help="Print structured JSON to stdout")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    model_name = resolve_model(args.model)

    try:
        model = WhisperModel(model_name, device=args.device, compute_type=args.compute_type)
        segments, info = model.transcribe(
            str(input_path),
            beam_size=args.beam_size,
            language=args.language,
            vad_filter=not args.no_vad,
        )
        segs = list(segments)
        transcript = " ".join(seg.text.strip() for seg in segs).strip()
    except Exception as exc:
        print(f"Transcription failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "success": True,
        "input": str(input_path),
        "model": model_name,
        "device": args.device,
        "compute_type": args.compute_type,
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "transcript": transcript,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            for seg in segs
        ],
    }

    if args.output_dir:
        out_dir = Path(args.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = input_path.stem
        txt_path = out_dir / f"{stem}.txt"
        json_path = out_dir / f"{stem}.json"
        txt_path.write_text(transcript + ("\n" if transcript else ""), encoding="utf-8")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(transcript)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
