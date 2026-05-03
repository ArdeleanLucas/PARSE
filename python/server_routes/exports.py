"""PARSE server route-domain module: exports."""
from __future__ import annotations

import server as _server

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
    response = _server._app_build_get_export_nexus_response(enrichments_path=_server._enrichments_path(), project_json_path=_server._project_json_path(), read_json_file=_server._read_json_file, default_enrichments_payload=_server._default_enrichments_payload, concept_sort_key=_server._concept_sort_key)
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

def _api_post_tags_import(self) -> None:
    """Import a custom concept list as a TAG with auto-assigned concepts."""
    try:
        response = _server._app_build_tags_import_response(headers=self.headers, rfile=self.rfile, project_root=_server._project_root(), normalize_concept_id=_server._normalize_concept_id, concept_sort_key=_server._concept_sort_key, upload_limit=_server.ONBOARD_MAX_UPLOAD_BYTES)
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

__all__ = ['_api_get_export_lingpy', '_api_get_export_nexus', '_api_post_concepts_import', '_api_post_tags_import']

