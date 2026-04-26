import json
import pathlib
import sys
from datetime import datetime, timezone
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from app.http.clef_http_handlers import (
    ClefHttpHandlerError,
    build_get_clef_catalog_response,
    build_get_clef_config_response,
    build_get_clef_providers_response,
    build_get_clef_sources_report_response,
    build_get_contact_lexeme_coverage_response,
    build_post_clef_config_response,
    build_post_clef_form_selections_response,
)
from compare.providers.provenance import iter_forms_with_sources


def test_build_get_contact_lexeme_coverage_response_reports_totals_filled_and_empty(tmp_path: pathlib.Path) -> None:
    (tmp_path / "concepts.csv").write_text(
        "concept_en\nwater\nfire\nearth\n",
        encoding="utf-8",
    )

    response = build_get_contact_lexeme_coverage_response(
        config_path=tmp_path / "config" / "sil_contact_languages.json",
        project_root=tmp_path,
        load_sil_config_safe=lambda path: {
            "_meta": {"primary_contact_languages": ["ar"]},
            "ar": {
                "name": "Arabic",
                "concepts": {
                    "water": ["ماء"],
                    "fire": [],
                    "earth": [{"form": "turab", "sources": ["wikidata"]}],
                },
            },
            "broken": {"concepts": {"water": ["x"]}},
            "fa": "not-a-dict",
        },
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "languages": {
            "ar": {
                "name": "Arabic",
                "total": 3,
                "filled": 2,
                "empty": 1,
                "concepts": {
                    "water": ["ماء"],
                    "earth": [{"form": "turab", "sources": ["wikidata"]}],
                },
            }
        }
    }


def test_build_get_clef_config_response_reports_configured_and_sorts_languages(tmp_path: pathlib.Path) -> None:
    (tmp_path / "concepts.csv").write_text("concept_en\nwater\n", encoding="utf-8")
    config_path = tmp_path / "config" / "sil_contact_languages.json"

    response = build_get_clef_config_response(
        config_path=config_path,
        project_root=tmp_path,
        load_sil_config_safe=lambda path: {
            "_meta": {
                "primary_contact_languages": [" AR ", "", 7, "fa"],
                "configured_at": "2026-04-26T12:00:00Z",
            },
            "fa": {
                "name": "Persian",
                "family": "Iranian",
                "script": "Arab",
                "concepts": {"water": ["آو"]},
            },
            "ar": {
                "name": "Arabic",
                "concepts": {"water": ["ماء"], "fire": []},
            },
        },
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "configured": True,
        "primary_contact_languages": ["ar", "fa"],
        "languages": [
            {
                "code": "ar",
                "name": "Arabic",
                "family": None,
                "script": None,
                "filled": 1,
                "total": 2,
            },
            {
                "code": "fa",
                "name": "Persian",
                "family": "Iranian",
                "script": "Arab",
                "filled": 1,
                "total": 1,
            },
        ],
        "config_path": str(config_path),
        "concepts_csv_exists": True,
        "meta": {
            "primary_contact_languages": [" AR ", "", 7, "fa"],
            "configured_at": "2026-04-26T12:00:00Z",
        },
    }


