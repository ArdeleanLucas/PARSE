"""Tag-filter MCP chat tools — Lane C wrapper around Lane A's resolver.

Two tools:

* ``list_concepts_by_tag`` — read-only query that mirrors
  ``POST /api/concepts/by-tag``. Returns ``{totalConcepts, perSpeaker,
  unknownTags, ambiguousTags}`` so the chat agent can show the user which
  concepts WILL be touched before any rerun is dispatched.

* ``rerun_lexemes_by_tag`` — runs the per-interval ORTH/IPA helpers
  once per matched concept hit, mirroring the
  ``POST /api/lexemes/rerun-by-tag`` synchronous shape. Returns
  ``{jobId, resolved, total, results}``; per-concept failures surface
  as ``results[i].statusCode`` (preserving Lane A fix-up cabc9a9's
  contract) without aborting the batch.

Strict label boundaries — mirrored verbatim from Lane A
``app.http.tag_filtered_rerun_handlers`` (PR #321 fix-up cabc9a9):

* ``match='all'`` with any unknown OR ambiguous label → 400 with the
  message format ``"match='all' requires every tagLabel to resolve to
  exactly one tag; ..."``.
* ``rerun_lexemes_by_tag`` with any ambiguous label, even under
  ``match='any'`` → 409 with ``"rerun-by-tag refuses to disambiguate;
  ambiguous tagLabels: ..."``. Silently disambiguating would consume
  GPU and overwrite annotations on a concept set the caller never
  approved.

The MCP tools call Lane A's pure resolver in
``app.services.tag_resolver`` directly — they do NOT go through the
HTTP layer. The server does not need to be running.
"""
from __future__ import annotations

import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Sequence

from app.services.audio_paths import pipeline_audio_path_for_speaker
from app.services.lexeme_rerun_loop import per_concept_rerun as _shared_per_concept_rerun
from app.services.speaker_id import normalize_speaker_id as _shared_normalize_speaker_id
from app.services.tag_resolver import (
    ConceptHit,
    ResolvedTags,
    SpeakerExpansionError,
    expand_speakers,
    resolve_tag_labels,
    select_concepts_by_tag,
)

from ..chat_tools import ChatToolSpec

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools

# ``app.http.lexeme_rerun_handlers`` and ``server_routes.lexeme_rerun`` are
# imported lazily inside the rerun handler. Importing them at module load
# time creates a cycle: ``app.http.__init__`` re-exports
# ``external_api_handlers`` which imports ``ai.chat_tools``, which in turn
# imports this module. Lazy-loading at first-use breaks the cycle without
# changing observable behaviour.
build_post_run_ortho_response: Any = None
build_post_run_ipa_response: Any = None
LexemeRerunHandlerError: Any = None  # populated by _ensure_rerun_imports()


def _ensure_rerun_imports() -> None:
    """Late-bind the rerun helpers on first call. Tests monkeypatch the
    module-level names; we only assign them if they're still ``None`` so a
    monkeypatched stub survives subsequent calls.
    """
    global build_post_run_ortho_response, build_post_run_ipa_response, LexemeRerunHandlerError
    if LexemeRerunHandlerError is not None:
        return
    from app.http.lexeme_rerun_handlers import (
        LexemeRerunHandlerError as _Err,
        build_post_run_ipa_response as _ipa,
        build_post_run_ortho_response as _ortho,
    )

    LexemeRerunHandlerError = _Err
    if build_post_run_ortho_response is None:
        build_post_run_ortho_response = _ortho
    if build_post_run_ipa_response is None:
        build_post_run_ipa_response = _ipa

logger = logging.getLogger(__name__)

_PAD_VALUES = (0.0, 0.2, 0.5)
_VALID_FIELDS = ("ipa", "ortho", "both")
_VALID_MATCH = ("any", "all")


TAG_FILTER_TOOL_NAMES = (
    "list_concepts_by_tag",
    "rerun_lexemes_by_tag",
)


# Description text for ``match`` is fixed — keep these constants single-source so
# Lane A and Lane C can't drift. The exact "ANY = the union ... ALL = the
# intersection" wording was specified by the handoff for the LLM's benefit.
_MATCH_DESCRIPTION = (
    "ANY = the union: a concept is included if it carries at least one of the "
    "selected tags. Use for broad discovery and batching. "
    "ALL = the intersection: a concept is included only if it carries every "
    "selected tag. Use for precise filtering."
)


