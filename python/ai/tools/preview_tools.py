from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from ..chat_tools import (
    ChatToolSpec,
    ChatToolValidationError,
    TEXT_PREVIEW_EXTENSIONS,
    _coerce_float,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


PREVIEW_TOOL_NAMES = (
    "spectrogram_preview",
    "read_audio_info",
    "read_csv_preview",
    "read_text_preview",
)


PREVIEW_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "spectrogram_preview": ChatToolSpec(
        name="spectrogram_preview",
        description=(
            "Validate a speaker/audio time window for spectrogram inspection and return the "
            "normalized request payload. Read-only placeholder until the backend image render "
            "path is wired."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["sourceWav", "startSec", "endSec"],
            "properties": {
                "sourceWav": {"type": "string", "minLength": 1, "maxLength": 1024},
                "startSec": {"type": "number", "minimum": 0.0},
                "endSec": {"type": "number", "minimum": 0.0},
                "windowSize": {"type": "integer", "minimum": 128, "maximum": 8192},
            },
        },
    ),
    "read_audio_info": ChatToolSpec(
        name="read_audio_info",
        description=(
            "Read WAV metadata (duration, channels, sample rate, size) from project or explicitly "
            "allowlisted external roots without loading the full audio into memory. Read-only."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["sourceWav"],
            "properties": {
                "sourceWav": {"type": "string", "minLength": 1, "maxLength": 2048},
            },
        },
    ),
    "read_csv_preview": ChatToolSpec(
        name="read_csv_preview",
        description=(
            "Read the header and first rows of a CSV/TSV file from the project or configured external "
            "read roots. Read-only."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "csvPath": {"type": "string", "minLength": 1, "maxLength": 2048},
                "maxRows": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    ),
    "read_text_preview": ChatToolSpec(
        name="read_text_preview",
        description=(
            "Read a bounded preview of a Markdown/text document from the project/docs root or configured "
            "external read roots. Read-only."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 2048},
                "startLine": {"type": "integer", "minimum": 1, "maximum": 1000000},
                "maxLines": {"type": "integer", "minimum": 1, "maximum": 500},
                "maxChars": {"type": "integer", "minimum": 1, "maximum": 50000},
            },
        },
    ),
}