def test_build_get_clef_config_response_handles_unconfigured_workspace(tmp_path: pathlib.Path) -> None:
    response = build_get_clef_config_response(
        config_path=tmp_path / "config" / "sil_contact_languages.json",
        project_root=tmp_path,
        load_sil_config_safe=lambda path: {},
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["configured"] is False
    assert response.payload["primary_contact_languages"] == []
    assert response.payload["languages"] == []
    assert response.payload["concepts_csv_exists"] is False
    assert response.payload["meta"] == {}


def test_build_post_clef_config_response_preserves_existing_concepts_and_form_selections(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / "config" / "sil_contact_languages.json"
    captured = {}

    response = build_post_clef_config_response(
        {
            "primary_contact_languages": [" FA ", "AR"],
            "languages": [
                {"code": "ar", "name": "Arabic", "family": "Semitic", "script": "Arab"},
                {"code": "fa", "name": "Persian"},
                {"code": "_meta", "name": "skip me"},
                "bad-item",
            ],
        },
        config_path=config_path,
        load_sil_config_safe=lambda path: {
            "ar": {
                "name": "Arabic",
                "concepts": {"water": ["ماء"]},
            },
            "fa": {
                "name": "Old Persian",
                "concepts": {"fire": ["آتَش"]},
            },
            "_meta": {
                "form_selections": {"water": {"ar": ["ماء"]}},
            },
        },
        write_sil_config=lambda path, data: captured.update({"path": path, "data": data}),
        now_factory=lambda: datetime(2026, 4, 26, 13, 14, 15, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "success": True,
        "config_path": str(config_path),
        "primary_contact_languages": ["fa", "ar"],
        "language_count": 2,
    }
    assert captured["path"] == config_path
    assert captured["data"]["ar"] == {
        "name": "Arabic",
        "family": "Semitic",
        "script": "Arab",
        "concepts": {"water": ["ماء"]},
    }
    assert captured["data"]["fa"] == {
        "name": "Persian",
        "concepts": {"fire": ["آتَش"]},
    }
    assert captured["data"]["_meta"] == {
        "primary_contact_languages": ["fa", "ar"],
        "configured_at": "2026-04-26T13:14:15Z",
        "schema_version": 1,
        "form_selections": {"water": {"ar": ["ماء"]}},
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"primary_contact_languages": "ar", "languages": []}, "primary_contact_languages must be a list"),
        ({"primary_contact_languages": ["ar", "fa", "tr"], "languages": []}, "Pick at most 2 primary contact languages"),
        ({"primary_contact_languages": [], "languages": "bad"}, "languages must be a list"),
    ],
)
def test_build_post_clef_config_response_validates_payload(body, message: str, tmp_path: pathlib.Path) -> None:
    with pytest.raises(ClefHttpHandlerError) as exc_info:
        build_post_clef_config_response(
            body,
            config_path=tmp_path / "config" / "sil_contact_languages.json",
            load_sil_config_safe=lambda path: {},
            write_sil_config=lambda path, data: None,
            now_factory=lambda: datetime.now(timezone.utc),
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == message


def test_build_post_clef_form_selections_response_normalizes_deduplicates_and_persists(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / "config" / "sil_contact_languages.json"
    captured = {}

    response = build_post_clef_form_selections_response(
        {
            "concept_en": " Water ",
            "lang_code": " AR ",
            "forms": [" ماء ", "maːʔ", "ماء", "", 4],
        },
        config_path=config_path,
        load_sil_config_safe=lambda path: {
            "ar": {"name": "Arabic", "concepts": {"water": ["ماء"]}},
            "_meta": {"form_selections": {"fire": {"ar": ["نار"]}}},
        },
        write_sil_config=lambda path, data: captured.update({"path": path, "data": data}),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "success": True,
        "concept_en": "Water",
        "lang_code": "ar",
        "forms": ["ماء", "maːʔ"],
    }
    assert captured["path"] == config_path
    assert captured["data"]["ar"] == {"name": "Arabic", "concepts": {"water": ["ماء"]}}
    assert captured["data"]["_meta"] == {
        "form_selections": {
            "fire": {"ar": ["نار"]},
            "Water": {"ar": ["ماء", "maːʔ"]},
        }
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"concept_en": "", "lang_code": "ar", "forms": []}, "concept_en must be a non-empty string"),
        ({"concept_en": "water", "lang_code": "_meta", "forms": []}, "lang_code must not start with '_'"),
        ({"concept_en": "water", "lang_code": "ar", "forms": "bad"}, "forms must be a list of strings"),
    ],
)
def test_build_post_clef_form_selections_response_validates_payload(body, message: str, tmp_path: pathlib.Path) -> None:
    with pytest.raises(ClefHttpHandlerError) as exc_info:
        build_post_clef_form_selections_response(
            body,
            config_path=tmp_path / "config" / "sil_contact_languages.json",
            load_sil_config_safe=lambda path: {},
            write_sil_config=lambda path, data: None,
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == message


def test_build_get_clef_catalog_response_merges_workspace_extras_and_sorts_by_name(tmp_path: pathlib.Path) -> None:
    extras_path = tmp_path / "config" / "sil_catalog_extra.json"
    extras_path.parent.mkdir(parents=True, exist_ok=True)
    extras_path.write_text(
        json.dumps(
            {
                "languages": [
                    {"code": "spa", "name": "Spanish (Custom)", "family": "Romance", "script": "Latn"},
                    {"code": "ckb", "name": "Central Kurdish", "family": "Iranian"},
                ]
            }
        ),
        encoding="utf-8",
    )

    response = build_get_clef_catalog_response(
        project_root=tmp_path,
        sil_catalog=[
            {"code": "eng", "name": "English", "family": "Germanic", "script": "Latn"},
            {"code": "spa", "name": "Spanish", "family": "Romance"},
        ],
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "languages": [
            {"code": "ckb", "name": "Central Kurdish", "family": "Iranian"},
            {"code": "eng", "name": "English", "family": "Germanic", "script": "Latn"},
            {"code": "spa", "name": "Spanish (Custom)", "family": "Romance", "script": "Latn"},
        ]
    }


def test_build_get_clef_providers_response_preserves_priority_order() -> None:
    response = build_get_clef_providers_response(provider_priority=["csv_override", "wikidata", "literature"])

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "providers": [
            {"id": "csv_override", "name": "csv_override"},
            {"id": "wikidata", "name": "wikidata"},
            {"id": "literature", "name": "literature"},
        ]
    }