TAG_FILTER_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "list_concepts_by_tag": ChatToolSpec(
        name="list_concepts_by_tag",
        description=(
            "Resolve a tag query and return matched concepts per speaker without "
            "running any STT/IPA work. Useful as the dry-run preview before "
            "calling rerun_lexemes_by_tag. " + _MATCH_DESCRIPTION
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speakers", "tagLabels"],
            "properties": {
                "speakers": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 200}, "minItems": 0, "maxItems": 500},
                        {"type": "string", "enum": ["all"]},
                    ]
                },
                "tagLabels": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "match": {"type": "string", "enum": list(_VALID_MATCH), "default": "any"},
            },
        },
    ),
    "rerun_lexemes_by_tag": ChatToolSpec(
        name="rerun_lexemes_by_tag",
        description=(
            "Run ORTH and/or IPA per concept that matches the tag query, returning "
            "the rerun text per (speaker, conceptId, field). Synchronous — jobId is "
            "always null. Per-concept failures populate results[i].statusCode and do "
            "not abort the batch. " + _MATCH_DESCRIPTION + " "
            "Refuses ambiguous tag labels in any mode (409) and refuses "
            "match='all' if any label is unknown OR ambiguous (400) — surface those "
            "to the user instead of running GPU on the wrong concept set."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speakers", "tagLabels", "field"],
            "properties": {
                "speakers": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 200}, "minItems": 0, "maxItems": 500},
                        {"type": "string", "enum": ["all"]},
                    ]
                },
                "tagLabels": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "match": {"type": "string", "enum": list(_VALID_MATCH), "default": "any"},
                "field": {"type": "string", "enum": list(_VALID_FIELDS)},
                "pad": {"type": "number", "enum": list(_PAD_VALUES), "default": 0.2},
            },
        },
    ),
}


def _format_label_list(labels: Sequence[str]) -> str:
    return ", ".join("'{0}'".format(label) for label in labels)


def _format_ambiguous(ambiguous: Mapping[str, Sequence[str]]) -> str:
    return "; ".join(
        "'{0}' -> [{1}]".format(label, ", ".join(candidates))
        for label, candidates in ambiguous.items()
    )


def _all_match_strict_error(resolved: ResolvedTags) -> str | None:
    """Return a 400-style error message if match='all' cannot be honoured.

    Mirrors ``app.http.tag_filtered_rerun_handlers._enforce_all_match_label_strictness``
    verbatim so the FE/MCP/CLI surfaces are interchangeable.
    """
    problems: List[str] = []
    if resolved.unknown:
        problems.append("unknown tagLabels: {0}".format(_format_label_list(resolved.unknown)))
    if resolved.ambiguous:
        problems.append(
            "ambiguous tagLabels (resolve by id or rename in the vocab): {0}".format(
                _format_ambiguous(resolved.ambiguous)
            )
        )
    if not problems:
        return None
    return "match='all' requires every tagLabel to resolve to exactly one tag; {0}".format(
        "; ".join(problems)
    )


def _ambiguous_rerun_error(resolved: ResolvedTags) -> str | None:
    if not resolved.ambiguous:
        return None
    return "rerun-by-tag refuses to disambiguate; ambiguous tagLabels: {0}".format(
        _format_ambiguous(resolved.ambiguous)
    )


def _load_tags_vocab(tools: "ParseChatTools") -> List[Dict[str, Any]]:
    """Load the global tag vocabulary from ``parse-tags.json``.

    The on-disk shape varies by writer — the chat-side tag-import tool writes
    ``[{id, label, color, concepts}, ...]`` directly while the storage helper
    used by the HTTP API writes ``{version, tags: [...]}``. Accept both;
    return a flat list of ``{id, label, color, ...}`` entries.
    """
    path: Path = getattr(tools, "tags_path", None) or (tools.project_root / "parse-tags.json")
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)]
    if isinstance(raw, dict):
        tags = raw.get("tags")
        if isinstance(tags, list):
            return [entry for entry in tags if isinstance(entry, dict)]
    return []


