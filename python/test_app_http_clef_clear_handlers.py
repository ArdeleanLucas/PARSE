import json
import pathlib
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server
from app.http.clef_http_handlers import (
    ClefHttpHandlerError,
    build_post_clef_clear_response,
)


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body=None):
        self._body = {} if body is None else body
        self.sent_json = []

    def _read_json_body(self, required: bool = True):
        return self._body

    def _expect_object(self, value, label: str):
        return value

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


class _DummyClefHttpHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def _config_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "config" / "sil_contact_languages.json"



def _seed_config(tmp_path: pathlib.Path, payload: dict) -> pathlib.Path:
    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path



def _read_config(config_path: pathlib.Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))



def _sample_clef_payload() -> dict:
    return {
        "_meta": {
            "primary_contact_languages": ["ar", "fa"],
            "form_selections": {
                "water": {"ar": ["maːʔ"], "fa": ["ɒːb"]},
                "fire": {"ar": ["naːr"]},
            },
        },
        "ar": {
            "name": "Arabic",
            "concepts": {
                "water": [
                    {"form": "maːʔ", "sources": ["wiktionary", "wikidata"]},
                    {"form": "mijeh", "sources": ["literature"]},
                ],
                "fire": ["naːr"],
            },
        },
        "fa": {
            "name": "Persian",
            "concepts": {
                "water": [
                    {"form": "ɒːb", "sources": ["wiktionary"]},
                ],
            },
        },
    }



