"""Regression tests for _extract_concepts_from_annotation id/label collision handling."""
import csv
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools


def _write_concepts_csv(project_root: pathlib.Path, rows: list) -> None:
    path = project_root / "concepts.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "concept_en"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _tools(tmp_path) -> ParseChatTools:
    return ParseChatTools(project_root=tmp_path)


def _annotation(text_list: list) -> dict:
    intervals = [
        {"start": float(i), "end": float(i) + 0.5, "text": txt}
        for i, txt in enumerate(text_list)
    ]
    return {
        "speaker": "spk",
        "source_audio": "x.wav",
        "tiers": {
            "ipa": {"type": "interval", "display_order": 1, "intervals": []},
            "ortho": {"type": "interval", "display_order": 2, "intervals": []},
            "concept": {"type": "interval", "display_order": 3, "intervals": intervals},
            "speaker": {"type": "interval", "display_order": 4, "intervals": []},
        },
    }


def test_extract_reuses_existing_id_for_same_label(tmp_path) -> None:
    _write_concepts_csv(tmp_path, [
        {"id": "1", "concept_en": "hair"},
        {"id": "2", "concept_en": "forehead"},
    ])
    tools = _tools(tmp_path)
    # Annotation uses label-only text — should match by label
    result = tools._extract_concepts_from_annotation(_annotation(["hair", "forehead"]))
    ids_by_label = {c["label"]: c["id"] for c in result}
    assert ids_by_label == {"hair": "1", "forehead": "2"}


def test_extract_reassigns_when_digit_prefix_collides_with_different_label(tmp_path) -> None:
    """If an incoming annotation says `1: hair` but existing concepts.csv has
    id=1 bound to a DIFFERENT label (e.g. 'ash'), the importer must not
    overwrite concept 1. It should reassign 'hair' to a fresh id (or reuse
    one if 'hair' already exists by label)."""
    _write_concepts_csv(tmp_path, [
        {"id": "1", "concept_en": "ash"},
        {"id": "2", "concept_en": "bark"},
    ])
    tools = _tools(tmp_path)
    result = tools._extract_concepts_from_annotation(_annotation(["1: hair", "2: tree"]))
    ids_by_label = {c["label"]: c["id"] for c in result}
    # Neither "hair" nor "tree" existed — they should get fresh ids (3, 4)
    # not overwrite ash/bark at 1/2.
    assert ids_by_label["hair"] not in {"1", "2"}
    assert ids_by_label["tree"] not in {"1", "2"}
    assert ids_by_label["hair"] != ids_by_label["tree"]


def test_extract_respects_existing_label_lookup_on_digit_collision(tmp_path) -> None:
    """Digit-prefixed annotation with collision should still pick up existing
    id-by-label mapping if the label does exist (so concept references stay
    stable)."""
    _write_concepts_csv(tmp_path, [
        {"id": "1", "concept_en": "ash"},
        {"id": "42", "concept_en": "hair"},
    ])
    tools = _tools(tmp_path)
    result = tools._extract_concepts_from_annotation(_annotation(["1: hair"]))
    # "1: hair" collides with id=1 (ash); should resolve by label "hair" → existing id 42
    assert result == [{"id": "42", "label": "hair"}]


def test_extract_keeps_digit_when_no_collision(tmp_path) -> None:
    """When the numeric prefix matches the existing label for that id, keep it."""
    _write_concepts_csv(tmp_path, [
        {"id": "1", "concept_en": "hair"},
    ])
    tools = _tools(tmp_path)
    result = tools._extract_concepts_from_annotation(_annotation(["1: hair"]))
    assert result == [{"id": "1", "label": "hair"}]


def test_extract_does_not_reassign_into_seen_id(tmp_path) -> None:
    """The fallback-id generator must skip ids already consumed in the current
    annotation so we don't introduce new collisions inside one import."""
    _write_concepts_csv(tmp_path, [
        {"id": "1", "concept_en": "ash"},
    ])
    tools = _tools(tmp_path)
    # Two annotations that both collide at id=1 with different labels.
    result = tools._extract_concepts_from_annotation(_annotation(["1: hair", "1: forehead"]))
    ids = {c["id"] for c in result}
    assert len(ids) == len(result)
    assert "1" not in ids  # both were reassigned
