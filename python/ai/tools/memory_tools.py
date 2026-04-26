from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from ..chat_tools import ChatToolExecutionError, ChatToolSpec, ChatToolValidationError, MEMORY_MAX_BYTES

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


MEMORY_TOOL_NAMES = (
    "parse_memory_read",
    "parse_memory_upsert_section",
)


MEMORY_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "parse_memory_read": ChatToolSpec(
        name="parse_memory_read",
        description=(
            "Read PARSE's persistent chat memory markdown (parse-memory.md). This is "
            "where speaker provenance, file origins, user preferences, and session "
            "context are recorded. Read-only. Returns the full document bounded by "
            "maxBytes, or a specific `## Section` when section is provided."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "section": {
                    "type": "string",
                    "maxLength": 200,
                    "description": "Heading text (without leading `##`). If given, only that section is returned.",
                },
                "maxBytes": {
                    "type": "integer",
                    "minimum": 512,
                    "maximum": MEMORY_MAX_BYTES,
                    "description": "Cap on bytes returned. Defaults to full file (up to {0} bytes).".format(MEMORY_MAX_BYTES),
                },
            },
        },
    ),
    "parse_memory_upsert_section": ChatToolSpec(
        name="parse_memory_upsert_section",
        description=(
            "Create or replace a `## Section` block in parse-memory.md. Use for "
            "persisting user preferences, speaker notes, onboarding decisions, and "
            "file provenance that should survive across chat turns. Gated by dryRun — "
            "call dryRun=true first to preview the resulting block, then dryRun=false "
            "after the user confirms. The existing block under the same heading is "
            "overwritten; other sections are left untouched."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["section", "body", "dryRun"],
            "properties": {
                "section": {"type": "string", "minLength": 1, "maxLength": 200},
                "body": {"type": "string", "minLength": 1, "maxLength": 16000},
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, return the rewritten file preview without writing.",
                },
            },
        },
    ),
}


def _memory_normalize_heading(raw: str) -> str:
    return " ".join(str(raw or "").strip().split())


def _memory_match_section(section: str, heading_line: str) -> bool:
    stripped = heading_line.strip()
    if not stripped.startswith("##"):
        return False
    heading_text = stripped.lstrip("#").strip()
    return heading_text.lower() == section.lower()


def _memory_split_sections(content: str) -> List[Tuple[str, str]]:
    """Return [(heading_line_or_empty, body_text), ...] preserving order.

    The first entry has heading_line="" and contains any prelude before the
    first `##` heading. Subsequent entries start with their heading line.
    """
    lines = content.splitlines(keepends=True)
    sections: List[Tuple[str, List[str]]] = [("", [])]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") or stripped == "##":
            sections.append((line.rstrip("\n"), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "".join(body)) for heading, body in sections]


def _memory_read_raw(tools: "ParseChatTools") -> str:
    if not tools.memory_path.exists():
        return ""
    try:
        return tools.memory_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ChatToolExecutionError("Failed to read parse-memory.md: {0}".format(exc)) from exc


