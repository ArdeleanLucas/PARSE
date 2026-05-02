"""PARSE server route-domain module: IPA candidate review sidecars."""
from __future__ import annotations

import json
import threading

import server as _server


_IPA_REVIEW_LOCK = threading.RLock()
_VALID_REVIEW_STATUSES = {"needs_review", "auto_accepted", "accepted", "rejected"}


def _annotation_not_found(speaker: str) -> _server.ApiError:
    return _server.ApiError(_server.HTTPStatus.NOT_FOUND, "No annotation file for speaker: {0}".format(speaker))


def _read_annotation_for_sidecars(speaker_part: str) -> tuple[str, _server.pathlib.Path, _server.pathlib.Path, _server.pathlib.Path, _server.Dict[str, _server.Any]]:
    try:
        speaker = _server._normalize_speaker_id(speaker_part)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc)) from exc
    try:
        annotation_path, canonical_path, legacy_path = _server._annotation_paths_for_speaker(speaker)
    except RuntimeError as exc:
        raise _annotation_not_found(speaker) from exc
    raw = _server._read_json_file(annotation_path, {})
    if not isinstance(raw, dict):
        raise _annotation_not_found(speaker)
    annotation = _server._normalize_annotation_record(raw, speaker)
    return speaker, annotation_path, canonical_path, legacy_path, annotation


def _atomic_write_json(path: _server.pathlib.Path, payload: _server.Dict[str, _server.Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _atomic_write_annotation_to_paths(
    annotation_path: _server.pathlib.Path,
    canonical_path: _server.pathlib.Path,
    legacy_path: _server.pathlib.Path,
    annotation: _server.Dict[str, _server.Any],
) -> None:
    _atomic_write_json(annotation_path, annotation)
    if canonical_path != annotation_path:
        _atomic_write_json(canonical_path, annotation)
    if legacy_path != annotation_path:
        _atomic_write_json(legacy_path, annotation)


def _validate_review_state(payload: _server.Any) -> _server.Dict[str, _server.Any]:
    if not isinstance(payload, dict):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "Review payload must be a JSON object")
    raw_status = payload.get("status")
    if not isinstance(raw_status, str) or raw_status not in _VALID_REVIEW_STATUSES:
        raise _server.ApiError(
            _server.HTTPStatus.BAD_REQUEST,
            "status must be one of {0}".format(", ".join(sorted(_VALID_REVIEW_STATUSES))),
        )
    evidence_sources = payload.get("evidence_sources", [])
    if evidence_sources is None:
        evidence_sources = []
    if not isinstance(evidence_sources, list) or not all(isinstance(item, str) for item in evidence_sources):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "evidence_sources must be a list of strings")
    return {
        "status": raw_status,
        "suggested_ipa": payload.get("suggested_ipa", "") if isinstance(payload.get("suggested_ipa", ""), str) else str(payload.get("suggested_ipa")),
        "resolution_type": payload.get("resolution_type", "") if isinstance(payload.get("resolution_type", ""), str) else str(payload.get("resolution_type")),
        "evidence_sources": list(evidence_sources),
        "notes": payload.get("notes", "") if isinstance(payload.get("notes", ""), str) else str(payload.get("notes")),
    }


def _api_get_ipa_candidates(self, speaker_part: str) -> None:
    """GET /api/annotations/<speaker>/ipa-candidates."""
    _speaker, _annotation_path, _canonical_path, _legacy_path, annotation = _read_annotation_for_sidecars(speaker_part)
    candidates = annotation.get("ipa_candidates") if isinstance(annotation.get("ipa_candidates"), dict) else {}
    review = annotation.get("ipa_review") if isinstance(annotation.get("ipa_review"), dict) else {}
    self._send_json(_server.HTTPStatus.OK, {"candidates": candidates, "review": review})


def _api_put_ipa_review(self, speaker_part: str, key: str) -> None:
    """PUT /api/annotations/<speaker>/ipa-review/<key>."""
    if not isinstance(key, str) or not key:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "Review key is required")
    body = self._read_json_body(required=True)
    review_state = _validate_review_state(body)
    with _IPA_REVIEW_LOCK:
        _speaker, annotation_path, canonical_path, legacy_path, annotation = _read_annotation_for_sidecars(speaker_part)
        review = annotation.get("ipa_review")
        if not isinstance(review, dict):
            review = {}
            annotation["ipa_review"] = review
        review[key] = review_state
        _server._annotation_touch_metadata(annotation, preserve_created=True)
        _atomic_write_annotation_to_paths(annotation_path, canonical_path, legacy_path, annotation)
    self._send_json(_server.HTTPStatus.OK, {"review": review_state})


__all__ = [
    "_api_get_ipa_candidates",
    "_api_put_ipa_review",
]
