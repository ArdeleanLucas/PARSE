#!/usr/bin/env python3
"""PARSE MCP Server — expose ParseChatTools as MCP tools for third-party agents.

Starts a stdio MCP server that lets any MCP client (Claude Code, Cursor, Codex,
Windsurf, etc.) call PARSE's linguistic analysis tools programmatically.

Tools exposed (14):
  project_context_read, annotation_read, read_csv_preview,
  cognate_compute_preview, cross_speaker_match_preview, spectrogram_preview,
  contact_lexeme_lookup, stt_start, stt_status,
  import_tag_csv, prepare_tag_import,
  onboard_speaker_import, parse_memory_read, parse_memory_upsert_section

Usage:
    python python/adapters/mcp_adapter.py
    python python/adapters/mcp_adapter.py --project-root /path/to/project
    python python/adapters/mcp_adapter.py --verbose

MCP client config (e.g. claude_desktop_config.json):
    {
        "mcpServers": {
            "parse": {
                "command": "python",
                "args": ["python/adapters/mcp_adapter.py"],
                "env": {
                    "PARSE_PROJECT_ROOT": "/path/to/your/parse/project",
                    "PARSE_EXTERNAL_READ_ROOTS": "/mnt/c/Users/Lucas/Thesis",
                    "PARSE_CHAT_MEMORY_PATH": "/path/to/parse-memory.md"
                }
            }
        }
    }
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("parse.mcp_adapter")

# ---------------------------------------------------------------------------
# Ensure the python/ package is importable
# ---------------------------------------------------------------------------

_ADAPTER_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _ADAPTER_DIR.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

# ---------------------------------------------------------------------------
# Lazy MCP SDK import
# ---------------------------------------------------------------------------

_MCP_AVAILABLE = False
try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------

def _resolve_project_root(cli_root: Optional[str] = None) -> Path:
    """Resolve PARSE project root from CLI arg, env var, or cwd."""
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env_root = os.environ.get("PARSE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    # Fallback: assume the repo root is 2 levels up from this file
    candidate = _ADAPTER_DIR.parent.parent
    if (candidate / "python" / "ai" / "chat_tools.py").exists():
        return candidate
    return Path.cwd()


def _resolve_api_base() -> str:
    """Resolve the HTTP base URL of the running PARSE API server.

    The MCP adapter proxies STT calls through the HTTP server instead of
    running a parallel job manager — this keeps job state consistent with
    the browser UI and avoids forking the in-memory job store.
    """
    port = os.environ.get("PARSE_API_PORT") or os.environ.get("PARSE_PORT") or "8766"
    return "http://127.0.0.1:{0}".format(str(port).strip() or "8766")


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
        try:
            response = _post_json("/api/stt/status", {"job_id": job_id})
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "PARSE API unreachable at {0} — cannot poll STT job. "
                "Underlying error: {1}".format(base_url, exc)
            )
        return response or None

    return start_stt_job, get_job_snapshot


def _resolve_external_read_roots() -> list:
    """Parse PARSE_EXTERNAL_READ_ROOTS from env into a list of Paths.

    Mirrors server._chat_external_read_roots so MCP clients and the in-process
    chat runtime share the same sandbox roots.
    """
    raw = str(os.environ.get("PARSE_EXTERNAL_READ_ROOTS") or "").strip()
    if not raw:
        return []
    sep = ";" if os.name == "nt" or ";" in raw else os.pathsep
    roots: list = []
    for piece in raw.split(sep):
        piece = piece.strip()
        if not piece:
            continue
        candidate = Path(piece).expanduser()
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _resolve_memory_path(project_root_path: Path) -> Path:
    raw = str(os.environ.get("PARSE_CHAT_MEMORY_PATH") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = project_root_path / candidate
        try:
            return candidate.resolve()
        except Exception:
            return candidate
    return (project_root_path / "parse-memory.md").resolve()


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
            with urllib.request.urlopen(req, timeout=120.0) as resp:
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
        deadline = time.time() + 120.0
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


def create_mcp_server(project_root: Optional[str] = None) -> "FastMCP":
    """Create and return the PARSE MCP server with all tools registered.

    Wraps ParseChatTools so every tool available to the built-in AI chat
    is also available over MCP for third-party agents. STT and onboarding
    tools proxy through the running HTTP server on PARSE_API_PORT
    (default 8766) so job state is shared with the browser UI.
    """
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP server requires the 'mcp' package. "
            "Install with: pip install 'mcp[cli]'"
        )

    from ai.chat_tools import ParseChatTools

    root = _resolve_project_root(project_root)
    external_roots = _resolve_external_read_roots()
    memory_path = _resolve_memory_path(root)
    logger.info("PARSE MCP server starting with project root: %s", root)
    if external_roots:
        logger.info("External read roots: %s", ", ".join(str(r) for r in external_roots))
    logger.info("Chat memory path: %s", memory_path)

    start_stt, get_snapshot = _build_stt_callbacks()
    onboard_callback = _build_onboard_callback()
    tools = ParseChatTools(
        project_root=root,
        start_stt_job=start_stt,
        get_job_snapshot=get_snapshot,
        external_read_roots=external_roots,
        memory_path=memory_path,
        onboard_speaker=onboard_callback,
    )

    mcp = FastMCP(
        "parse",
        instructions=(
            "PARSE — Phonetic Analysis & Review Source Explorer. "
            "Linguistic fieldwork tools for annotation, cross-speaker comparison, "
            "cognate analysis, STT pipeline control, and contact-language lookup."
        ),
    )

    # -- Register each ParseChatTools tool as an MCP tool --------------------
    # The cross-check test in python/adapters/test_mcp_adapter.py enforces
    # that every @mcp.tool() below maps to a name in tools.tool_names(), so
    # phantom registrations fail in CI rather than at runtime.

    @mcp.tool()
    def project_context_read(
        include: Optional[list] = None,
        maxSpeakers: Optional[int] = None,
    ) -> str:
        """Read high-level PARSE project context (project metadata, source index summary,
        annotation inventory, and enrichment summary). Read-only.

        Args:
            include: Sections to include (project, source_index, annotation_inventory, enrichments_summary, ai_config, constraints)
            maxSpeakers: Maximum number of speakers to include in summaries
        """
        args: Dict[str, Any] = {}
        if include is not None:
            args["include"] = include
        if maxSpeakers is not None:
            args["maxSpeakers"] = maxSpeakers
        result = tools.execute("project_context_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def annotation_read(
        speaker: str,
        conceptIds: Optional[list] = None,
        includeTiers: Optional[list] = None,
        maxIntervals: Optional[int] = None,
    ) -> str:
        """Read one speaker's annotation data with optional concept/tier filtering. Read-only.

        Args:
            speaker: Speaker name (filename stem from annotations/)
            conceptIds: Filter to specific concept IDs
            includeTiers: Filter to specific tiers (ipa, ortho, concept, speaker)
            maxIntervals: Maximum number of intervals to return
        """
        args: Dict[str, Any] = {"speaker": speaker}
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if includeTiers is not None:
            args["includeTiers"] = includeTiers
        if maxIntervals is not None:
            args["maxIntervals"] = maxIntervals
        result = tools.execute("annotation_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def read_csv_preview(
        csvPath: Optional[str] = None,
        maxRows: Optional[int] = None,
    ) -> str:
        """Read first N rows of a CSV file. Defaults to concepts.csv. Read-only.

        Args:
            csvPath: Path to CSV file (relative to project root, or absolute)
            maxRows: Maximum rows to return (default 20, max 200)
        """
        args: Dict[str, Any] = {}
        if csvPath is not None:
            args["csvPath"] = csvPath
        if maxRows is not None:
            args["maxRows"] = maxRows
        result = tools.execute("read_csv_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def cognate_compute_preview(
        speakers: Optional[list] = None,
        conceptIds: Optional[list] = None,
        threshold: Optional[float] = None,
        contactLanguages: Optional[list] = None,
        includeSimilarity: Optional[bool] = None,
        maxConcepts: Optional[int] = None,
    ) -> str:
        """Compute a read-only cognate/similarity preview from annotations.
        Does not write parse-enrichments.json.

        Args:
            speakers: Filter to specific speakers
            conceptIds: Filter to specific concept IDs
            threshold: Similarity threshold (0.01–2.0)
            contactLanguages: ISO 639 codes for contact languages to compare against
            includeSimilarity: Include pairwise similarity scores
            maxConcepts: Maximum concepts to process
        """
        args: Dict[str, Any] = {}
        if speakers is not None:
            args["speakers"] = speakers
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if threshold is not None:
            args["threshold"] = threshold
        if contactLanguages is not None:
            args["contactLanguages"] = contactLanguages
        if includeSimilarity is not None:
            args["includeSimilarity"] = includeSimilarity
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        result = tools.execute("cognate_compute_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def cross_speaker_match_preview(
        speaker: Optional[str] = None,
        sttJobId: Optional[str] = None,
        sttSegments: Optional[list] = None,
        topK: Optional[int] = None,
        minConfidence: Optional[float] = None,
        maxConcepts: Optional[int] = None,
    ) -> str:
        """Compute read-only cross-speaker match candidates from STT output
        and existing annotations.

        Args:
            speaker: Target speaker to find matches for
            sttJobId: ID of a completed STT job to use as input
            sttSegments: Inline STT segments (alternative to sttJobId)
            topK: Number of top candidates per concept (1–20)
            minConfidence: Minimum confidence threshold (0.0–1.0)
            maxConcepts: Maximum concepts to process
        """
        args: Dict[str, Any] = {}
        if speaker is not None:
            args["speaker"] = speaker
        if sttJobId is not None:
            args["sttJobId"] = sttJobId
        if sttSegments is not None:
            args["sttSegments"] = sttSegments
        if topK is not None:
            args["topK"] = topK
        if minConfidence is not None:
            args["minConfidence"] = minConfidence
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        result = tools.execute("cross_speaker_match_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def spectrogram_preview(
        sourceWav: str,
        startSec: float,
        endSec: float,
        windowSize: Optional[int] = None,
    ) -> str:
        """Generate spectrogram preview for a segment. Read-only.

        Args:
            sourceWav: Path to the source WAV file
            startSec: Start time in seconds
            endSec: End time in seconds
            windowSize: FFT window size (256, 512, 1024, 2048, or 4096)
        """
        args: Dict[str, Any] = {
            "sourceWav": sourceWav,
            "startSec": startSec,
            "endSec": endSec,
        }
        if windowSize is not None:
            args["windowSize"] = windowSize
        result = tools.execute("spectrogram_preview", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def contact_lexeme_lookup(
        dryRun: bool,
        languages: Optional[list] = None,
        conceptIds: Optional[list] = None,
        providers: Optional[list] = None,
        maxConcepts: Optional[int] = None,
        overwrite: Optional[bool] = None,
    ) -> str:
        """Fetch reference forms (IPA) for contact/comparison languages.

        Gated by dryRun — ALWAYS pass dryRun=true first to preview, then
        dryRun=false after the user confirms. Only the second call writes to
        sil_contact_languages.json.

        Args:
            dryRun: Required. If true, preview only (no filesystem writes).
                If false, fetch and merge into sil_contact_languages.json.
            languages: ISO 639 language codes (e.g. ["ar", "fa", "ckb"]).
                Defaults to all configured languages in sil_contact_languages.json.
            conceptIds: Concept labels matching the concept_en column in
                concepts.csv. Defaults to all concepts.
            providers: Provider priority order (csv_override, lingpy_wordlist,
                pycldf, pylexibank, asjp, cldf, wikidata, wiktionary, grokipedia,
                literature).
            maxConcepts: Cap on concepts processed this call (1–200). Useful for
                bounded previews.
            overwrite: When dryRun=false, re-fetch even if forms already exist.
                Ignored when dryRun=true.
        """
        args: Dict[str, Any] = {"dryRun": dryRun}
        if languages is not None:
            args["languages"] = languages
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if providers is not None:
            args["providers"] = providers
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
        if overwrite is not None:
            args["overwrite"] = overwrite
        result = tools.execute("contact_lexeme_lookup", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def stt_start(
        speaker: str,
        sourceWav: str,
        language: Optional[str] = None,
    ) -> str:
        """Start a bounded STT background job for a project audio file.
        Returns a jobId for polling with stt_status.

        Args:
            speaker: Speaker name
            sourceWav: Path to source WAV file (relative to audio/)
            language: Language code hint for the STT model
        """
        args: Dict[str, Any] = {"speaker": speaker, "sourceWav": sourceWav}
        if language is not None:
            args["language"] = language
        result = tools.execute("stt_start", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def stt_status(
        jobId: str,
        includeSegments: Optional[bool] = None,
        maxSegments: Optional[int] = None,
    ) -> str:
        """Read status/progress of an existing STT job.

        Args:
            jobId: The job ID returned by stt_start
            includeSegments: Include transcribed segments in response
            maxSegments: Maximum segments to return (1–300)
        """
        args: Dict[str, Any] = {"jobId": jobId}
        if includeSegments is not None:
            args["includeSegments"] = includeSegments
        if maxSegments is not None:
            args["maxSegments"] = maxSegments
        result = tools.execute("stt_status", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def import_tag_csv(
        dryRun: bool,
        csvPath: Optional[str] = None,
        tagName: Optional[str] = None,
        color: Optional[str] = None,
        labelColumn: Optional[str] = None,
    ) -> str:
        """Import a CSV file as a custom tag list. Use dryRun=true first to preview,
        then dryRun=false after user confirmation.

        Args:
            dryRun: If true, returns preview without writing. Always use true first.
            csvPath: Path to the CSV file
            tagName: Name for the new tag
            color: Hex color code (e.g. #FF0000)
            labelColumn: Column name containing concept labels
        """
        args: Dict[str, Any] = {"dryRun": dryRun}
        if csvPath is not None:
            args["csvPath"] = csvPath
        if tagName is not None:
            args["tagName"] = tagName
        if color is not None:
            args["color"] = color
        if labelColumn is not None:
            args["labelColumn"] = labelColumn
        result = tools.execute("import_tag_csv", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def prepare_tag_import(
        tagName: str,
        conceptIds: list,
        dryRun: bool,
        color: Optional[str] = None,
    ) -> str:
        """Create or update a tag with a list of concept IDs and write to parse-tags.json.
        Use dryRun=true first to preview, then dryRun=false after user confirmation.

        Args:
            tagName: Name for the tag
            conceptIds: List of concept IDs to assign to this tag
            dryRun: If true, returns preview without writing
            color: Hex color code (e.g. #FF0000)
        """
        args: Dict[str, Any] = {
            "tagName": tagName,
            "conceptIds": conceptIds,
            "dryRun": dryRun,
        }
        if color is not None:
            args["color"] = color
        result = tools.execute("prepare_tag_import", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def onboard_speaker_import(
        speaker: str,
        sourceWav: str,
        dryRun: bool,
        sourceCsv: Optional[str] = None,
        isPrimary: Optional[bool] = None,
    ) -> str:
        """Import a new speaker from on-disk audio (and optional transcription CSV).

        Copies the audio into audio/original/<speaker>/, scaffolds an annotation
        record, and registers the speaker in source_index.json. sourceWav/sourceCsv
        may be absolute paths under PARSE_EXTERNAL_READ_ROOTS or project-relative.
        Use dryRun=true first to preview, then dryRun=false to execute.

        Args:
            speaker: Speaker ID (filename-safe, no path separators)
            sourceWav: Path to the source audio file
            dryRun: If true, preview only. Run false to perform the import.
            sourceCsv: Optional path to a transcription CSV to store alongside
            isPrimary: Flag this WAV as the speaker's primary source
        """
        args: Dict[str, Any] = {
            "speaker": speaker,
            "sourceWav": sourceWav,
            "dryRun": dryRun,
        }
        if sourceCsv is not None:
            args["sourceCsv"] = sourceCsv
        if isPrimary is not None:
            args["isPrimary"] = isPrimary
        result = tools.execute("onboard_speaker_import", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def parse_memory_read(
        section: Optional[str] = None,
        maxBytes: Optional[int] = None,
    ) -> str:
        """Read the persistent chat memory markdown (parse-memory.md).

        Records speaker provenance, file origins, user preferences, and session
        context. Read-only. Returns the full document bounded by maxBytes, or a
        specific `## Section` when section is provided.

        Args:
            section: Heading text (without leading `##`). If given, only that
                section is returned.
            maxBytes: Cap on bytes returned (min 512).
        """
        args: Dict[str, Any] = {}
        if section is not None:
            args["section"] = section
        if maxBytes is not None:
            args["maxBytes"] = maxBytes
        result = tools.execute("parse_memory_read", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    def parse_memory_upsert_section(
        section: str,
        body: str,
        dryRun: bool,
    ) -> str:
        """Create or replace a `## Section` block in parse-memory.md.

        Use for persisting user preferences, speaker notes, onboarding decisions,
        and file provenance that should survive across chat turns. The existing
        block under the same heading is overwritten; other sections are untouched.
        Use dryRun=true first to preview, then dryRun=false to write.

        Args:
            section: Section heading (without leading `##`)
            body: Markdown body for the section
            dryRun: If true, returns preview without writing
        """
        args: Dict[str, Any] = {
            "section": section,
            "body": body,
            "dryRun": dryRun,
        }
        result = tools.execute("parse_memory_upsert_section", args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    return mcp


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the PARSE MCP server on stdio."""
    import argparse

    parser = argparse.ArgumentParser(description="PARSE MCP Server")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Path to PARSE project root (default: $PARSE_PROJECT_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging on stderr",
    )
    args = parser.parse_args()

    if not _MCP_AVAILABLE:
        print(
            "Error: MCP server requires the 'mcp' package.\n"
            "Install with: pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    server = create_mcp_server(project_root=args.project_root)

    import asyncio

    async def _run():
        await server.run_stdio_async()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
