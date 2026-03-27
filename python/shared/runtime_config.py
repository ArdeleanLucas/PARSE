"""Runtime configuration helpers for PARSE desktop packaging.

This module composes configuration-file settings and environment overrides into
an immutable ``RuntimeConfig`` object, including cross-platform runtime paths
resolved by ``python/shared/app_paths.py``.

It is intentionally not wired into the current backend runtime yet.
"""

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

try:
    from .app_paths import (
        AppPaths,
        PathOverrides,
        load_env_path_overrides,
        merge_path_overrides,
        path_overrides_from_mapping,
        resolve_app_paths,
    )
except ImportError:  # pragma: no cover - fallback for direct script usage
    from app_paths import (  # type: ignore
        AppPaths,
        PathOverrides,
        load_env_path_overrides,
        merge_path_overrides,
        path_overrides_from_mapping,
        resolve_app_paths,
    )

PathLike = Union[str, Path]

DEFAULT_APP_NAME = "PARSE"
DEFAULT_APP_SLUG = "parse"
DEFAULT_ORGANIZATION = "ArdeleanLucas"
DEFAULT_RUNTIME_ENVIRONMENT = "desktop"


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved runtime metadata and directories."""

    app_name: str
    app_slug: str
    organization: str
    environment: str
    project_root: Optional[Path]
    config_file: Optional[Path]
    paths: AppPaths
    raw: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of this config."""
        payload: Dict[str, Any] = {
            "app": {
                "name": self.app_name,
                "slug": self.app_slug,
                "organization": self.organization,
            },
            "runtime": {
                "environment": self.environment,
                "project_root": str(self.project_root) if self.project_root else None,
                "config_file": str(self.config_file) if self.config_file else None,
            },
            "paths": self.paths.as_dict(),
            "raw": copy.deepcopy(self.raw),
        }
        return payload


def _normalize_env_prefix(env_prefix: str) -> str:
    cleaned = str(env_prefix or "PARSE").strip().upper()
    return cleaned or "PARSE"


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text:
            return text

    return None


def _coerce_optional_path(value: Any, base_dir: Optional[Path] = None) -> Optional[Path]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    path = Path(text).expanduser()
    if not path.is_absolute():
        anchor = base_dir if base_dir is not None else Path.cwd()
        path = anchor / path

    return path.resolve()


def _load_json_object(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _resolve_runtime_config_path(config_path: Optional[PathLike], env_prefix: str) -> Optional[Path]:
    if config_path is not None:
        return _coerce_optional_path(config_path)

    key = "{0}_RUNTIME_CONFIG".format(env_prefix)
    return _coerce_optional_path(os.environ.get(key))


def _mapping_section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def load_runtime_config(
    config_path: Optional[PathLike] = None,
    env_prefix: str = "PARSE",
    create_dirs: bool = False,
) -> RuntimeConfig:
    """Resolve runtime config from defaults + config file + environment.

    Precedence order:
    1) hardcoded defaults
    2) runtime config JSON values
    3) environment variables (``<PREFIX>_*``)
    """
    prefix = _normalize_env_prefix(env_prefix)
    resolved_config_path = _resolve_runtime_config_path(config_path, prefix)
    payload = _load_json_object(resolved_config_path)

    app_section = _mapping_section(payload, "app")
    runtime_section = _mapping_section(payload, "runtime")
    paths_section = _mapping_section(payload, "paths")

    config_base_dir = resolved_config_path.parent if resolved_config_path is not None else None

    app_name = _first_non_empty(
        os.environ.get("{0}_APP_NAME".format(prefix)),
        app_section.get("name"),
        DEFAULT_APP_NAME,
    ) or DEFAULT_APP_NAME

    app_slug = _first_non_empty(
        os.environ.get("{0}_APP_SLUG".format(prefix)),
        app_section.get("slug"),
        DEFAULT_APP_SLUG,
    ) or DEFAULT_APP_SLUG

    organization = _first_non_empty(
        os.environ.get("{0}_APP_ORG".format(prefix)),
        app_section.get("organization"),
        app_section.get("org"),
        DEFAULT_ORGANIZATION,
    ) or DEFAULT_ORGANIZATION

    environment = _first_non_empty(
        os.environ.get("{0}_RUNTIME_ENV".format(prefix)),
        runtime_section.get("environment"),
        payload.get("environment"),
        DEFAULT_RUNTIME_ENVIRONMENT,
    ) or DEFAULT_RUNTIME_ENVIRONMENT

    project_root = _coerce_optional_path(
        _first_non_empty(
            os.environ.get("{0}_PROJECT_ROOT".format(prefix)),
            runtime_section.get("project_root"),
            payload.get("project_root"),
        ),
        base_dir=config_base_dir,
    )

    config_file_overrides = path_overrides_from_mapping(paths_section, base_dir=config_base_dir)
    env_overrides = load_env_path_overrides(env_prefix=prefix, base_dir=config_base_dir)
    merged_overrides = merge_path_overrides(config_file_overrides, env_overrides)

    paths = resolve_app_paths(
        app_name=app_name,
        app_slug=app_slug,
        organization=organization,
        env_prefix=prefix,
        overrides=merged_overrides,
        use_env=False,
        create_dirs=create_dirs,
    )

    return RuntimeConfig(
        app_name=app_name,
        app_slug=app_slug,
        organization=organization,
        environment=environment,
        project_root=project_root,
        config_file=resolved_config_path,
        paths=paths,
        raw=payload,
    )


def build_backend_environment(
    runtime_config: RuntimeConfig,
    base_env: Optional[Mapping[str, str]] = None,
    env_prefix: str = "PARSE",
) -> Dict[str, str]:
    """Build an environment block for launching a Python backend process.

    Electron can call this helper (or mirror its behavior in JS) and pass the
    resulting environment to ``subprocess`` / ``child_process.spawn`` so the
    backend can resolve identical runtime directories.
    """
    prefix = _normalize_env_prefix(env_prefix)
    env: Dict[str, str] = dict(base_env if base_env is not None else os.environ)

    env.update(runtime_config.paths.to_env(env_prefix=prefix))
    env["{0}_APP_NAME".format(prefix)] = runtime_config.app_name
    env["{0}_APP_SLUG".format(prefix)] = runtime_config.app_slug
    env["{0}_APP_ORG".format(prefix)] = runtime_config.organization
    env["{0}_RUNTIME_ENV".format(prefix)] = runtime_config.environment

    if runtime_config.project_root is not None:
        env["{0}_PROJECT_ROOT".format(prefix)] = str(runtime_config.project_root)

    if runtime_config.config_file is not None:
        env["{0}_RUNTIME_CONFIG".format(prefix)] = str(runtime_config.config_file)

    return env


__all__ = [
    "RuntimeConfig",
    "build_backend_environment",
    "load_runtime_config",
]
