import json
import pathlib
import sys
import threading
from typing import Any, Dict, Iterable, Optional

import pytest

connect = pytest.importorskip("websockets.sync.client").connect

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


class _StreamingStubProvider:
    def __init__(self, *, partial_segments: Optional[Iterable[Dict[str, Any]]] = None, final_segments: Optional[Iterable[Dict[str, Any]]] = None):
        self.partial_segments = list(partial_segments or [])
        self.final_segments = list(final_segments or [])

    def transcribe(
        self,
        audio_path,
        language=None,
        progress_callback=None,
        segment_callback=None,
    ):
        if progress_callback is not None:
            progress_callback(12.5, 0)
        if segment_callback is not None:
            for segment in self.partial_segments:
                segment_callback(segment)
        if progress_callback is not None:
            progress_callback(55.0, len(self.partial_segments))
        return list(self.final_segments)


def _recv_event(ws, expected_event: str, *, timeout: float = 5.0) -> Dict[str, Any]:
    while True:
        payload = json.loads(ws.recv(timeout=timeout))
        if payload.get("event") == expected_event:
            return payload


def _recv_events(ws, expected_events: Iterable[str], *, timeout: float = 5.0) -> Dict[str, Dict[str, Any]]:
    wanted = {str(event) for event in expected_events}
    received: Dict[str, Dict[str, Any]] = {}
    while wanted - received.keys():
        payload = json.loads(ws.recv(timeout=timeout))
        event_name = str(payload.get("event") or "")
        if event_name in wanted and event_name not in received:
            received[event_name] = payload
    return received


def test_resolve_ws_port_prefers_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PARSE_WS_PORT", "9876")
    assert server._resolve_ws_port() == 9876


def test_websocket_stream_receives_snapshot_progress_log_and_complete_events() -> None:
    server._jobs.clear()
    sidecar = server._start_websocket_sidecar(host="127.0.0.1", port=0)
    try:
        job_id = server._create_job("stt", {"speaker": "Fail01", "sourceWav": "audio.wav"})
        with connect(sidecar.job_url(job_id), open_timeout=5, close_timeout=5) as ws:
            snapshot = _recv_event(ws, "job.snapshot")
            assert snapshot["jobId"] == job_id
            assert snapshot["type"] == "stt"
            assert snapshot["payload"]["status"] == "running"

            server._set_job_progress(
                job_id,
                25.0,
                message="Transcribing (1 segments)",
                segments_processed=1,
            )
            streamed = _recv_events(ws, {"job.progress", "job.log"})
            progress = streamed["job.progress"]
            assert progress["payload"]["progress"] == 25.0
            assert progress["payload"]["segmentsProcessed"] == 1
            assert progress["payload"]["message"] == "Transcribing (1 segments)"

            log_event = streamed["job.log"]
            assert log_event["payload"]["event"] == "job.progress"
            assert log_event["payload"]["message"] == "Transcribing (1 segments)"

            server._set_job_complete(job_id, {"segments": []}, message="STT complete")
            complete = _recv_event(ws, "job.complete")
            assert complete["payload"]["status"] == "complete"
            assert complete["payload"]["result"] == {"segments": []}
    finally:
        sidecar.stop()


def test_run_stt_job_streams_provisional_segments_over_websocket(tmp_path, monkeypatch) -> None:
    server._jobs.clear()
    monkeypatch.setattr(server, "_project_root", lambda: tmp_path)
    audio_path = tmp_path / "speaker.wav"
    audio_path.write_bytes(b"\0")
    monkeypatch.setattr(
        server,
        "get_stt_provider",
        lambda: _StreamingStubProvider(
            partial_segments=[
                {
                    "start": 0.0,
                    "end": 0.4,
                    "text": "partial one",
                    "confidence": 0.31,
                }
            ],
            final_segments=[
                {
                    "start": 0.0,
                    "end": 0.5,
                    "text": "final one",
                    "confidence": 0.88,
                }
            ],
        ),
    )

    sidecar = server._start_websocket_sidecar(host="127.0.0.1", port=0)
    try:
        job_id = server._create_job("stt", {"speaker": "Fail01", "sourceWav": "speaker.wav"})
        result_holder: Dict[str, Any] = {}

        def _run() -> None:
            result_holder["result"] = server._run_stt_job(job_id, "Fail01", "speaker.wav", "ckb")

        with connect(sidecar.job_url(job_id), open_timeout=5, close_timeout=5) as ws:
            _recv_event(ws, "job.snapshot")
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            stt_segment = _recv_event(ws, "stt.segment")
            assert stt_segment["payload"]["provisional"] is True
            assert stt_segment["payload"]["segment"] == {
                "start": 0.0,
                "end": 0.4,
                "text": "partial one",
                "confidence": 0.31,
            }

            progress = _recv_event(ws, "job.progress")
            assert progress["payload"]["progress"] >= 2.0

            thread.join(timeout=5)
            assert result_holder["result"]["segments"] == [
                {
                    "start": 0.0,
                    "end": 0.5,
                    "text": "final one",
                    "confidence": 0.88,
                }
            ]
    finally:
        sidecar.stop()
