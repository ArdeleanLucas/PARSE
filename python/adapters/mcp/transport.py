from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from adapters.mcp.env_config import _resolve_api_base, _resolve_onboard_http_timeout

logger = logging.getLogger("parse.mcp_adapter")

def _build_stt_callbacks() -> tuple:
    """Build ParseChatTools' start_stt_job / get_job_snapshot callbacks that
    proxy to the running HTTP server. Returns (start_fn, snapshot_fn).

    If the HTTP server is unreachable, the callbacks return clear errors that
    surface through the chat tool's normal validation path rather than letting
    urllib exceptions leak to the MCP client.
    """
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def _get_json(path: str, timeout: float = 20.0) -> Dict[str, Any]:
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                pass
            try:
                parsed_err = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed_err = {"error": body[:400] or http_err.reason}
            if isinstance(parsed_err, dict):
                parsed_err.setdefault("httpStatus", http_err.code)
                return parsed_err
            return {"error": str(parsed_err), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def _post_json(path: str, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        """POST JSON to the PARSE API and return the parsed body.

        For HTTP errors (404, 500, etc.) the server still sends a JSON body
        with an error message — read it and return that so the calling chat
        tool can surface the real reason (e.g. "Unknown jobId") instead of a
        generic "unreachable" message. Only network-level failures raise.
        """
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                pass
            try:
                parsed_err = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed_err = {"error": body[:400] or http_err.reason}
            if isinstance(parsed_err, dict):
                parsed_err.setdefault("status", "error")
                parsed_err.setdefault("httpStatus", http_err.code)
                return parsed_err
            return {"status": "error", "error": str(parsed_err), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def start_stt_job(speaker: str, source_wav: str, language: Optional[str]) -> str:
        try:
            response = _post_json(
                "/api/stt",
                {"speaker": speaker, "source_wav": source_wav, "language": language},
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot start STT job. "
                "Ensure the Python server is running (scripts/parse-run.sh). "
                "Underlying error: {1}".format(base_url, exc)
            )
        job_id = str(
            response.get("job_id") or response.get("jobId") or ""
        ).strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no job_id for STT start: {0}".format(response)
            )
        return job_id

    def get_job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
        import urllib.parse

        safe_job_id = urllib.parse.quote(str(job_id or "").strip(), safe="")
        if not safe_job_id:
            return None
        try:
            response = _get_json("/api/jobs/{0}".format(safe_job_id))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot poll job. "
                "Underlying error: {1}".format(base_url, exc)
            )
        if isinstance(response, dict) and response.get("error") == "Unknown jobId":
            return None
        return response or None

    return start_stt_job, get_job_snapshot

def _build_pipeline_callbacks() -> tuple:
    """Build ParseChatTools' pipeline_state and start_compute callbacks.

    Both proxy to the running PARSE HTTP server so chat/MCP callers see
    the same job state as the browser UI — same in-memory job registry,
    same pipeline sequencer, same annotations-on-disk.

    Returns ``(pipeline_state, start_compute)``.
    """
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def _get_json(path: str, timeout: float = 20.0) -> Dict[str, Any]:
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            try:
                parsed = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed = {"error": body[:400] or http_err.reason}
            if isinstance(parsed, dict):
                parsed.setdefault("httpStatus", http_err.code)
                return parsed
            return {"error": str(parsed), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def _post_json(path: str, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}{1}".format(base_url, path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            try:
                parsed = _json.loads(body) if body else {}
            except _json.JSONDecodeError:
                parsed = {"error": body[:400] or http_err.reason}
            if isinstance(parsed, dict):
                parsed.setdefault("httpStatus", http_err.code)
                return parsed
            return {"error": str(parsed), "httpStatus": http_err.code}
        parsed = _json.loads(body)
        return parsed if isinstance(parsed, dict) else {}

    def pipeline_state(speaker: str) -> Dict[str, Any]:
        import urllib.parse
        safe = urllib.parse.quote(str(speaker or "").strip(), safe="")
        try:
            return _get_json("/api/pipeline/state/{0}".format(safe))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot probe pipeline state. "
                "Underlying error: {1}".format(base_url, exc)
            )

    def start_compute(compute_type: str, payload: Dict[str, Any]) -> str:
        import urllib.parse
        safe = urllib.parse.quote(str(compute_type or "").strip(), safe="")
        try:
            response = _post_json("/api/compute/{0}".format(safe), payload or {})
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot start compute job. "
                "Underlying error: {1}".format(base_url, exc)
            )
        job_id = str(response.get("job_id") or response.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no jobId for compute start: {0}".format(response)
            )
        return job_id

    return pipeline_state, start_compute

