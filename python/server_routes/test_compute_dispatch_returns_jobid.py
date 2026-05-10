from __future__ import annotations

import copy
import pathlib
from http import HTTPStatus
from typing import Any

import pytest
import server

from server_routes._compute_dispatch_introspection import list_canonical_compute_types, parse_compute_dispatches

_CANONICAL_COMPUTE_TYPES = tuple(list_canonical_compute_types())

# Typical-case payloads must avoid the concept-scoped no-op branch so each
# registered compute_type proves that the normal start path returns a jobId.
_MINIMAL_PAYLOADS: dict[str, dict[str, Any]] = {
    "cognates": {"speaker": "Test01"},
    "contact-lexemes": {"speaker": "Test01", "conceptId": "demo"},
    "ipa_only": {"speaker": "Test01", "run_mode": "full"},
    "ortho": {"speaker": "Test01", "run_mode": "full"},
    "forced_align": {"speaker": "Test01"},
    "boundaries": {"speaker": "Test01"},
    "full_pipeline": {"speaker": "Test01", "steps": ["stt"], "run_mode": "full"},
    "train_ipa_model": {"speaker": "Test01"},
    "stt": {"speaker": "Test01", "run_mode": "full"},
    "retranscribe_with_boundaries": {"speaker": "Test01"},
    "offset_detect": {"speaker": "Test01"},
    "offset_detect_from_pair": {
        "speaker": "Test01",
        "pairs": [{"audioTimeSec": 1.0, "csvTimeSec": 1.0}],
    },
    "lexemes_rerun_by_tag": {"speaker": "Test01", "tagLabels": ["Smoke"], "field": "ortho"},
    "lexeme_rerun_ipa": {"speaker": "Test01", "concept_key": "root", "start": 1.0, "end": 2.0},
    "lexeme_rerun_ortho": {"speaker": "Test01", "concept_key": "root", "start": 1.0, "end": 2.0},
}


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body
        self.sent_json: list[tuple[HTTPStatus, dict[str, Any]]] = []

    def _read_json_body(self, required: bool = True) -> dict[str, Any]:
        return self._body

    def _expect_object(self, value: Any, label: str) -> dict[str, Any]:
        assert isinstance(value, dict), f"{label} must be a dict in the test harness"
        return value

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self.sent_json.append((status, payload))


@pytest.fixture(autouse=True)
def _isolate_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    server._install_route_bindings()
    monkeypatch.setenv("PARSE_JOB_SNAPSHOT_DIR", str(tmp_path / "job-snapshots"))
    server._jobs.clear()
    yield
    server._jobs.clear()


def _runner_attrs() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                entry.runner_attr
                for entries in parse_compute_dispatches().values()
                for entry in entries
            }
        )
    )


def test_minimal_payloads_cover_every_registered_compute_type() -> None:
    missing = sorted(set(_CANONICAL_COMPUTE_TYPES) - set(_MINIMAL_PAYLOADS))
    extra = sorted(set(_MINIMAL_PAYLOADS) - set(_CANONICAL_COMPUTE_TYPES))
    assert not missing, (
        "registered compute_type(s) missing minimal payload fixtures in "
        "test_compute_dispatch_returns_jobid.py — declare one: "
        f"{missing}"
    )
    assert not extra, f"_MINIMAL_PAYLOADS contains unregistered compute_type(s): {extra}"


@pytest.mark.parametrize("compute_type", _CANONICAL_COMPUTE_TYPES, ids=_CANONICAL_COMPUTE_TYPES)
def test_registered_compute_type_start_returns_non_null_job_id(
    compute_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert compute_type in _MINIMAL_PAYLOADS, (
        f"compute_type {compute_type!r} is registered in jobs.py but has no minimal payload fixture "
        "in test_compute_dispatch_returns_jobid.py — declare one"
    )

    for runner_attr in _runner_attrs():
        monkeypatch.setattr(
            server,
            runner_attr,
            lambda job_id, payload: {"jobId": job_id, "ok": True, "payload": payload},
        )

    launches: list[tuple[str, str, dict[str, Any]]] = []

    def fake_launch_compute_runner(job_id: str, launched_type: str, payload: dict[str, Any]) -> None:
        launches.append((job_id, launched_type, copy.deepcopy(payload)))

    monkeypatch.setattr(server, "_launch_compute_runner", fake_launch_compute_runner)

    payload = copy.deepcopy(_MINIMAL_PAYLOADS[compute_type])
    handler = _HandlerHarness(payload)

    handler._api_post_compute_start(compute_type)

    assert len(handler.sent_json) == 1
    status, body = handler.sent_json[0]
    assert status in {HTTPStatus.OK, HTTPStatus.ACCEPTED}
    job_id = body.get("jobId")
    assert isinstance(job_id, str) and job_id.strip(), (
        f"compute_type {compute_type!r} returned null jobId on the typical-case start path: {body!r}"
    )
    assert body.get("status") == "running"
    assert launches == [(job_id, compute_type, payload)]
    assert job_id in server._jobs
