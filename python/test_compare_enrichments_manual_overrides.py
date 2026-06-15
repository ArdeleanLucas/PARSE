from __future__ import annotations

import io
import json
import pathlib
import sys
from dataclasses import dataclass
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import server  # noqa: E402
from server_routes import jobs  # noqa: E402


@dataclass
class _ConceptSpec:
    concept_id: str
    label: str = ""


class _FakeCognateComputeModule:
    ConceptSpec = _ConceptSpec

    @staticmethod
    def load_contact_language_data(_path: pathlib.Path):  # type: ignore[no-untyped-def]
        return ["ar"], {}, {}

    @staticmethod
    def load_annotations(_annotations_dir: pathlib.Path):  # type: ignore[no-untyped-def]
        return {
            "538": [
                SimpleNamespace(speaker="Mand01"),
                SimpleNamespace(speaker="Qasr01"),
                SimpleNamespace(speaker="Saha01"),
            ]
        }, {"Mand01", "Qasr01", "Saha01"}

    @staticmethod
    def _compute_cognate_sets_with_lingpy(_forms, _concepts, _threshold, skipped_out=None):  # type: ignore[no-untyped-def]
        return {"538": {"AUTO": ["Mand01", "Qasr01", "Saha01"]}}

    @staticmethod
    def compute_similarity_scores(**_kwargs):  # type: ignore[no-untyped-def]
        return {"538": {"Mand01": {"Qasr01": {"score": 0.75, "has_reference_data": True}}}}


class _FakeWfile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def payload(self) -> dict[str, Any]:
        raw = b"".join(self.chunks).decode("utf-8")
        body = raw.split("\r\n\r\n", 1)[-1]
        return json.loads(body)


class _Handler(server.RangeRequestHandler):
    def __init__(self, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.path = "/api/enrichments"
        self.rfile = io.BytesIO(encoded)
        self.wfile = _FakeWfile()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(encoded))}
        self.status: int | None = None
        self.sent_headers: dict[str, str] = {}

    def send_response(self, code):  # type: ignore[no-untyped-def]
        self.status = code

    def send_header(self, key, value):  # type: ignore[no-untyped-def]
        self.sent_headers[str(key)] = str(value)

    def end_headers(self) -> None:
        pass


def _manual_overrides() -> dict[str, Any]:
    return {
        "cognate_sets": {"538": {"A": ["Mand01", "Qasr01"], "B": ["Saha01"]}},
        "speaker_flags": {"538": {"Mand01": {"excluded": True}}},
        "canonical_lexemes": {"538": {"Mand01": {"csv_row_id": "538", "source": "manual"}}},
        "borrowing_flags": {"538": {"Saha01": "confirmed"}},
        "discarded_forms": {"538": {"Qasr01": {"discarded": True}}},
        "lexeme_notes": {"Mand01": {"538": {"user_note": "checked"}}},
    }


