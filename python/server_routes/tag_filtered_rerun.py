"""PARSE server route-domain module: tag-filtered concept query + lexeme rerun."""
from __future__ import annotations

import server as _server
from app.http.lexeme_rerun_handlers import build_post_run_ipa_response, build_post_run_ortho_response
from app.http.tag_filtered_rerun_handlers import (
    TagFilteredHandlerError,
    build_post_concepts_by_tag_response,
    build_post_lexemes_rerun_by_tag_response,
)
from server_routes.lexeme_rerun import _run_ipa_interval, _run_ortho_interval
from server_routes.locks import _locks_dir


def _load_tags_vocab() -> list[dict]:
    from storage import tags_store

    return list(tags_store.fetch_all().get("tags", []))


def _write_tagged_rerun_annotation(speaker: str, annotation_path: _server.pathlib.Path, annotation: dict) -> None:
    canonical_path = _server._annotation_record_path_for_speaker(speaker)
    legacy_path = _server._annotation_legacy_record_path_for_speaker(speaker)
    _server._write_annotation_to_canonical_and_legacy(annotation_path, canonical_path, legacy_path, annotation)


def _api_post_concepts_by_tag(self) -> None:
    try:
        body = self._expect_object(self._read_json_body(), "body")
        response = build_post_concepts_by_tag_response(
            body,
            project_root=_server._project_root(),
            load_tags_vocab=_load_tags_vocab,
            annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker,
            read_json_any_file=_server._read_json_any_file,
            normalize_annotation_record=_server._normalize_annotation_record,
        )
    except TagFilteredHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


def _api_post_lexemes_rerun_by_tag(self) -> None:
    try:
        body = self._expect_object(self._read_json_body(), "body")
        response = build_post_lexemes_rerun_by_tag_response(
            body,
            project_root=_server._project_root(),
            load_tags_vocab=_load_tags_vocab,
            normalize_speaker_id=_server._normalize_speaker_id,
            annotation_read_path_for_speaker=_server._annotation_read_path_for_speaker,
            read_json_any_file=_server._read_json_any_file,
            normalize_annotation_record=_server._normalize_annotation_record,
            resolve_audio_path_for_speaker=_server._pipeline_audio_path_for_speaker,
            run_ipa_interval=_run_ipa_interval,
            run_ortho_interval=_run_ortho_interval,
            build_post_run_ipa_response=build_post_run_ipa_response,
            build_post_run_ortho_response=build_post_run_ortho_response,
            locks_dir=_locks_dir(),
            create_job=_server._create_job,
            launch_compute_runner=_server._launch_compute_runner,
            job_conflict_error_cls=_server.JobResourceConflictError,
            annotation_writer=_write_tagged_rerun_annotation,
            annotation_touch_metadata=_server._annotation_touch_metadata,
            align_ortho_words=_server._align_partial_ortho_words,
        )
    except TagFilteredHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


__all__ = ["_api_post_concepts_by_tag", "_api_post_lexemes_rerun_by_tag"]
