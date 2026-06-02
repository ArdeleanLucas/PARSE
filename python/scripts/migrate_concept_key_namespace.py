#!/usr/bin/env python3
"""Re-key per-concept decision state off survey-local `source_item` keys.

Companion to the frontend fix in `src/lib/conceptGrouping.ts`: grouped concepts
now key by their canonical csv id (`min(member_ids)`, matching backend #529)
instead of `source_item`. Existing decision blocks in `parse-enrichments.json`
were written under the old keys and must be re-keyed.

Design (mirrors python/scripts/migrate_concept_suffix_pollution.py):
  * dry-run by default — writes a report, never mutates;
  * idempotent — a second run finds nothing to do;
  * refuses to guess — old keys that *collided* with a real concept id (a shared
    storage slot) are reported for manual triage, never silently moved.

Concept-key-keyed blocks migrated:
  manual_overrides.{speaker_flags,cognate_sets,cognate_decisions,discarded_forms,
                    borrowing_flags,concept_merges}
  top-level borrowing_flags
Skipped: manual_overrides.canonical_lexemes (keyed by `bundle:<slug>`, not concept
key) and parse-tags.json (tag.concepts hold csv ids, already id-namespaced).

Usage:
  python migrate_concept_key_namespace.py --workspace /path/to/workspace [--execute]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

# Reuse the backend's canonical writer so re-keyed files stay byte-compatible
# with how the server persists enrichments (ensure_ascii=False, sort_keys,
# trailing newline). Falls back to an inline writer if run outside the tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from canonical_lexemes import save_enrichments_atomic  # type: ignore
except Exception:  # pragma: no cover - standalone fallback
    save_enrichments_atomic = None


def _dump_enrichments(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

CONCEPT_KEYED_BLOCKS = (
    "speaker_flags",
    "cognate_sets",
    "cognate_decisions",
    "discarded_forms",
    "borrowing_flags",
    "concept_merges",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_key(member_ids: list[str]) -> str:
    """Frontend `canonicalConceptKey` mirror: min numeric id, else first."""
    best: str | None = None
    best_num = float("inf")
    for mid in member_ids:
        try:
            n = float(mid)
        except ValueError:
            if best is None:
                best = mid
            continue
        if n < best_num:
            best_num, best = n, mid
    return best if best is not None else (member_ids[0] if member_ids else "")


def build_remap(concepts_csv: Path) -> dict[str, Any]:
    """Return {old_key: {new_key, members, classification}} for grouped concepts
    whose key changes, plus the set of all csv ids."""
    rows = list(csv.DictReader(concepts_csv.open()))
    ids = {_norm(r["id"]) for r in rows if _norm(r.get("id"))}

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        si = _norm(r.get("source_item"))
        if si:
            buckets[(_norm(r.get("source_survey")), si)].append(r)

    # Old frontend logic: a source_item used by >=2 grouped buckets keys as
    # "source:{survey}:{item}"; otherwise bare source_item.
    item_grouped_bucket_count: dict[str, int] = defaultdict(int)
    for (_sv, si), members in buckets.items():
        if len(members) >= 2:
            item_grouped_bucket_count[si] += 1
    multi = {si for si, n in item_grouped_bucket_count.items() if n >= 2}

    remap: dict[str, Any] = {}
    for (sv, si), members in buckets.items():
        if len(members) < 2:
            continue  # singleton — key == its own id, unchanged
        member_ids = [_norm(m["id"]) for m in members]
        old_key = f"source:{sv}:{si}" if si in multi else si
        new_key = _canonical_key(member_ids)
        if old_key == new_key:
            continue
        # AMBIGUOUS: the old key equals a real concept id that is NOT a member of
        # this group => the slot was shared with that unrelated concept.
        collides_with = old_key if (old_key in ids and old_key not in member_ids) else None
        remap[old_key] = {
            "new_key": new_key,
            "members": member_ids,
            "names": [_norm(m["concept_en"]) for m in members],
            "classification": "AMBIGUOUS" if collides_with else "SAFE",
            "collides_with_id": collides_with,
        }
    return {"remap": remap, "ids": ids}


def _remap_dict_keys(block: dict, remap: dict[str, Any], touched: list, ambiguous: list, block_name: str) -> dict:
    """Return a re-keyed copy of one concept-keyed dict block."""
    out: dict[str, Any] = {}
    for key, value in block.items():
        entry = remap.get(key)
        if entry is None:
            out[key] = value  # singleton id or already-canonical — keep
            continue
        if entry["classification"] == "AMBIGUOUS":
            ambiguous.append({"block": block_name, "key": key, **entry,
                              "affected": list(value) if isinstance(value, dict) else value})
            out[key] = value  # leave under the (now unrelated) id; do not guess
            continue
        new_key = entry["new_key"]
        touched.append({"block": block_name, "old_key": key, "new_key": new_key})
        if new_key in out and isinstance(out[new_key], dict) and isinstance(value, dict):
            merged = dict(out[new_key])
            merged.update(value)  # incoming wins on conflict; both kept otherwise
            out[new_key] = merged
        else:
            out[new_key] = value
    return out


def migrate(workspace: Path, execute: bool) -> dict[str, Any]:
    enr_path = workspace / "parse-enrichments.json"
    info = build_remap(workspace / "concepts.csv")
    remap = info["remap"]
    enr = json.loads(enr_path.read_text())

    touched: list[dict] = []
    ambiguous: list[dict] = []

    def _safe_new(key: str) -> str:
        entry = remap.get(key)
        return entry["new_key"] if entry and entry["classification"] == "SAFE" else key

    def migrate_container(container: dict):
        for name in CONCEPT_KEYED_BLOCKS:
            block = container.get(name)
            if not isinstance(block, dict):
                continue
            container[name] = _remap_dict_keys(block, remap, touched, ambiguous, name)
            # concept_merges values are absorbed concept keys — re-key them too.
            if name == "concept_merges":
                for k, arr in container[name].items():
                    if isinstance(arr, list):
                        container[name][k] = [_safe_new(_norm(x)) for x in arr]

    if isinstance(enr.get("manual_overrides"), dict):
        migrate_container(enr["manual_overrides"])
    migrate_container(enr)  # top-level borrowing_flags

    # Post-state verification: no decision key is a bare source_item remap source.
    leftover = []
    for name in CONCEPT_KEYED_BLOCKS:
        for container in (enr.get("manual_overrides") or {}, enr):
            blk = container.get(name)
            if isinstance(blk, dict):
                for k in blk:
                    if k in remap and remap[k]["classification"] == "SAFE":
                        leftover.append({"block": name, "key": k})

    report = {
        "workspace": str(workspace),
        "mode": "execute" if execute else "dry-run",
        "grouped_concepts_rekeyed": len(remap),
        "safe_remaps_total": sum(1 for v in remap.values() if v["classification"] == "SAFE"),
        "ambiguous_remaps_total": sum(1 for v in remap.values() if v["classification"] == "AMBIGUOUS"),
        "decision_keys_migrated": touched,
        "decision_keys_ambiguous_left_in_place": ambiguous,
        "verification_leftover_safe_keys": leftover,
        "verification_ok": not leftover,
    }

    if execute:
        if touched:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = enr_path.with_name(f"{enr_path.name}.bak-{stamp}-pre-key-namespace")
            # Backup the original bytes verbatim — do not reformat what we preserve.
            backup.write_text(enr_path.read_text(encoding="utf-8"), encoding="utf-8")
            if save_enrichments_atomic is not None:
                save_enrichments_atomic(workspace, enr)
            else:  # pragma: no cover
                enr_path.write_text(_dump_enrichments(enr), encoding="utf-8")
            report["backup_written"] = str(backup.name)
        else:
            report["backup_written"] = None
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--execute", action="store_true", help="apply changes (default: dry-run)")
    ap.add_argument("--report", type=Path, help="write the JSON report here")
    args = ap.parse_args()

    report = migrate(args.workspace, args.execute)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.write_text(text)
    print(text)
    return 0 if report["verification_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
