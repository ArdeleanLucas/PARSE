"""Cross-platform runtime path helpers for PARSE desktop packaging.

This module is intentionally isolated and currently not wired into the active ``python/server.py`` thin orchestrator / ``python/server_routes/*`` runtime.
It provides a portable foundation for resolving application-owned directories
without relying on machine-specific absolute paths or repository working
directory assumptions.
"""

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Union

PathLike = Union[str, Path]


@dataclass(frozen=True)
class PathOverrides:
    """Optional runtime path overrides."""

    root_dir: Optional[Path] = None
    data_dir: Optional[Path] = None
    config_dir: Optional[Path] = None
    cache_dir: Optional[Path] = None
    log_dir: Optional[Path] = None
    models_dir: Optional[Path] = None
    temp_dir: Optional[Path] = None


@dataclass(frozen=True)
class AppPaths:
    """Resolved runtime directories for a PARSE application instance."""

    app_name: str
    app_slug: str
    organization: str
    root_dir: Optional[Path]
    data_dir: Path
    config_dir: Path
    cache_dir: Path
    log_dir: Path
    models_dir: Path
    temp_dir: Path

    def ensure_directories(self) -> None:
        """Create all runtime directories if they do not exist."""
        for path in self.iter_directories():
            path.mkdir(parents=True, exist_ok=True)

    def iter_directories(self) -> Sequence[Path]:
        """Return all managed directories in a stable order."""
        return (
            self.data_dir,
            self.config_dir,
            self.cache_dir,
            self.log_dir,
            self.models_dir,
            self.temp_dir,
        )

    def as_dict(self) -> Dict[str, str]:
        """Return stringified paths for serialization/logging."""
        payload = {
            "data_dir": str(self.data_dir),
            "config_dir": str(self.config_dir),
            "cache_dir": str(self.cache_dir),
            "log_dir": str(self.log_dir),
            "models_dir": str(self.models_dir),
            "temp_dir": str(self.temp_dir),
        }
        if self.root_dir is not None:
            payload["root_dir"] = str(self.root_dir)
        return payload

    def to_env(self, env_prefix: str = "PARSE") -> Dict[str, str]:
        """Return environment variables suitable for child-process launches."""
        prefix = _normalize_env_prefix(env_prefix)
        payload = {
            "{0}_DATA_DIR".format(prefix): str(self.data_dir),
            "{0}_CONFIG_DIR".format(prefix): str(self.config_dir),
            "{0}_CACHE_DIR".format(prefix): str(self.cache_dir),
            "{0}_LOG_DIR".format(prefix): str(self.log_dir),
            "{0}_MODELS_DIR".format(prefix): str(self.models_dir),
            "{0}_TEMP_DIR".format(prefix): str(self.temp_dir),
        }
        if self.root_dir is not None:
            payload["{0}_RUNTIME_ROOT".format(prefix)] = str(self.root_dir)
        return payload


def _normalize_env_prefix(env_prefix: str) -> str:
    cleaned = str(env_prefix or "PARSE").strip().upper()
    return cleaned or "PARSE"


def _slugify(value: str) -> str:
    source = str(value or "").strip().lower()
    if not source:
        return "parse"

    chars = []
    for char in source:
        if char.isalnum():
            chars.append(char)
        else:
            chars.append("-")

    slug = "".join(chars)
    slug = "-".join(token for token in slug.split("-") if token)
    return slug or "parse"


def _coerce_optional_path(value: Optional[PathLike], base_dir: Optional[Path] = None) -> Optional[Path]:
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


