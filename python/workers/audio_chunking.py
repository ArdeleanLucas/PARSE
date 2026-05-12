"""Pure audio chunking primitives for robust PARSE compute paths."""

from __future__ import annotations

from typing import Literal, TypedDict

from typing_extensions import NotRequired

__all__ = ["ChunkResult", "ChunkSpan", "merge_chunk_segments", "split_audio_duration"]


class ChunkSpan(TypedDict):
    idx: int
    start: float  # seconds, inclusive
    end: float  # seconds, exclusive


class ChunkResult(TypedDict):
    idx: int
    span: ChunkSpan
    status: Literal['ok', 'error', 'skipped', 'cancelled']
    error_code: NotRequired[str]  # e.g. 'oom_suspect', 'chunk_failed', 'provider_error', 'timeout'
    error: NotRequired[str]  # human-readable


def split_audio_duration(total_seconds: float, chunk_seconds: float) -> list[ChunkSpan]:
    """Split an audio duration into adjacent chunk spans.

    Boundaries are tracked in integer milliseconds for deterministic adjacency;
    only the API surface uses seconds. The final span preserves the caller's
    exact ``total_seconds`` value as its exclusive end.
    """
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be > 0")
    if total_seconds <= 0:
        return []
    if total_seconds <= chunk_seconds:
        return [{"idx": 0, "start": 0.0, "end": total_seconds}]

    chunk_ms = max(1, round(chunk_seconds * 1000))
    total_ms = round(total_seconds * 1000)

    spans: list[ChunkSpan] = []
    start_ms = 0
    idx = 0
    while start_ms < total_ms:
        end_ms = min(start_ms + chunk_ms, total_ms)
        start = start_ms / 1000
        end = total_seconds if end_ms >= total_ms else end_ms / 1000
        spans.append({"idx": idx, "start": start, "end": end})
        start_ms = end_ms
        idx += 1
    return spans


def merge_chunk_segments(per_chunk_segments: list[list[dict]], spans: list[ChunkSpan]) -> list[dict]:
    """Merge chunk-local transcription segments into global timestamps."""
    if len(per_chunk_segments) != len(spans):
        raise ValueError("per_chunk_segments and spans must have the same length")

    merged: list[dict] = []
    for segments, span in zip(per_chunk_segments, spans):
        offset = span["start"]
        for segment in segments:
            text = str(segment.get("text", ""))
            if not text.strip():
                continue
            shifted = dict(segment)
            shifted["start"] = segment["start"] + offset
            shifted["end"] = segment["end"] + offset
            if "words" in segment:
                shifted["words"] = [_offset_word_timestamps(word, offset) for word in segment["words"]]
            merged.append(shifted)

    return sorted(merged, key=lambda segment: (segment["start"], segment["end"]))


def _offset_word_timestamps(word: dict, offset: float) -> dict:
    shifted = dict(word)
    if "start" in shifted:
        shifted["start"] = shifted["start"] + offset
    if "end" in shifted:
        shifted["end"] = shifted["end"] + offset
    return shifted
