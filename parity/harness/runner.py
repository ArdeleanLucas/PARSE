from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
TIMESTAMP_FIELD_NAMES = {
    "completed_at",
    "completedAt",
    "computed_at",
    "computedAt",
    "created",
    "created_at",
    "createdAt",
    "modified",
    "modified_at",
    "modifiedAt",
    "started_at",
    "startedAt",
    "updated_at",
    "updatedAt",
}
JOB_ID_FIELD_NAMES = {"job_id", "jobId"}
TERMINAL_JOB_STATUSES = {"complete", "completed", "done", "error", "failed"}
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
JSON_SNAPSHOT_PATTERNS = (
    "project.json",
    "source_index.json",
    "parse-enrichments.json",
    "parse-tags.json",
    "annotations/*.json",
    "annotations/*.parse.json",
)


@dataclass(frozen=True)
class FixtureBundle:
    workspace_root: Path
    input_root: Path
    seed_speaker_id: str
    speaker_id: str
    tag_name: str
    tag_color: str


@dataclass(frozen=True)
class ScenarioCapture:
    label: str
    api: dict[str, Any]
    job_lifecycles: dict[str, Any]
    exports: dict[str, str]
    persisted_json: dict[str, Any]


@dataclass(frozen=True)
class DiffEntry:
    section: str
    key: str
    oracle_value: Any
    rebuild_value: Any


@dataclass(frozen=True)
class ServerInstance:
    label: str
    repo_root: Path
    workspace_root: Path
    base_url: str
    log_path: Path
    process: subprocess.Popen[bytes]


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_REBUILD_REPO = _repo_root_from_module()
DEFAULT_ORACLE_REPO = Path(os.environ.get("PARSE_ORACLE_REPO", "/home/lucas/gh/ardeleanlucas/parse"))


def normalize_for_diff(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            item = normalize_for_diff(value[key])
            if key in JOB_ID_FIELD_NAMES and item not in {None, ""}:
                normalized[key] = "<job-id>"
                continue
            if key in TIMESTAMP_FIELD_NAMES and isinstance(item, str) and item:
                normalized[key] = "<timestamp>"
                continue
            normalized[key] = item
        return normalized

    if isinstance(value, list):
        return [normalize_for_diff(item) for item in value]

    if isinstance(value, tuple):
        return [normalize_for_diff(item) for item in value]

    if isinstance(value, Path):
        return value.as_posix()

    if isinstance(value, str) and TIMESTAMP_RE.match(value):
        return "<timestamp>"

    return value


def prepare_fixture_bundle(root: Path) -> FixtureBundle:
    workspace_root = root / "workspace"
    input_root = root / "inputs"
    workspace_root.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)

    for relative_name in ("concepts-import.csv", "tags-import.csv", "onboard-concepts.csv", "lexeme-notes.csv"):
        shutil.copy2(FIXTURE_ROOT / relative_name, input_root / relative_name)

    onboard_dir = input_root / "onboard"
    onboard_dir.mkdir(parents=True, exist_ok=True)
    _write_silence_wav(onboard_dir / "Parity01.wav")

    workspace_fixture_root = FIXTURE_ROOT / "workspace"
    for relative_name in ("project.json", "source_index.json", "parse-enrichments.json"):
        shutil.copy2(workspace_fixture_root / relative_name, workspace_root / relative_name)

    for relative_dir in (
        "annotations",
        "audio/original",
        "audio/working",
        "config",
        "peaks",
    ):
        (workspace_root / relative_dir).mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        workspace_fixture_root / "annotations" / "Base01.parse.json",
        workspace_root / "annotations" / "Base01.parse.json",
    )
    _write_silence_wav(workspace_root / "audio" / "original" / "Base01" / "source.wav")

    (workspace_root / "config" / "sil_contact_languages.json").write_text(
        '{\n  "_meta": {\n    "primary_contact_languages": [],\n    "configured_at": null,\n    "schema_version": 1\n  }\n}\n',
        encoding="utf-8",
    )

    return FixtureBundle(
        workspace_root=workspace_root,
        input_root=input_root,
        seed_speaker_id="Base01",
        speaker_id="Parity01",
        tag_name="Import Parity Tag 2",
        tag_color="#10b981",
    )


