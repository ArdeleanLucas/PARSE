import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest
import server


def test_server_py_is_thin_orchestrator() -> None:
    server_path = pathlib.Path(server.__file__).resolve()
    line_count = len(server_path.read_text(encoding="utf-8").splitlines())
    assert line_count < 2000, f"python/server.py should be <2000 LoC after decomposition, got {line_count}"


@pytest.mark.parametrize(
    ("module_name", "handler_name"),
    [
        ("annotate", "_api_post_annotation"),
        ("compare", "_api_get_enrichments"),
        ("jobs", "_api_get_jobs"),
        ("exports", "_api_get_export_lingpy"),
        ("config", "_api_get_config"),
        ("clef", "_api_get_clef_config"),
        ("chat", "_api_post_chat_run_start"),
        ("media", "_api_post_normalize"),
    ],
)
def test_route_handlers_are_installed_from_server_routes_modules(module_name: str, handler_name: str) -> None:
    module = __import__(f"server_routes.{module_name}", fromlist=[handler_name])
    assert getattr(server.RangeRequestHandler, handler_name) is getattr(module, handler_name)


@pytest.mark.parametrize(
    ("module_name", "export_name"),
    [
        ("annotate", "_compute_full_pipeline"),
        ("compare", "_api_get_lexeme_search"),
        ("jobs", "_create_job"),
        ("exports", "_api_post_concepts_import"),
        ("config", "_workspace_frontend_config"),
        ("clef", "_compute_contact_lexemes"),
        ("chat", "_run_chat_job"),
        ("media", "_run_stt_job"),
    ],
)
def test_server_re_exports_public_backend_surface_from_route_modules(module_name: str, export_name: str) -> None:
    module = __import__(f"server_routes.{module_name}", fromlist=[export_name])
    assert getattr(server, export_name) is getattr(module, export_name)
    assert inspect.getmodule(getattr(server, export_name)).__name__ == module.__name__
