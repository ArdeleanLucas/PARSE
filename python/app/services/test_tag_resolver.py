"""Unit tests for the pure tag/concept resolver helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.tag_resolver import (
    SpeakerExpansionError,
    expand_speakers,
    resolve_tag_labels,
    select_concepts_by_tag,
)


def _vocab(*entries: tuple[str, str]) -> list[dict[str, object]]:
    return [
        {"id": tag_id, "label": label, "color": "#000000", "concepts": [], "lexemeTargets": []}
        for tag_id, label in entries
    ]


# ---------------- resolve_tag_labels ----------------

def test_resolve_tag_labels_returns_ids_for_known_labels() -> None:
    vocab = _vocab(("t1", "Thesis"), ("t2", "WordList"))
    resolved = resolve_tag_labels(["Thesis", "WordList"], vocab)
    assert resolved.ids_by_label == {"Thesis": "t1", "WordList": "t2"}
    assert resolved.unknown == []
    assert resolved.ambiguous == {}


def test_resolve_tag_labels_is_case_insensitive_after_trim() -> None:
    vocab = _vocab(("t1", "Thesis"))
    resolved = resolve_tag_labels(["  thesis  "], vocab)
    assert resolved.ids_by_label == {"  thesis  ": "t1"}
    assert resolved.unknown == []


def test_resolve_tag_labels_lists_unknown_labels() -> None:
    vocab = _vocab(("t1", "Thesis"))
    resolved = resolve_tag_labels(["Thesis", "Mystery", ""], vocab)
    assert resolved.ids_by_label == {"Thesis": "t1"}
    assert resolved.unknown == ["Mystery", ""]


def test_resolve_tag_labels_flags_ambiguous_label_collisions() -> None:
    vocab = _vocab(("t1", "Thesis"), ("t2", "thesis"), ("t3", "WordList"))
    resolved = resolve_tag_labels(["Thesis", "WordList"], vocab)
    # The duplicate is reported in `ambiguous`, NOT in ids_by_label.
    assert resolved.ids_by_label == {"WordList": "t3"}
    assert resolved.unknown == []
    assert sorted(resolved.ambiguous["Thesis"]) == ["t1", "t2"]


# ---------------- select_concepts_by_tag ----------------

def _record_with_concept_intervals() -> dict[str, object]:
    """Annotation record with three concept intervals and per-concept tag membership."""
    return {
        "speaker": "Saha01",
        "concept_tags": {
            "c1": ["t1"],
            "c2": ["t1", "t2"],
            "c3": ["t2"],
        },
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 1.0, "end": 2.0, "text": "root", "concept_id": "c1"},
                    {"start": 3.0, "end": 4.0, "text": "leaf", "concept_id": "c2"},
                    {"start": 5.0, "end": 6.0, "text": "twig", "concept_id": "c3"},
                ],
            },
        },
    }


def test_select_concepts_by_tag_any_returns_all_concepts_with_any_tag() -> None:
    record = _record_with_concept_intervals()
    hits = select_concepts_by_tag(record, ["t1", "t2"], match="any")
    assert [hit.conceptId for hit in hits] == ["c1", "c2", "c3"]
    assert hits[0].name == "root"
    assert hits[0].start == 1.0
    assert hits[0].end == 2.0
    assert sorted(hits[1].tags) == ["t1", "t2"]


def test_select_concepts_by_tag_all_requires_full_subset() -> None:
    record = _record_with_concept_intervals()
    hits = select_concepts_by_tag(record, ["t1", "t2"], match="all")
    assert [hit.conceptId for hit in hits] == ["c2"]


def test_select_concepts_by_tag_returns_empty_for_empty_tag_ids() -> None:
    record = _record_with_concept_intervals()
    assert select_concepts_by_tag(record, [], match="any") == []
    assert select_concepts_by_tag(record, [], match="all") == []


def test_select_concepts_by_tag_skips_intervals_without_concept_id() -> None:
    record = {
        "concept_tags": {"c1": ["t1"]},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 0.0, "end": 1.0, "text": "no-id"},  # missing concept_id
                    {"start": 2.0, "end": 3.0, "text": "leaf", "concept_id": "c1"},
                ],
            },
        },
    }
    hits = select_concepts_by_tag(record, ["t1"], match="any")
    assert [hit.conceptId for hit in hits] == ["c1"]


def test_select_concepts_by_tag_accepts_camelcase_concept_id_alias() -> None:
    record = {
        "concept_tags": {"c1": ["t1"]},
        "tiers": {
            "concept": {
                "type": "interval",
                "display_order": 3,
                "intervals": [
                    {"start": 0.0, "end": 1.0, "text": "leaf", "conceptId": "c1"},
                ],
            },
        },
    }
    hits = select_concepts_by_tag(record, ["t1"], match="any")
    assert [hit.conceptId for hit in hits] == ["c1"]


# ---------------- expand_speakers ----------------

def _make_speaker_files(root: Path, speakers: list[str]) -> None:
    annotations_dir = root / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    for speaker in speakers:
        (annotations_dir / f"{speaker}.parse.json").write_text(
            json.dumps({"speaker": speaker}), encoding="utf-8"
        )


def test_expand_speakers_all_returns_speaker_ids_in_sorted_order(tmp_path: Path) -> None:
    _make_speaker_files(tmp_path, ["Saha02", "Saha01"])
    assert expand_speakers("all", tmp_path) == ["Saha01", "Saha02"]


def test_expand_speakers_list_returns_input_when_all_present(tmp_path: Path) -> None:
    _make_speaker_files(tmp_path, ["Saha01", "Saha02"])
    assert expand_speakers(["Saha02", "Saha01"], tmp_path) == ["Saha02", "Saha01"]


def test_expand_speakers_list_raises_on_unknown_speaker(tmp_path: Path) -> None:
    _make_speaker_files(tmp_path, ["Saha01"])
    with pytest.raises(SpeakerExpansionError) as exc:
        expand_speakers(["Saha01", "Mystery"], tmp_path)
    assert "Mystery" in str(exc.value)


def test_expand_speakers_legacy_filenames_are_recognized(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    (annotations_dir / "Legacy.json").write_text("{}", encoding="utf-8")
    assert expand_speakers("all", tmp_path) == ["Legacy"]
