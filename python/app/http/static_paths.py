"""Static asset path resolution for the PARSE HTTP server."""

from __future__ import annotations

import pathlib
from typing import List
from urllib.parse import unquote, urlparse


def dist_dir(project_root: pathlib.Path) -> pathlib.Path:
    root = project_root.resolve()
    return root / "dist"


def dist_index_path(project_root: pathlib.Path) -> pathlib.Path:
    return dist_dir(project_root) / "index.html"


def has_built_frontend(project_root: pathlib.Path) -> bool:
    return dist_index_path(project_root).is_file()


def static_request_parts(raw_path: str) -> List[str]:
    request_path = urlparse(raw_path).path or "/"
    pure_path = pathlib.PurePosixPath(unquote(request_path))
    return [part for part in pure_path.parts if part not in {"/", "", ".", ".."}]


def resolve_static_request_path(raw_path: str, project_root: pathlib.Path) -> pathlib.Path:
    root = project_root.resolve()
    parts = static_request_parts(raw_path)
    root_candidate = root.joinpath(*parts) if parts else root

    if not has_built_frontend(root):
        return root_candidate

    dist_candidate = dist_dir(root).joinpath(*parts) if parts else dist_index_path(root)
    if parts and dist_candidate.exists():
        return dist_candidate
    if parts and root_candidate.exists():
        return root_candidate

    request_suffix = pathlib.PurePosixPath("/".join(parts)).suffix if parts else ""
    if not parts or request_suffix == "":
        return dist_index_path(root)

    return root_candidate
