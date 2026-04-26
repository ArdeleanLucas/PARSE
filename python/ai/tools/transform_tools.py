from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from ..chat_tools import (
    ChatToolError,
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


TRANSFORM_TOOL_NAMES = (
    "phonetic_rules_apply",
    "transcript_reformat",
)


TRANSFORM_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "phonetic_rules_apply": ChatToolSpec(
                    name="phonetic_rules_apply",
                    description=(
                        "Apply the project phonetic rules to IPA forms. Three modes:\n"
                        "  normalize — strip delimiters, lowercase, normalise whitespace\n"
                        "  apply     — return all rule-generated variants of a form\n"
                        "  equivalence — compare two forms; returns isEquivalent + similarity score\n"
                        "Uses project phonetic_rules.json unless custom rules are supplied."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["form"],
                        "properties": {
                            "form": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 256,
                                "description": "Primary IPA form to operate on.",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["normalize", "apply", "equivalence"],
                                "description": "Operation mode (default: normalize).",
                            },
                            "form2": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 256,
                                "description": "Second form for equivalence mode.",
                            },
                            "rules": {
                                "type": "array",
                                "maxItems": 64,
                                "items": {"type": "object"},
                                "description": (
                                    "Optional inline rule list (same schema as phonetic_rules.json entries). "
                                    "Omit to use the project file."
                                ),
                            },
                        },
                    },
                ),
    "transcript_reformat": ChatToolSpec(
                    name="transcript_reformat",
                    description=(
                        "Reformat a *_coarse.json alignment file into PARSE CoarseTranscript schema "
                        "(speaker, source_wav, duration_sec, segments[]). Without outputPath returns "
                        "the reformatted JSON object; with outputPath writes inside the project."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["inputPath"],
                        "properties": {
                            "inputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Path to the *_coarse.json file to reformat (absolute or project-relative).",
                            },
                            "outputPath": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Project-relative or absolute path inside project root to write the result.",
                            },
                            "speaker": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 200,
                                "description": "Override speaker ID (inferred from filename if omitted).",
                            },
                            "sourceWav": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 512,
                                "description": "Override source WAV path written into the output metadata.",
                            },
                            "durationSec": {
                                "type": "number",
                                "minimum": 0.0,
                                "description": "Override total duration in seconds (inferred from segments if omitted).",
                            },
                            "dryRun": {"type": "boolean", "description": "Return parsed JSON without writing."},
                        },
                    },
                ),
}


def phonetic_rules_apply(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize, apply, or compare IPA forms using project phonetic rules."""
        try:
            from compare.phonetic_rules import (  # type: ignore[import]
                apply_rules,
                are_phonetically_equivalent,
                load_rules_from_file,
                normalize_ipa_form,
            )
        except Exception as exc:
            raise ChatToolExecutionError("phonetic_rules is not importable: {0}".format(exc))

        form = str(args.get("form") or "").strip()
        if not form:
            raise ChatToolValidationError("form is required")

        mode = str(args.get("mode") or "normalize").strip().lower()
        inline_rules = args.get("rules")

        if isinstance(inline_rules, list) and inline_rules:
            rules = inline_rules
        else:
            rules = load_rules_from_file(tools.phonetic_rules_path)

        try:
            if mode == "normalize":
                result = normalize_ipa_form(form)
                return {"readOnly": True, "mode": "normalize", "form": form, "normalized": result}

            if mode == "apply":
                normalized = normalize_ipa_form(form)
                variants = apply_rules(normalized, rules)
                return {
                    "readOnly": True,
                    "mode": "apply",
                    "form": form,
                    "normalized": normalized,
                    "variants": variants,
                }

            if mode == "equivalence":
                form2 = str(args.get("form2") or "").strip()
                if not form2:
                    raise ChatToolValidationError("form2 is required for equivalence mode")
                is_equiv, score = are_phonetically_equivalent(form, form2, rules)
                return {
                    "readOnly": True,
                    "mode": "equivalence",
                    "form": form,
                    "form2": form2,
                    "isEquivalent": is_equiv,
                    "similarityScore": round(score, 4),
                }

            raise ChatToolValidationError("Unknown mode: {0}".format(mode))
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("phonetic_rules_apply failed: {0}".format(exc)) from exc


def transcript_reformat(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        """Convert *_coarse.json alignment to CoarseTranscript schema. Dry-run returns parsed object."""
        import os as _os
        import tempfile

        input_path_str = str(args.get("inputPath") or "").strip()
        if not input_path_str:
            raise ChatToolValidationError("inputPath is required")

        output_path_str = str(args.get("outputPath") or "").strip()
        dry_run = bool(args.get("dryRun", False))
        speaker = str(args.get("speaker") or "").strip() or None
        source_wav = str(args.get("sourceWav") or "").strip() or None
        duration_sec_raw = args.get("durationSec")
        duration_sec = float(duration_sec_raw) if duration_sec_raw is not None else None

        input_path = tools._resolve_readable_path(input_path_str)
        if not input_path.exists():
            raise ChatToolExecutionError("inputPath does not exist: {0}".format(input_path))

        try:
            from reformat_transcripts import reformat  # type: ignore[import]
        except Exception as exc:
            raise ChatToolExecutionError("reformat_transcripts is not importable: {0}".format(exc))

        try:
            if dry_run or not output_path_str:
                tmp_fd, tmp_str = tempfile.mkstemp(suffix=".json")
                _os.close(tmp_fd)
                tmp_path = Path(tmp_str)
                try:
                    reformat(str(input_path), speaker, source_wav, duration_sec, str(tmp_path))
                    result_data = json.loads(tmp_path.read_text(encoding="utf-8"))
                finally:
                    try:
                        _os.unlink(tmp_str)
                    except OSError:
                        pass
                return {"readOnly": True, "previewOnly": True, "result": result_data}

            out_path = tools._resolve_project_path(output_path_str, allowed_roots=[tools.project_root])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            reformat(str(input_path), speaker, source_wav, duration_sec, str(out_path))
            return {"success": True, "outputPath": str(out_path)}
        except ChatToolError:
            raise
        except Exception as exc:
            raise ChatToolExecutionError("transcript_reformat failed: {0}".format(exc)) from exc


TRANSFORM_TOOL_HANDLERS = {
    "phonetic_rules_apply": phonetic_rules_apply,
    "transcript_reformat": transcript_reformat,
}


__all__ = [
    "TRANSFORM_TOOL_NAMES",
    "TRANSFORM_TOOL_SPECS",
    "TRANSFORM_TOOL_HANDLERS",
    "phonetic_rules_apply",
    "transcript_reformat",
]
