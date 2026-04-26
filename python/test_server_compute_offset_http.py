import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


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


class _DispatchHarness(server.RangeRequestHandler):
    def __init__(self):
        self.calls = []

    def _api_post_compute_status(self, compute_type):
        self.calls.append(("status", compute_type))

    def _api_post_compute_start(self, compute_type):
        self.calls.append(("start", compute_type))

    def _api_post_offset_detect(self):
        self.calls.append(("offset-detect", None))

    def _api_post_offset_detect_from_pair(self):
        self.calls.append(("offset-detect-from-pair", None))

    def _api_post_offset_apply(self):
        self.calls.append(("offset-apply", None))


class _DummyComputeOffsetHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def test_api_post_offset_detect_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail01", "nAnchors": 5})
    observed = {}

    def fake_builder(data, **kwargs):
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"jobId": "offset-job-1", "status": "running"})

    monkeypatch.setattr(server, "_app_build_post_offset_detect_response", fake_builder, raising=False)

    handler._api_post_offset_detect()

    assert handler.sent_json == [(HTTPStatus.OK, {"jobId": "offset-job-1", "status": "running"})]
    assert observed["data"] == {"speaker": "Fail01", "nAnchors": 5}
    assert observed["normalize_speaker_id"] == server._normalize_speaker_id
    assert observed["create_job"] == server._create_job
    assert observed["launch_compute_runner"] == server._launch_compute_runner



def test_api_post_offset_detect_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail01"})

    def fake_builder(data, **kwargs):
        raise _DummyComputeOffsetHandlerError(HTTPStatus.BAD_REQUEST, "speaker is required")

    monkeypatch.setattr(server, "_app_ComputeOffsetHandlerError", _DummyComputeOffsetHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_offset_detect_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_offset_detect()

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "speaker is required"



def test_api_post_offset_apply_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail03", "offsetSec": 0})

    def fake_builder(data, **kwargs):
        raise _DummyComputeOffsetHandlerError(
            HTTPStatus.BAD_REQUEST,
            "offsetSec is effectively zero — nothing to apply",
        )

    monkeypatch.setattr(server, "_app_ComputeOffsetHandlerError", _DummyComputeOffsetHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_offset_apply_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_offset_apply()

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "offsetSec is effectively zero — nothing to apply"



def test_api_post_compute_start_wrapper_validates_compute_type_before_callback_url(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail04", "callbackUrl": "notaurl"})
    callback_checked = {"value": False}

    def fake_callback_url(_body):
        callback_checked["value"] = True
        raise server.ApiError(HTTPStatus.BAD_REQUEST, "callbackUrl must be absolute")

    monkeypatch.setattr(server, "_job_callback_url_from_mapping", fake_callback_url)

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_compute_start(" status ")

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "Compute type is required"
    assert callback_checked["value"] is False



def test_api_post_compute_start_wrapper_preserves_callback_url_prerequisite_errors(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail04", "callbackUrl": "notaurl"})
    helper_called = {"value": False}

    def fake_callback_url(_body):
        raise server.ApiError(HTTPStatus.BAD_REQUEST, "callbackUrl must be absolute")

    def fake_builder(*_args, **_kwargs):
        helper_called["value"] = True
        return SimpleNamespace(status=HTTPStatus.OK, payload={})

    monkeypatch.setattr(server, "_job_callback_url_from_mapping", fake_callback_url)
    monkeypatch.setattr(server, "_app_build_post_compute_start_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_compute_start("full_pipeline")

    assert excinfo.value.status == HTTPStatus.BAD_REQUEST
    assert excinfo.value.message == "callbackUrl must be absolute"
    assert helper_called["value"] is False



def test_api_post_compute_start_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"speaker": "Fail04"})
    observed = {}

    def fake_builder(compute_type, data, **kwargs):
        observed["compute_type"] = compute_type
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"jobId": "job-compute-1", "status": "running"})

    monkeypatch.setattr(server, "_job_callback_url_from_mapping", lambda body: "https://example.com/hook")
    monkeypatch.setattr(server, "_app_build_post_compute_start_response", fake_builder, raising=False)

    handler._api_post_compute_start("full_pipeline")

    assert handler.sent_json == [(HTTPStatus.OK, {"jobId": "job-compute-1", "status": "running"})]
    assert observed["compute_type"] == "full_pipeline"
    assert observed["data"] == {"speaker": "Fail04"}
    assert observed["callback_url"] == "https://example.com/hook"
    assert observed["create_job"] == server._create_job
    assert observed["launch_compute_runner"] == server._launch_compute_runner
    assert observed["job_conflict_error_cls"] == server.JobResourceConflictError



def test_api_post_compute_status_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _HandlerHarness({"job_id": "job-55"})
    observed = {}

    def fake_builder(compute_type, data, **kwargs):
        observed["compute_type"] = compute_type
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"jobId": "job-55", "status": "running"})

    monkeypatch.setattr(server, "_app_build_post_compute_status_response", fake_builder, raising=False)

    handler._api_post_compute_status("offset_detect")

    assert handler.sent_json == [(HTTPStatus.OK, {"jobId": "job-55", "status": "running"})]
    assert observed["compute_type"] == "offset_detect"
    assert observed["data"] == {"job_id": "job-55"}
    assert observed["get_job_snapshot"] == server._get_job_snapshot
    assert observed["job_response_payload"] == server._job_response_payload



def test_api_post_compute_status_wrapper_maps_helper_errors_to_api_error(monkeypatch) -> None:
    handler = _HandlerHarness({"job_id": "missing-job"})

    def fake_builder(compute_type, data, **kwargs):
        raise _DummyComputeOffsetHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")

    monkeypatch.setattr(server, "_app_ComputeOffsetHandlerError", _DummyComputeOffsetHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_compute_status_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as excinfo:
        handler._api_post_compute_status("offset_detect")

    assert excinfo.value.status == HTTPStatus.NOT_FOUND
    assert excinfo.value.message == "Unknown jobId"



def test_dispatch_api_post_preserves_compute_status_alias_routes() -> None:
    handler = _DispatchHarness()

    handler._dispatch_api_post("/api/compute/status")
    handler._dispatch_api_post("/api/compute/offset_detect/status")
    handler._dispatch_api_post("/api/offset_detect/status")

    assert handler.calls == [
        ("status", None),
        ("status", "offset_detect"),
        ("status", "offset_detect"),
    ]
