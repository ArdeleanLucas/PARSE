from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from ..chat_tools import (
    ANNOTATION_FILENAME_SUFFIX,
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    _project_loaded_condition,
    _tool_condition,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


ARTIFACT_TOOL_NAMES = (
    "peaks_generate",
    "source_index_validate",
)


ARTIFACT_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "peaks_generate": ChatToolSpec(
                    name="peaks_generate",
                    description=(
                        "Generate waveform peak data for a speaker's audio and write to "
                        "peaks/<speaker>.json (or a custom outputPath). Required for the "
                        "waveform visualiser after audio changes. Provide speaker or audioPath."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speaker": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "Speaker ID — resolves audio from annotations.",
                            },
                            "audioPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Explicit audio file path (absolute or project-relative). Overrides speaker lookup.",
                            },
                            "outputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Where to write peaks JSON. Defaults to peaks/<speaker>.json.",
                            },
                            "samplesPerPixel": {
                                "type": "integer",
                                "minimum": 64,
                                "maximum": 8192,
                                "description": "Samples per waveform pixel (default 512).",
                            },
                            "dryRun": {"type": "boolean", "description": "Compute peaks but do not write to disk."},
                        },
                    },
                ),
    "source_index_validate": ChatToolSpec(
                    name="source_index_validate",
                    description=(
                        "Validate a speaker manifest entry or full manifest against the SourceIndex schema. "
                        "Two modes:\n"
                        "  speaker — validate + transform one speaker entry; returns errors and transformed shape\n"
                        "  full    — validate + build the complete source_index.json; "
                        "optionally write to outputPath inside the project"
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["speaker", "full"],
                                "description": "Validation scope (default: speaker).",
                            },
                            "speakerId": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "Speaker ID (required for mode=speaker).",
                            },
                            "speakerData": {
                                "type": "object",
                                "description": "Speaker manifest entry to validate (required for mode=speaker).",
                            },
                            "manifest": {
                                "type": "object",
                                "description": "Full manifest with top-level 'speakers' key (required for mode=full).",
                            },
                            "outputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Write built source_index.json here (mode=full only, project-relative or absolute inside project).",
                            },
                            "dryRun": {
                                "type": "boolean",
                                "description": "If true, never writes outputPath even when provided; returns the validated/constructed payload only.",
                            },
                        },
                    },
                ),
}