def compare_capture_sections(oracle: ScenarioCapture, rebuild: ScenarioCapture) -> list[DiffEntry]:
    diffs: list[DiffEntry] = []
    for section in ("api", "job_lifecycles", "exports", "persisted_json"):
        oracle_section = normalize_for_diff(getattr(oracle, section))
        rebuild_section = normalize_for_diff(getattr(rebuild, section))
        keys = sorted(set(oracle_section.keys()) | set(rebuild_section.keys()))
        for key in keys:
            oracle_value = oracle_section.get(key)
            rebuild_value = rebuild_section.get(key)
            if oracle_value != rebuild_value:
                diffs.append(
                    DiffEntry(
                        section=section,
                        key=key,
                        oracle_value=oracle_value,
                        rebuild_value=rebuild_value,
                    )
                )
    return diffs


def render_markdown_report(oracle: ScenarioCapture, rebuild: ScenarioCapture, diffs: list[DiffEntry]) -> str:
    counts_by_section: dict[str, int] = {}
    for diff in diffs:
        counts_by_section[diff.section] = counts_by_section.get(diff.section, 0) + 1

    lines = [
        "# PARSE parity diff harness report",
        "",
        f"Compared **{oracle.label}** vs **{rebuild.label}**.",
        "",
        f"Current diff count: **{len(diffs)}**",
        "",
        "## Diff counts by section",
        "",
    ]

    if counts_by_section:
        for section in sorted(counts_by_section):
            lines.append(f"- `{section}`: {counts_by_section[section]}")
    else:
        lines.append("- none")

    lines.extend(["", "## Diff details", ""])

    if not diffs:
        lines.append("No diffs detected for the current fixture and scenario.")
        return "\n".join(lines) + "\n"

    for entry in diffs:
        lines.extend(
            [
                f"### {entry.section} — {entry.key}",
                "",
                "**oracle**",
                "```",
                _format_value(entry.oracle_value),
                "```",
                "",
                "**rebuild**",
                "```",
                _format_value(entry.rebuild_value),
                "```",
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def collect_persisted_json(workspace_root: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for pattern in JSON_SNAPSHOT_PATTERNS:
        for file_path in sorted(workspace_root.glob(pattern)):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(workspace_root).as_posix()
            snapshot[relative_path] = json.loads(file_path.read_text(encoding="utf-8"))
    return snapshot


def run_harness(
    *,
    oracle_repo: Path,
    rebuild_repo: Path,
    output_dir: Path,
    keep_temp: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="parse-parity-oracle-") as oracle_tmp, TemporaryDirectory(prefix="parse-parity-rebuild-") as rebuild_tmp:
        oracle_fixture = prepare_fixture_bundle(Path(oracle_tmp))
        rebuild_fixture = prepare_fixture_bundle(Path(rebuild_tmp))

        oracle_server = _start_server(
            label="oracle",
            repo_root=oracle_repo,
            workspace_root=oracle_fixture.workspace_root,
            log_path=output_dir / "oracle-server.log",
        )
        rebuild_server = _start_server(
            label="rebuild",
            repo_root=rebuild_repo,
            workspace_root=rebuild_fixture.workspace_root,
            log_path=output_dir / "rebuild-server.log",
        )

        try:
            oracle_capture = _run_default_scenario(oracle_server, oracle_fixture)
            rebuild_capture = _run_default_scenario(rebuild_server, rebuild_fixture)
        finally:
            _stop_server(oracle_server)
            _stop_server(rebuild_server)

        diffs = compare_capture_sections(oracle_capture, rebuild_capture)
        markdown = render_markdown_report(oracle_capture, rebuild_capture, diffs)

        report_json = {
            "oracle": _capture_to_jsonable(oracle_capture),
            "rebuild": _capture_to_jsonable(rebuild_capture),
            "diffs": [asdict(diff) for diff in diffs],
            "diff_count": len(diffs),
        }

        report_json_path = output_dir / "report.json"
        report_markdown_path = output_dir / "report.md"
        report_json_path.write_text(json.dumps(normalize_for_diff(report_json), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_markdown_path.write_text(markdown, encoding="utf-8")

        if keep_temp:
            _copy_workspace_snapshot(oracle_fixture.workspace_root, output_dir / "oracle-workspace")
            _copy_workspace_snapshot(rebuild_fixture.workspace_root, output_dir / "rebuild-workspace")

        return {
            "diff_count": len(diffs),
            "report_json": report_json_path,
            "report_markdown": report_markdown_path,
            "oracle_server_log": oracle_server.log_path,
            "rebuild_server_log": rebuild_server.log_path,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PARSE oracle-vs-rebuild parity diff harness.")
    parser.add_argument("--oracle-repo", type=Path, default=DEFAULT_ORACLE_REPO)
    parser.add_argument("--rebuild-repo", type=Path, default=DEFAULT_REBUILD_REPO)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REBUILD_REPO / "parity" / "harness" / "output" / "latest")
    parser.add_argument("--keep-temp", action="store_true", help="Copy final workspace snapshots into the output directory.")
    args = parser.parse_args(argv)

    result = run_harness(
        oracle_repo=args.oracle_repo.resolve(),
        rebuild_repo=args.rebuild_repo.resolve(),
        output_dir=args.output_dir.resolve(),
        keep_temp=args.keep_temp,
    )

    print(f"parity diff count: {result['diff_count']}")
    print(f"markdown report: {Path(result['report_markdown']).resolve()}")
    print(f"json report: {Path(result['report_json']).resolve()}")
    return 0


def _capture_to_jsonable(capture: ScenarioCapture) -> dict[str, Any]:
    return {
        "label": capture.label,
        "api": capture.api,
        "job_lifecycles": capture.job_lifecycles,
        "exports": capture.exports,
        "persisted_json": capture.persisted_json,
    }


def _start_server(*, label: str, repo_root: Path, workspace_root: Path, log_path: Path) -> ServerInstance:
    port = _allocate_port()
    base_url = f"http://127.0.0.1:{port}"
    bootstrap = "\n".join(
        [
            "import os",
            "import sys",
            "repo_root = os.environ['PARSE_HARNESS_REPO_ROOT']",
            "workspace_root = os.environ['PARSE_HARNESS_WORKSPACE_ROOT']",
            "port = int(os.environ['PARSE_HARNESS_PORT'])",
            "os.chdir(workspace_root)",
            "sys.path.insert(0, os.path.join(repo_root, 'python'))",
            "import server as s",
            "s.HOST = '127.0.0.1'",
            "s.PORT = port",
            "s.main()",
        ]
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_path, "wb")
    process = subprocess.Popen(
        [sys.executable, "-c", bootstrap],
        cwd=str(repo_root),
        env={
            **os.environ,
            "PARSE_HARNESS_REPO_ROOT": str(repo_root),
            "PARSE_HARNESS_WORKSPACE_ROOT": str(workspace_root),
            "PARSE_HARNESS_PORT": str(port),
        },
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    instance = ServerInstance(
        label=label,
        repo_root=repo_root,
        workspace_root=workspace_root,
        base_url=base_url,
        log_path=log_path,
        process=process,
    )
    _wait_for_server(instance)
    return instance


def _stop_server(instance: ServerInstance) -> None:
    if instance.process.poll() is not None:
        return
    instance.process.terminate()
    try:
        instance.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        instance.process.kill()
        instance.process.wait(timeout=5)


def _wait_for_server(instance: ServerInstance, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = _request_json("GET", f"{instance.base_url}/api/config")
            if response["status"] == 200:
                return
            last_error = RuntimeError(f"GET /api/config returned {response['status']}")
        except Exception as exc:  # pragma: no cover - exercised in real harness runs
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {instance.label} server at {instance.base_url}: {last_error}")


def _run_default_scenario(instance: ServerInstance, fixture: FixtureBundle) -> ScenarioCapture:
    api: dict[str, Any] = {}

    api["config"] = _request_json("GET", f"{instance.base_url}/api/config")
    api["concepts_import"] = _multipart_request(
        f"{instance.base_url}/api/concepts/import",
        fields={"mode": "merge"},
        files={"csv": fixture.input_root / "concepts-import.csv"},
    )
    api["tags_import"] = _multipart_request(
        f"{instance.base_url}/api/tags/import",
        fields={"tagName": fixture.tag_name, "color": fixture.tag_color},
        files={"csv": fixture.input_root / "tags-import.csv"},
    )
    api["onboard_start"] = _multipart_request(
        f"{instance.base_url}/api/onboard/speaker",
        fields={"speaker_id": fixture.speaker_id},
        files={
            "audio": fixture.input_root / "onboard" / "Parity01.wav",
            "csv": fixture.input_root / "onboard-concepts.csv",
        },
    )

    onboard_job_id = _resolve_job_id(api["onboard_start"].get("body"))
    job_lifecycles = {
        "onboard": _poll_job_lifecycle(
            base_url=instance.base_url,
            status_path="/api/onboard/speaker/status",
            job_id=onboard_job_id,
        ) if onboard_job_id else {"states": [], "terminal": None}
    }

    api["annotation_after_onboard"] = _request_json(
        "GET",
        f"{instance.base_url}/api/annotations/{urllib.parse.quote(fixture.speaker_id)}",
    )
    api["tags_get"] = _request_json("GET", f"{instance.base_url}/api/tags")
    api["lexeme_notes_import"] = _multipart_request(
        f"{instance.base_url}/api/lexeme-notes/import",
        fields={"speaker_id": fixture.seed_speaker_id},
        files={"csv": fixture.input_root / "lexeme-notes.csv"},
    )

    exports = {
        "lingpy": _request_text("GET", f"{instance.base_url}/api/export/lingpy"),
        "nexus": _request_text("GET", f"{instance.base_url}/api/export/nexus"),
    }

    return ScenarioCapture(
        label=instance.label,
        api=api,
        job_lifecycles=job_lifecycles,
        exports=exports,
        persisted_json=collect_persisted_json(instance.workspace_root),
    )


def _poll_job_lifecycle(*, base_url: str, status_path: str, job_id: str) -> dict[str, Any]:
    states: list[str] = []
    terminal_payload: dict[str, Any] | None = None
    for _ in range(60):
        response = _request_json("POST", f"{base_url}{status_path}", body={"jobId": job_id})
        status = str(response.get("body", {}).get("status") or "")
        if status:
            states.append(status)
        terminal_payload = response
        if status.lower() in TERMINAL_JOB_STATUSES:
            break
        time.sleep(0.2)
    return {
        "states": states,
        "terminal": terminal_payload,
    }


def _request_json(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return {
                "status": response.status,
                "body": _decode_json_or_text(raw),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return {
            "status": exc.code,
            "body": _decode_json_or_text(raw),
        }


def _request_text(method: str, url: str) -> str:
    request = urllib.request.Request(url=url, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def _multipart_request(url: str, *, fields: dict[str, str], files: dict[str, Path]) -> dict[str, Any]:
    boundary = f"----parseparity{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, file_path in files.items():
        filename = file_path.name
        content_type = "audio/wav" if file_path.suffix.lower() == ".wav" else "text/csv"
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request = urllib.request.Request(
        url=url,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return {"status": response.status, "body": _decode_json_or_text(raw)}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return {"status": exc.code, "body": _decode_json_or_text(raw)}


def _decode_json_or_text(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _resolve_job_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("job_id", "jobId"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_silence_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 1600)


def _copy_workspace_snapshot(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
