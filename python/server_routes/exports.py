"""PARSE server route-domain module: exports."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import server as _server
from canonical_lexemes import drop_canonical_references_for
from concept_relink import ConceptRelinkError, apply_relink_by_gloss, build_relink_by_gloss_plan
from concepts_io import ConceptDeleteError, delete_concept_variant
from storage import tags_store
from survey_overlap import load_survey_overlap_state, update_survey_overlap_state

_LOGGER = logging.getLogger(__name__)

def _api_get_export_lingpy(self) -> None:
    """Stream LingPy-compatible wordlist TSV as a file download."""
    response = _server._app_build_get_export_lingpy_response(export_wordlist_tsv=_server.cognate_compute_module.export_wordlist_tsv, enrichments_path=_server._enrichments_path(), annotations_dir=_server._project_root() / 'annotations')
    self.send_response(response.status)
    self.send_header('Content-Type', response.content_type)
    self.send_header('Content-Disposition', response.content_disposition)
    self.send_header('Content-Length', str(len(response.body)))
    self.end_headers()
    self.wfile.write(response.body)

def _api_get_export_nexus(self) -> None:
    """Emit a NEXUS character matrix compatible with BEAST2.

    One character per (concept, cognate group). For each speaker:
      1  — speaker is in this cognate group for the concept
      0  — speaker has a form for the concept but sits in a different group
      ?  — speaker has no form / unreviewed for the concept
    Manual overrides in ``manual_overrides.cognate_sets`` take precedence
    over the auto-computed ``cognate_sets`` block.
    """
    response = _server._app_build_get_export_nexus_response(enrichments_path=_server._enrichments_path(), project_json_path=_server._project_json_path(), read_json_file=_server._read_json_file, default_enrichments_payload=_server._default_enrichments_payload, concept_sort_key=_server._concept_sort_key, project_root=_server._project_root())
    self.send_response(response.status)
    self.send_header('Content-Type', response.content_type)
    self.send_header('Content-Disposition', response.content_disposition)
    self.send_header('Content-Length', str(len(response.body)))
    self.end_headers()
    try:
        self.wfile.write(response.body)
    except BrokenPipeError:
        pass

def _api_post_concepts_import(self) -> None:
    """Merge source_item/source_survey/custom_order from an uploaded CSV into concepts.csv."""
    try:
        response = _server._app_build_concepts_import_response(headers=self.headers, rfile=self.rfile, project_root=_server._project_root(), normalize_concept_id=_server._normalize_concept_id, upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES)
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


def _api_post_concepts_relink_by_gloss(self) -> None:
    """Dry-run or apply strict canonical-gloss concept relinking."""
    payload = self._read_json_body(required=False)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
    try:
        if bool(payload.get("apply")):
            result = apply_relink_by_gloss(
                _server._project_root(),
                accepted_groups=payload.get("accepted_groups") if "accepted_groups" in payload else None,
            )
            if result.get("error") == "fuzzy_candidates_require_manual_relabel":
                raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, "fuzzy_candidates_require_manual_relabel")
        else:
            result = build_relink_by_gloss_plan(_server._project_root())
    except ConceptRelinkError as exc:
        raise _server.ApiError(_server.HTTPStatus(exc.status), exc.message) from exc
    except OSError as exc:
        raise _server.ApiError(_server.HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)) from exc
    self._send_json(_server.HTTPStatus.OK, result)


def _api_post_tags_import(self) -> None:
    """Import a custom concept list as a TAG with auto-assigned concepts."""
    try:
        response = _server._app_build_tags_import_response(headers=self.headers, rfile=self.rfile, project_root=_server._project_root(), normalize_concept_id=_server._normalize_concept_id, concept_sort_key=_server._concept_sort_key, upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES)
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _drop_concept_tags_from_annotations(annotations_dir: Path, concept_id: str) -> None:
    """Best-effort removal of one concept_tags entry from every annotation file."""
    if not annotations_dir.is_dir():
        return
    for annotation_path in sorted(annotations_dir.glob('*.json')):
        try:
            data = json.loads(annotation_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        concept_tags = data.get('concept_tags')
        if not isinstance(concept_tags, dict) or concept_id not in concept_tags:
            continue
        concept_tags.pop(concept_id, None)
        data['concept_tags'] = concept_tags
        tmp = annotation_path.with_suffix('.json.tmp')
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(annotation_path)
        except OSError as exc:
            _LOGGER.warning("Failed to drop concept tag sidecar %s from %s: %s", concept_id, annotation_path, exc)


def _drop_global_tag_concept_membership(concept_id: str) -> None:
    """Best-effort removal of one concept id from global tag memberships."""
    try:
        current = tags_store.fetch_all()
    except OSError as exc:
        _LOGGER.warning("Failed to drop deleted concept from global tags: fetch failed: %s", exc)
        return
    changed = False
    next_tags = []
    for tag in current.get("tags", []):
        concepts = list(tag.get("concepts", []))
        filtered = [cid for cid in concepts if cid != concept_id]
        if filtered != concepts:
            changed = True
        next_tags.append({**tag, "concepts": filtered})
    if not changed:
        return
    try:
        tags_store.replace_all(next_tags)
    except (OSError, tags_store.TagValidationError) as exc:
        _LOGGER.warning("Failed to drop deleted concept from global tags: write failed: %s", exc)


def _drop_survey_link_overrides(project_root: Path, concept_id: str) -> None:
    """Best-effort removal of speaker-scoped survey-link overrides for one concept."""
    try:
        state = load_survey_overlap_state(project_root)
        speaker_links = state.get("speaker_concept_survey_links", {})
        next_speaker_links = {
            speaker: {cid: dict(links) for cid, links in concept_links.items() if cid != concept_id}
            for speaker, concept_links in speaker_links.items()
        }
        next_speaker_links = {speaker: links for speaker, links in next_speaker_links.items() if links}
        if next_speaker_links == speaker_links:
            return
        update_survey_overlap_state(
            project_root,
            {
                "reset_speaker_concept_survey_links": True,
                "speaker_concept_survey_links": next_speaker_links,
            },
        )
    except Exception as exc:
        _LOGGER.warning("Failed to drop deleted concept survey-link overrides: %s", exc)


def _drop_canonical_references(project_root: Path, concept_id: str) -> None:
    """Best-effort removal of canonical selections for one deleted concept row."""
    try:
        drop_canonical_references_for(project_root, row_id=concept_id)
    except Exception as exc:
        _LOGGER.warning("Failed to drop deleted concept canonical references: %s", exc)


def _api_delete_concept(self, concept_id: str) -> None:
    """Delete one concepts.csv row and clean best-effort sidecars.

    ``?cascade=true`` first purges the blocking recordings from every annotation
    file (each backed up) so an annotated garbage variant can be removed.
    """
    query = _server.parse_qs(_server.urlparse(self.path).query)
    cascade = str((query.get("cascade") or [""])[0]).strip().lower() in ("1", "true", "yes")
    try:
        payload = delete_concept_variant(_server._project_root(), concept_id, cascade=cascade)
    except ConceptDeleteError as exc:
        body: dict[str, object] = {"error": exc.message}
        if exc.blocking_speakers:
            body["blocking_speakers"] = exc.blocking_speakers
        self._send_json(exc.status, body)
        return
    deleted_id = str(payload["deleted_id"])
    _drop_concept_tags_from_annotations(_server._annotations_dir_path(), deleted_id)
    _drop_global_tag_concept_membership(deleted_id)
    _drop_survey_link_overrides(_server._project_root(), deleted_id)
    _drop_canonical_references(_server._project_root(), deleted_id)
    self._send_json(_server.HTTPStatus.OK, payload)


def _api_post_concept_survey_link(self, concept_id: str) -> None:
    """Add a sidecar concept_survey_links entry for an existing concept."""
    try:
        response = _server._app_build_concept_survey_link_post_response(
            headers=self.headers,
            rfile=self.rfile,
            project_root=_server._project_root(),
            concept_id=concept_id,
            upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES,
        )
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


def _api_post_concept_promote_survey_primary(self, concept_id: str) -> None:
    """Promote one existing survey link into the concepts.csv primary link."""
    try:
        response = _server._app_build_concept_promote_survey_primary_response(
            headers=self.headers,
            rfile=self.rfile,
            project_root=_server._project_root(),
            concept_id=concept_id,
            upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES,
        )
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


def _api_delete_concept_survey_link(self, concept_id: str) -> None:
    """Remove a sidecar concept_survey_links entry; legacy CSV link returns 409."""
    try:
        response = _server._app_build_concept_survey_link_delete_response(
            headers=self.headers,
            rfile=self.rfile,
            project_root=_server._project_root(),
            concept_id=concept_id,
            upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES,
        )
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)


__all__ = ['_api_get_export_lingpy', '_api_get_export_nexus', '_api_post_concepts_import', '_api_post_concepts_relink_by_gloss', '_api_post_tags_import', '_api_delete_concept', '_api_post_concept_survey_link', '_api_post_concept_promote_survey_primary', '_api_delete_concept_survey_link']