def _first_mapping_value(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key not in mapping:
            continue

        value = mapping.get(key)
        if isinstance(value, str) and not value.strip():
            continue

        if value is None:
            continue

        return value

    return None


def _first_env_path(keys: Sequence[str], base_dir: Optional[Path] = None) -> Optional[Path]:
    for key in keys:
        raw = os.environ.get(key)
        candidate = _coerce_optional_path(raw, base_dir=base_dir)
        if candidate is not None:
            return candidate
    return None


def _xdg_dir(env_name: str, fallback: Path) -> Path:
    raw = os.environ.get(env_name, "")
    if raw.strip():
        return Path(raw).expanduser().resolve()
    return fallback.resolve()


def _platform_defaults(app_name: str, app_slug: str, organization: str) -> Dict[str, Path]:
    home = Path.home().resolve()

    if os.name == "nt":
        roaming_base = _coerce_optional_path(
            os.environ.get("APPDATA"),
            base_dir=home,
        ) or (home / "AppData" / "Roaming")
        local_base = _coerce_optional_path(
            os.environ.get("LOCALAPPDATA"),
            base_dir=home,
        ) or (home / "AppData" / "Local")

        org_dir = organization or app_name
        return {
            "data_dir": (local_base / org_dir / app_name / "data").resolve(),
            "config_dir": (roaming_base / org_dir / app_name / "config").resolve(),
            "cache_dir": (local_base / org_dir / app_name / "cache").resolve(),
            "log_dir": (local_base / org_dir / app_name / "logs").resolve(),
        }

    if sys.platform == "darwin":
        support_root = (home / "Library" / "Application Support" / app_name).resolve()
        return {
            "data_dir": (support_root / "data").resolve(),
            "config_dir": (support_root / "config").resolve(),
            "cache_dir": (home / "Library" / "Caches" / app_name).resolve(),
            "log_dir": (home / "Library" / "Logs" / app_name).resolve(),
        }

    # Linux / other UNIX: prefer XDG locations.
    data_home = _xdg_dir("XDG_DATA_HOME", home / ".local" / "share")
    config_home = _xdg_dir("XDG_CONFIG_HOME", home / ".config")
    cache_home = _xdg_dir("XDG_CACHE_HOME", home / ".cache")
    state_home = _xdg_dir("XDG_STATE_HOME", home / ".local" / "state")

    return {
        "data_dir": (data_home / app_slug).resolve(),
        "config_dir": (config_home / app_slug).resolve(),
        "cache_dir": (cache_home / app_slug).resolve(),
        "log_dir": (state_home / app_slug / "logs").resolve(),
    }


def merge_path_overrides(base: PathOverrides, override: PathOverrides) -> PathOverrides:
    """Merge path overrides, where ``override`` values win when present."""
    return PathOverrides(
        root_dir=override.root_dir or base.root_dir,
        data_dir=override.data_dir or base.data_dir,
        config_dir=override.config_dir or base.config_dir,
        cache_dir=override.cache_dir or base.cache_dir,
        log_dir=override.log_dir or base.log_dir,
        models_dir=override.models_dir or base.models_dir,
        temp_dir=override.temp_dir or base.temp_dir,
    )


def path_overrides_from_mapping(
    payload: Optional[Mapping[str, Any]],
    base_dir: Optional[Path] = None,
) -> PathOverrides:
    """Parse a mapping (e.g., JSON) into ``PathOverrides``."""
    if not isinstance(payload, Mapping):
        return PathOverrides()

    root_value = _first_mapping_value(payload, ("root", "root_dir", "runtime_root", "app_root"))
    data_value = _first_mapping_value(payload, ("data", "data_dir"))
    config_value = _first_mapping_value(payload, ("config", "config_dir"))
    cache_value = _first_mapping_value(payload, ("cache", "cache_dir"))
    log_value = _first_mapping_value(payload, ("log", "logs", "log_dir", "logs_dir"))
    models_value = _first_mapping_value(payload, ("models", "model", "models_dir", "model_dir"))
    temp_value = _first_mapping_value(payload, ("temp", "tmp", "temp_dir", "tmp_dir"))

    root_dir = _coerce_optional_path(root_value, base_dir=base_dir)
    per_path_base = root_dir if root_dir is not None else base_dir

    return PathOverrides(
        root_dir=root_dir,
        data_dir=_coerce_optional_path(data_value, base_dir=per_path_base),
        config_dir=_coerce_optional_path(config_value, base_dir=per_path_base),
        cache_dir=_coerce_optional_path(cache_value, base_dir=per_path_base),
        log_dir=_coerce_optional_path(log_value, base_dir=per_path_base),
        models_dir=_coerce_optional_path(models_value, base_dir=per_path_base),
        temp_dir=_coerce_optional_path(temp_value, base_dir=per_path_base),
    )


def load_env_path_overrides(env_prefix: str = "PARSE", base_dir: Optional[Path] = None) -> PathOverrides:
    """Read per-path overrides from environment variables."""
    prefix = _normalize_env_prefix(env_prefix)

    root_dir = _first_env_path(
        (
            "{0}_RUNTIME_ROOT".format(prefix),
            "{0}_APP_ROOT".format(prefix),
            "{0}_PORTABLE_ROOT".format(prefix),
        ),
        base_dir=base_dir,
    )
    per_path_base = root_dir if root_dir is not None else base_dir

    return PathOverrides(
        root_dir=root_dir,
        data_dir=_first_env_path(("{0}_DATA_DIR".format(prefix),), base_dir=per_path_base),
        config_dir=_first_env_path(("{0}_CONFIG_DIR".format(prefix),), base_dir=per_path_base),
        cache_dir=_first_env_path(("{0}_CACHE_DIR".format(prefix),), base_dir=per_path_base),
        log_dir=_first_env_path(
            (
                "{0}_LOG_DIR".format(prefix),
                "{0}_LOGS_DIR".format(prefix),
            ),
            base_dir=per_path_base,
        ),
        models_dir=_first_env_path(
            (
                "{0}_MODELS_DIR".format(prefix),
                "{0}_MODEL_DIR".format(prefix),
            ),
            base_dir=per_path_base,
        ),
        temp_dir=_first_env_path(
            (
                "{0}_TEMP_DIR".format(prefix),
                "{0}_TMP_DIR".format(prefix),
            ),
            base_dir=per_path_base,
        ),
    )


def resolve_app_paths(
    app_name: str = "PARSE",
    app_slug: Optional[str] = None,
    organization: str = "ArdeleanLucas",
    env_prefix: str = "PARSE",
    overrides: Optional[PathOverrides] = None,
    use_env: bool = True,
    create_dirs: bool = False,
) -> AppPaths:
    """Resolve runtime directories in a cross-platform way.

    Precedence order:
    1) platform defaults
    2) environment overrides (if ``use_env``)
    3) explicit ``overrides`` argument
    """
    resolved_app_name = str(app_name or "PARSE").strip() or "PARSE"
    resolved_app_slug = _slugify(app_slug or resolved_app_name)
    resolved_org = str(organization or "ArdeleanLucas").strip() or "ArdeleanLucas"

    default_paths = _platform_defaults(resolved_app_name, resolved_app_slug, resolved_org)

    effective = PathOverrides()
    if use_env:
        effective = merge_path_overrides(effective, load_env_path_overrides(env_prefix=env_prefix))
    if overrides is not None:
        effective = merge_path_overrides(effective, overrides)

    root_dir = _coerce_optional_path(effective.root_dir)
    per_path_base = root_dir

    default_data = default_paths["data_dir"]
    default_config = default_paths["config_dir"]
    default_cache = default_paths["cache_dir"]
    default_log = default_paths["log_dir"]

    if root_dir is not None:
        default_data = (root_dir / "data").resolve()
        default_config = (root_dir / "config").resolve()
        default_cache = (root_dir / "cache").resolve()
        default_log = (root_dir / "logs").resolve()

    data_dir = _coerce_optional_path(effective.data_dir, base_dir=per_path_base) or default_data
    config_dir = _coerce_optional_path(effective.config_dir, base_dir=per_path_base) or default_config
    cache_dir = _coerce_optional_path(effective.cache_dir, base_dir=per_path_base) or default_cache
    log_dir = _coerce_optional_path(effective.log_dir, base_dir=per_path_base) or default_log

    default_models = (root_dir / "models").resolve() if root_dir is not None else (data_dir / "models").resolve()
    models_dir = _coerce_optional_path(effective.models_dir, base_dir=per_path_base) or default_models

    default_temp = (root_dir / "tmp").resolve() if root_dir is not None else (Path(tempfile.gettempdir()) / resolved_app_slug).resolve()
    temp_dir = _coerce_optional_path(effective.temp_dir, base_dir=per_path_base) or default_temp

    app_paths = AppPaths(
        app_name=resolved_app_name,
        app_slug=resolved_app_slug,
        organization=resolved_org,
        root_dir=root_dir,
        data_dir=data_dir,
        config_dir=config_dir,
        cache_dir=cache_dir,
        log_dir=log_dir,
        models_dir=models_dir,
        temp_dir=temp_dir,
    )

    if create_dirs:
        app_paths.ensure_directories()

    return app_paths


__all__ = [
    "AppPaths",
    "PathOverrides",
    "load_env_path_overrides",
    "merge_path_overrides",
    "path_overrides_from_mapping",
    "resolve_app_paths",
]