def test_build_get_clef_sources_report_response_aggregates_legacy_and_provenance_forms(tmp_path: pathlib.Path) -> None:
    (tmp_path / "concepts.csv").write_text(
        "concept_en\nwater\nfire\nearth\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config" / "sil_contact_languages.json"

    response = build_get_clef_sources_report_response(
        config_path=config_path,
        project_root=tmp_path,
        load_sil_config_safe=lambda path: {
            "ar": {
                "name": "Arabic",
                "family": "Semitic",
                "script": "Arab",
                "concepts": {
                    "water": ["ma:ʔ"],
                    "fire": [{"form": "na:r", "sources": ["wikidata", "wiktionary"]}],
                    "earth": [],
                },
            }
        },
        iter_forms_with_sources=iter_forms_with_sources,
        get_citations=lambda: {
            "unknown": {"title": "Unknown"},
            "wikidata": {"title": "Wikidata"},
            "wiktionary": {"title": "Wiktionary"},
        },
        citation_display_order=("wikidata", "wiktionary", "unknown"),
        now_factory=lambda: datetime(2026, 4, 26, 14, 15, 16, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload == {
        "generated_at": "2026-04-26T14:15:16Z",
        "providers": [
            {"id": "unknown", "total_forms": 1},
            {"id": "wikidata", "total_forms": 1},
            {"id": "wiktionary", "total_forms": 1},
        ],
        "languages": [
            {
                "code": "ar",
                "name": "Arabic",
                "family": "Semitic",
                "script": "Arab",
                "total_forms": 2,
                "concepts_covered": 2,
                "concepts_total": 3,
                "per_provider": {"unknown": 1, "wikidata": 1, "wiktionary": 1},
                "forms": [
                    {"concept_en": "fire", "form": "na:r", "sources": ["wikidata", "wiktionary"]},
                    {"concept_en": "water", "form": "ma:ʔ", "sources": ["unknown"]},
                ],
            }
        ],
        "concepts_total": 3,
        "citations": {
            "unknown": {"title": "Unknown"},
            "wikidata": {"title": "Wikidata"},
            "wiktionary": {"title": "Wiktionary"},
        },
        "citation_order": ["wikidata", "wiktionary", "unknown"],
    }
