import pathlib
import sys
from http import HTTPStatus
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _GetHarness(server.RangeRequestHandler):
    def __init__(self, path: str = "/api/stt-segments/Fail01"):
        self.path = path
        self.sent_json = []

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


class _PostHarness(server.RangeRequestHandler):
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

    def _api_get_stt_segments(self, speaker):
        self.calls.append(("get-stt-segments", speaker))

    def _api_post_normalize(self):
        self.calls.append(("post-normalize", None))

    def _api_post_normalize_status(self):
        self.calls.append(("post-normalize-status", None))

    def _api_post_stt_start(self):
        self.calls.append(("post-stt", None))

    def _api_post_stt_status(self):
        self.calls.append(("post-stt-status", None))

    def _api_post_suggest(self):
        self.calls.append(("post-suggest", None))


class _DummySpeechHandlerError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message



def test_api_get_stt_segments_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _GetHarness()
    observed = {}

    def fake_builder(speaker_part, **kwargs):
        observed["speaker_part"] = speaker_part
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"speaker": "Fail01", "segments": []})

    monkeypatch.setattr(server, "_app_build_get_stt_segments_response", fake_builder, raising=False)

    handler._api_get_stt_segments("Fail01")

    assert handler.sent_json == [(HTTPStatus.OK, {"speaker": "Fail01", "segments": []})]
    assert observed["speaker_part"] == "Fail01"
    assert observed["normalize_speaker_id"] == server._normalize_speaker_id
    assert observed["stt_cache_path"] == server._stt_cache_path



def test_api_post_normalize_wrapper_preserves_callback_prerequisite_errors(monkeypatch) -> None:
    handler = _PostHarness({"speaker": "Fail01", "callbackUrl": "notaurl"})
    helper_called = {"value": False}

    def fake_callback_url(_body):
        raise server.ApiError(HTTPStatus.BAD_REQUEST, "callbackUrl must be absolute")

    def fake_builder(*_args, **_kwargs):
        helper_called["value"] = True
        return SimpleNamespace(status=HTTPStatus.OK, payload={})

    monkeypatch.setattr(server, "_job_callback_url_from_mapping", fake_callback_url)
    monkeypatch.setattr(server, "_app_build_post_normalize_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_normalize()

    assert exc_info.value.status == HTTPStatus.BAD_REQUEST
    assert exc_info.value.message == "callbackUrl must be absolute"
    assert helper_called["value"] is False



def test_api_post_stt_start_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _PostHarness({"speaker": "Fail02", "source_wav": "audio/original/Fail02/input.wav"})
    observed = {}

    def fake_builder(data, **kwargs):
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"jobId": "job-stt-1", "status": "running"})

    monkeypatch.setattr(server, "_job_callback_url_from_mapping", lambda body: "https://example.test/hooks/stt")
    monkeypatch.setattr(server, "_app_build_post_stt_start_response", fake_builder, raising=False)

    handler._api_post_stt_start()

    assert handler.sent_json == [(HTTPStatus.OK, {"jobId": "job-stt-1", "status": "running"})]
    assert observed["data"] == {"speaker": "Fail02", "source_wav": "audio/original/Fail02/input.wav"}
    assert observed["callback_url"] == "https://example.test/hooks/stt"
    assert observed["create_job"] == server._create_job
    assert observed["launch_compute_runner"] == server._launch_compute_runner
    assert observed["job_conflict_error_cls"] == server.JobResourceConflictError



def test_api_post_stt_status_wrapper_maps_helper_errors(monkeypatch) -> None:
    handler = _PostHarness({"job_id": "missing-job"})

    def fake_builder(data, **kwargs):
        raise _DummySpeechHandlerError(HTTPStatus.NOT_FOUND, "Unknown jobId")

    monkeypatch.setattr(server, "_app_SpeechAnnotationHandlerError", _DummySpeechHandlerError, raising=False)
    monkeypatch.setattr(server, "_app_build_post_stt_status_response", fake_builder, raising=False)

    with pytest.raises(server.ApiError) as exc_info:
        handler._api_post_stt_status()

    assert exc_info.value.status == HTTPStatus.NOT_FOUND
    assert exc_info.value.message == "Unknown jobId"



def test_api_post_suggest_wrapper_delegates_to_helper(monkeypatch) -> None:
    handler = _PostHarness({"speaker": "Fail03", "concept_ids": ["1"]})
    observed = {}

    def fake_builder(data, **kwargs):
        observed["data"] = data
        observed.update(kwargs)
        return SimpleNamespace(status=HTTPStatus.OK, payload={"suggestions": []})

    monkeypatch.setattr(server, "_app_build_post_suggest_response", fake_builder, raising=False)

    handler._api_post_suggest()

    assert handler.sent_json == [(HTTPStatus.OK, {"suggestions": []})]
    assert observed["data"] == {"speaker": "Fail03", "concept_ids": ["1"]}
    assert observed["get_llm_provider"] == server.get_llm_provider
    assert observed["load_cached_suggestions"] == server._load_cached_suggestions
    assert observed["coerce_concept_id_list"] == server._coerce_concept_id_list



def test_dispatch_routes_preserve_speech_http_endpoints() -> None:
    handler = _DispatchHarness()

    handler._dispatch_api_get("/api/stt-segments/Fail01")
    handler._dispatch_api_post("/api/normalize")
    handler._dispatch_api_post("/api/normalize/status")
    handler._dispatch_api_post("/api/stt")
    handler._dispatch_api_post("/api/stt/status")
    handler._dispatch_api_post("/api/suggest")

    assert handler.calls == [
        ("get-stt-segments", "Fail01"),
        ("post-normalize", None),
        ("post-normalize-status", None),
        ("post-stt", None),
        ("post-stt-status", None),
        ("post-suggest", None),
    ]
