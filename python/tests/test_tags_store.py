from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import pytest

PYTHON_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from storage import tags_store


def _tag(
    tag_id: str = "tag_archaic",
    label: str = "archaic",
    color: str = "#3554B8",
    concepts: list[str] | None = None,
    lexeme_targets: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": tag_id,
        "label": label,
        "color": color,
        "concepts": [] if concepts is None else concepts,
        "lexemeTargets": [] if lexeme_targets is None else lexeme_targets,
    }


@pytest.fixture(autouse=True)
def isolated_tags_path(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "tags.json"
    monkeypatch.setenv("PARSE_TAGS_PATH", str(path))
    return path


def test_fetch_all_returns_empty_old_shape_when_file_missing(isolated_tags_path: pathlib.Path) -> None:
    assert tags_store.fetch_all() == {"version": 2, "tags": []}
    assert not isolated_tags_path.exists()


def test_replace_all_round_trips_old_shape_and_writes_version_2(isolated_tags_path: pathlib.Path) -> None:
    tags = [_tag(concepts=["water", "fire"], lexeme_targets=["Saha01::sister"])]

    result = tags_store.replace_all(tags)

    assert result == {"version": 2, "tags": tags}
    assert tags_store.fetch_all() == result
    assert json.loads(isolated_tags_path.read_text(encoding="utf-8")) == result


def test_replace_all_dedupes_concepts_preserving_first_occurrence_order() -> None:
    tag = _tag(concepts=["water", "fire", "water", "earth", "fire"])

    result = tags_store.replace_all([tag])

    assert result["tags"][0]["concepts"] == ["water", "fire", "earth"]


def test_replace_all_dedupes_lexeme_targets_preserving_first_occurrence_order() -> None:
    tag = _tag(lexeme_targets=["Saha01::sister", "Khan01::sister", "Saha01::sister"])

    result = tags_store.replace_all([tag])

    assert result["tags"][0]["lexemeTargets"] == ["Saha01::sister", "Khan01::sister"]


def test_replace_all_is_idempotent() -> None:
    tags = [_tag(), _tag("tag_uncertain", "uncertain", "#aabbcc")]

    first = tags_store.replace_all(tags)
    second = tags_store.replace_all(tags)

    assert first == second == {"version": 2, "tags": tags}


@pytest.mark.parametrize(
    ("bad_tag", "message"),
    [
        ({"id": "tag_bad", "label": "bad", "color": "blue", "concepts": [], "lexemeTargets": []}, "color"),
        ({"id": "tag_bad", "label": "", "color": "#3554B8", "concepts": [], "lexemeTargets": []}, "label"),
        ({"id": "tag_bad", "color": "#3554B8", "concepts": [], "lexemeTargets": []}, "label"),
        ({"id": "tag_bad", "label": "bad", "color": "#3554B8", "concepts": "water", "lexemeTargets": []}, "concepts"),
        ({"id": "tag_bad", "label": "bad", "color": "#3554B8", "concepts": [], "lexemeTargets": ["missing-separator"]}, "lexemeTargets"),
    ],
)
def test_replace_all_rejects_malformed_tags(bad_tag: dict[str, Any], message: str) -> None:
    with pytest.raises(tags_store.TagValidationError, match=message):
        tags_store.replace_all([bad_tag])

    assert tags_store.fetch_all() == {"version": 2, "tags": []}


def test_replace_all_rejects_duplicate_ids() -> None:
    with pytest.raises(tags_store.TagValidationError, match="duplicate tag id"):
        tags_store.replace_all([_tag("tag_same", "one"), _tag("tag_same", "two")])


@pytest.mark.parametrize("duplicate_label", ["archaic", "ARCHAIC", " Archaic "])
def test_replace_all_rejects_case_insensitive_duplicate_labels(duplicate_label: str) -> None:
    with pytest.raises(tags_store.TagValidationError, match="duplicate label"):
        tags_store.replace_all([_tag("tag_one", "archaic"), _tag("tag_two", duplicate_label)])


@pytest.mark.parametrize("color", ["#3554B8", "#aabbcc"])
def test_replace_all_accepts_six_digit_hex_colors(color: str) -> None:
    tag = _tag(color=color)

    assert tags_store.replace_all([tag])["tags"] == [tag]


@pytest.mark.parametrize("color", ["3554B8", "#3554B", "#3554B88", "#zzzzzz", "blue"])
def test_replace_all_rejects_non_hex_colors(color: str) -> None:
    with pytest.raises(tags_store.TagValidationError, match="color"):
        tags_store.replace_all([_tag(color=color)])


def test_parse_tags_path_env_redirects_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    redirected = tmp_path / "nested" / "custom-tags.json"
    monkeypatch.setenv("PARSE_TAGS_PATH", str(redirected))

    tags_store.replace_all([_tag()])

    assert redirected.exists()
    assert json.loads(redirected.read_text(encoding="utf-8"))["tags"][0]["label"] == "archaic"


def test_v1_file_shape_migrates_attachments_into_tag_concepts_and_drops_created_at(
    isolated_tags_path: pathlib.Path,
) -> None:
    isolated_tags_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_tags_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tags": [
                    {
                        "id": "tag_archaic",
                        "name": "archaic",
                        "color": "#3554B8",
                        "createdAt": "2026-05-01T00:00:00Z",
                    },
                    {
                        "id": "tag_uncertain",
                        "label": "uncertain",
                        "color": "#aabbcc",
                        "createdAt": "2026-05-01T00:00:00Z",
                    },
                ],
                "attachments": {
                    "water": ["tag_archaic", "tag_uncertain"],
                    "fire": ["tag_archaic"],
                    "bad": [123],
                },
            }
        ),
        encoding="utf-8",
    )

    data = tags_store.fetch_all()

    assert data == {
        "version": 2,
        "tags": [
            _tag("tag_archaic", "archaic", "#3554B8", concepts=["water", "fire"]),
            _tag("tag_uncertain", "uncertain", "#aabbcc", concepts=["water"]),
        ],
    }
    assert "createdAt" not in data["tags"][0]


