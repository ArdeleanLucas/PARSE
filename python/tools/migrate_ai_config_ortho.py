from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_DROPPED_REASONS = {
    "vad_filter": "removed; VAD lives upstream in interval pipeline",
    "vad_parameters": "removed; VAD lives upstream in interval pipeline",
    "provider": "removed; redundant with `backend`",
    "compute_type": (
        "removed; HF backend never honored it (runtime stayed fp32); future MC will reinstate "
        "fp16 after quality A/B on milk/two/that/Khan02-cid-4 baseline"
    ),
}
_LEGACY_KEYS = frozenset(
    {
        "backend",
        "model_path",
        "language",
        "device",
        "condition_on_previous_text",
        "compression_ratio_threshold",
        "no_repeat_ngram_size",
        "repetition_penalty",
        "initial_prompt",
        "refine_lexemes",
        "task",
        *tuple(_DROPPED_REASONS),
    }
)
_SECTIONED_KEYS = frozenset({"backend", "model", "generation", "decoding"})


class MigrationError(Exception):
    pass


def _config_path(workspace: Path) -> Path:
    return workspace.expanduser().resolve() / "config" / "ai_config.json"


def _is_sectioned(ortho: dict[str, Any]) -> bool:
    return any(key in ortho for key in ("model", "generation", "decoding"))


def migrate_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str], bool]:
    current = config.get("ortho")
    if current is None:
        return copy.deepcopy(config), ["No ortho section found; nothing to migrate."], False
    if not isinstance(current, dict):
        raise MigrationError("config.ortho must be an object")
    ortho = dict(current)
    if _is_sectioned(ortho):
        return copy.deepcopy(config), ["config.ortho already uses the sectioned ORTH schema; no changes."], False

    unknown = sorted(set(ortho) - _LEGACY_KEYS)
    if unknown:
        raise MigrationError("Unknown legacy ortho key(s): " + ", ".join(unknown))

    migrated_ortho: dict[str, Any] = {"backend": ortho.get("backend", "hf")}
    model: dict[str, Any] = {}
    generation: dict[str, Any] = {}
    decoding: dict[str, Any] = {}

    if "model_path" in ortho:
        model["repo_id"] = ortho["model_path"]
    if "device" in ortho:
        model["device"] = ortho["device"]
    if model:
        migrated_ortho["model"] = model

    mapping = {
        "language": "language",
        "condition_on_previous_text": "condition_on_prev_tokens",
        "compression_ratio_threshold": "compression_ratio_threshold",
        "no_repeat_ngram_size": "no_repeat_ngram_size",
        "repetition_penalty": "repetition_penalty",
        "task": "task",
    }
    for old_key, new_key in mapping.items():
        if old_key in ortho:
            generation[new_key] = ortho[old_key]
    if generation:
        migrated_ortho["generation"] = generation

    for key in ("initial_prompt", "refine_lexemes"):
        if key in ortho:
            decoding[key] = ortho[key]
    if decoding:
        migrated_ortho["decoding"] = decoding

    messages: list[str] = []
    for key in ("vad_filter", "vad_parameters", "provider", "compute_type"):
        if key in ortho:
            messages.append(f"{key}: {_DROPPED_REASONS[key]}")
    messages.append("Migrated config.ortho from legacy flat schema to sectioned ORTH HF schema.")

    migrated = copy.deepcopy(config)
    migrated["ortho"] = migrated_ortho
    return migrated, messages, migrated != config


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{counter}")
        counter += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reads <workspace>/config/ai_config.json, rewrites the ortho section from the "
            "flat legacy schema to the new sectioned schema, drops dead keys, and writes back. "
            "Default is dry-run; --apply persists."
        )
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="PARSE workspace root")
    parser.add_argument("--apply", action="store_true", help="Persist the migration and write a timestamped backup")
    args = parser.parse_args(argv)

    path = _config_path(args.workspace)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise MigrationError("ai_config.json root must be an object")
        migrated, messages, changed = migrate_config(config)
    except FileNotFoundError:
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: failed to parse {path}: {exc}", file=sys.stderr)
        return 2
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not changed:
        for message in messages:
            print(message)
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: would migrate {path}" if not args.apply else f"APPLY: migrating {path}")
    for message in messages:
        print(message)
    if not args.apply:
        print(json.dumps(migrated.get("ortho", {}), ensure_ascii=False, indent=2))
        return 0

    backup = _backup_path(path)
    backup.write_bytes(path.read_bytes())
    _write_json(path, migrated)
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
