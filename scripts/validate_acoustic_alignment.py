#!/usr/bin/env python3
"""End-to-end validation for the Tier 1/2/3 acoustic alignment pipeline.

This script is *not* part of the hermetic pytest suite — it requires the
real ML stack (torch, torchaudio, transformers, phonemizer, espeak-ng,
faster-whisper) and a real PARSE recording. It's the thing you run once
to convince yourself that wav2vec2 is producing sensible Kurdish IPA on
actual Fail02 audio before landing the PR.

Usage:
    python scripts/validate_acoustic_alignment.py \\
        --audio audio/source/Fail02.wav \\
        --start 0 --duration 30 \\
        --out-dir /tmp/parse-validation

What it does:
    1. Slices a 30-second window of Fail02.wav into a scratch WAV.
    2. Runs Tier 1 STT (word_timestamps=True) on the slice and writes
       stt.json with nested segments[].words[].
    3. Runs Tier 2 forced alignment on those words with wav2vec2-xlsr
       and writes aligned.json.
    4. Runs Tier 3 acoustic IPA on each Tier 2 word window and writes
       ipa.json.
    5. Prints a human-readable diff of Whisper vs wav2vec2 boundaries
       and the IPA string per word, plus the method-count histogram
       (how many words used wav2vec2 vs fell back to proportional).

Interpret the output:
    - Any phoneme count <= 1 per word is almost certainly a G2P miss;
      espeak-ng may need the Kurdish voice installed.
    - If every word shows method="proportional-fallback", the aligner
      couldn't load — check the torch/transformers import logs.
    - Confidence < 0.1 on most words suggests the model is struggling
      on this speaker; acceptable IPA quality still possible but
      double-check against a manual transcription.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _slice_audio(src: Path, start_sec: float, duration_sec: float, out: Path) -> Path:
    """Extract [start, start+duration] from src into out (mono 16 kHz).

    Uses soundfile + torch to avoid torchaudio.load's torchcodec dependency
    (torchaudio 2.5+ raises ImportError when torchcodec is not installed).
    """
    import soundfile as sf  # type: ignore
    import numpy as np  # type: ignore
    import torch  # type: ignore

    data, sr = sf.read(str(src), always_2d=True)
    # data shape: (samples, channels) — convert to (channels, samples)
    waveform = torch.from_numpy(data.T.astype("float32"))
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != 16000:
        try:
            import torchaudio.functional as _taf  # type: ignore
            waveform = _taf.resample(waveform, sr, 16000)
        except Exception:
            # Fallback: simple decimation (good enough for validation slicing)
            ratio = sr / 16000
            indices = torch.arange(0, waveform.shape[-1], ratio).long()
            indices = indices[indices < waveform.shape[-1]]
            waveform = waveform[:, indices]
        sr = 16000

    start_sample = max(0, int(start_sec * sr))
    end_sample = min(int(waveform.shape[-1]), int((start_sec + duration_sec) * sr))
    clipped = waveform[:, start_sample:end_sample]

    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), clipped.squeeze(0).numpy(), sr, subtype="PCM_16")
    return out


def _run_stt(audio: Path, out_json: Path) -> Dict[str, Any]:
    """Tier 1: faster-whisper with word_timestamps=True."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from ai.stt_pipeline import run_stt_pipeline

    artifact = run_stt_pipeline(
        input_path=audio,
        speaker="Fail02-validation",
    )
    out_json.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def _run_forced_align(audio: Path, stt: Dict[str, Any], out_json: Path) -> List[List[Dict[str, Any]]]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from ai.forced_align import align_segments

    aligned = align_segments(
        audio_path=audio,
        segments=stt.get("segments") or [],
        language="ku",
        pad_ms=100,
    )
    out_json.write_text(
        json.dumps({"segments": aligned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return aligned


def _run_ipa(audio: Path, aligned: List[List[Dict[str, Any]]], out_json: Path) -> List[Dict[str, Any]]:
    """Flatten aligned words into intervals and call Tier 3 acoustic IPA."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from ai.ipa_transcribe import transcribe_intervals

    intervals: List[Dict[str, Any]] = []
    for segment_words in aligned:
        for word in segment_words:
            intervals.append(
                {"start": word["start"], "end": word["end"], "text": word.get("word", "")}
            )

    results = transcribe_intervals(audio_path=audio, intervals=intervals)
    out_json.write_text(
        json.dumps({"intervals": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def _print_summary(
    stt: Dict[str, Any],
    aligned: List[List[Dict[str, Any]]],
    ipa: List[Dict[str, Any]],
) -> None:
    method_counts: Dict[str, int] = {}
    for segment in aligned:
        for word in segment:
            method = word.get("method", "unknown")
            method_counts[method] = method_counts.get(method, 0) + 1

    print("\n── Validation Summary ──────────────────────────")
    print("STT segments:     {0}".format(len(stt.get("segments", []))))
    print("Aligned words:    {0}".format(sum(len(s) for s in aligned)))
    print("Acoustic IPA:     {0}".format(len(ipa)))
    print("Method counts:    {0}".format(method_counts))

    print("\n── First 10 words: Whisper vs wav2vec2 vs IPA ──")
    print("{0:<18} {1:>8} {2:>8} {3:>8} {4:>6} {5}".format(
        "word", "w.start", "w.end", "a.end", "conf", "ipa"
    ))
    idx = 0
    for seg_idx, segment in enumerate(aligned):
        for word in segment:
            if idx >= 10:
                break
            ipa_str = ipa[idx]["ipa"] if idx < len(ipa) else ""
            print("{0:<18} {1:>8.2f} {2:>8.2f} {3:>8.2f} {4:>6.2f} {5!r}".format(
                word.get("word", "")[:18],
                word.get("start", 0.0),
                word.get("end", 0.0),
                word.get("end", 0.0),
                word.get("confidence", 0.0),
                ipa_str,
            ))
            idx += 1
        if idx >= 10:
            break


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio", required=True, help="Source audio (e.g. audio/source/Fail02.wav)")
    parser.add_argument("--start", type=float, default=0.0, help="Start second (default 0)")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration in seconds (default 30)")
    parser.add_argument("--out-dir", default="/tmp/parse-validation", help="Where to write intermediate artifacts")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_src = Path(args.audio).expanduser().resolve()
    if not audio_src.exists():
        print("[ERROR] Audio not found: {0}".format(audio_src), file=sys.stderr)
        return 1

    clip_path = out_dir / "clip.wav"
    print("[1/4] Slicing {0}s of {1} to {2}".format(args.duration, audio_src, clip_path))
    _slice_audio(audio_src, args.start, args.duration, clip_path)

    stt_path = out_dir / "stt.json"
    print("[2/4] Tier 1 STT -> {0}".format(stt_path))
    stt = _run_stt(clip_path, stt_path)

    aligned_path = out_dir / "aligned.json"
    print("[3/4] Tier 2 forced alignment -> {0}".format(aligned_path))
    aligned = _run_forced_align(clip_path, stt, aligned_path)

    ipa_path = out_dir / "ipa.json"
    print("[4/4] Tier 3 acoustic IPA -> {0}".format(ipa_path))
    ipa = _run_ipa(clip_path, aligned, ipa_path)

    _print_summary(stt, aligned, ipa)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