def test_v1_migration_uses_label_fallbacks_and_default_color(isolated_tags_path: pathlib.Path) -> None:
    isolated_tags_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_tags_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tags": [
                    {"id": "tag_name", "name": "from-name"},
                    {"id": "tag_label", "label": "from-label"},
                    {"id": "tag_untitled"},
                ],
                "attachments": {},
            }
        ),
        encoding="utf-8",
    )

    assert tags_store.fetch_all() == {
        "version": 2,
        "tags": [
            _tag("tag_name", "from-name", "#6b7280"),
            _tag("tag_label", "from-label", "#6b7280"),
            _tag("tag_untitled", "Untitled", "#6b7280"),
        ],
    }


def test_load_drops_malformed_v2_entries_with_warnings(
    isolated_tags_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    isolated_tags_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_tags_path.write_text(
        json.dumps(
            {
                "version": 2,
                "tags": [
                    _tag("tag_good", "archaic", concepts=["water"], lexeme_targets=["Saha01::sister"]),
                    _tag("tag_bad_color", "broken", color="not-a-hex"),
                    _tag("", "empty-id", color="#aabbcc"),
                    {"id": "tag_bad_lexeme", "label": "bad lexeme", "color": "#aabbcc", "concepts": [], "lexemeTargets": ["bad"]},
                    "not-a-dict",
                ],
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        data = tags_store.fetch_all()

    assert data == {"version": 2, "tags": [_tag("tag_good", "archaic", concepts=["water"], lexeme_targets=["Saha01::sister"])]}
    assert any("dropped" in record.message.lower() for record in caplog.records)


def test_atomic_write_failure_leaves_original_file_untouched(
    monkeypatch: pytest.MonkeyPatch,
    isolated_tags_path: pathlib.Path,
) -> None:
    original = {"version": 2, "tags": [_tag("tag_original", "original")]}
    tags_store.replace_all(original["tags"])
    original_text = isolated_tags_path.read_text(encoding="utf-8")
    original_replace = tags_store.Path.replace

    def fail_replace(self: pathlib.Path, target: pathlib.Path | str):
        if self.name == "tags.json.tmp" and pathlib.Path(target) == isolated_tags_path:
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(tags_store.Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        tags_store.replace_all([_tag("tag_new", "new", "#aabbcc")])

    assert isolated_tags_path.read_text(encoding="utf-8") == original_text
    assert tags_store.fetch_all() == original
