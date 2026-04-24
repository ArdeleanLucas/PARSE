#!/usr/bin/env python3
"""Tier 3 acoustic IPA transcription for PARSE.

wav2vec2 CTC is the **only** IPA engine after this module landed. The
previous text-driven chain (Epitran, ``southern_kurdish_arabic_to_ipa``,
LLM-prompt fallbacks) has been removed. Input is always audio slices;
output is always the phoneme sequence the acoustic model predicted.

CLI:
    # Per-interval mode — reads a Tier 1 STT artifact or raw interval list,
    # writes an IPA string per interval.
    python -m ai.ipa_transcribe \\
        --audio recording.wav \\
        --intervals intervals.json \\
        --output ipa.json

Library API:
    - :func:`transcribe_intervals` - batch audio+intervals -> List[IpaResult]
    - :func:`transcribe_slice`     - single audio slice   -> str
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, TypedDict

try:
    from .forced_align import (
        DEFAULT_MODEL_NAME,
        DEFAULT_PAD_MS,
        DEFAULT_SAMPLE_RATE,
        Aligner,
        _load_audio_mono_16k,
    )
except ImportError:  # pragma: no cover - CLI invocation
    from forced_align import (  # type: ignore
        DEFAULT_MODEL_NAME,
        DEFAULT_PAD_MS,
        DEFAULT_SAMPLE_RATE,
        Aligner,
        _load_audio_mono_16k,
    )


class IpaResult(TypedDict):
    """One interval's acoustic IPA output."""

    start: float
    end: float
    ipa: str


@dataclass
class IntervalSpec:
    """Minimal shape an input interval needs: (start, end). Any ``text`` key
    present on the source dict is ignored — Tier 3 is acoustic."""

    start: float
    end: float


# ---------------------------------------------------------------------------
# Core transcription
# ---------------------------------------------------------------------------


def transcribe_slice(
    audio_16k: Any,
    start_sec: float,
    end_sec: float,
    aligner: Aligner,
) -> str:
    """Run wav2vec2 CTC on a single [start, end] audio window.

    The caller owns the loaded mono-16 kHz tensor so that the full-file
    load happens once per speaker rather than once per interval.
    """
    if end_sec <= start_sec:
        return ""
    total = int(audio_16k.shape[0])
    start_sample = max(0, int(round(float(start_sec) * DEFAULT_SAMPLE_RATE)))
    end_sample = min(total, int(round(float(end_sec) * DEFAULT_SAMPLE_RATE)))
    if end_sample <= start_sample:
        return ""
    window = audio_16k[start_sample:end_sample]
    return aligner.transcribe_window(window)


def transcribe_intervals(
    audio_path: Path,
    intervals: Sequence[Any],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    device: Optional[str] = None,
    aligner: Optional[Aligner] = None,
    progress_callback: Optional[Any] = None,
) -> List[IpaResult]:
    """Transcribe every [start, end] interval to an IPA string.

    ``intervals`` can be dicts with ``start``/``end`` keys (e.g. the
    annotation JSON's ``ortho.intervals``) or tuples/lists of
    ``(start, end, ...)``. Any extra keys (``text``, ``ortho``, ...) are
    ignored — Tier 3 is purely acoustic.

    ``aligner`` is lazy-loaded when not provided so the caller can reuse
    one model load across many speakers.
    """
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("Audio file not found: {0}".format(path))

    parsed = _coerce_intervals(intervals)
    if not parsed:
        return []

    audio = _load_audio_mono_16k(path)

    local_aligner = aligner or Aligner.load(model_name=model_name, device=device)

    total = len(parsed)
    out: List[IpaResult] = []
    for idx, spec in enumerate(parsed):
        ipa = transcribe_slice(audio, spec.start, spec.end, local_aligner)
        out.append({"start": spec.start, "end": spec.end, "ipa": ipa})
        if progress_callback is not None:
            try:
                progress_callback((idx + 1) / float(total) * 100.0, idx + 1)
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Full 3-tier path: forced alignment → word windows → wav2vec2 CTC
# ---------------------------------------------------------------------------


