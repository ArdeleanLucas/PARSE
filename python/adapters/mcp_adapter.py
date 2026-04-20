#!/usr/bin/env python3
"""PARSE MCP Server — expose ParseChatTools as MCP tools for third-party agents.

Starts a stdio MCP server that lets any MCP client (Claude Code, Cursor, Codex,
Windsurf, etc.) call PARSE's linguistic analysis tools programmatically.

Tools exposed (11):
  project_context_read, annotation_read, read_csv_preview,
  cognate_compute_preview, cross_speaker_match_preview, spectrogram_preview,
  contact_lexeme_lookup, stt_start, stt_status,
  import_tag_csv, prepare_tag_import

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
                    "PARSE_PROJECT_ROOT": "/path/to/your/parse/project"
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


def create_mcp_server(project_root: Optional[str] = None) -> "FastMCP":
    """Create and return the PARSE MCP server with all tools registered.

    Wraps ParseChatTools so every tool available to the built-in AI chat
    is also available over MCP for third-party agents.
    """
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP server requires the 'mcp' package. "
            "Install with: pip install 'mcp[cli]'"
        )

    from ai.chat_tools import ParseChatTools

    root = _resolve_project_root(project_root)
    logger.info("PARSE MCP server starting with project root: %s", root)

    tools = ParseChatTools(project_root=root)

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
        languages: Optional[list] = None,
        conceptIds: Optional[list] = None,
        providers: Optional[list] = None,
        maxConcepts: Optional[int] = None,
    ) -> str:
        """Preview reference forms (IPA) for contact/comparison languages. Read-only —
        returns fetched forms without writing to sil_contact_languages.json. To
        persist results, run the contact-lexemes compute job from the Compare UI.

        Args:
            languages: ISO 639 language codes registered in sil_contact_languages.json
                (e.g. ["ar", "fa", "ckb"]). Defaults to all configured languages.
            conceptIds: Concept labels matching the concept_en column in concepts.csv.
                Defaults to all concepts.
            providers: Provider priority order (csv_override, lingpy_wordlist, pycldf,
                pylexibank, asjp, cldf, wikidata, wiktionary, grokipedia, literature).
            maxConcepts: Cap on concepts processed this call (1–200). Prevents runaway
                fetches for sessions that only want a small sample.
        """
        args: Dict[str, Any] = {}
        if languages is not None:
            args["languages"] = languages
        if conceptIds is not None:
            args["conceptIds"] = conceptIds
        if providers is not None:
            args["providers"] = providers
        if maxConcepts is not None:
            args["maxConcepts"] = maxConcepts
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
