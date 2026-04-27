from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from ..chat_tools import ChatToolExecutionError, ChatToolSpec, ChatToolValidationError

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


ACOUSTIC_STARTER_TOOL_NAMES = (
    "stt_start",
    "stt_word_level_start",
    "forced_align_start",
    "ipa_transcribe_acoustic_start",
    "compute_boundaries_start",
    "retranscribe_with_boundaries_start",
    "audio_normalize_start",
)


ACOUSTIC_STARTER_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "stt_start": ChatToolSpec(
        name="stt_start",
        description=(
            "Start a bounded STT background job for a project audio file. "
            "Returns a jobId for polling with stt_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "sourceWav"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                "language": {"type": "string", "minLength": 1, "maxLength": 32},
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, validate inputs and preview the STT job without launching it.",
                },
            },
        },
    ),
    "stt_word_level_start": ChatToolSpec(
        name="stt_word_level_start",
        description=(
            "Start a word-level STT job (Tier 1 acoustic alignment). "
            "Segments are returned with a nested words[] array of "
            "(word, start, end, prob) spans from faster-whisper's "
            "word_timestamps=True output. Mirrors stt_start but the "
            "name is explicit about Tier 1 semantics so agents can "
            "distinguish word-level jobs from plain sentence-level "
            "STT. Returns a jobId for polling with stt_word_level_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "sourceWav"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "sourceWav": {"type": "string", "minLength": 1, "maxLength": 512},
                "language": {"type": "string", "minLength": 1, "maxLength": 32},
                "dryRun": {"type": "boolean"},
            },
        },
    ),
    "forced_align_start": ChatToolSpec(
        name="forced_align_start",
        description=(
            "Start a Tier 2 forced-alignment job for a speaker. Runs "
            "torchaudio.functional.forced_align against "
            "facebook/wav2vec2-xlsr-53-espeak-cv-ft on each word window "
            "from the speaker's Tier 1 STT output, producing tight per-"
            "word (and optional per-phoneme) boundaries. G2P is used "
            "only internally to build CTC targets and is discarded; no "
            "G2P output is persisted. Returns a jobId for polling with "
            "forced_align_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "overwrite": {
                    "type": "boolean",
                    "description": "When true, replaces an existing aligned artifact (default: false).",
                },
                "language": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 8,
                    "description": "espeak-ng language code for the internal G2P step (default: ku)",
                },
                "padMs": {"type": "integer", "minimum": 0, "maximum": 500},
                "emitPhonemes": {"type": "boolean"},
                "dryRun": {"type": "boolean"},
            },
        },
    ),
    "ipa_transcribe_acoustic_start": ChatToolSpec(
        name="ipa_transcribe_acoustic_start",
        description=(
            "Start a Tier 3 acoustic IPA job. Runs "
            "facebook/wav2vec2-xlsr-53-espeak-cv-ft CTC on each ortho "
            "interval's audio window and writes the decoded phoneme "
            "string into the speaker's IPA tier. wav2vec2 is the ONLY "
            "IPA engine — there are no text-based fallbacks. Equivalent "
            "to the ipa_only compute job exposed in the UI under "
            "Actions → Run IPA transcription. Returns a jobId for "
            "polling with ipa_transcribe_acoustic_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "overwrite": {
                    "type": "boolean",
                    "description": "When true, replaces existing non-empty IPA cells (default: false).",
                },
                "dryRun": {"type": "boolean"},
            },
        },
    ),
    "retranscribe_with_boundaries_start": ChatToolSpec(
        name="retranscribe_with_boundaries_start",
        description=(
            "Start a boundary-constrained STT job for a speaker. Reads the speaker's "
            "BND lane (tiers.ortho_words) as authoritative segment boundaries, slices "
            "the source audio in memory at each window, and runs faster-whisper on each "
            "slice independently. Writes the merged segments to coarse_transcripts/<speaker>.json "
            "with source=boundary_constrained. Returns a jobId for polling with "
            "retranscribe_with_boundaries_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "language": {
                    "type": "string",
                    "minLength": 0,
                    "maxLength": 8,
                    "description": "Optional ISO 639-1 language code for faster-whisper. Empty/omitted triggers auto-detect.",
                },
                "dryRun": {"type": "boolean"},
            },
        },
    ),
    "compute_boundaries_start": ChatToolSpec(
        name="compute_boundaries_start",
        description=(
            "Start a standalone BND (Boundaries) job for a speaker. Runs Tier 2 forced "
            "alignment on cached STT word timestamps and writes the refined word boundaries "
            "to tiers.ortho_words without rerunning Whisper or IPA. Returns a jobId for polling "
            "with compute_boundaries_status."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "overwrite": {
                    "type": "boolean",
                    "description": "When true, discards manuallyAdjusted ortho_words intervals and rebuilds the lane fully.",
                },
                "dryRun": {"type": "boolean"},
            },
        },
    ),
    "audio_normalize_start": ChatToolSpec(
        name="audio_normalize_start",
        description=(
            "Start an audio normalization job for a speaker (two-pass ffmpeg loudnorm: "
            "mono, 44.1 kHz, -16 LUFS). Returns a jobId; poll with audio_normalize_status. "
            "sourceWav is optional — defaults to the speaker's primary source audio."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "sourceWav": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 512,
                    "description": "Project-relative or absolute path to source WAV. Omit to use primary source.",
                },
                "dryRun": {
                    "type": "boolean",
                    "description": "If true, preview the normalize job without launching ffmpeg.",
                },
            },
        },
    ),
}