def test_build_post_clef_clear_response_dry_run_summarizes_without_mutating(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(tmp_path, _sample_clef_payload())
    before = config_path.read_text(encoding="utf-8")

    response = build_post_clef_clear_response(
        {"dryRun": True},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 45, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["ok"] is True
    assert response.payload["dryRun"] is True
    assert response.payload["summary"] == {
        "languagesAffected": 2,
        "conceptsAffected": 2,
        "formsRemoved": 4,
        "providersTouched": ["literature", "unknown", "wikidata", "wiktionary"],
        "cacheFilesRemoved": 0,
    }
    assert response.payload["warnings"] == []
    assert config_path.read_text(encoding="utf-8") == before
    assert list(config_path.parent.glob("sil_contact_languages.json.*.bak")) == []



def test_build_post_clef_clear_response_clears_all_forms_and_stale_selections_with_backup(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(tmp_path, _sample_clef_payload())

    response = build_post_clef_clear_response(
        {"dryRun": False},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 46, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["ok"] is True
    assert response.payload["dryRun"] is False
    assert response.payload["summary"]["languagesAffected"] == 2
    assert response.payload["summary"]["conceptsAffected"] == 2
    assert response.payload["summary"]["formsRemoved"] == 4

    written = _read_config(config_path)
    assert written["ar"]["concepts"] == {}
    assert written["fa"]["concepts"] == {}
    assert written["_meta"] == {"primary_contact_languages": ["ar", "fa"]}

    backups = list(config_path.parent.glob("sil_contact_languages.json.*.bak"))
    assert len(backups) == 1
    backup_payload = json.loads(backups[0].read_text(encoding="utf-8"))
    assert backup_payload["ar"]["concepts"]["water"][0]["form"] == "maːʔ"
    assert backup_payload["_meta"]["form_selections"]["water"]["ar"] == ["maːʔ"]



def test_build_post_clef_clear_response_language_scope_preserves_other_languages(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(tmp_path, _sample_clef_payload())

    response = build_post_clef_clear_response(
        {"languages": ["ar"]},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 47, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"] == {
        "languagesAffected": 1,
        "conceptsAffected": 2,
        "formsRemoved": 3,
        "providersTouched": ["literature", "unknown", "wikidata", "wiktionary"],
        "cacheFilesRemoved": 0,
    }

    written = _read_config(config_path)
    assert written["ar"]["concepts"] == {}
    assert written["fa"]["concepts"]["water"][0]["form"] == "ɒːb"
    assert written["_meta"]["form_selections"] == {"water": {"fa": ["ɒːb"]}}



def test_build_post_clef_clear_response_concept_scope_preserves_other_concepts(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(tmp_path, _sample_clef_payload())

    response = build_post_clef_clear_response(
        {"concepts": ["water"]},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 48, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"] == {
        "languagesAffected": 2,
        "conceptsAffected": 1,
        "formsRemoved": 3,
        "providersTouched": ["literature", "wikidata", "wiktionary"],
        "cacheFilesRemoved": 0,
    }

    written = _read_config(config_path)
    assert written["ar"]["concepts"] == {"fire": ["naːr"]}
    assert written["fa"]["concepts"] == {}
    assert written["_meta"]["form_selections"] == {"fire": {"ar": ["naːr"]}}



def test_build_post_clef_clear_response_clear_cache_removes_only_known_cache_entries(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(tmp_path, _sample_clef_payload())
    cache_dir = config_path.parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "wiktionary_ar.json").write_text("{}", encoding="utf-8")
    (cache_dir / "asjp_fa.json").write_text("{}", encoding="utf-8")
    (cache_dir / "keep-me.txt").write_text("untouched", encoding="utf-8")
    cldf_dir = cache_dir / "cldf_wold"
    cldf_dir.mkdir()
    (cldf_dir / "forms.csv").write_text("id,form\n1,maːʔ\n", encoding="utf-8")

    response = build_post_clef_clear_response(
        {"clearCache": True},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 49, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"]["cacheFilesRemoved"] == 3
    assert not (cache_dir / "wiktionary_ar.json").exists()
    assert not (cache_dir / "asjp_fa.json").exists()
    assert not cldf_dir.exists()
    assert (cache_dir / "keep-me.txt").exists()



def test_build_post_clef_clear_response_warns_when_no_clef_forms_are_present(tmp_path: pathlib.Path) -> None:
    config_path = _seed_config(
        tmp_path,
        {
            "_meta": {"primary_contact_languages": ["ar"]},
            "ar": {"name": "Arabic", "concepts": {}},
        },
    )

    response = build_post_clef_clear_response(
        {"dryRun": True},
        config_path=config_path,
        now_factory=lambda: datetime(2026, 4, 28, 20, 50, tzinfo=timezone.utc),
    )

    assert response.status == HTTPStatus.OK
    assert response.payload["summary"] == {
        "languagesAffected": 0,
        "conceptsAffected": 0,
        "formsRemoved": 0,
        "providersTouched": [],
        "cacheFilesRemoved": 0,
    }
    assert response.payload["warnings"] == [
        "No CLEF reference forms found in config/sil_contact_languages.json for the requested scope."
    ]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"dryRun": "true"}, "dryRun must be a boolean"),
        ({"languages": "ar"}, "languages must be null or a list of strings"),
        ({"languages": ["ar", 7]}, "languages must be null or a list of strings"),
        ({"concepts": "water"}, "concepts must be null or a list of strings"),
        ({"concepts": ["water", 9]}, "concepts must be null or a list of strings"),
        ({"clearCache": 1}, "clearCache must be a boolean"),
    ],
)
def test_build_post_clef_clear_response_validates_payload(body: dict, message: str, tmp_path: pathlib.Path) -> None:
    with pytest.raises(ClefHttpHandlerError) as exc_info:
        build_post_clef_clear_response(
            body,
            config_path=_config_path(tmp_path),
            now_factory=lambda: datetime.now(timezone.utc),
        )

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == message



def test_api_post_clef_clear_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"dryRun": True})
    observed = {}

    def fake_builder(body, **kwargs):
        observed["body"] = body
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"ok": True, "dryRun": True})

    monkeypatch.setattr(server, "_app_build_post_clef_clear_response", fake_builder, raising=False)

    handler._api_post_clef_clear()

    assert handler.sent_json == [(HTTPStatus.OK, {"ok": True, "dryRun": True})]
    assert observed["body"] == {"dryRun": True}
    assert observed["config_path"] == server._sil_config_path()
    assert callable(observed["now_factory"])



def test_api_post_clef_clear_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"dryRun": True})

    def fake_builder(body, **kwargs):
        del body, kwargs
        raise _DummyClefHttpHandlerError(HTTPStatus.BAD_REQUEST, "bad clear request")

    monkeypatch.setattr(server, "_app_ClefHttpHandlerError", _DummyClefHttpHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_clef_clear_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_clef_clear()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "bad clear request"
