import json
import os
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server
from app.http.project_artifact_handlers import (
    BinaryResponseSpec,
    ProjectArtifactHandlerError,
    build_get_export_lingpy_response,
    build_get_export_nexus_response,
    build_get_tags_response,
    build_post_tags_merge_response,
)


def test_build_get_tags_response_returns_empty_list_when_file_missing(tmp_path: pathlib.Path) -> None:
    response = build_get_tags_response(project_root=tmp_path)

    assert response.status == HTTPStatus.OK
    assert response.payload == {"tags": []}


def test_build_get_tags_response_returns_empty_list_for_non_list_payload(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parse-tags.json").write_text(json.dumps({"id": "bad"}), encoding="utf-8")

    response = build_get_tags_response(project_root=tmp_path)

    assert response.status == HTTPStatus.OK
    assert response.payload == {"tags": []}


def test_build_get_tags_response_raises_500_for_malformed_json(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parse-tags.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ProjectArtifactHandlerError) as exc_info:
        build_get_tags_response(project_root=tmp_path)

    assert exc_info.value.status == HTTPStatus.INTERNAL_SERVER_ERROR


def test_build_post_tags_merge_response_additively_merges_existing_tags(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parse-tags.json").write_text(
        json.dumps(
            [
                {
                    "id": "review-needed",
                    "label": "Review needed",
                    "color": "#f59e0b",
                    "concepts": ["1"],
                }
            ]
        ),
        encoding="utf-8",
    )

    response = build_post_tags_merge_response(
        {
            "tags": [
                {
                    "id": "review-needed",
                    "label": "Review needed",
                    "concepts": ["2"],
                },
                {
                    "id": "confirmed",
                    "label": "Confirmed",
                    "color": "#10b981",
                    "concepts": ["3", "3"],
                },
            ]
        },
        project_root=tmp_path,
    )

    payload = json.loads((tmp_path / "parse-tags.json").read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in payload}

    assert response.status == HTTPStatus.OK
    assert response.payload == {"ok": True, "tagCount": 2}
    assert set(by_id["review-needed"]["concepts"]) == {"1", "2"}
    assert by_id["review-needed"]["color"] == "#f59e0b"
    assert by_id["confirmed"]["color"] == "#10b981"
    assert by_id["confirmed"]["concepts"] == ["3"]


def test_build_post_tags_merge_response_requires_tags_array(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ProjectArtifactHandlerError) as exc_info:
        build_post_tags_merge_response({"tags": "not-a-list"}, project_root=tmp_path)

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "tags must be an array"


def test_build_get_export_lingpy_response_preserves_headers_and_cleans_up_tempfile(tmp_path: pathlib.Path) -> None:
    removed: list[str] = []
    temp_path = tmp_path / "export.tsv"
    temp_path.write_text("", encoding="utf-8")

    def fake_mkstemp(*, suffix: str):
        assert suffix == ".tsv"
        fd = os.open(temp_path, os.O_RDWR)
        return fd, str(temp_path)

    def fake_export_wordlist_tsv(enrichments_path: pathlib.Path, annotations_dir: pathlib.Path, out_path: pathlib.Path) -> None:
        assert enrichments_path == tmp_path / "parse-enrichments.json"
        assert annotations_dir == tmp_path / "annotations"
        out_path.write_text("COGID\tDOCULECT\n1\tFail01\n", encoding="utf-8")

    def fake_unlink(path: str) -> None:
        removed.append(path)
        os.unlink(path)

    response = build_get_export_lingpy_response(
        export_wordlist_tsv=fake_export_wordlist_tsv,
        enrichments_path=tmp_path / "parse-enrichments.json",
        annotations_dir=tmp_path / "annotations",
        mkstemp=fake_mkstemp,
        close_fd=os.close,
        unlink=fake_unlink,
    )

    assert isinstance(response, BinaryResponseSpec)
    assert response.status == HTTPStatus.OK
    assert response.content_type == "text/tab-separated-values; charset=utf-8"
    assert response.content_disposition == 'attachment; filename="parse-wordlist.tsv"'
    assert response.body == b"COGID\tDOCULECT\n1\tFail01\n"
    assert removed == [str(temp_path)]
    assert not temp_path.exists()


def test_build_get_export_lingpy_response_cleans_up_tempfile_on_export_failure(tmp_path: pathlib.Path) -> None:
    removed: list[str] = []
    temp_path = tmp_path / "failed-export.tsv"
    temp_path.write_text("", encoding="utf-8")

    def fake_mkstemp(*, suffix: str):
        fd = os.open(temp_path, os.O_RDWR)
        return fd, str(temp_path)

    def fake_export_wordlist_tsv(enrichments_path: pathlib.Path, annotations_dir: pathlib.Path, out_path: pathlib.Path) -> None:
        raise RuntimeError("export failed")

    def fake_unlink(path: str) -> None:
        removed.append(path)
        os.unlink(path)

    with pytest.raises(RuntimeError, match="export failed"):
        build_get_export_lingpy_response(
            export_wordlist_tsv=fake_export_wordlist_tsv,
            enrichments_path=tmp_path / "parse-enrichments.json",
            annotations_dir=tmp_path / "annotations",
            mkstemp=fake_mkstemp,
            close_fd=os.close,
            unlink=fake_unlink,
        )

    assert removed == [str(temp_path)]
    assert not temp_path.exists()


def test_build_get_export_nexus_response_preserves_override_precedence_and_matrix_semantics(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parse-enrichments.json").write_text(
        json.dumps(
            {
                "cognate_sets": {
                    "1": {"A": ["Fail01"], "B": ["Fail02"]},
                },
                "manual_overrides": {
                    "cognate_sets": {
                        "1": {"A": ["Fail01", "Fail02"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "project.json").write_text(
        json.dumps({"speakers": {"Fail01": {}, "Fail02": {}, "Kalh01": {}}}),
        encoding="utf-8",
    )

    response = build_get_export_nexus_response(
        enrichments_path=tmp_path / "parse-enrichments.json",
        project_json_path=tmp_path / "project.json",
        read_json_file=server._read_json_file,
        default_enrichments_payload=server._default_enrichments_payload,
        concept_sort_key=server._concept_sort_key,
    )

    text = response.body.decode("utf-8")
    assert response.status == HTTPStatus.OK
    assert response.content_type == "text/plain; charset=utf-8"
    assert response.content_disposition == 'attachment; filename="parse-cognates.nex"'
    assert "#NEXUS" in text
    assert "DIMENSIONS NTAX=3;" in text
    assert "DIMENSIONS NCHAR=1;" in text
    assert "1 1_A" in text
    assert "Fail01    1" in text
    assert "Fail02    1" in text
    assert "Kalh01    ?" in text
