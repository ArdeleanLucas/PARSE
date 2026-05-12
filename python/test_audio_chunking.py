from __future__ import annotations

import ast
from pathlib import Path

import pytest

from workers.audio_chunking import merge_chunk_segments, split_audio_duration


def test_split_audio_duration_basic() -> None:
    spans = split_audio_duration(total_seconds=18130.5, chunk_seconds=600)

    assert len(spans) == 31
    assert spans[0] == {"idx": 0, "start": 0.0, "end": 600.0}
    assert spans[29] == {"idx": 29, "start": 17400.0, "end": 18000.0}
    assert spans[30] == {"idx": 30, "start": 18000.0, "end": 18130.5}


def test_split_audio_duration_under_threshold() -> None:
    assert split_audio_duration(total_seconds=300, chunk_seconds=600) == [
        {"idx": 0, "start": 0.0, "end": 300}
    ]


def test_split_audio_duration_zero_or_negative() -> None:
    assert split_audio_duration(total_seconds=0, chunk_seconds=600) == []
    assert split_audio_duration(total_seconds=-1, chunk_seconds=600) == []
    with pytest.raises(ValueError):
        split_audio_duration(total_seconds=10, chunk_seconds=0)


def test_split_audio_duration_indices_contiguous_and_adjacent() -> None:
    for total_seconds, chunk_seconds in [(1.5, 0.5), (600.001, 300), (1200, 600)]:
        spans = split_audio_duration(total_seconds=total_seconds, chunk_seconds=chunk_seconds)
        for idx, span in enumerate(spans):
            assert span["idx"] == idx
        for left, right in zip(spans, spans[1:]):
            assert left["end"] == right["start"]
        if spans:
            assert spans[0]["start"] == 0.0
            assert spans[-1]["end"] == total_seconds


def test_merge_chunk_segments_timestamp_offset() -> None:
    spans = [
        {"idx": 0, "start": 0.0, "end": 600.0},
        {"idx": 1, "start": 600.0, "end": 1200.0},
    ]

    merged = merge_chunk_segments([[], [{"start": 10, "end": 20, "text": "hello"}]], spans)

    assert merged == [{"start": 610, "end": 620, "text": "hello"}]


def test_merge_chunk_segments_words_offset_recursive() -> None:
    spans = [{"idx": 0, "start": 600.0, "end": 1200.0}]

    merged = merge_chunk_segments(
        [
            [
                {
                    "start": 10,
                    "end": 20,
                    "text": "hello world",
                    "words": [
                        {"word": "hello", "start": 10, "end": 12, "score": 0.9},
                        {"word": "world", "start": 13.5, "end": 20},
                    ],
                }
            ]
        ],
        spans,
    )

    assert merged[0]["words"] == [
        {"word": "hello", "start": 610, "end": 612, "score": 0.9},
        {"word": "world", "start": 613.5, "end": 620},
    ]


def test_merge_chunk_segments_drops_empty_text() -> None:
    spans = [{"idx": 0, "start": 0.0, "end": 600.0}]

    merged = merge_chunk_segments(
        [[{"start": 0, "end": 1, "text": ""}, {"start": 1, "end": 2, "text": "   "}, {"start": 2, "end": 3, "text": "kept"}]],
        spans,
    )

    assert merged == [{"start": 2, "end": 3, "text": "kept"}]


def test_merge_chunk_segments_sorted_by_start_end() -> None:
    spans = [
        {"idx": 0, "start": 0.0, "end": 600.0},
        {"idx": 1, "start": 600.0, "end": 1200.0},
    ]

    merged = merge_chunk_segments(
        [
            [{"start": 590, "end": 595, "text": "second"}, {"start": 10, "end": 20, "text": "first"}],
            [{"start": 0, "end": 5, "text": "third"}],
        ],
        spans,
    )

    assert [segment["text"] for segment in merged] == ["first", "second", "third"]
    assert [(segment["start"], segment["end"]) for segment in merged] == [(10, 20), (590, 595), (600, 605)]


def test_merge_chunk_segments_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        merge_chunk_segments([[{"start": 0, "end": 1, "text": "x"}]], [])


def test_module_has_no_server_imports() -> None:
    module_path = Path(__file__).with_name("workers") / "audio_chunking.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    banned_roots = {"server", "annotate", "compute_worker", "torch", "soundfile"}
    banned_from_prefixes = (
        "server",
        "server_routes",
        "annotate",
        "workers.compute_worker",
        "compute_worker",
        "torch",
        "soundfile",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in banned_roots
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not any(module == prefix or module.startswith(f"{prefix}.") for prefix in banned_from_prefixes)