def _seed_enrichments(root: pathlib.Path, payload: dict[str, Any]) -> None:
    (root / "parse-enrichments.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_enrichments(root: pathlib.Path) -> dict[str, Any]:
    return json.loads((root / "parse-enrichments.json").read_text(encoding="utf-8"))


def _install_compute_fakes(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "annotations").mkdir()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(server, "cognate_compute_module", _FakeCognateComputeModule)
    monkeypatch.setattr(server, "_utc_now_iso", lambda: "2026-06-15T00:00:00Z")
    monkeypatch.setattr(server, "_set_job_progress", lambda *args, **kwargs: None)
    server._install_route_bindings()


@pytest.mark.parametrize("compute_type", ["cognates", "similarity"])
def test_compute_job_preserves_manual_overrides_and_unrelated_enrichment_keys(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, compute_type: str
) -> None:
    _install_compute_fakes(tmp_path, monkeypatch)
    manual_overrides = _manual_overrides()
    existing = {
        "computed_at": "old",
        "config": {"old": True},
        "cognate_sets": {"538": {"OLD_AUTO": ["Mand01"]}},
        "similarity": {"old": {"score": 0.1}},
        "borrowing_flags": {"538": {"Mand01": "top-level-review"}},
        "concept_notes": {"538": {"note": "preserve me"}},
        "lexeme_notes": {"Qasr01": {"538": {"user_note": "top-level note"}}},
        "manual_overrides": manual_overrides,
    }
    _seed_enrichments(tmp_path, existing)
    completions: list[dict[str, Any]] = []
    errors: list[str] = []
    monkeypatch.setattr(server, "_set_job_complete", lambda _job_id, result, **_kwargs: completions.append(result))
    monkeypatch.setattr(server, "_set_job_error", lambda _job_id, error, **_kwargs: errors.append(str(error)))

    jobs._run_compute_job("job-1", compute_type, {"threshold": 0.7})

    assert errors == []
    assert completions and completions[0]["type"] == "cognates"
    written = _read_enrichments(tmp_path)
    assert written["manual_overrides"] == manual_overrides
    assert written["borrowing_flags"] == existing["borrowing_flags"]
    assert written["concept_notes"] == existing["concept_notes"]
    assert written["lexeme_notes"] == existing["lexeme_notes"]
    assert written["cognate_sets"] == {"538": {"AUTO": ["Mand01", "Qasr01", "Saha01"]}}
    assert written["similarity"] == {"538": {"Mand01": {"Qasr01": {"score": 0.75, "has_reference_data": True}}}}
    assert written["computed_at"] == "2026-06-15T00:00:00Z"
    assert written["config"]["lexstat_threshold"] == 0.7


def test_compute_cognates_without_existing_enrichments_defaults_manual_overrides_to_empty(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_compute_fakes(tmp_path, monkeypatch)

    server._compute_cognates("job-1", {"threshold": 0.6})

    written = _read_enrichments(tmp_path)
    assert written["manual_overrides"] == {}
    assert written["cognate_sets"] == {"538": {"AUTO": ["Mand01", "Qasr01", "Saha01"]}}


@pytest.mark.parametrize("incoming_enrichments", [{"cognate_sets": {"538": {"AUTO": ["Mand01"]}}}, {"manual_overrides": {}}])
def test_post_enrichments_preserves_non_empty_disk_manual_overrides_when_client_omits_them(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, incoming_enrichments: dict[str, Any]
) -> None:
    manual_overrides = _manual_overrides()
    _seed_enrichments(
        tmp_path,
        {
            "manual_overrides": manual_overrides,
            "concept_notes": {"538": {"note": "existing server note"}},
            "cognate_sets": {"538": {"OLD_AUTO": ["Qasr01"]}},
        },
    )
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    handler = _Handler({"enrichments": incoming_enrichments})

    handler._api_post_enrichments()

    assert handler.status == HTTPStatus.OK
    assert handler.wfile.payload() == {"success": True}
    written = _read_enrichments(tmp_path)
    assert written["manual_overrides"] == manual_overrides


def test_post_enrichments_persists_emptied_cognate_group_from_full_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The frontend emits every existing group (an empty list for an emptied
    # group) so the deep-merge replaces membership rather than re-adding it.
    # Lock that contract: a non-empty incoming manual_overrides that empties
    # group B must leave B == [] on disk, not re-populate it from the prior
    # decision. (Guards against a future "prune empty groups" change silently
    # reintroducing the deletion-suppression bug.)
    _seed_enrichments(
        tmp_path,
        {"manual_overrides": {"cognate_sets": {"538": {"A": ["Mand01", "Qasr01"], "B": ["Saha01"]}}}},
    )
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    server._install_route_bindings()
    incoming = {"manual_overrides": {"cognate_sets": {"538": {"A": ["Mand01", "Qasr01", "Saha01"], "B": []}}}}
    handler = _Handler({"enrichments": incoming})

    handler._api_post_enrichments()

    assert handler.status == HTTPStatus.OK
    written = _read_enrichments(tmp_path)
    assert written["manual_overrides"]["cognate_sets"]["538"] == {"A": ["Mand01", "Qasr01", "Saha01"], "B": []}