def transcribe_words_with_forced_align(
    audio_path: Path,
    segments: Sequence[Any],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    device: Optional[str] = None,
    language: str = "ku",
    pad_ms: int = DEFAULT_PAD_MS,
    aligner: Optional[Aligner] = None,
    progress_callback: Optional[Any] = None,
    segment_batch_size: int = 5,
    chunk_size: int = 150,
) -> List[IpaResult]:
    """Full 3-tier IPA: G2P + torchaudio forced alignment → word windows → wav2vec2 CTC.

    For each word in ``segments[].words[]``:
      1. ``align_word()`` refines the Whisper boundary via G2P +
         ``torchaudio.functional.forced_align`` against the xlsr-53 vocab.
      2. ``transcribe_window()`` runs wav2vec2 CTC on the refined word window.

    Returns one :class:`IpaResult` per word. Segments that carry no
    ``words[]`` are skipped. Falls back to segment-level
    :func:`transcribe_intervals` when no words are found at all.

    ``segment_batch_size`` controls how many Whisper segments are fed to
    ``align_segments`` at a time. Processing all segments in one call
    accumulates GPU state across hundreds of forced-align invocations and
    can exhaust VRAM / WSL memory on long recordings (≥150 segments).
    Batching keeps peak memory proportional to the batch rather than the
    full recording.
    """
    try:
        from .forced_align import align_segments as _align_segments
    except ImportError:
        from forced_align import align_segments as _align_segments  # type: ignore

    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("Audio file not found: {0}".format(path))

    local_aligner = aligner or Aligner.load(model_name=model_name, device=device)
    audio = _load_audio_mono_16k(path)

    seg_list = list(segments)
    word_intervals: List[IntervalSpec] = []

    # Tier 2: forced alignment in batches to bound peak GPU memory.
    # Report progress after each batch so long Tier 2 runs (Fail02-scale
    # speakers can be minutes per batch on CPU) don't look stuck at 0%.
    # Tier 2 occupies the 0-50% range; Tier 3 picks up at 50%.
    tier2_total_words = sum(len(s.get("words") or []) for s in seg_list)
    tier2_words_done = 0

    for batch_start in range(0, len(seg_list), segment_batch_size):
        batch = seg_list[batch_start: batch_start + segment_batch_size]
        aligned_batch = _align_segments(
            audio_path=path,
            segments=batch,
            language=language,
            pad_ms=pad_ms,
            aligner=local_aligner,
            audio_tensor=audio,
        )
        for seg_words in aligned_batch:
            for word in seg_words:
                s = float(word.get("start", 0.0) or 0.0)
                e = float(word.get("end", 0.0) or 0.0)
                if e > s:
                    word_intervals.append(IntervalSpec(start=s, end=e))
        # Count every word in the batch (aligned or not) so the progress
        # counter advances monotonically even when some words fall through
        # to proportional fallback.
        tier2_words_done += sum(len(s.get("words") or []) for s in batch)
        if progress_callback is not None:
            try:
                pct = (tier2_words_done / float(max(1, tier2_total_words))) * 50.0
                progress_callback(pct, tier2_words_done)
            except Exception:
                pass
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        # Force a GC cycle between batches to reclaim the Tier 2 tensors
        # (CTC logits, forced_align outputs, phonemizer temporaries).
        # Python's generational GC lags significantly inside a tight
        # tensor loop, compounding the memory pressure seen on Fail02.
        gc.collect()

    if not word_intervals:
        # No words produced — fall back to segment-level coarse transcription
        seg_intervals = [
            {"start": s.get("start", 0.0), "end": s.get("end", 0.0)}
            for s in seg_list
        ]
        return transcribe_intervals(
            path, seg_intervals, aligner=local_aligner,
            progress_callback=progress_callback,
        )

    # Tier 3: wav2vec2 CTC on each refined word window, processed in chunks
    # to bound peak memory and give the allocator a chance to reset between
    # batches. chunk_size=150 is the empirically safe limit on WSL2/Blackwell.
    total = len(word_intervals)
    out: List[IpaResult] = []

    def _gpu_cleanup() -> None:
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass

    for chunk_start in range(0, total, chunk_size):
        chunk = word_intervals[chunk_start: chunk_start + chunk_size]
        for idx_in_chunk, spec in enumerate(chunk):
            global_idx = chunk_start + idx_in_chunk
            ipa = transcribe_slice(audio, spec.start, spec.end, local_aligner)
            out.append({"start": spec.start, "end": spec.end, "ipa": ipa})
            if progress_callback is not None:
                try:
                    # Tier 3 occupies the 50-100% range (Tier 2 took 0-50%).
                    pct = 50.0 + (global_idx + 1) / float(total) * 50.0
                    progress_callback(pct, global_idx + 1)
                except Exception:
                    pass
        _gpu_cleanup()

    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_intervals(raw: Iterable[Any]) -> List[IntervalSpec]:
    """Normalise dict/tuple/list interval inputs to IntervalSpec."""
    out: List[IntervalSpec] = []
    for item in raw:
        try:
            if isinstance(item, dict):
                start = float(item.get("start", 0.0) or 0.0)
                end = float(item.get("end", start) or start)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                start = float(item[0])
                end = float(item[1])
            else:
                continue
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        out.append(IntervalSpec(start=start, end=end))
    return out


def _load_intervals_json(path: Path) -> List[Any]:
    """Accept a Tier 1 STT artifact, an annotation-tier dump, or a raw list."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("intervals"), list):
            return data["intervals"]
        if isinstance(data.get("segments"), list):
            return data["segments"]
        tiers = data.get("tiers")
        if isinstance(tiers, dict):
            ortho = tiers.get("ortho")
            if isinstance(ortho, dict) and isinstance(ortho.get("intervals"), list):
                return ortho["intervals"]
    raise ValueError("Unrecognized interval JSON shape in {0}".format(path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acoustic IPA transcription via wav2vec2 CTC (Tier 3).",
    )
    parser.add_argument("--audio", required=True, help="Input WAV/audio path")
    parser.add_argument(
        "--intervals",
        required=True,
        help="JSON file with intervals (STT artifact, annotation tier, or raw list)",
    )
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--device", default=None, help="cpu|cuda (auto-detect by default)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    intervals_path = Path(args.intervals).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    intervals = _load_intervals_json(intervals_path)
    results = transcribe_intervals(
        audio_path=audio_path,
        intervals=intervals,
        model_name=args.model,
        device=args.device,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"intervals": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "[INFO] Wrote {0} acoustic IPA intervals -> {1}".format(len(results), output_path),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