def tool_spectrogram_preview(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    source_wav = str(args.get("sourceWav") or "").strip()
    if not source_wav:
        raise ChatToolValidationError("sourceWav is required")

    start_sec = _coerce_float(args.get("startSec"), 0.0)
    end_sec = _coerce_float(args.get("endSec"), 0.0)
    if end_sec <= start_sec:
        raise ChatToolValidationError("endSec must be greater than startSec")

    window_size = int(args.get("windowSize", 2048) or 2048)

    safe_audio = tools._resolve_project_path(source_wav, allowed_roots=[tools.audio_dir])

    return {
        "readOnly": True,
        "previewOnly": True,
        "status": "placeholder",
        "message": (
            "Spectrogram preview backend hook acknowledged, but binary/image generation "
            "is not wired in this MVP."
        ),
        "request": {
            "sourceWav": str(safe_audio.relative_to(tools.project_root)),
            "startSec": round(start_sec, 3),
            "endSec": round(end_sec, 3),
            "windowSize": window_size,
        },
        "backendHook": {
            "implemented": False,
            "plannedEndpoint": "/api/compute/spectrograms",
            "notes": "Client-side spectrogram worker remains the active rendering path.",
        },
    }


def tool_read_audio_info(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    import wave as _wave

    source_wav = str(args.get("sourceWav") or "").strip()
    if not source_wav:
        raise ChatToolValidationError("sourceWav is required")

    candidate = Path(source_wav).expanduser()
    if candidate.is_absolute():
        safe_audio = tools._resolve_readable_path(source_wav)
    else:
        safe_audio = tools._resolve_project_path(source_wav, allowed_roots=[tools.audio_dir])

    if not safe_audio.exists() or not safe_audio.is_file():
        return {"ok": False, "error": "File not found: {0}".format(safe_audio)}

    if safe_audio.suffix.lower() != ".wav":
        return {"ok": False, "error": "Not a .wav file: {0}".format(safe_audio.name)}

    try:
        with _wave.open(str(safe_audio), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frame_rate = wav.getframerate()
            n_frames = wav.getnframes()
    except _wave.Error as exc:
        return {"ok": False, "error": "Invalid WAV file: {0}".format(exc)}
    except Exception as exc:
        return {"ok": False, "error": "Failed to read audio file: {0}".format(exc)}

    duration_sec = (n_frames / frame_rate) if frame_rate > 0 else 0.0

    return {
        "ok": True,
        "path": tools._display_readable_path(safe_audio),
        "channels": channels,
        "sampleWidthBytes": sample_width,
        "sampleRateHz": frame_rate,
        "numFrames": n_frames,
        "durationSec": round(duration_sec, 3),
        "fileSizeBytes": safe_audio.stat().st_size,
    }


def tool_read_csv_preview(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    import csv as _csv

    raw_path = str(args.get("csvPath") or "").strip()
    max_rows = int(args.get("maxRows") or 20)

    if raw_path:
        csv_path = tools._resolve_readable_path(raw_path)
    else:
        csv_path = tools.project_root / "concepts.csv"

    if not csv_path.exists():
        return {"ok": False, "error": "File not found: {0}".format(csv_path)}

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            sample = f.read(8192)

        delimiter = ","
        try:
            dialect = _csv.Sniffer().sniff(sample, delimiters=",\t;")
            delimiter = dialect.delimiter
        except Exception:
            pass

        rows: list = []
        total = 0
        columns: list = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f, delimiter=delimiter)
            columns = list(reader.fieldnames or [])
            for row in reader:
                total += 1
                if len(rows) < max_rows:
                    rows.append(dict(row))

        return {
            "ok": True,
            "path": str(csv_path),
            "delimiter": delimiter,
            "columns": columns,
            "totalRows": total,
            "sampleRows": rows,
            "maxRowsShown": min(max_rows, total),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def tool_read_text_preview(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    raw_path = str(args.get("path") or "").strip()
    start_line = int(args.get("startLine") or 1)
    max_lines = int(args.get("maxLines") or 120)
    max_chars = int(args.get("maxChars") or 12000)

    extra_roots: List[Path] = []
    if tools.docs_root is not None:
        extra_roots.append(tools.docs_root)

    try:
        text_path = tools._resolve_readable_path(raw_path, extra_roots=extra_roots)
    except ChatToolValidationError as exc:
        return {"ok": False, "error": str(exc)}

    extension = text_path.suffix.lower()
    if extension not in TEXT_PREVIEW_EXTENSIONS:
        return {
            "ok": False,
            "error": "Unsupported file type: {0}. Allowed: {1}".format(
                extension or "(none)", ", ".join(sorted(TEXT_PREVIEW_EXTENSIONS))
            ),
        }

    if not text_path.exists() or not text_path.is_file():
        return {"ok": False, "error": "File not found: {0}".format(text_path)}

    try:
        lines = text_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return {"ok": False, "error": "Failed to read text file: {0}".format(exc)}

    if start_line < 1:
        start_line = 1

    start_idx = start_line - 1
    if start_idx >= len(lines):
        return {
            "ok": True,
            "path": str(text_path),
            "lineStart": start_line,
            "lineEnd": start_line,
            "totalLines": len(lines),
            "truncated": False,
            "content": "",
            "message": "startLine is beyond end-of-file",
        }

    selected = lines[start_idx:start_idx + max_lines]
    content = "\n".join(selected)
    truncated = False
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True
    if (start_idx + max_lines) < len(lines):
        truncated = True

    return {
        "ok": True,
        "path": str(text_path),
        "lineStart": start_line,
        "lineEnd": start_line + max(0, len(selected) - 1),
        "totalLines": len(lines),
        "truncated": truncated,
        "content": content,
    }


PREVIEW_TOOL_HANDLERS = {
    "spectrogram_preview": tool_spectrogram_preview,
    "read_audio_info": tool_read_audio_info,
    "read_csv_preview": tool_read_csv_preview,
    "read_text_preview": tool_read_text_preview,
}
