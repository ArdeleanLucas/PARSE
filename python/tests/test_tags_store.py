from __future__ import annotations

import json
import pathlib
import sys

import pytest

PYTHON_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from storage import tags_store


@pytest.fixture(autouse=True)
def isolated_tags_path(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "tags.json"
    monkeypatch.setenv("PARSE_TAGS_PATH", str(path))
    return path


def test_create_tag_round_trips_through_fetch_all(isolated_tags_path: pathlib.Path) -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")

    data = tags_store.fetch_all()

    assert data == {
        "version": 1,
        "tags": [tag],
        "attachments": {},
    }
    assert tag["id"].startswith("tag_")
    assert tag["name"] == "archaic"
    assert tag["color"] == "#3554B8"
    assert tag["createdAt"].endswith("Z")
    assert json.loads(isolated_tags_path.read_text(encoding="utf-8")) == data


def test_create_tag_rejects_case_insensitive_name_conflicts() -> None:
    tags_store.create_tag("archaic", "#3554B8")

    with pytest.raises(ValueError, match="already exists"):
        tags_store.create_tag("ARCHAIC", "#aabbcc")

    assert [tag["name"] for tag in tags_store.fetch_all()["tags"]] == ["archaic"]


@pytest.mark.parametrize("color", ["#3554B8", "#aabbcc"])
def test_create_tag_accepts_six_digit_hex_colors(color: str) -> None:
    tag = tags_store.create_tag(f"tag-{color[-2:]}", color)

    assert tag["color"] == color


@pytest.mark.parametrize("color", ["3554B8", "#3554B", "#3554B88", "#zzzzzz", "blue"])
def test_create_tag_rejects_non_hex_colors(color: str) -> None:
    with pytest.raises(ValueError, match="color"):
        tags_store.create_tag("archaic", color)


def test_delete_tag_cascades_attachments_and_prunes_empty_concepts() -> None:
    archaic = tags_store.create_tag("archaic", "#3554B8")
    uncertain = tags_store.create_tag("uncertain", "#aabbcc")
    tags_store.attach("concept_a", archaic["id"])
    tags_store.attach("concept_a", uncertain["id"])
    tags_store.attach("concept_b", archaic["id"])

    tags_store.delete_tag(archaic["id"])

    assert tags_store.fetch_all() == {
        "version": 1,
        "tags": [uncertain],
        "attachments": {"concept_a": [uncertain["id"]]},
    }


def test_delete_tag_is_idempotent_for_unknown_id() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")
    tags_store.attach("concept_a", tag["id"])

    tags_store.delete_tag("tag_does_not_exist")

    assert tags_store.fetch_all() == {
        "version": 1,
        "tags": [tag],
        "attachments": {"concept_a": [tag["id"]]},
    }


def test_attach_is_idempotent() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")

    tags_store.attach("concept_a", tag["id"])
    tags_store.attach("concept_a", tag["id"])

    assert tags_store.fetch_all()["attachments"] == {"concept_a": [tag["id"]]}


def test_detach_is_idempotent_and_prunes_empty_concepts() -> None:
    tag = tags_store.create_tag("archaic", "#3554B8")
    tags_store.attach("concept_a", tag["id"])

    tags_store.detach("concept_a", tag["id"])
    tags_store.detach("concept_a", tag["id"])
    tags_store.detach("missing_concept", tag["id"])

    assert tags_store.fetch_all()["attachments"] == {}


def test_parse_tags_path_env_redirects_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    redirected = tmp_path / "nested" / "custom-tags.json"
    monkeypatch.setenv("PARSE_TAGS_PATH", str(redirected))

    tags_store.create_tag("archaic", "#3554B8")

    assert redirected.exists()
    assert json.loads(redirected.read_text(encoding="utf-8"))["tags"][0]["name"] == "archaic"


def test_atomic_write_failure_leaves_original_file_untouched(
    monkeypatch: pytest.MonkeyPatch,
    isolated_tags_path: pathlib.Path,
) -> None:
    original_tag = tags_store.create_tag("original", "#3554B8")
    original_text = isolated_tags_path.read_text(encoding="utf-8")
    original_replace = tags_store.Path.replace

    def fail_replace(self: pathlib.Path, target: pathlib.Path | str):
        if self.name == "tags.json.tmp" and pathlib.Path(target) == isolated_tags_path:
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(tags_store.Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        tags_store.create_tag("new", "#aabbcc")

    assert isolated_tags_path.read_text(encoding="utf-8") == original_text
    assert tags_store.fetch_all()["tags"] == [original_tag]


def test_load_drops_malformed_entries_with_warnings(
    isolated_tags_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    isolated_tags_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_tags_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tags": [
                    {
                        "id": "tag_good",
                        "name": "archaic",
                        "color": "#3554B8",
                        "createdAt": "2026-05-01T00:00:00Z",
                    },
                    {
                        "id": "tag_bad_color",
                        "name": "broken",
                        "color": "not-a-hex",
                        "createdAt": "2026-05-01T00:00:00Z",
                    },
                    {"id": "", "name": "empty-id", "color": "#aabbcc", "createdAt": "2026-05-01T00:00:00Z"},
                    "not-a-dict",
                ],
                "attachments": {
                    "concept_a": ["tag_good", "tag_bad_color", "tag_does_not_exist"],
                    "": ["tag_good"],
                },
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        data = tags_store.fetch_all()

    assert [t["id"] for t in data["tags"]] == ["tag_good"]
    assert data["attachments"] == {"concept_a": ["tag_good"]}
    assert any("dropped" in record.message.lower() for record in caplog.records)
