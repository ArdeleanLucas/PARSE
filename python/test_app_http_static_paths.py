import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.http.static_paths import (
    dist_dir,
    dist_index_path,
    has_built_frontend,
    resolve_static_request_path,
    static_request_parts,
)


def test_dist_helpers_resolve_from_project_root(tmp_path: pathlib.Path) -> None:
    assert dist_dir(tmp_path) == tmp_path / "dist"
    assert dist_index_path(tmp_path) == tmp_path / "dist" / "index.html"
    assert has_built_frontend(tmp_path) is False



def test_resolve_static_request_path_prefers_dist_assets(tmp_path: pathlib.Path) -> None:
    dist_index = tmp_path / "dist" / "index.html"
    dist_index.parent.mkdir(parents=True)
    dist_index.write_text("<html></html>", encoding="utf-8")
    dist_asset = tmp_path / "dist" / "assets" / "app.js"
    dist_asset.parent.mkdir(parents=True)
    dist_asset.write_text("console.log('ok');", encoding="utf-8")

    resolved = resolve_static_request_path("/assets/app.js", project_root=tmp_path)

    assert resolved == dist_asset



def test_resolve_static_request_path_uses_spa_fallback_for_compare_route(tmp_path: pathlib.Path) -> None:
    dist_index = tmp_path / "dist" / "index.html"
    dist_index.parent.mkdir(parents=True)
    dist_index.write_text("<html></html>", encoding="utf-8")

    resolved = resolve_static_request_path("/compare", project_root=tmp_path)

    assert resolved == dist_index



def test_resolve_static_request_path_keeps_audio_under_project_root(tmp_path: pathlib.Path) -> None:
    dist_index = tmp_path / "dist" / "index.html"
    dist_index.parent.mkdir(parents=True)
    dist_index.write_text("<html></html>", encoding="utf-8")
    audio_file = tmp_path / "audio" / "Fail01.wav"
    audio_file.parent.mkdir(parents=True)
    audio_file.write_bytes(b"wav")

    resolved = resolve_static_request_path("/audio/Fail01.wav", project_root=tmp_path)

    assert resolved == audio_file



def test_static_request_parts_strip_traversal_segments() -> None:
    assert static_request_parts("/../dist//assets/../app.js") == ["dist", "assets", "app.js"]