def tool_parse_memory_read(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    section_arg = _memory_normalize_heading(args.get("section"))
    max_bytes_raw = args.get("maxBytes")
    try:
        max_bytes = int(max_bytes_raw) if max_bytes_raw is not None else MEMORY_MAX_BYTES
    except (TypeError, ValueError):
        max_bytes = MEMORY_MAX_BYTES
    max_bytes = max(512, min(MEMORY_MAX_BYTES, max_bytes))

    path_display = tools._display_readable_path(tools.memory_path)

    if not tools.memory_path.exists():
        return {
            "ok": True,
            "path": path_display,
            "exists": False,
            "content": "",
            "sections": [],
            "message": "parse-memory.md does not exist yet. Use parse_memory_upsert_section to create it.",
        }

    raw = _memory_read_raw(tools)
    parsed = _memory_split_sections(raw)
    section_headings = [
        heading_line.lstrip("#").strip()
        for heading_line, _body in parsed
        if heading_line
    ]

    if section_arg:
        for heading_line, body in parsed:
            if heading_line and _memory_match_section(section_arg, heading_line):
                content = "{0}\n{1}".format(heading_line, body).strip("\n")
                truncated = False
                encoded = content.encode("utf-8")
                if len(encoded) > max_bytes:
                    content = encoded[:max_bytes].decode("utf-8", errors="ignore")
                    truncated = True
                return {
                    "ok": True,
                    "path": path_display,
                    "exists": True,
                    "section": section_arg,
                    "content": content,
                    "truncated": truncated,
                    "sections": section_headings,
                }
        return {
            "ok": True,
            "path": path_display,
            "exists": True,
            "section": section_arg,
            "found": False,
            "content": "",
            "sections": section_headings,
            "message": "Section not found. Existing sections: {0}".format(
                ", ".join(section_headings) or "(none)"
            ),
        }

    encoded = raw.encode("utf-8")
    truncated = len(encoded) > max_bytes
    content = encoded[:max_bytes].decode("utf-8", errors="ignore") if truncated else raw

    return {
        "ok": True,
        "path": path_display,
        "exists": True,
        "content": content,
        "truncated": truncated,
        "totalBytes": len(encoded),
        "sections": section_headings,
    }


def tool_parse_memory_upsert_section(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    section = _memory_normalize_heading(args.get("section"))
    if not section:
        raise ChatToolValidationError("section is required")

    body = str(args.get("body") or "").rstrip()
    if not body:
        raise ChatToolValidationError("body is required")

    dry_run = bool(args.get("dryRun"))

    try:
        tools.memory_path.relative_to(tools.project_root)
    except ValueError:
        pass

    existing = _memory_read_raw(tools)
    sections = _memory_split_sections(existing) if existing else [("", "")]

    rendered_heading = "## {0}".format(section)
    rendered_section = "{0}\n{1}\n".format(rendered_heading, body)

    updated_parts: List[str] = []
    replaced = False
    for heading_line, section_body in sections:
        if heading_line and _memory_match_section(section, heading_line):
            updated_parts.append(rendered_section)
            replaced = True
        elif not heading_line:
            updated_parts.append(section_body)
        else:
            updated_parts.append("{0}\n{1}".format(heading_line, section_body))

    if not replaced:
        preface = "".join(updated_parts)
        if preface and not preface.endswith("\n"):
            preface = preface + "\n"
        if preface and not preface.endswith("\n\n"):
            preface = preface + "\n"
        if not preface:
            preface = "# PARSE chat memory\n\n"
        updated_content = preface + rendered_section
    else:
        updated_content = "".join(updated_parts)
        if not updated_content.endswith("\n"):
            updated_content = updated_content + "\n"

    if len(updated_content.encode("utf-8")) > MEMORY_MAX_BYTES:
        return {
            "ok": False,
            "error": "parse-memory.md would exceed {0} bytes. Trim an old section first.".format(MEMORY_MAX_BYTES),
        }

    path_display = tools._display_readable_path(tools.memory_path)

    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "path": path_display,
            "section": section,
            "action": "replace" if replaced else "create",
            "previewSection": rendered_section,
            "totalBytesAfter": len(updated_content.encode("utf-8")),
        }

    try:
        tools.memory_path.parent.mkdir(parents=True, exist_ok=True)
        tools.memory_path.write_text(updated_content, encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": "Failed to write parse-memory.md: {0}".format(exc)}

    return {
        "ok": True,
        "dryRun": False,
        "path": path_display,
        "section": section,
        "action": "replace" if replaced else "create",
        "totalBytesAfter": len(updated_content.encode("utf-8")),
        "message": "parse-memory.md {0}d section {1!r}.".format(
            "update" if replaced else "create",
            section,
        ),
    }


MEMORY_TOOL_HANDLERS = {
    "parse_memory_read": tool_parse_memory_read,
    "parse_memory_upsert_section": tool_parse_memory_upsert_section,
}