def tool_stt_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    if tools._start_stt_job is None:
        raise ChatToolExecutionError("STT start callback is unavailable")

    speaker = tools._normalize_speaker(args.get("speaker"))
    source_wav = str(args.get("sourceWav") or "").strip()
    if not source_wav:
        raise ChatToolValidationError("sourceWav is required")

    safe_path = tools._resolve_project_path(source_wav, allowed_roots=[tools.audio_dir])
    project_relative = safe_path.relative_to(tools.project_root).as_posix()

    language_raw = args.get("language")
    language = str(language_raw).strip() if language_raw is not None else None
    if language == "":
        language = None

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "stt_start",
            "plan": {
                "speaker": speaker,
                "sourceWav": project_relative,
                "language": language,
            },
            "message": "Dry run. Would start an STT job for the requested audio file.",
        }

    job_id = tools._start_stt_job(speaker, project_relative, language)

    return {
        "readOnly": True,
        "previewOnly": True,
        "jobId": job_id,
        "status": "running",
        "speaker": speaker,
        "sourceWav": project_relative,
        "message": "STT job started. Poll with stt_status.",
    }


def tool_stt_word_level_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Start a Tier 1 word-level STT job.

    STT now always runs with word_timestamps=True (Tier 1), so this
    delegates to the same callback as stt_start but the tool name
    documents the expectation that segments[].words[] is present in
    the output.
    """
    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "stt_word_level_start",
            "speaker": tools._normalize_speaker(args.get("speaker")),
            "note": (
                "Dry run. Tier 1 STT would run with word_timestamps=True; "
                "segments would include a nested words[] array."
            ),
        }

    payload = tool_stt_start(tools, args)
    payload["tier"] = "tier1_word_level"
    payload["message"] = "Word-level STT job started. Poll with stt_word_level_status."
    return payload


def tool_forced_align_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Start a Tier 2 forced-alignment compute job."""
    speaker = tools._normalize_speaker(args.get("speaker"))

    language_raw = args.get("language")
    language = str(language_raw).strip() if language_raw is not None else "ku"
    if not language:
        language = "ku"

    pad_ms_raw = args.get("padMs", 100)
    try:
        pad_ms = int(pad_ms_raw)
    except (TypeError, ValueError):
        pad_ms = 100
    pad_ms = max(0, min(500, pad_ms))

    emit_phonemes = bool(args.get("emitPhonemes", True))
    overwrite = bool(args.get("overwrite", False))

    payload_body: Dict[str, Any] = {
        "speaker": speaker,
        "overwrite": overwrite,
        "language": language,
        "padMs": pad_ms,
        "emitPhonemes": emit_phonemes,
    }

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "forced_align_start",
            "plan": payload_body,
            "note": (
                "Dry run. Would launch a forced_align compute job against "
                "facebook/wav2vec2-xlsr-53-espeak-cv-ft. G2P output is "
                "used only to build CTC targets and is never persisted."
            ),
        }

    if tools._start_compute_job is None:
        raise ChatToolExecutionError(
            "Compute-job start callback is unavailable — wire ParseChatTools "
            "with start_compute_job to enable Tier 2 forced alignment."
        )

    job_id = tools._start_compute_job("forced_align", payload_body)

    return {
        "readOnly": True,
        "previewOnly": True,
        "jobId": job_id,
        "status": "running",
        "tier": "tier2_forced_align",
        "speaker": speaker,
        "message": "Forced-alignment job started. Poll with forced_align_status.",
    }