def _build_normalize_callback():
    """Build ParseChatTools' start_normalize_job callback that proxies to the HTTP server."""
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def start_normalize_job(speaker: str, source_wav: Optional[str]) -> str:
        payload: Dict[str, Any] = {"speaker": speaker}
        if source_wav:
            payload["sourceWav"] = source_wav
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url="{0}/api/normalize".format(base_url),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            try:
                body = http_err.read().decode("utf-8") or ""
            except Exception:
                body = ""
            raise RuntimeError(
                "PARSE API normalize start failed ({0}): {1}".format(http_err.code, body[:300])
            )
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        job_id = str(parsed.get("jobId") or parsed.get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError(
                "PARSE API returned no jobId for normalize start: {0}".format(parsed)
            )
        return job_id

    return start_normalize_job

def _build_jobs_callback():
    """Build ParseChatTools' list_active_jobs callback that proxies to the HTTP server."""
    import json as _json
    import urllib.error
    import urllib.request

    base_url = _resolve_api_base()

    def list_active_jobs() -> List[Dict[str, Any]]:
        req = urllib.request.Request(
            url="{0}/api/jobs/active".format(base_url),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            raise RuntimeError(
                "PARSE API jobs/active failed ({0})".format(http_err.code)
            )
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        return list(parsed.get("jobs") or [])

    return list_active_jobs

def _build_jobs_list_callback():
    """Build ParseChatTools' generic jobs_list callback via GET /api/jobs."""
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url = _resolve_api_base()

    def list_jobs(filters: Dict[str, Any]) -> Dict[str, Any]:
        query_parts: List[tuple[str, str]] = []
        filters_obj = dict(filters or {})
        for status in filters_obj.get("statuses") or []:
            query_parts.append(("status", str(status)))
        for job_type in filters_obj.get("types") or []:
            query_parts.append(("type", str(job_type)))
        speaker = str(filters_obj.get("speaker") or "").strip()
        if speaker:
            query_parts.append(("speaker", speaker))
        limit = filters_obj.get("limit")
        if limit is not None:
            query_parts.append(("limit", str(limit)))
        query = urllib.parse.urlencode(query_parts, doseq=True)
        url = "{0}/api/jobs{1}".format(base_url, "?{0}".format(query) if query else "")
        req = urllib.request.Request(url=url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            raise RuntimeError("PARSE API /api/jobs failed ({0})".format(http_err.code))
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        return parsed if isinstance(parsed, dict) else {"jobs": [], "count": 0}

    return list_jobs

def _build_job_logs_callback():
    """Build ParseChatTools' job_logs callback via GET /api/jobs/<jobId>/logs."""
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url = _resolve_api_base()

    def get_job_logs(job_id: str, offset: int, limit: int) -> Dict[str, Any]:
        safe_job_id = urllib.parse.quote(str(job_id or "").strip(), safe="")
        if not safe_job_id:
            return {"jobId": "", "count": 0, "offset": offset, "limit": limit, "logs": []}
        query = urllib.parse.urlencode({"offset": int(offset or 0), "limit": int(limit or 100)})
        req = urllib.request.Request(
            url="{0}/api/jobs/{1}/logs?{2}".format(base_url, safe_job_id, query),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                body = resp.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as http_err:
            raise RuntimeError("PARSE API job logs failed ({0})".format(http_err.code))
        except urllib.error.URLError as exc:
            raise RuntimeError("PARSE API unreachable at {0}: {1}".format(base_url, exc))
        parsed = _json.loads(body) if body else {}
        return parsed if isinstance(parsed, dict) else {"jobId": str(job_id or ""), "count": 0, "offset": offset, "limit": limit, "logs": []}

    return get_job_logs

def _build_onboard_callback() -> Optional[object]:
    """Return a callback that proxies onboard_speaker_import through the HTTP API.

    The MCP adapter runs out-of-process from the PARSE server, so we can't call
    the in-process job worker directly. Instead, POST the source files as
    multipart/form-data to /api/onboard/speaker and block on the resulting job
    until it completes. Returns None if the API is unreachable when invoked.
    """
    import email.generator
    import mimetypes
    import time
    import urllib.error
    import urllib.request
    import uuid

    base_url = _resolve_api_base()

    def onboard(speaker: str, source_wav: Path, source_csv: Optional[Path], is_primary: bool) -> Dict[str, Any]:
        boundary = "----parse-mcp-{0}".format(uuid.uuid4().hex)
        crlf = b"\r\n"
        parts: list = []
        total_bytes = source_wav.stat().st_size + (source_csv.stat().st_size if source_csv is not None else 0)
        http_timeout = _resolve_onboard_http_timeout(total_bytes)

        def add_field(name: str, value: str) -> None:
            parts.append(
                (
                    "--{0}\r\nContent-Disposition: form-data; name=\"{1}\"\r\n\r\n{2}\r\n"
                    .format(boundary, name, value)
                ).encode("utf-8")
            )

        def add_file(name: str, path: Path) -> None:
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            header = (
                "--{0}\r\nContent-Disposition: form-data; name=\"{1}\"; filename=\"{2}\"\r\n"
                "Content-Type: {3}\r\n\r\n".format(boundary, name, path.name, mime)
            ).encode("utf-8")
            parts.append(header)
            parts.append(path.read_bytes())
            parts.append(crlf)

        add_field("speaker_id", speaker)
        add_file("audio", source_wav)
        if source_csv is not None:
            add_file("csv", source_csv)
        parts.append("--{0}--\r\n".format(boundary).encode("utf-8"))

        body = b"".join(parts)
        req = urllib.request.Request(
            url="{0}/api/onboard/speaker".format(base_url),
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary={0}".format(boundary)},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:
                response = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot onboard speaker. Underlying: {1}".format(
                    base_url, exc
                )
            )

        job_id = str(response.get("job_id") or response.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError("Onboard API did not return a job_id: {0}".format(response))

        # Poll for completion (bounded).
        status_req_body = json.dumps({"job_id": job_id}).encode("utf-8")
        deadline = time.time() + http_timeout
        final: Dict[str, Any] = {}
        while time.time() < deadline:
            status_req = urllib.request.Request(
                url="{0}/api/onboard/speaker/status".format(base_url),
                data=status_req_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(status_req, timeout=10.0) as sresp:
                    final = json.loads(sresp.read().decode("utf-8") or "{}")
            except urllib.error.URLError:
                time.sleep(1.0)
                continue
            status = str(final.get("status") or "").lower()
            if status in {"complete", "error"}:
                break
            time.sleep(1.0)

        if str(final.get("status") or "").lower() != "complete":
            raise RuntimeError(
                "Onboarding failed for speaker {0!r}: {1}".format(speaker, final.get("error") or final)
            )

        result = final.get("result") if isinstance(final.get("result"), dict) else {}
        return {
            "jobId": job_id,
            "annotationPath": result.get("annotationPath"),
            "wavPath": result.get("wavPath"),
            "csvPath": result.get("csvPath"),
            "isPrimary": is_primary,
        }

    return onboard

__all__ = [
    '_build_stt_callbacks',
    '_build_pipeline_callbacks',
    '_build_normalize_callback',
    '_build_jobs_callback',
    '_build_jobs_list_callback',
    '_build_job_logs_callback',
    '_build_onboard_callback',
]
