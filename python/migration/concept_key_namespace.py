"""Re-key per-concept decision state off survey-local ``source_item`` keys.

Companion to the frontend fix in ``src/lib/conceptGrouping.ts``: grouped
concepts now key by their canonical csv id (``min(member_ids)``, matching the
backend #529 identity model) instead of ``source_item``. Existing decision
blocks in ``parse-enrichments.json`` were written under the old keys and must be
re-keyed.

Design (mirrors ``python/migration/concept_suffix_pollution.py``):
  * dry-run is the safe default — callers pass ``execute=True`` to write;
  * idempotent — a second run finds nothing to do;
  * refuses to guess — old keys that *collided* with a real concept id (a shared
    storage slot) are reported for manual triage, never silently moved;
  * optimistic-concurrency guarded — aborts if the file changed under it.

Concept-key-keyed blocks migrated:
  ``manual_overrides.{speaker_flags,cognate_sets,cognate_decisions,
  discarded_forms,borrowing_flags,concept_merges}`` and top-level
  ``borrowing_flags``. Skipped: ``manual_overrides.canonical_lexemes`` (keyed by
  ``bundle:<slug>``, not a concept key) and ``parse-tags.json`` (tag.concepts
  hold csv ids, already id-namespaced).

Operational note: stop the PARSE server before running with ``execute=True`` so
``parse-enrichments.json`` cannot be written concurrently by the server. The
writer is atomic (temp+rename) and this module re-reads the file immediately
before writing and aborts if it changed since load, but stopping the server is
the only way to fully avoid a lost update.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # python/ is on sys.path in server + CLI contexts
    from canonical_lexemes import save_enrichments_atomic
except Exception:  # pragma: no cover - standalone fallback
    save_enrichments_atomic = None

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
    """Frontend ``canonicalConceptKey`` mirror: min numeric id, else first."""
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
    """Return ``{old_key: {new_key, members, classification, collides_with_id}}``
    for grouped concepts whose key changes, classified SAFE vs AMBIGUOUS."""
    rows = list(csv.DictReader(concepts_csv.open()))
    ids = {_norm(r["id"]) for r in rows if _norm(r.get("id"))}

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        si = _norm(r.get("source_item"))
        if si:
            buckets[(_norm(r.get("source_survey")), si)].append(r)

    # Old frontend logic: a source_item used by >=2 grouped buckets keyed as
    # "source:{survey}:{item}"; otherwise the bare source_item.
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
    return remap


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
            merged.update(value)
            out[new_key] = merged
        else:
            out[new_key] = value
    return out


def migrate(workspace: Path, *, execute: bool = False) -> dict[str, Any]:
    """Plan (and, when ``execute`` is true, apply) the re-key. Returns a report."""
    workspace = Path(workspace)
    enr_path = workspace / "parse-enrichments.json"
    remap = build_remap(workspace / "concepts.csv")

    original_text = enr_path.read_text(encoding="utf-8")
    enr = json.loads(original_text)

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
            if name == "concept_merges":  # values are absorbed concept keys — re-key too
                for k, arr in container[name].items():
                    if isinstance(arr, list):
                        container[name][k] = [_safe_new(_norm(x)) for x in arr]

    if isinstance(enr.get("manual_overrides"), dict):
        migrate_container(enr["manual_overrides"])
    migrate_container(enr)  # top-level borrowing_flags

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
        "backup_written": None,
    }

    if execute and touched:
        # Optimistic concurrency: abort if the server rewrote the file under us.
        if enr_path.read_text(encoding="utf-8") != original_text:
            raise RuntimeError(
                "parse-enrichments.json changed since load — aborting. Stop the "
                "PARSE server and re-run so no decision write is lost."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = enr_path.with_name(f"{enr_path.name}.bak-{stamp}-pre-key-namespace")
        backup.write_text(original_text, encoding="utf-8")  # original bytes, verbatim
        if save_enrichments_atomic is not None:
            save_enrichments_atomic(workspace, enr)
        else:  # pragma: no cover
            enr_path.write_text(
                json.dumps(enr, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        report["backup_written"] = backup.name
    return report
