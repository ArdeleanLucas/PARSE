"""Shared per-concept rerun loop used by Lane A's HTTP route and the
chat-tool MCP wrapper.

Both ``app.http.tag_filtered_rerun_handlers._per_concept_rerun`` and
``ai.tools.tag_filter_tools._per_concept_rerun`` previously implemented
the same per-tier dispatch (``ortho`` then ``ipa``, with status/statusCode
propagation Lane A pinned in fix-up cabc9a9). They delegate to this
helper so future contract changes (e.g. a third tier, or different lock
semantics) land in a single place.

The dispatch is dependency-injected — every server-side helper is a
callable parameter — so neither caller pulls server globals into the
shared module.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, List, Optional

from app.services.tag_resolver import ConceptHit


logger = logging.getLogger(__name__)


SpeakerNormalizer = Callable[[Any], str]
AnnotationPathResolver = Callable[[str], Path]
JsonAnyReader = Callable[[Path], Any]
AnnotationNormalizer = Callable[[Any, str], dict]
AudioPathResolver = Callable[[str], Path]
IntervalRunner = Callable[..., str]
PerIntervalHandler = Callable[..., Any]


def per_concept_rerun(
    speaker: str,
    hit: ConceptHit,
    field: str,
    pad: float,
    *,
    project_root: Path,
    locks_dir: Optional[Path],
    normalize_speaker_id: SpeakerNormalizer,
    annotation_read_path_for_speaker: AnnotationPathResolver,
    read_json_any_file: JsonAnyReader,
    normalize_annotation_record: AnnotationNormalizer,
    resolve_audio_path_for_speaker: AudioPathResolver,
    run_ortho_interval: IntervalRunner,
    run_ipa_interval: IntervalRunner,
    build_post_run_ortho_response: PerIntervalHandler,
    build_post_run_ipa_response: PerIntervalHandler,
    lexeme_rerun_handler_error: type,
) -> List[dict]:
    """Run ORTH then IPA (or one of them) for a single concept hit.

    ``lexeme_rerun_handler_error`` is the exception class raised by the
    per-interval handlers — passed in as a parameter so the chat-tool
    caller (which lazy-imports it) and the HTTP-route caller (which
    imports at module load) share this loop without a hard import here.

    Returns one ``{speaker, conceptId, field, status, statusCode?, text?, error?}``
    entry per tier executed, mirroring the contract Lane A pinned in
    fix-up cabc9a9.
    """
    fields_to_run: List[str] = []
    if field in ("ortho", "both"):
        fields_to_run.append("ortho")
    if field in ("ipa", "both"):
        fields_to_run.append("ipa")

    body = {
        "speaker": speaker,
        "concept_key": hit.conceptId,
        "start": hit.start,
        "end": hit.end,
        "pad": pad,
        "async": False,
    }

    out: List[dict] = []
    for tier_field in fields_to_run:
        kwargs: dict = {
            "project_root": project_root,
            "normalize_speaker_id": normalize_speaker_id,
            "annotation_read_path_for_speaker": annotation_read_path_for_speaker,
            "read_json_any_file": read_json_any_file,
            "normalize_annotation_record": normalize_annotation_record,
            "resolve_audio_path_for_speaker": resolve_audio_path_for_speaker,
            "locks_dir": locks_dir,
        }
        if tier_field == "ortho":
            kwargs["run_ortho_interval"] = run_ortho_interval
            handler = build_post_run_ortho_response
        else:
            kwargs["run_ipa_interval"] = run_ipa_interval
            handler = build_post_run_ipa_response

        entry: dict = {
            "speaker": speaker,
            "conceptId": hit.conceptId,
            "field": tier_field,
        }
        try:
            response = handler(body, **kwargs)
            entry["status"] = "ok"
            payload = getattr(response, "payload", None)
            if isinstance(payload, dict):
                value = payload.get(tier_field)
                if isinstance(value, str):
                    entry["text"] = value
        except lexeme_rerun_handler_error as exc:
            # Preserve the per-interval handler's HTTP status so callers
            # can distinguish "concept not found" (404) from "speaker
            # locked" (409) from "runner died" (500) without parsing
            # error strings.
            entry["status"] = "error"
            entry["statusCode"] = int(getattr(exc, "status", HTTPStatus.INTERNAL_SERVER_ERROR))
            entry["error"] = getattr(exc, "message", str(exc))
        except Exception as exc:
            entry["status"] = "error"
            entry["statusCode"] = int(HTTPStatus.INTERNAL_SERVER_ERROR)
            entry["error"] = str(exc)
        out.append(entry)
    return out


__all__ = ["per_concept_rerun"]