def peaks_generate(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate waveform peak data; resolves audio from annotation source_audio when only speaker given."""
        try:
            from peaks import (  # type: ignore[import]
                generate_peaks_for_audio,
                build_peaks_payload,
                write_peaks_json,
            )
        except Exception as exc:
            raise ChatToolExecutionError("peaks is not importable: {0}".format(exc))

        speaker_raw = str(args.get("speaker") or "").strip()
        audio_path_str = str(args.get("audioPath") or "").strip()
        output_path_str = str(args.get("outputPath") or "").strip()
        samples_per_pixel = int(args.get("samplesPerPixel") or 512)
        dry_run = bool(args.get("dryRun", False))

        if not speaker_raw and not audio_path_str:
            raise ChatToolValidationError("speaker or audioPath is required")

        if audio_path_str:
            audio_path = tools._resolve_readable_path(audio_path_str)
        else:
            speaker = tools._normalize_speaker(speaker_raw)
            ann_path = tools.annotations_dir / "{0}{1}".format(speaker, ANNOTATION_FILENAME_SUFFIX)
            if not ann_path.exists():
                raise ChatToolExecutionError("No annotation found for speaker: {0}".format(speaker))
            ann_data = json.loads(ann_path.read_text(encoding="utf-8"))
            source_audio = str(ann_data.get("source_audio") or "").strip()
            if not source_audio:
                raise ChatToolExecutionError(
                    "Speaker {0} annotation has no source_audio field".format(speaker)
                )
            audio_path = tools._resolve_readable_path(source_audio)

        if not audio_path.exists():
            raise ChatToolExecutionError("Audio file not found: {0}".format(audio_path))

        try:
            sample_rate, peak_data, total_samples = generate_peaks_for_audio(
                audio_path, samples_per_pixel
            )
        except Exception as exc:
            raise ChatToolExecutionError("peaks generation failed: {0}".format(exc)) from exc

        payload = build_peaks_payload(sample_rate, samples_per_pixel, peak_data)

        if dry_run:
            return {
                "readOnly": True,
                "previewOnly": True,
                "sampleRate": sample_rate,
                "samplesPerPixel": samples_per_pixel,
                "totalSamples": total_samples,
                "peakCount": len(peak_data) // 2,
                "durationSec": round(total_samples / sample_rate, 3) if sample_rate else None,
            }

        if output_path_str:
            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
        elif speaker_raw:
            speaker = tools._normalize_speaker(speaker_raw)
            out_path = tools.peaks_dir / "{0}.json".format(speaker)
        else:
            out_path = tools.peaks_dir / "{0}.json".format(audio_path.stem)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_peaks_json(out_path, payload)
        return {
            "success": True,
            "outputPath": str(out_path),
            "sampleRate": sample_rate,
            "samplesPerPixel": samples_per_pixel,
            "totalSamples": total_samples,
            "peakCount": len(peak_data) // 2,
            "durationSec": round(total_samples / sample_rate, 3) if sample_rate else None,
        }


def source_index_validate(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a speaker manifest entry or full manifest; optionally write source_index.json."""
        try:
            from source_index import validate_speaker, transform_speaker, build_source_index  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("source_index is not importable: {0}".format(exc))

        import io as _io

        def _call(fn: Any, *fn_args: Any) -> Tuple[bool, List[str], Any]:
            """Invoke a source_index function; capture stderr and catch SystemExit."""
            old_stderr = sys.stderr
            sys.stderr = _io.StringIO()
            result = None
            try:
                result = fn(*fn_args)
                errors: List[str] = []
                ok = True
            except SystemExit:
                raw = sys.stderr.getvalue()
                errors = [
                    line.replace("ERROR: ", "", 1).strip()
                    for line in raw.strip().splitlines()
                    if line.strip()
                ]
                ok = False
            finally:
                sys.stderr = old_stderr
            return ok, errors, result

        mode = str(args.get("mode") or "speaker").strip().lower()

        if mode == "speaker":
            speaker_id = str(args.get("speakerId") or "").strip()
            if not speaker_id:
                raise ChatToolValidationError("speakerId is required for mode=speaker")
            speaker_data = args.get("speakerData")
            if not isinstance(speaker_data, dict):
                raise ChatToolValidationError("speakerData must be an object for mode=speaker")

            valid, errors, _ = _call(validate_speaker, speaker_id, speaker_data)
            transformed = None
            if valid:
                ok2, errs2, transformed = _call(transform_speaker, speaker_id, speaker_data)
                if not ok2:
                    valid = False
                    errors = errs2

            return {
                "readOnly": True,
                "mode": "speaker",
                "speakerId": speaker_id,
                "valid": valid,
                "errors": errors,
                "transformed": transformed,
            }

        if mode == "full":
            manifest = args.get("manifest")
            if not isinstance(manifest, dict):
                raise ChatToolValidationError("manifest must be an object for mode=full")
            output_path_str = str(args.get("outputPath") or "").strip()

            valid, errors, source_index = _call(build_source_index, manifest)

            if not valid or source_index is None:
                return {"readOnly": True, "mode": "full", "valid": False, "errors": errors}

            speaker_count = len(source_index.get("speakers") or {})
            wav_count = sum(
                len(v.get("source_wavs") or [])
                for v in (source_index.get("speakers") or {}).values()
            )

            if output_path_str and not bool(args.get("dryRun", False)):
                out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(source_index, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return {
                    "success": True,
                    "mode": "full",
                    "valid": True,
                    "errors": [],
                    "speakerCount": speaker_count,
                    "wavCount": wav_count,
                    "outputPath": str(out_path),
                }

            return {
                "readOnly": True,
                "previewOnly": True,
                "mode": "full",
                "valid": True,
                "errors": [],
                "speakerCount": speaker_count,
                "wavCount": wav_count,
                "sourceIndex": source_index,
                "dryRun": bool(args.get("dryRun", False)),
            }

        raise ChatToolValidationError("mode must be 'speaker' or 'full'")


ARTIFACT_TOOL_HANDLERS = {
    "peaks_generate": peaks_generate,
    "source_index_validate": source_index_validate,
}


__all__ = [
    "ARTIFACT_TOOL_NAMES",
    "ARTIFACT_TOOL_SPECS",
    "ARTIFACT_TOOL_HANDLERS",
    "peaks_generate",
    "source_index_validate",
]
