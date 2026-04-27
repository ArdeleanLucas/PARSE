from __future__ import annotations

import argparse
import copy
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
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable

from parity.harness.diff.mcp_tools import build_mcp_tools_capture

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in CI/runtime if dependency is missing
    raise RuntimeError("PyYAML is required for parity/harness/allowlist.yaml support") from exc


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
DEFAULT_REBUILD_REPO = Path(__file__).resolve().parents[2]
DEFAULT_ORACLE_REPO = Path(os.environ.get("PARSE_ORACLE_REPO", "/home/lucas/gh/ardeleanlucas/parse"))
DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().parent / "allowlist.yaml"
DEFAULT_FIXTURE_NAME = "saha-2speaker"
SUPPORTED_FIXTURE_NAMES = ("saha-2speaker", "round2-multispeaker")
FIXTURE_ROOTS = {name: FIXTURE_ROOT for name in SUPPORTED_FIXTURE_NAMES}
DEFAULT_SCRIPT_BOOT_PORT = 8766
CANONICALIZATION_VERSION = 2
DIFF_CATEGORY_SECTIONS: dict[str, tuple[str, ...]] = {
    "all": ("api", "job_lifecycles", "exports", "persisted_json", "mcp_tools"),
    "mcp_tools": ("mcp_tools",),
}
TIMESTAMP_FIELD_NAMES = {
    "completed_at",
    "completedAt",
    "computed_at",
    "computedAt",
    "configured_at",
    "configuredAt",
    "created",
    "created_at",
    "createdAt",
    "expires_at",
    "expiresAt",
    "modified",
    "modified_at",
    "modifiedAt",
    "released_at",
    "releasedAt",
    "started_at",
    "startedAt",
    "ts",
    "updated_at",
    "updatedAt",
}
JOB_ID_FIELD_NAMES = {"job_id", "jobId"}
SESSION_ID_FIELD_NAMES = {"session_id", "sessionId"}
TERMINAL_JOB_STATUSES = {"complete", "completed", "done", "error", "failed", "expired"}
TIMESTAMP_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
UUID_VALUE_RE = re.compile(r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
CHAT_SESSION_VALUE_RE = re.compile(r"^chat_[0-9a-f]+$", re.IGNORECASE)
HEX_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
TRACEBACK_LINE_RE = re.compile(r"line\s+\d+")
TIMESTAMP_INLINE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")
MCP_GENERATED_MODEL_NAME_RE = re.compile(r"\bmcp_([A-Za-z0-9_]+(?:Arguments|Output))\b")
JSON_SNAPSHOT_PATTERNS = (
    "project.json",
    "source_index.json",
    "parse-enrichments.json",
    "parse-tags.json",
    "config/*.json",
    "annotations/*.json",
    "annotations/*.parse.json",
)
ROUND2_CONTRACT_GROUP_COVERAGE: dict[str, tuple[str, ...]] = {
    "annotation_data": (
        "annotation_get_seed",
        "annotation_save_roundtrip",
        "annotation_save_invalid",
        "annotation_get_missing",
        "stt_segments_get_seed",
    ),
    "project_config_and_pipeline_state": (
        "config_get",
        "config_update",
        "config_get_after_update",
        "pipeline_state_seed",
    ),
    "enrichments_tags_notes_imports": (
        "enrichments_get_before",
        "enrichments_save_manual_decisions",
        "enrichments_get_after_manual_decisions",
        "concepts_import",
        "tags_import",
        "tags_get_after_import",
        "tags_merge",
        "tags_get_after_merge",
        "lexeme_note_save",
        "lexeme_notes_import",
        "enrichments_get_after_notes_import",
    ),
    "auth": (
        "auth_status",
        "auth_poll_no_active_flow",
        "auth_logout",
        "auth_key_invalid",
    ),
    "stt_normalize_onboard": (
        "stt_start",
        "normalize_start",
        "onboard_start",
    ),
    "offset_tools": (
        "offset_detect_from_pair_start",
        "offset_apply",
    ),
    "suggestions_lexeme_search": (
        "suggestions_request",
        "lexeme_search",
    ),
    "chat_and_generic_compute": (
        "chat_session_start",
        "chat_session_get",
        "chat_run_invalid_session",
        "chat_status_unknown_job",
        "full_pipeline_start",
    ),
    "job_observability": (
        "jobs_list",
        "jobs_active",
        "onboard.active_job",
        "onboard.final_logs",
    ),
    "export_and_media": (
        "spectrogram_url",
        "lingpy",
        "nexus",
        "lingpy_empty_wordlist",
        "nexus_empty_wordlist",
    ),
    "clef_contact_lexeme": (
        "clef_config_get_before",
        "clef_config_invalid",
        "clef_config_save",
        "clef_config_get_after_save",
        "clef_form_selections_save",
        "clef_catalog_get",
        "clef_providers_get",
        "clef_sources_report_get",
        "contact_lexeme_coverage_get",
        "contact_lexeme_fetch_start",
    ),
}
ROUND2_FAILURE_CASES = (
    "annotation_save_invalid",
    "annotation_get_missing",
    "clef_config_invalid",
    "lingpy_empty_wordlist",
    "nexus_empty_wordlist",
)
ROUND2_JOB_LIFECYCLE_KEYS = (
    "stt",
    "normalize",
    "full_pipeline",
    "onboard",
    "offset_detect_from_pair",
    "contact_lexemes",
)
PLACEHOLDER_REASON_RE = re.compile(r"\b(?:todo|tbd|fixme|fill this in)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalizationContext:
    repo_roots: dict[str, Path] = field(default_factory=dict)
    workspace_roots: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class BootSmokeResult:
    repo_label: str
    success: bool
    port: int
    detail: str
    log_path: Path


@dataclass(frozen=True)
class FixtureBundle:
    workspace_root: Path
    input_root: Path
    seed_speaker_id: str
    compare_speaker_id: str
    onboard_speaker_id: str
    tag_name: str
    tag_color: str


@dataclass(frozen=True)
class ScenarioCapture:
    label: str
    api: dict[str, Any]
    job_lifecycles: dict[str, Any]
    exports: dict[str, Any]
    persisted_json: dict[str, Any]
    mcp_tools: dict[str, Any]


@dataclass(frozen=True)
class AllowlistRule:
    rule_id: str
    sections: tuple[str, ...]
    path: str | None
    path_regex: str | None
    classification: str | None
    permanence: str | None
    reason: str | None
    reason_ref: str | None

    def matches(self, entry: "DiffEntry") -> bool:
        if self.sections and entry.section not in self.sections:
            return False
        if self.path and entry.path != self.path:
            return False
        if self.path_regex and not re.search(self.path_regex, entry.path):
            return False
        return True


@dataclass(frozen=True)
class DiffEntry:
    section: str
    path: str
    oracle_value: Any
    rebuild_value: Any
    allowlist_rule_id: str | None = None
    classification: str | None = None
    permanence: str | None = None
    reason: str | None = None
    reason_ref: str | None = None


@dataclass
class DiffReport:
    raw_diffs: list[DiffEntry]
    allowlisted_diffs: list[DiffEntry] = field(default_factory=list)
    unallowlisted_diffs: list[DiffEntry] = field(default_factory=list)
    raw_diff_count: int = 0
    allowlisted_diff_count: int = 0
    unallowlisted_diff_count: int = 0

    def finalize(self) -> "DiffReport":
        self.raw_diff_count = len(self.raw_diffs)
        self.allowlisted_diffs = [entry for entry in self.raw_diffs if entry.allowlist_rule_id]
        self.unallowlisted_diffs = [entry for entry in self.raw_diffs if not entry.allowlist_rule_id]
        self.allowlisted_diff_count = len(self.allowlisted_diffs)
        self.unallowlisted_diff_count = len(self.unallowlisted_diffs)
        return self


@dataclass(frozen=True)
class ServerInstance:
    label: str
    repo_root: Path
    workspace_root: Path
    base_url: str
    log_path: Path
    process: subprocess.Popen[bytes]


@dataclass(frozen=True)
class JobStartSpec:
    key: str
    start_response: dict[str, Any]
    status_path: str


@dataclass(frozen=True)
class TextResponse:
    status: int
    body: Any


def normalize_for_diff(
    value: Any,
    *,
    context: CanonicalizationContext | None = None,
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            item_path = f"{path}.{key}"
            item = normalize_for_diff(value[key], context=context, path=item_path)
            if key in JOB_ID_FIELD_NAMES and isinstance(item, str) and item:
                normalized[key] = "<job-id>"
                continue
            if key in SESSION_ID_FIELD_NAMES and isinstance(item, str) and item:
                normalized[key] = "<session-id>"
                continue
            if key in TIMESTAMP_FIELD_NAMES and isinstance(item, str) and item:
                normalized[key] = "<timestamp>"
                continue
            normalized[key] = item
        return normalized

    if isinstance(value, list):
        normalized_items = [normalize_for_diff(item, context=context, path=f"{path}[{index}]") for index, item in enumerate(value)]
        if path.startswith("$.job_lifecycles.") and path.endswith(".states"):
            terminal_state = next(
                (
                    item
                    for item in reversed(normalized_items)
                    if isinstance(item, str) and item.lower() in TERMINAL_JOB_STATUSES
                ),
                None,
            )
            if terminal_state is not None:
                return [terminal_state]
        return _sort_normalized_list(path, normalized_items)

    if isinstance(value, tuple):
        return normalize_for_diff(list(value), context=context, path=path)

    if isinstance(value, Path):
        return _normalize_path_text(value.as_posix(), context)

    if isinstance(value, float):
        return round(value, 6)

    if isinstance(value, str):
        return _normalize_string(value, context)

    return value


def load_allowlist_rules(path: Path) -> list[AllowlistRule]:
    if not path.exists():
        return []

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Allowlist YAML must be an object: {path}")

    raw_rules = payload.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ValueError(f"Allowlist rules must be a list: {path}")

    rules: list[AllowlistRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Allowlist rule #{index + 1} must be a mapping")
        rule_id = str(raw_rule.get("id") or "").strip()
        if not rule_id:
            raise ValueError(f"Allowlist rule #{index + 1} is missing id")
        raw_sections = raw_rule.get("section", raw_rule.get("sections", []))
        sections = _normalize_sections(raw_sections)
        path_exact = _optional_text(raw_rule.get("path"))
        path_regex = _optional_text(raw_rule.get("path_regex"))
        classification = _optional_text(raw_rule.get("classification"))
        permanence = _optional_text(raw_rule.get("permanence"))
        reason = _optional_text(raw_rule.get("reason"))
        reason_ref = _optional_text(raw_rule.get("reason_ref"))
        if permanence == "permanent":
            _validate_reason_text(rule_id, reason)
            if not reason_ref:
                raise ValueError(f"Permanent allowlist rule {rule_id} must include reason_ref")
        rules.append(
            AllowlistRule(
                rule_id=rule_id,
                sections=sections,
                path=path_exact,
                path_regex=path_regex,
                classification=classification,
                permanence=permanence,
                reason=reason,
                reason_ref=reason_ref,
            )
        )
    return rules


def _fixture_root_for_name(fixture_name: str) -> Path:
    normalized_name = str(fixture_name or "").strip()
    fixture_root = FIXTURE_ROOTS.get(normalized_name)
    if fixture_root is None:
        supported = ", ".join(sorted(SUPPORTED_FIXTURE_NAMES))
        raise ValueError(f"Unknown fixture '{fixture_name}'. Supported fixtures: {supported}")
    return fixture_root


def prepare_fixture_bundle(root: Path, *, fixture_name: str = DEFAULT_FIXTURE_NAME) -> FixtureBundle:
    workspace_root = root / "workspace"
    input_root = root / "inputs"
    workspace_root.mkdir(parents=True, exist_ok=True)
    input_root.mkdir(parents=True, exist_ok=True)

    fixture_root = _fixture_root_for_name(fixture_name)

    for relative_name in ("concepts-import.csv", "tags-import.csv", "onboard-concepts.csv", "lexeme-notes.csv"):
        shutil.copy2(fixture_root / relative_name, input_root / relative_name)

    onboard_dir = input_root / "onboard"
    onboard_dir.mkdir(parents=True, exist_ok=True)
    _write_silence_wav(onboard_dir / "Parity01.wav")

    workspace_fixture_root = fixture_root / "workspace"
    for relative_name in (
        "project.json",
        "source_index.json",
        "parse-enrichments.json",
        "concepts.csv",
    ):
        shutil.copy2(workspace_fixture_root / relative_name, workspace_root / relative_name)

    for relative_dir in (
        "annotations",
        "audio/original/Base01",
        "audio/original/Base02",
        "audio/working",
        "config",
        "peaks",
    ):
        (workspace_root / relative_dir).mkdir(parents=True, exist_ok=True)

    for speaker_id in ("Base01", "Base02"):
        shutil.copy2(
            workspace_fixture_root / "annotations" / f"{speaker_id}.parse.json",
            workspace_root / "annotations" / f"{speaker_id}.parse.json",
        )
        _write_silence_wav(workspace_root / "audio" / "original" / speaker_id / "source.wav")

    (workspace_root / "config" / "sil_contact_languages.json").write_text(
        '{\n  "_meta": {\n    "primary_contact_languages": [],\n    "configured_at": null,\n    "schema_version": 1\n  }\n}\n',
        encoding="utf-8",
    )

    return FixtureBundle(
        workspace_root=workspace_root,
        input_root=input_root,
        seed_speaker_id="Base01",
        compare_speaker_id="Base02",
        onboard_speaker_id="Parity01",
        tag_name="Import Parity Tag 2",
        tag_color="#10b981",
    )


def compare_capture_sections(
    oracle: ScenarioCapture,
    rebuild: ScenarioCapture,
    *,
    context: CanonicalizationContext | None = None,
    sections: Iterable[str] | None = None,
) -> list[DiffEntry]:
    diffs: list[DiffEntry] = []
    selected_sections = tuple(sections or ("api", "job_lifecycles", "exports", "persisted_json", "mcp_tools"))
    for section in selected_sections:
        base_path = f"$.{section}"
        oracle_section = normalize_for_diff(getattr(oracle, section), context=context, path=base_path)
        rebuild_section = normalize_for_diff(getattr(rebuild, section), context=context, path=base_path)
        diffs.extend(_collect_diffs(section, base_path, oracle_section, rebuild_section))
    return diffs


def build_diff_report(
    oracle: ScenarioCapture,
    rebuild: ScenarioCapture,
    *,
    context: CanonicalizationContext,
    allowlist_rules: Iterable[AllowlistRule],
    sections: Iterable[str] | None = None,
) -> DiffReport:
    raw_diffs: list[DiffEntry] = []
    for entry in compare_capture_sections(oracle, rebuild, context=context, sections=sections):
        matched_rule = next((rule for rule in allowlist_rules if rule.matches(entry)), None)
        if matched_rule is None:
            raw_diffs.append(entry)
            continue
        raw_diffs.append(
            DiffEntry(
                section=entry.section,
                path=entry.path,
                oracle_value=entry.oracle_value,
                rebuild_value=entry.rebuild_value,
                allowlist_rule_id=matched_rule.rule_id,
                classification=matched_rule.classification,
                permanence=matched_rule.permanence,
                reason=matched_rule.reason,
                reason_ref=matched_rule.reason_ref,
            )
        )
    return DiffReport(raw_diffs=raw_diffs).finalize()


def build_server_boot_smoke_blockers(results: dict[str, BootSmokeResult]) -> list[DiffEntry]:
    blockers: list[DiffEntry] = []
    for label in sorted(results):
        result = results[label]
        if result.success:
            continue
        blockers.append(
            DiffEntry(
                section="server_boot_smoke",
                path=f"$.server_boot_smoke.{label}",
                oracle_value={"expected": "boot success"},
                rebuild_value=_boot_smoke_result_to_jsonable(result),
            )
        )
    return blockers


def build_signoff_payload(
    *,
    fixture_name: str,
    oracle_repo: Path,
    rebuild_repo: Path,
    oracle_sha: str,
    rebuild_sha: str,
    report: DiffReport,
    server_boot_results: dict[str, BootSmokeResult],
) -> dict[str, Any]:
    return {
        "fixture": fixture_name,
        "repos": {
            "oracle": {"path": str(oracle_repo), "sha": oracle_sha},
            "rebuild": {"path": str(rebuild_repo), "sha": rebuild_sha},
        },
        "diff_counts": {
            "raw": report.raw_diff_count,
            "allowlisted": report.allowlisted_diff_count,
            "unallowlisted": report.unallowlisted_diff_count,
        },
        "server_boot_smoke": {
            label: _boot_smoke_result_to_jsonable(result)
            for label, result in sorted(server_boot_results.items())
        },
    }


def render_markdown_report(
    oracle: ScenarioCapture,
    rebuild: ScenarioCapture,
    report: DiffReport,
) -> str:
    counts_by_section: dict[str, int] = {}
    for diff in report.raw_diffs:
        counts_by_section[diff.section] = counts_by_section.get(diff.section, 0) + 1

    lines = [
        "# PARSE parity diff harness report",
        "",
        f"Compared **{oracle.label}** vs **{rebuild.label}**.",
        "",
        f"Raw diff count: **{report.raw_diff_count}**",
        f"Allowlisted diff count: **{report.allowlisted_diff_count}**",
        f"Remaining unallowlisted diff count: **{report.unallowlisted_diff_count}**",
        "",
        "## Diff counts by section",
        "",
    ]
    if counts_by_section:
        for section in sorted(counts_by_section):
            lines.append(f"- `{section}`: {counts_by_section[section]}")
    else:
        lines.append("- none")

    lines.extend(["", "## Remaining unallowlisted diffs", ""])
    if not report.unallowlisted_diffs:
        lines.append("No unallowlisted diffs remain for the current fixture and scenario.")
    else:
        for entry in report.unallowlisted_diffs:
            lines.extend(_render_diff_entry(entry))

    lines.extend(["", "## Allowlisted diffs", ""])
    if not report.allowlisted_diffs:
        lines.append("No allowlist rules matched this run.")
    else:
        for entry in report.allowlisted_diffs:
            lines.extend(_render_diff_entry(entry, include_allowlist=True))

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
    allowlist_path: Path = DEFAULT_ALLOWLIST_PATH,
    fixture_name: str = DEFAULT_FIXTURE_NAME,
    emit_signoff: bool = False,
    keep_temp: bool = False,
    diff_category: str = "all",
) -> dict[str, Any]:
    selected_sections = _resolve_diff_sections(diff_category)
    output_dir.mkdir(parents=True, exist_ok=True)
    allowlist_rules = load_allowlist_rules(allowlist_path)
    oracle_sha = _git_rev_parse(oracle_repo)
    rebuild_sha = _git_rev_parse(rebuild_repo)

    with TemporaryDirectory(prefix="parse-parity-oracle-") as oracle_tmp, TemporaryDirectory(prefix="parse-parity-rebuild-") as rebuild_tmp:
        oracle_fixture = prepare_fixture_bundle(Path(oracle_tmp), fixture_name=fixture_name)
        rebuild_fixture = prepare_fixture_bundle(Path(rebuild_tmp), fixture_name=fixture_name)

        server_boot_results: dict[str, BootSmokeResult] = {}
        oracle_server_log = output_dir / "oracle-server.log"
        rebuild_server_log = output_dir / "rebuild-server.log"
        oracle_script_log = output_dir / "oracle-server-script.log"
        rebuild_script_log = output_dir / "rebuild-server-script.log"
        oracle_capture = _empty_capture("oracle")
        rebuild_capture = _empty_capture("rebuild")

        if _requires_http_server(selected_sections):
            server_boot_results = {
                "oracle": _run_server_boot_smoke(
                    repo_root=oracle_repo,
                    workspace_root=oracle_fixture.workspace_root,
                    label="oracle",
                    log_path=oracle_script_log,
                ),
                "rebuild": _run_server_boot_smoke(
                    repo_root=rebuild_repo,
                    workspace_root=rebuild_fixture.workspace_root,
                    label="rebuild",
                    log_path=rebuild_script_log,
                ),
            }

            oracle_server = _start_server(
                label="oracle",
                repo_root=oracle_repo,
                workspace_root=oracle_fixture.workspace_root,
                log_path=oracle_server_log,
            )
            rebuild_server = _start_server(
                label="rebuild",
                repo_root=rebuild_repo,
                workspace_root=rebuild_fixture.workspace_root,
                log_path=rebuild_server_log,
            )

            try:
                oracle_capture = _run_default_scenario(oracle_server, oracle_fixture)
                rebuild_capture = _run_default_scenario(rebuild_server, rebuild_fixture)
            finally:
                _stop_server(oracle_server)
                _stop_server(rebuild_server)

        if "mcp_tools" in selected_sections:
            oracle_capture = replace(
                oracle_capture,
                mcp_tools=build_mcp_tools_capture(
                    repo_root=oracle_repo,
                    workspace_root=oracle_fixture.workspace_root,
                    input_root=oracle_fixture.input_root,
                    seed_speaker_id=oracle_fixture.seed_speaker_id,
                    compare_speaker_id=oracle_fixture.compare_speaker_id,
                    onboard_speaker_id=oracle_fixture.onboard_speaker_id,
                    tag_name=oracle_fixture.tag_name,
                    tag_color=oracle_fixture.tag_color,
                ),
            )
            rebuild_capture = replace(
                rebuild_capture,
                mcp_tools=build_mcp_tools_capture(
                    repo_root=rebuild_repo,
                    workspace_root=rebuild_fixture.workspace_root,
                    input_root=rebuild_fixture.input_root,
                    seed_speaker_id=rebuild_fixture.seed_speaker_id,
                    compare_speaker_id=rebuild_fixture.compare_speaker_id,
                    onboard_speaker_id=rebuild_fixture.onboard_speaker_id,
                    tag_name=rebuild_fixture.tag_name,
                    tag_color=rebuild_fixture.tag_color,
                ),
            )

        context = CanonicalizationContext(
            repo_roots={"oracle": oracle_repo, "rebuild": rebuild_repo},
            workspace_roots={"oracle": oracle_fixture.workspace_root, "rebuild": rebuild_fixture.workspace_root},
        )
        report = build_diff_report(
            oracle_capture,
            rebuild_capture,
            context=context,
            allowlist_rules=allowlist_rules,
            sections=selected_sections,
        )
        report.raw_diffs.extend(build_server_boot_smoke_blockers(server_boot_results))
        report.finalize()
        markdown = render_markdown_report(oracle_capture, rebuild_capture, report)
        signoff_payload = build_signoff_payload(
            fixture_name=fixture_name,
            oracle_repo=oracle_repo,
            rebuild_repo=rebuild_repo,
            oracle_sha=oracle_sha,
            rebuild_sha=rebuild_sha,
            report=report,
            server_boot_results=server_boot_results,
        )

        report_json = {
            "fixture": fixture_name,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "allowlist_path": str(allowlist_path),
            "allowlist_rule_count": len(allowlist_rules),
            "diff_category": diff_category,
            "selected_sections": list(selected_sections),
            "repos": signoff_payload["repos"],
            "coverage": {
                "contract_groups": ROUND2_CONTRACT_GROUP_COVERAGE,
                "failure_cases": ROUND2_FAILURE_CASES,
                "job_lifecycles": ROUND2_JOB_LIFECYCLE_KEYS,
            },
            "server_boot_smoke": signoff_payload["server_boot_smoke"],
            "diff_count_raw": report.raw_diff_count,
            "diff_count_allowlisted": report.allowlisted_diff_count,
            "diff_count_unallowlisted": report.unallowlisted_diff_count,
            "oracle": _capture_to_jsonable(oracle_capture),
            "rebuild": _capture_to_jsonable(rebuild_capture),
            "diffs": [asdict(diff) for diff in report.raw_diffs],
            "allowlisted_diffs": [asdict(diff) for diff in report.allowlisted_diffs],
            "unallowlisted_diffs": [asdict(diff) for diff in report.unallowlisted_diffs],
        }

        report_json_path = output_dir / "report.json"
        report_markdown_path = output_dir / "report.md"
        report_json_path.write_text(
            json.dumps(normalize_for_diff(report_json, context=context), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report_markdown_path.write_text(markdown, encoding="utf-8")

        signoff_json_path = None
        signoff_markdown_path = None
        if emit_signoff:
            signoff_json_path = output_dir / "signoff-summary.json"
            signoff_markdown_path = output_dir / "signoff-summary.md"
            signoff_json_path.write_text(json.dumps(signoff_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            signoff_markdown_path.write_text(_render_signoff_summary(signoff_payload), encoding="utf-8")

        if keep_temp:
            _copy_workspace_snapshot(oracle_fixture.workspace_root, output_dir / "oracle-workspace")
            _copy_workspace_snapshot(rebuild_fixture.workspace_root, output_dir / "rebuild-workspace")

        return {
            "diff_count": report.unallowlisted_diff_count,
            "diff_count_raw": report.raw_diff_count,
            "diff_count_allowlisted": report.allowlisted_diff_count,
            "report_json": report_json_path,
            "report_markdown": report_markdown_path,
            "signoff_json": signoff_json_path,
            "signoff_markdown": signoff_markdown_path,
            "oracle_server_log": oracle_server_log,
            "rebuild_server_log": rebuild_server_log,
            "oracle_script_log": oracle_script_log,
            "rebuild_script_log": rebuild_script_log,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PARSE oracle-vs-rebuild parity diff harness.")
    parser.add_argument("--oracle-repo", "--oracle", dest="oracle_repo", type=Path, default=DEFAULT_ORACLE_REPO)
    parser.add_argument("--rebuild-repo", "--rebuild", dest="rebuild_repo", type=Path, default=DEFAULT_REBUILD_REPO)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REBUILD_REPO / "parity" / "harness" / "output" / "latest")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST_PATH)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE_NAME)
    parser.add_argument("--diff-category", choices=sorted(DIFF_CATEGORY_SECTIONS), default="all")
    parser.add_argument("--emit-signoff", action="store_true", help="Write sign-off summary artifacts next to report.json/report.md.")
    parser.add_argument("--keep-temp", action="store_true", help="Copy final workspace snapshots into the output directory.")
    args = parser.parse_args(argv)

    result = run_harness(
        oracle_repo=args.oracle_repo.resolve(),
        rebuild_repo=args.rebuild_repo.resolve(),
        output_dir=args.output_dir.resolve(),
        allowlist_path=args.allowlist.resolve(),
        fixture_name=str(args.fixture),
        emit_signoff=bool(args.emit_signoff),
        keep_temp=args.keep_temp,
        diff_category=str(args.diff_category),
    )

    print(f"parity diff count: {result['diff_count']}")
    print(f"raw diff count: {result['diff_count_raw']}")
    print(f"allowlisted diff count: {result['diff_count_allowlisted']}")
    print(f"markdown report: {Path(result['report_markdown']).resolve()}")
    print(f"json report: {Path(result['report_json']).resolve()}")
    if result.get("signoff_json"):
        print(f"signoff json: {Path(result['signoff_json']).resolve()}")
    if result.get("signoff_markdown"):
        print(f"signoff markdown: {Path(result['signoff_markdown']).resolve()}")
    return 0


def _capture_to_jsonable(capture: ScenarioCapture) -> dict[str, Any]:
    return {
        "label": capture.label,
        "api": capture.api,
        "job_lifecycles": capture.job_lifecycles,
        "exports": capture.exports,
        "persisted_json": capture.persisted_json,
        "mcp_tools": capture.mcp_tools,
    }


def _resolve_diff_sections(diff_category: str) -> tuple[str, ...]:
    try:
        return DIFF_CATEGORY_SECTIONS[diff_category]
    except KeyError as exc:
        raise ValueError(f"Unsupported diff category: {diff_category}") from exc


def _requires_http_server(selected_sections: Iterable[str]) -> bool:
    return any(section != "mcp_tools" for section in selected_sections)


def _empty_capture(label: str) -> ScenarioCapture:
    return ScenarioCapture(label=label, api={}, job_lifecycles={}, exports={}, persisted_json={}, mcp_tools={})


def _git_rev_parse(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_server_boot_smoke(*, repo_root: Path, workspace_root: Path, label: str, log_path: Path, timeout_seconds: float = 10.0) -> BootSmokeResult:
    port = DEFAULT_SCRIPT_BOOT_PORT
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not _is_port_available(port):
        log_path.write_text(f"Port {port} already in use before {label} script smoke run.\n", encoding="utf-8")
        return BootSmokeResult(
            repo_label=label,
            success=False,
            port=port,
            detail=f"Port {port} already in use before script boot smoke.",
            log_path=log_path,
        )

    log_handle = open(log_path, "wb")
    process = subprocess.Popen(
        [sys.executable, str(repo_root / "python" / "server.py")],
        cwd=str(workspace_root),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    last_error: str | None = None
    success = False
    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            if process.poll() is not None:
                break
            try:
                response = _request_json("GET", f"http://127.0.0.1:{port}/api/config")
                if response.get("status") == 200 and process.poll() is None:
                    success = True
                    break
                last_error = f"GET /api/config returned {response.get('status')}"
            except Exception as exc:  # pragma: no cover - exercised in runtime smoke checks
                last_error = str(exc)
            time.sleep(0.25)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log_handle.close()

    detail = f"Booted on port {port}." if success else _read_boot_failure_detail(log_path, last_error)
    return BootSmokeResult(
        repo_label=label,
        success=success,
        port=port,
        detail=detail,
        log_path=log_path,
    )


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _read_boot_failure_detail(log_path: Path, last_error: str | None) -> str:
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8", errors="replace").strip()
        if log_text:
            tail = "\n".join(log_text.splitlines()[-12:])
            return tail
    return last_error or "Server did not bind before timeout."


def _boot_smoke_result_to_jsonable(result: BootSmokeResult) -> dict[str, Any]:
    return {
        "repo_label": result.repo_label,
        "success": result.success,
        "port": result.port,
        "detail": result.detail,
        "log_path": str(result.log_path),
    }


def _render_signoff_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# PARSE parity harness sign-off summary",
        "",
        f"- Fixture: `{payload['fixture']}`",
        f"- Oracle SHA: `{payload['repos']['oracle']['sha']}`",
        f"- Rebuild SHA: `{payload['repos']['rebuild']['sha']}`",
        f"- Raw diff count: **{payload['diff_counts']['raw']}**",
        f"- Allowlisted diff count: **{payload['diff_counts']['allowlisted']}**",
        f"- Remaining unallowlisted diff count: **{payload['diff_counts']['unallowlisted']}**",
        "",
        "## Server boot smoke",
        "",
    ]
    for label, result in payload["server_boot_smoke"].items():
        status = "PASS" if result["success"] else "FAIL"
        lines.extend(
            [
                f"### {label}",
                f"- Status: **{status}**",
                f"- Port: `{result['port']}`",
                f"- Detail: {result['detail']}",
                f"- Log: `{result['log_path']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


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
    job_lifecycles: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    base_url = instance.base_url

    api["config_get"] = _request_json("GET", f"{base_url}/api/config")
    api["config_update"] = _request_json("PUT", f"{base_url}/api/config", body={"chat": {"enabled": False}})
    api["config_get_after_update"] = _request_json("GET", f"{base_url}/api/config")

    api["annotation_get_seed"] = _request_json("GET", f"{base_url}/api/annotations/{urllib.parse.quote(fixture.seed_speaker_id)}")
    api["annotation_get_missing"] = _request_json("GET", f"{base_url}/api/annotations/{urllib.parse.quote('MissingParity')}" )
    api["annotation_save_roundtrip"] = _request_json(
        "POST",
        f"{base_url}/api/annotations/{urllib.parse.quote(fixture.seed_speaker_id)}",
        body=api["annotation_get_seed"].get("body"),
    )
    api["annotation_save_invalid"] = _request_json(
        "POST",
        f"{base_url}/api/annotations/{urllib.parse.quote(fixture.seed_speaker_id)}",
        raw_json='"invalid"',
    )
    api["stt_segments_get_seed"] = _request_json("GET", f"{base_url}/api/stt-segments/{urllib.parse.quote(fixture.seed_speaker_id)}")
    api["pipeline_state_seed"] = _request_json("GET", f"{base_url}/api/pipeline/state/{urllib.parse.quote(fixture.seed_speaker_id)}")

    api["enrichments_get_before"] = _request_json("GET", f"{base_url}/api/enrichments")
    enrichments_payload = _extract_enrichments_payload(api["enrichments_get_before"].get("body"))
    enrichments_payload["manual_overrides"] = {
        "cognate_sets": {
            "1": {
                "A": [fixture.seed_speaker_id, fixture.compare_speaker_id],
            }
        }
    }
    api["enrichments_save_manual_decisions"] = _request_json(
        "POST",
        f"{base_url}/api/enrichments",
        body={"enrichments": enrichments_payload},
    )
    api["enrichments_get_after_manual_decisions"] = _request_json("GET", f"{base_url}/api/enrichments")

    api["concepts_import"] = _multipart_request(
        f"{base_url}/api/concepts/import",
        fields={"mode": "merge"},
        files={"csv": fixture.input_root / "concepts-import.csv"},
    )
    api["tags_import"] = _multipart_request(
        f"{base_url}/api/tags/import",
        fields={"tagName": fixture.tag_name, "color": fixture.tag_color},
        files={"csv": fixture.input_root / "tags-import.csv"},
    )
    api["tags_get_after_import"] = _request_json("GET", f"{base_url}/api/tags")
    tags_body = api["tags_get_after_import"].get("body")
    api["tags_merge"] = _request_json(
        "POST",
        f"{base_url}/api/tags/merge",
        body={"tags": _build_tag_merge_payload(tags_body)},
    )
    api["tags_get_after_merge"] = _request_json("GET", f"{base_url}/api/tags")

    api["lexeme_note_save"] = _request_json(
        "POST",
        f"{base_url}/api/lexeme-notes",
        body={"speaker": fixture.seed_speaker_id, "concept_id": "1", "user_note": "keep vowel length"},
    )
    api["enrichments_get_after_lexeme_note"] = _request_json("GET", f"{base_url}/api/enrichments")
    api["lexeme_notes_import"] = _multipart_request(
        f"{base_url}/api/lexeme-notes/import",
        fields={"speaker_id": fixture.seed_speaker_id},
        files={"csv": fixture.input_root / "lexeme-notes.csv"},
    )
    api["enrichments_get_after_notes_import"] = _request_json("GET", f"{base_url}/api/enrichments")

    api["auth_status"] = _request_json("GET", f"{base_url}/api/auth/status")
    api["auth_poll_no_active_flow"] = _request_json("POST", f"{base_url}/api/auth/poll", body={})
    api["auth_logout"] = _request_json("POST", f"{base_url}/api/auth/logout", body={})
    api["auth_key_invalid"] = _request_json("POST", f"{base_url}/api/auth/key", body={"key": ""})

    api["suggestions_request"] = _request_json(
        "POST",
        f"{base_url}/api/suggest",
        body={"speaker": fixture.seed_speaker_id, "concept_ids": []},
    )
    lexeme_query = urllib.parse.urlencode(
        {
            "speaker": fixture.seed_speaker_id,
            "variants": "ash",
            "concept_id": "1",
            "language": "ar",
            "limit": "3",
        }
    )
    api["lexeme_search"] = _request_json("GET", f"{base_url}/api/lexeme/search?{lexeme_query}")

    api["chat_session_start"] = _request_json("POST", f"{base_url}/api/chat/session", body={})
    chat_session_id = _resolve_session_id(api["chat_session_start"].get("body"))
    api["chat_session_get"] = _request_json(
        "GET",
        f"{base_url}/api/chat/session/{urllib.parse.quote(chat_session_id)}",
    ) if chat_session_id else {"status": 500, "body": {"error": "missing chat session id"}}
    api["chat_run_invalid_session"] = _request_json(
        "POST",
        f"{base_url}/api/chat/run",
        body={"session_id": "bad session!", "message": "test"},
    )
    api["chat_status_unknown_job"] = _request_json(
        "POST",
        f"{base_url}/api/chat/run/status",
        body={"job_id": "nonexistent-chat-job"},
    )

    api["clef_config_get_before"] = _request_json("GET", f"{base_url}/api/clef/config")
    api["clef_config_invalid"] = _request_json(
        "POST",
        f"{base_url}/api/clef/config",
        body={"primary_contact_languages": "ar", "languages": []},
    )
    api["clef_config_save"] = _request_json(
        "POST",
        f"{base_url}/api/clef/config",
        body={
            "primary_contact_languages": ["ar"],
            "languages": [{"code": "ar", "name": "Arabic", "family": "Semitic", "script": "Arab"}],
        },
    )
    api["clef_config_get_after_save"] = _request_json("GET", f"{base_url}/api/clef/config")
    api["clef_form_selections_save"] = _request_json(
        "POST",
        f"{base_url}/api/clef/form-selections",
        body={"concept_en": "ash", "lang_code": "ar", "forms": ["aʃ"]},
    )
    api["clef_catalog_get"] = _request_json("GET", f"{base_url}/api/clef/catalog")
    api["clef_providers_get"] = _request_json("GET", f"{base_url}/api/clef/providers")
    api["clef_sources_report_get"] = _request_json("GET", f"{base_url}/api/clef/sources-report")
    api["contact_lexeme_coverage_get"] = _request_json("GET", f"{base_url}/api/contact-lexemes/coverage")

    api["stt_missing_speaker"] = _request_json("POST", f"{base_url}/api/stt", body={"source_wav": "missing.wav"})
    api["normalize_missing_speaker"] = _request_json("POST", f"{base_url}/api/normalize", body={})

    onboard_start = _multipart_request(
        f"{base_url}/api/onboard/speaker",
        fields={"speaker_id": fixture.onboard_speaker_id},
        files={
            "audio": fixture.input_root / "onboard" / "Parity01.wav",
            "csv": fixture.input_root / "onboard-concepts.csv",
        },
    )
    api["onboard_start"] = onboard_start
    job_lifecycles["onboard"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(onboard_start.get("body")),
        status_path="/api/onboard/speaker/status",
        capture_active=True,
    )
    api["annotation_get_onboarded"] = _request_json(
        "GET",
        f"{base_url}/api/annotations/{urllib.parse.quote(fixture.onboard_speaker_id)}",
    )

    stt_start = _request_json(
        "POST",
        f"{base_url}/api/stt",
        body={"speaker": fixture.seed_speaker_id, "source_wav": "audio/original/Base01/missing.wav"},
    )
    api["stt_start"] = stt_start
    job_lifecycles["stt"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(stt_start.get("body")),
        status_path="/api/stt/status",
    )

    normalize_start = _request_json(
        "POST",
        f"{base_url}/api/normalize",
        body={"speaker": fixture.seed_speaker_id, "source_wav": "audio/original/Base01/missing.wav"},
    )
    api["normalize_start"] = normalize_start
    job_lifecycles["normalize"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(normalize_start.get("body")),
        status_path="/api/normalize/status",
    )

    full_pipeline_start = _request_json(
        "POST",
        f"{base_url}/api/compute/full_pipeline",
        body={
            "speaker": fixture.compare_speaker_id,
            "steps": [],
        },
    )
    api["full_pipeline_start"] = full_pipeline_start
    job_lifecycles["full_pipeline"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(full_pipeline_start.get("body")),
        status_path="/api/compute/full_pipeline/status",
    )

    offset_pair_start = _request_json(
        "POST",
        f"{base_url}/api/offset/detect-from-pair",
        body={"speaker": fixture.compare_speaker_id, "audioTimeSec": 0.05, "csvTimeSec": 0.0},
    )
    api["offset_detect_from_pair_start"] = offset_pair_start
    job_lifecycles["offset_detect_from_pair"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(offset_pair_start.get("body")),
        status_path="/api/compute/offset_detect_from_pair/status",
    )
    offset_result = _extract_job_result(job_lifecycles["offset_detect_from_pair"])
    apply_offset_sec = offset_result.get("offsetSec", 0.05) if isinstance(offset_result, dict) else 0.05
    api["offset_apply"] = _request_json(
        "POST",
        f"{base_url}/api/offset/apply",
        body={"speaker": fixture.compare_speaker_id, "offsetSec": apply_offset_sec},
    )

    clef_fetch_start = _request_json(
        "POST",
        f"{base_url}/api/compute/contact-lexemes",
        body={"providers": ["no_such_provider"], "languages": ["ar"], "overwrite": True},
    )
    api["contact_lexeme_fetch_start"] = clef_fetch_start
    job_lifecycles["contact_lexemes"] = _observe_job(
        base_url=base_url,
        job_id=_resolve_job_id(clef_fetch_start.get("body")),
        status_path="/api/compute/contact-lexemes/status",
    )

    api["jobs_list"] = _request_json("GET", f"{base_url}/api/jobs")
    api["jobs_active"] = _request_json("GET", f"{base_url}/api/jobs/active")

    exports["spectrogram_url"] = _spectrogram_url(fixture.seed_speaker_id, 0.0, 0.1)
    exports["lingpy"] = asdict(_request_text_response("GET", f"{base_url}/api/export/lingpy"))
    exports["nexus"] = asdict(_request_text_response("GET", f"{base_url}/api/export/nexus"))

    annotations_dir = instance.workspace_root / "annotations"
    hidden_annotations_dir = instance.workspace_root / "annotations.__parity_hidden__"
    if hidden_annotations_dir.exists():
        shutil.rmtree(hidden_annotations_dir)
    annotations_dir.rename(hidden_annotations_dir)
    try:
        exports["lingpy_empty_wordlist"] = asdict(_request_text_response("GET", f"{base_url}/api/export/lingpy"))
        exports["nexus_empty_wordlist"] = asdict(_request_text_response("GET", f"{base_url}/api/export/nexus"))
    finally:
        hidden_annotations_dir.rename(annotations_dir)

    return ScenarioCapture(
        label=instance.label,
        api=api,
        job_lifecycles=job_lifecycles,
        exports=exports,
        persisted_json=collect_persisted_json(instance.workspace_root),
        mcp_tools={},
    )


def _observe_job(
    *,
    base_url: str,
    job_id: str,
    status_path: str,
    capture_active: bool = False,
) -> dict[str, Any]:
    if not job_id:
        return {"states": [], "terminal": None, "active_job": None, "final_logs": None, "job_detail": None}

    active_job = None
    states: list[str] = []
    terminal_payload: dict[str, Any] | None = None
    for _ in range(80):
        if capture_active and active_job is None:
            active_response = _request_json("GET", f"{base_url}/api/jobs/active")
            active_job = _extract_active_job_summary(active_response, job_id)
        response = _request_json("POST", f"{base_url}{status_path}", body={"job_id": job_id})
        status = str(response.get("body", {}).get("status") or "")
        if status:
            states.append(status)
        terminal_payload = response
        if status.lower() in TERMINAL_JOB_STATUSES:
            break
        time.sleep(0.15)
    final_logs = _request_json("GET", f"{base_url}/api/jobs/{urllib.parse.quote(job_id)}/logs")
    job_detail = _request_json("GET", f"{base_url}/api/jobs/{urllib.parse.quote(job_id)}")
    return {
        "active_job": active_job,
        "states": states,
        "terminal": terminal_payload,
        "final_logs": final_logs,
        "job_detail": job_detail,
    }


def _request_json(
    method: str,
    url: str,
    *,
    body: Any | None = None,
    raw_json: str | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    payload = None
    if raw_json is not None:
        payload = raw_json.encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
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


def _request_text_response(method: str, url: str) -> TextResponse:
    request = urllib.request.Request(url=url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return TextResponse(status=response.status, body=response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return TextResponse(status=exc.code, body=_decode_json_or_text(raw))


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
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
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


def _resolve_session_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("session_id", "sessionId"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_active_job_summary(response: Any, job_id: str) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    body = response.get("body")
    jobs = body.get("jobs") if isinstance(body, dict) else None
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if _resolve_job_id(job) != job_id:
            continue
        summary: dict[str, Any] = {
            key: job.get(key)
            for key in ("jobId", "job_id", "type", "status", "speaker", "locks")
            if key in job
        }
        return {
            "status": response.get("status"),
            "body": {"job": summary},
        }
    return None


def _extract_job_result(lifecycle: dict[str, Any]) -> Any:
    terminal = lifecycle.get("terminal") if isinstance(lifecycle, dict) else None
    if not isinstance(terminal, dict):
        return None
    body = terminal.get("body")
    if not isinstance(body, dict):
        return None
    return body.get("result")


def _extract_enrichments_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("enrichments"), dict):
        return copy.deepcopy(payload["enrichments"])
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    return {}


def _build_tag_merge_payload(tags_body: Any) -> list[dict[str, Any]]:
    existing_tags = tags_body.get("tags") if isinstance(tags_body, dict) else []
    if isinstance(existing_tags, list) and existing_tags:
        first = existing_tags[0] if isinstance(existing_tags[0], dict) else {}
        merged_concepts = sorted({*(first.get("concepts") or []), "2"})
        merged = {
            "id": str(first.get("id") or "round2-merged"),
            "label": str(first.get("label") or "Round 2 Merged"),
            "color": str(first.get("color") or "#10b981"),
            "concepts": merged_concepts,
        }
    else:
        merged = {
            "id": "round2-merged",
            "label": "Round 2 Merged",
            "color": "#10b981",
            "concepts": ["1", "2"],
        }
    extra = {
        "id": "round2-extra",
        "label": "Round 2 Extra",
        "color": "#2563eb",
        "concepts": ["1"],
    }
    return [merged, extra]


def _spectrogram_url(speaker: str, start_sec: float, end_sec: float, *, audio: str | None = None, force: bool = False) -> str:
    params = {
        "speaker": speaker,
        "start": f"{start_sec:.3f}",
        "end": f"{end_sec:.3f}",
    }
    if audio:
        params["audio"] = audio
    if force:
        params["force"] = "1"
    return f"/api/spectrogram?{urllib.parse.urlencode(params)}"


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


def _normalize_sections(raw_sections: Any) -> tuple[str, ...]:
    if isinstance(raw_sections, str):
        text = raw_sections.strip()
        return (text,) if text else tuple()
    if not isinstance(raw_sections, list):
        return tuple()
    sections: list[str] = []
    for item in raw_sections:
        text = str(item or "").strip()
        if text:
            sections.append(text)
    return tuple(sections)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _validate_reason_text(rule_id: str, reason: str | None) -> None:
    if not reason:
        raise ValueError(f"Permanent allowlist rule {rule_id} must include a reason")
    if PLACEHOLDER_REASON_RE.search(reason):
        raise ValueError(f"Permanent allowlist rule {rule_id} still contains a TODO/TBD placeholder")


def _normalize_string(value: str, context: CanonicalizationContext | None) -> str:
    text = value.replace("\r\n", "\n")
    if TIMESTAMP_VALUE_RE.match(text):
        return "<timestamp>"
    if UUID_VALUE_RE.match(text):
        return "<uuid>"
    if CHAT_SESSION_VALUE_RE.match(text):
        return "<session-id>"
    text = _normalize_path_text(text, context)
    text = TIMESTAMP_INLINE_RE.sub("<timestamp>", text)
    text = MCP_GENERATED_MODEL_NAME_RE.sub(r"\1", text)
    text = HEX_ADDRESS_RE.sub("<hex-addr>", text)
    text = TRACEBACK_LINE_RE.sub("line <line>", text)
    return text


def _normalize_path_text(value: str, context: CanonicalizationContext | None) -> str:
    normalized = value.replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    if context is None:
        return normalized
    for root in context.workspace_roots.values():
        root_text = root.as_posix().rstrip("/")
        normalized = normalized.replace(root_text, "<workspace>")
    for root in context.repo_roots.values():
        root_text = root.as_posix().rstrip("/")
        normalized = normalized.replace(root_text, "<repo>")
    return normalized


def _sort_normalized_list(path: str, items: list[Any]) -> list[Any]:
    if not items:
        return items
    if _path_has_no_sort_semantics(path):
        return items

    if all(_is_scalar(item) for item in items):
        if _path_supports_scalar_sort(path):
            return sorted(items, key=lambda item: str(item))
        return items

    if all(isinstance(item, dict) for item in items):
        if _path_supports_tag_sort(path):
            return sorted(items, key=lambda item: (str(item.get("id") or ""), str(item.get("label") or "")))
        if _path_supports_source_wav_sort(path):
            return sorted(items, key=lambda item: (str(item.get("filename") or item.get("path") or ""), bool(item.get("is_primary"))))
        if _path_supports_resource_sort(path):
            return sorted(items, key=lambda item: (str(item.get("kind") or ""), str(item.get("id") or "")))
        if _path_supports_job_sort(path):
            return sorted(items, key=lambda item: (str(item.get("jobId") or item.get("job_id") or ""), str(item.get("type") or "")))
    return items


def _path_has_no_sort_semantics(path: str) -> bool:
    return any(
        path.endswith(suffix)
        for suffix in (
            ".states",
            ".intervals",
            ".logs",
            ".matches",
            ".messages",
            ".steps_run",
        )
    )


def _path_supports_scalar_sort(path: str) -> bool:
    return any(
        path.endswith(suffix)
        for suffix in (
            ".concepts",
            ".missedLabels",
            ".primary_contact_languages",
            ".speakers_included",
            ".concepts_included",
            ".providers",
            ".languages_requested",
            ".sources",
            ".forms",
        )
    )


def _path_supports_tag_sort(path: str) -> bool:
    return path.endswith(".tags") or path.endswith("parse-tags.json")


def _path_supports_source_wav_sort(path: str) -> bool:
    return path.endswith(".source_wavs")


def _path_supports_resource_sort(path: str) -> bool:
    return path.endswith(".resources")


def _path_supports_job_sort(path: str) -> bool:
    return path.endswith(".jobs")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _collect_diffs(section: str, path: str, oracle_value: Any, rebuild_value: Any) -> list[DiffEntry]:
    if isinstance(oracle_value, dict) and isinstance(rebuild_value, dict):
        diffs: list[DiffEntry] = []
        keys = sorted(set(oracle_value.keys()) | set(rebuild_value.keys()))
        for key in keys:
            child_path = f"{path}.{key}"
            diffs.extend(_collect_diffs(section, child_path, oracle_value.get(key), rebuild_value.get(key)))
        return diffs

    if isinstance(oracle_value, list) and isinstance(rebuild_value, list):
        diffs: list[DiffEntry] = []
        max_length = max(len(oracle_value), len(rebuild_value))
        for index in range(max_length):
            child_path = f"{path}[{index}]"
            oracle_item = oracle_value[index] if index < len(oracle_value) else None
            rebuild_item = rebuild_value[index] if index < len(rebuild_value) else None
            diffs.extend(_collect_diffs(section, child_path, oracle_item, rebuild_item))
        return diffs

    if oracle_value != rebuild_value:
        return [DiffEntry(section=section, path=path, oracle_value=oracle_value, rebuild_value=rebuild_value)]
    return []


def _render_diff_entry(entry: DiffEntry, *, include_allowlist: bool = False) -> list[str]:
    lines = [
        f"### {entry.section} — {entry.path}",
        "",
    ]
    if include_allowlist:
        lines.extend(
            [
                f"- Rule: `{entry.allowlist_rule_id}`",
                f"- Classification: `{entry.classification or 'unspecified'}`",
                f"- Permanence: `{entry.permanence or 'unspecified'}`",
                f"- Reason: {entry.reason or 'n/a'}",
                f"- Reason ref: {entry.reason_ref or 'n/a'}",
                "",
            ]
        )
    lines.extend(
        [
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
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
