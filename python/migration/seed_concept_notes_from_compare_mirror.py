"""Seed server-backed concept notes from the legacy compare-notes mirror.

The general per-concept notes box in Compare historically persisted only to a
browser ``localStorage`` value (key ``parseui-compare-notes-v1``); the workspace
file ``parseui-compare-notes-v1.json`` is a server-side *mirror* of that value.

Concept notes are now a first-class, shareable field in
``parse-enrichments.json`` (``concept_notes``), loaded via ``/api/enrichments``
like the rest of the workspace data. This one-off migration copies the mirror's
per-concept strings into ``concept_notes`` so existing notes — and any research
seeded into the mirror — appear in the server-backed Compare notes box.

Importing this module has no side effects; writes happen only through
``run_migration`` (or the explicit pure helper ``seed_concept_notes``).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MIRROR_FILENAME = "parseui-compare-notes-v1.json"
ENRICHMENTS_FILENAME = "parse-enrichments.json"
_BACKUP_SUFFIX = "pre-concept-notes-seed"


@dataclass
class SeedResult:
    seeded: int = 0
    skipped_existing: int = 0
    skipped_empty: int = 0
    concept_ids: List[str] = field(default_factory=list)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def seed_concept_notes(
    enrichments: Dict[str, Any],
    mirror: Dict[str, Any],
    *,
    now: Optional[str] = None,
    overwrite: bool = False,
) -> Tuple[Dict[str, Any], SeedResult]:
    """Fold the mirror ``{concept_id: note_string}`` into
    ``enrichments['concept_notes']`` as ``{concept_id: {note, updated_at}}``.

    Pure aside from mutating the passed ``enrichments`` dict in place (and
    returning it). Existing ``concept_notes`` entries with non-empty text are
    preserved unless ``overwrite`` is set, so server-side edits win over the
    legacy mirror.
    """
    stamp = now or _utc_now_iso()
    result = SeedResult()

    block = enrichments.get("concept_notes")
    if not isinstance(block, dict):
        block = {}
        enrichments["concept_notes"] = block

    for raw_id, raw_note in mirror.items():
        concept_id = str(raw_id).strip()
        note = raw_note if isinstance(raw_note, str) else ""
        if not concept_id or not note.strip():
            result.skipped_empty += 1
            continue
        existing = block.get(concept_id)
        if (
            isinstance(existing, dict)
            and str(existing.get("note") or "").strip()
            and not overwrite
        ):
            result.skipped_existing += 1
            continue
        block[concept_id] = {"note": note, "updated_at": stamp}
        result.seeded += 1
        result.concept_ids.append(concept_id)

    return enrichments, result


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def run_migration(workspace: Path, *, overwrite: bool = False) -> SeedResult:
    """Read the mirror + enrichments from ``workspace``, back up enrichments,
    seed ``concept_notes`` and write back atomically."""
    workspace = Path(workspace)
    enrichments_path = workspace / ENRICHMENTS_FILENAME
    mirror_path = workspace / MIRROR_FILENAME

    if not mirror_path.exists():
        raise FileNotFoundError("mirror not found: {0}".format(mirror_path))

    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    if not isinstance(mirror, dict):
        raise ValueError(
            "{0} must be a JSON object of concept_id -> note string".format(MIRROR_FILENAME)
        )

    if enrichments_path.exists():
        enrichments = json.loads(enrichments_path.read_text(encoding="utf-8"))
        if not isinstance(enrichments, dict):
            raise ValueError("{0} must be a JSON object".format(ENRICHMENTS_FILENAME))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = enrichments_path.with_name(
            "{0}.bak-{1}-{2}".format(enrichments_path.name, _BACKUP_SUFFIX, stamp)
        )
        shutil.copy2(enrichments_path, backup)
    else:
        enrichments = {}

    enrichments, result = seed_concept_notes(enrichments, mirror, overwrite=overwrite)
    _atomic_write_json(enrichments_path, enrichments)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed concept_notes in parse-enrichments.json from the compare-notes mirror."
    )
    parser.add_argument("workspace", nargs="?", default=".", help="PARSE workspace dir (default: cwd)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing concept_notes entries (default: keep server-side edits)",
    )
    args = parser.parse_args(argv)
    result = run_migration(Path(args.workspace), overwrite=args.overwrite)
    print(
        "seeded={0} skipped_existing={1} skipped_empty={2}".format(
            result.seeded, result.skipped_existing, result.skipped_empty
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