def tool_ipa_transcribe_acoustic_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Start a Tier 3 acoustic IPA job (wav2vec2 on audio slices)."""
    speaker = tools._normalize_speaker(args.get("speaker"))
    overwrite = bool(args.get("overwrite", False))

    payload_body: Dict[str, Any] = {
        "speaker": speaker,
        "overwrite": overwrite,
    }

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "ipa_transcribe_acoustic_start",
            "plan": payload_body,
            "note": (
                "Dry run. Would launch the ipa_only compute job, running "
                "facebook/wav2vec2-xlsr-53-espeak-cv-ft CTC on each ortho "
                "interval's audio window. No text-based IPA paths exist."
            ),
        }

    if tools._start_compute_job is None:
        raise ChatToolExecutionError(
            "Compute-job start callback is unavailable — wire ParseChatTools "
            "with start_compute_job to enable Tier 3 acoustic IPA."
        )

    job_id = tools._start_compute_job("ipa_only", payload_body)

    return {
        "readOnly": True,
        "previewOnly": True,
        "jobId": job_id,
        "status": "running",
        "tier": "tier3_acoustic_ipa",
        "speaker": speaker,
        "overwrite": overwrite,
        "message": (
            "Acoustic IPA job started. Poll with "
            "ipa_transcribe_acoustic_status."
        ),
    }


def tool_retranscribe_with_boundaries_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
    language_raw = args.get("language")
    language = str(language_raw).strip() if language_raw is not None else ""

    payload_body: Dict[str, Any] = {"speaker": speaker}
    if language:
        payload_body["language"] = language

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "retranscribe_with_boundaries_start",
            "plan": payload_body,
            "note": (
                "Dry run. Would launch the retranscribe_with_boundaries compute job, "
                "slicing the source audio at each tiers.ortho_words interval and running "
                "faster-whisper on each slice in memory. Writes the merged segments to "
                "coarse_transcripts/<speaker>.json with source=boundary_constrained."
            ),
        }

    if tools._start_compute_job is None:
        raise ChatToolExecutionError(
            "Compute-job start callback is unavailable — wire ParseChatTools with "
            "start_compute_job to enable boundary-constrained STT."
        )

    job_id = tools._start_compute_job("retranscribe_with_boundaries", payload_body)
    return {
        "readOnly": True,
        "previewOnly": True,
        "jobId": job_id,
        "status": "running",
        "tier": "boundary_constrained_stt",
        "speaker": speaker,
        "language": language or None,
        "message": "Boundary-constrained STT job started. Poll with retranscribe_with_boundaries_status.",
    }


def tool_compute_boundaries_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    speaker = tools._normalize_speaker(args.get("speaker"))
    overwrite = bool(args.get("overwrite", False))
    payload_body: Dict[str, Any] = {
        "speaker": speaker,
        "overwrite": overwrite,
    }

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "compute_boundaries_start",
            "plan": payload_body,
            "note": (
                "Dry run. Would launch the boundaries compute job, running Tier 2 forced alignment "
                "on cached STT word timestamps and writing the refined word boundaries to tiers.ortho_words."
            ),
        }

    if tools._start_compute_job is None:
        raise ChatToolExecutionError(
            "Compute-job start callback is unavailable — wire ParseChatTools with start_compute_job to enable standalone BND."
        )

    job_id = tools._start_compute_job("boundaries", payload_body)
    return {
        "readOnly": True,
        "previewOnly": True,
        "jobId": job_id,
        "status": "running",
        "tier": "tier2_boundaries_only",
        "speaker": speaker,
        "overwrite": overwrite,
        "message": "Boundaries job started. Poll with compute_boundaries_status.",
    }


def tool_audio_normalize_start(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Start a two-pass ffmpeg loudnorm job; returns jobId for polling."""
    if tools._start_normalize_job is None:
        raise ChatToolExecutionError("normalize callback is unavailable")

    speaker = tools._normalize_speaker(args.get("speaker"))
    source_wav: Optional[str] = str(args.get("sourceWav") or "").strip() or None

    if bool(args.get("dryRun", False)):
        return {
            "readOnly": True,
            "previewOnly": True,
            "status": "dry_run",
            "tool": "audio_normalize_start",
            "plan": {
                "speaker": speaker,
                "sourceWav": source_wav,
            },
            "message": "Dry run. Would start an audio normalize job for this speaker.",
        }

    try:
        job_id = tools._start_normalize_job(speaker, source_wav)
    except Exception as exc:
        raise ChatToolExecutionError("normalize start failed: {0}".format(exc)) from exc

    return {
        "jobId": str(job_id),
        "status": "running",
        "speaker": speaker,
        "message": "Normalize job started. Poll with audio_normalize_status.",
    }


ACOUSTIC_STARTER_TOOL_HANDLERS = {
    "stt_start": tool_stt_start,
    "stt_word_level_start": tool_stt_word_level_start,
    "forced_align_start": tool_forced_align_start,
    "ipa_transcribe_acoustic_start": tool_ipa_transcribe_acoustic_start,
    "compute_boundaries_start": tool_compute_boundaries_start,
    "retranscribe_with_boundaries_start": tool_retranscribe_with_boundaries_start,
    "audio_normalize_start": tool_audio_normalize_start,
}