def _id_to_label(vocab: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in vocab:
        tid = entry.get("id")
        label = entry.get("label")
        if isinstance(tid, str) and isinstance(label, str):
            out[tid] = label
    return out


def _hit_to_payload(hit: ConceptHit, id_to_label: Mapping[str, str]) -> Dict[str, Any]:
    return {
        "conceptId": hit.conceptId,
        "name": hit.name,
        "start": hit.start,
        "end": hit.end,
        "tags": [id_to_label.get(tid, tid) for tid in hit.tags],
    }


def _coerce_tag_labels(args: Mapping[str, Any]) -> List[str]:
    raw = args.get("tagLabels")
    if not isinstance(raw, list) or not raw:
        return []
    out: List[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            return []
        out.append(entry)
    return out


def _coerce_match(args: Mapping[str, Any]) -> str | None:
    raw = args.get("match", "any")
    if isinstance(raw, str) and raw in _VALID_MATCH:
        return raw
    return None


def _coerce_field(args: Mapping[str, Any]) -> str | None:
    raw = args.get("field")
    if isinstance(raw, str) and raw in _VALID_FIELDS:
        return raw
    return None


def _coerce_pad(args: Mapping[str, Any]) -> float | None:
    raw = args.get("pad", 0.2)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value not in _PAD_VALUES:
        return None
    return value


def _expand_speakers(args: Mapping[str, Any], project_root: Path) -> tuple[List[str] | None, Dict[str, Any] | None]:
    """Returns (speakers, error_dict_or_None)."""
    raw = args.get("speakers")
    try:
        return expand_speakers(raw, project_root), None
    except SpeakerExpansionError as exc:
        # List with unknown id → 404; bad shape → 400. Mirrors Lane A.
        if isinstance(raw, list):
            return None, {"ok": False, "status": int(HTTPStatus.NOT_FOUND), "error": str(exc)}
        return None, {"ok": False, "status": int(HTTPStatus.BAD_REQUEST), "error": str(exc)}


def _walk_speakers(
    speakers: Sequence[str],
    tag_ids: Sequence[str],
    match: str,
    annotations_dir: Path,
    *,
    id_to_label: Mapping[str, str],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[ConceptHit]], int]:
    per_speaker: Dict[str, Dict[str, Any]] = {}
    by_speaker: Dict[str, List[ConceptHit]] = {}
    total = 0
    for speaker in speakers:
        record = _load_record(annotations_dir, speaker)
        hits = select_concepts_by_tag(record or {}, tag_ids, match=match) if tag_ids else []
        by_speaker[speaker] = hits
        total += len(hits)
        per_speaker[speaker] = {
            "conceptCount": len(hits),
            "concepts": [_hit_to_payload(hit, id_to_label) for hit in hits],
        }
    return per_speaker, by_speaker, total


def _load_record(annotations_dir: Path, speaker: str) -> Dict[str, Any] | None:
    """Read a speaker annotation file. Tries .parse.json then legacy .json."""
    for suffix in (".parse.json", ".json"):
        path = annotations_dir / "{0}{1}".format(speaker, suffix)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_speaker(value: Any) -> str:
    """Delegate to the shared sanitizer in ``app.services.speaker_id``.

    Lane A's HTTP route uses the same helper, so the chat-tool wrapper
    matches the route's exact behaviour and error wording.
    """
    return _shared_normalize_speaker_id(value)


def _read_json_any_file(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_annotation_record(payload: Any, speaker: str) -> Dict[str, Any]:
    """Auto-fill the keys the per-interval rerun handler reads.

    Mirrors the minimum auto-fills in
    ``server_routes/annotate.py::_normalize_annotation_record`` —
    legacy speaker records (no ``concept_tags``, no ``tiers``) need
    these defaults so ``_load_record`` downstream doesn't raise on a
    ``record["concept_tags"]`` lookup. The HTTP normalizer also
    rebuilds tiers / metadata / source_audio_duration_sec; that's
    overkill for the chat-tool callers, which only walk concept-tier
    intervals and read metadata.language_code.
    """
    if not isinstance(payload, dict):
        return {"speaker": speaker, "tiers": {}, "concept_tags": {}}
    record = dict(payload)
    record.setdefault("speaker", speaker)
    record.setdefault("concept_tags", {})
    record.setdefault("tiers", {})
    return record


def _annotation_read_path(project_root: Path) -> Callable[[str], Path]:
    annotations_dir = project_root / "annotations"

    def resolver(speaker: str) -> Path:
        canonical = annotations_dir / "{0}.parse.json".format(speaker)
        if canonical.is_file():
            return canonical
        return annotations_dir / "{0}.json".format(speaker)

    return resolver


def _annotation_writer(project_root: Path) -> Callable[[str, Path, Dict[str, Any]], None]:
    annotations_dir = project_root / "annotations"

    def writer(speaker: str, annotation_path: Path, record: Dict[str, Any]) -> None:
        canonical = annotations_dir / "{0}.parse.json".format(speaker)
        legacy = annotations_dir / "{0}.json".format(speaker)
        for path in (annotation_path, canonical, legacy):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return writer


def _resolve_audio_path(project_root: Path) -> Callable[[str], Path]:
    """Mirror Lane A's HTTP route via ``app.services.audio_paths``.

    The previous implementation hardcoded
    ``audio/working/<speaker>/working.wav``, which silently failed for
    Lucas's thesis corpus where Audition writes per-speaker filenames
    (``audio/working/Saha01/Saha01.wav``). The shared helper reads the
    annotation's ``source_audio`` field and computes the normalized
    working-copy path the same way the HTTP route does.

    Chat-tool callers don't have access to the source-index payload that
    backs ``server._annotation_primary_source_wav``, so
    ``primary_source_wav_for_speaker`` is left ``None`` — modern speakers
    have an explicit ``source_audio`` on the annotation record.
    """
    annotations_dir = project_root / "annotations"

    def read_record(speaker: str) -> Optional[Dict[str, Any]]:
        # Distinguish "no annotation file" (return None → resolver raises
        # 'No annotation found') from "exists but unparseable / non-dict"
        # (return {} → resolver continues source lookup chain and
        # raises 'No source_audio on annotation').
        for suffix in (".parse.json", ".json"):
            path = annotations_dir / "{0}{1}".format(speaker, suffix)
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return {}
                return payload if isinstance(payload, dict) else {}
        return None

    def resolver(speaker: str) -> Path:
        return pipeline_audio_path_for_speaker(
            speaker,
            project_root,
            read_annotation_record=read_record,
        )

    return resolver


def _run_ortho_interval(audio_path: Path, start: float, end: float, language: str | None = None) -> str:
    from server_routes.lexeme_rerun import _run_ortho_interval as _impl

    return _impl(audio_path=audio_path, start=start, end=end, language=language)


def _run_ipa_interval(audio_path: Path, start: float, end: float, language: str | None = None) -> str:
    from server_routes.lexeme_rerun import _run_ipa_interval as _impl

    return _impl(audio_path=audio_path, start=start, end=end, language=language)


def _per_concept_rerun(
    speaker: str,
    hit: ConceptHit,
    field: str,
    pad: float,
    *,
    project_root: Path,
    locks_dir: Path,
) -> List[Dict[str, Any]]:
    """Delegate to ``app.services.lexeme_rerun_loop.per_concept_rerun``.

    The shared helper is also used by Lane A's HTTP route so any contract
    change (per-tier ordering, statusCode propagation, etc.) lands in one
    place.
    """
    _ensure_rerun_imports()

    return _shared_per_concept_rerun(
        speaker,
        hit,
        field,
        pad,
        project_root=project_root,
        locks_dir=locks_dir,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_read_path(project_root),
        read_json_any_file=_read_json_any_file,
        normalize_annotation_record=_normalize_annotation_record,
        resolve_audio_path_for_speaker=_resolve_audio_path(project_root),
        run_ortho_interval=_run_ortho_interval,
        run_ipa_interval=_run_ipa_interval,
        build_post_run_ortho_response=build_post_run_ortho_response,
        build_post_run_ipa_response=build_post_run_ipa_response,
        lexeme_rerun_handler_error=LexemeRerunHandlerError,
    )


def tool_list_concepts_by_tag(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a tag query into per-speaker concept hits without rerunning."""
    labels = _coerce_tag_labels(args)
    if not labels:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "tagLabels must be a non-empty list of strings",
        }
    match = _coerce_match(args)
    if match is None:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "match must be 'any' or 'all'",
        }

    speakers, err = _expand_speakers(args, tools.project_root)
    if err is not None:
        return err

    vocab = _load_tags_vocab(tools)
    resolved = resolve_tag_labels(labels, vocab)

    if match == "all":
        msg = _all_match_strict_error(resolved)
        if msg is not None:
            return {"ok": False, "status": int(HTTPStatus.BAD_REQUEST), "error": msg}

    id_to_label = _id_to_label(vocab)
    tag_ids = list(resolved.ids_by_label.values())
    annotations_dir = tools.project_root / "annotations"
    per_speaker, _by_speaker, total = _walk_speakers(
        speakers or [],
        tag_ids,
        match,
        annotations_dir,
        id_to_label=id_to_label,
    )

    return {
        "ok": True,
        "totalConcepts": total,
        "perSpeaker": per_speaker,
        "unknownTags": list(resolved.unknown),
        "ambiguousTags": dict(resolved.ambiguous),
    }


def tool_rerun_lexemes_by_tag(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    """Run ORTH/IPA per concept hit, returning the locked Lane A shape."""
    labels = _coerce_tag_labels(args)
    if not labels:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "tagLabels must be a non-empty list of strings",
        }
    match = _coerce_match(args)
    if match is None:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "match must be 'any' or 'all'",
        }
    field = _coerce_field(args)
    if field is None:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "field must be one of ipa, ortho, both",
        }
    pad = _coerce_pad(args)
    if pad is None:
        return {
            "ok": False,
            "status": int(HTTPStatus.BAD_REQUEST),
            "error": "pad must be one of 0.0, 0.2, 0.5",
        }

    speakers, err = _expand_speakers(args, tools.project_root)
    if err is not None:
        return err

    vocab = _load_tags_vocab(tools)
    resolved = resolve_tag_labels(labels, vocab)

    if match == "all":
        msg = _all_match_strict_error(resolved)
        if msg is not None:
            return {"ok": False, "status": int(HTTPStatus.BAD_REQUEST), "error": msg}
    msg = _ambiguous_rerun_error(resolved)
    if msg is not None:
        return {"ok": False, "status": int(HTTPStatus.CONFLICT), "error": msg}

    id_to_label = _id_to_label(vocab)
    tag_ids = list(resolved.ids_by_label.values())
    annotations_dir = tools.project_root / "annotations"
    per_speaker, by_speaker, _total_hits = _walk_speakers(
        speakers or [],
        tag_ids,
        match,
        annotations_dir,
        id_to_label=id_to_label,
    )

    locks_dir = tools.project_root / ".parse-locks"
    _ensure_rerun_imports()
    from app.http.tag_filtered_rerun_handlers import LexemesRerunByTagPlan, run_lexemes_rerun_by_tag_loop

    all_hits = [hit for speaker in speakers or [] for hit in by_speaker.get(speaker, [])]
    plan = LexemesRerunByTagPlan(
        labels=labels,
        match=match,
        field=field,
        pad=pad,
        speakers=list(speakers or []),
        resolved=resolved,
        per_speaker=per_speaker,
        all_hits=all_hits,
        by_speaker=by_speaker,
    )
    payload = run_lexemes_rerun_by_tag_loop(
        plan,
        project_root=tools.project_root,
        normalize_speaker_id=_normalize_speaker,
        annotation_read_path_for_speaker=_annotation_read_path(tools.project_root),
        read_json_any_file=_read_json_any_file,
        normalize_annotation_record=_normalize_annotation_record,
        resolve_audio_path_for_speaker=_resolve_audio_path(tools.project_root),
        run_ortho_interval=_run_ortho_interval,
        run_ipa_interval=_run_ipa_interval,
        build_post_run_ortho_response=build_post_run_ortho_response,
        build_post_run_ipa_response=build_post_run_ipa_response,
        locks_dir=locks_dir,
        annotation_writer=_annotation_writer(tools.project_root),
    )

    return {
        "ok": True,
        "jobId": None,
        "resolved": payload["resolved"],
        "total": payload["total"],
        "results": payload["results"],
    }


TAG_FILTER_TOOL_HANDLERS: Dict[str, Callable[["ParseChatTools", Dict[str, Any]], Dict[str, Any]]] = {
    "list_concepts_by_tag": tool_list_concepts_by_tag,
    "rerun_lexemes_by_tag": tool_rerun_lexemes_by_tag,
}


__all__ = [
    "TAG_FILTER_TOOL_HANDLERS",
    "TAG_FILTER_TOOL_NAMES",
    "TAG_FILTER_TOOL_SPECS",
    "tool_list_concepts_by_tag",
    "tool_rerun_lexemes_by_tag",
]
