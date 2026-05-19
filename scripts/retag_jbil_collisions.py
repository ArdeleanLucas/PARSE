#!/usr/bin/env python3
"""Retag concept-tier intervals whose audition_prefix disagrees with concepts.csv.

Background
----------
PARSE's importer resolves Audition cue labels to concept_ids by stem-matching
the label (after _stem_label strips qualifiers like "(A)"/"(B)"). When two
concepts share the same stemmed label (e.g. concept 5 'nose' in KLQ and
concept 132 'nose (A)' in JBIL) the resolver picks the wrong one — anchoring
the interval to a non-JBIL concept_id even though `audition_prefix` already
encodes the JBIL row number.

Canonical truth: for an interval with audition_prefix=N, the concept_id
should be the row in concepts.csv where source_survey='JBIL' and
source_item==N. If multiple JBIL rows share the same source_item (A/B
variants of the same elicitation), we cannot disambiguate without the
original Audition CSV — those are reported as SKIP.

Usage
-----
    python3 scripts/retag_jbil_collisions.py                    # dry-run all
    python3 scripts/retag_jbil_collisions.py --speaker Mand01   # scope
    python3 scripts/retag_jbil_collisions.py --prefix 63        # scope
    python3 scripts/retag_jbil_collisions.py --apply            # commit

Each modified file is backed up as
    <name>.parse.json.bak-pre-jbil-retag-<UTC-timestamp>
before being rewritten.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import glob
import json
import os
import re
from collections import defaultdict

WORKSPACE = os.environ.get("PARSE_WORKSPACE", "/home/lucas/parse-workspace")


def qualifier(label: str) -> str:
    m = re.search(r"\(([^)]+)\)", label or "")
    return m.group(1).strip().lower() if m else ""


def build_jbil_index(workspace: str):
    by_item: dict[str, list[str]] = defaultdict(list)
    label_by_id: dict[str, str] = {}
    with open(os.path.join(workspace, "concepts.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            label_by_id[row["id"]] = row["concept_en"]
            if (row.get("source_survey") or "").strip() == "JBIL":
                item = (row.get("source_item") or "").strip()
                if item:
                    by_item[item].append(row["id"])
    return by_item, label_by_id


def expected_concept_id(prefix, tagged_id, jbil_index, label_by_id):
    """Return (new_id, reason) for the interval, or (None, reason)."""
    candidates = jbil_index.get(prefix, [])
    if not candidates:
        return None, "no-jbil-row"
    if str(tagged_id) in candidates:
        return None, "already-correct"
    if len(candidates) == 1:
        return candidates[0], "unambiguous"
    tagged_q = qualifier(label_by_id.get(str(tagged_id), ""))
    if tagged_q:
        for cid in candidates:
            if qualifier(label_by_id.get(cid, "")) == tagged_q:
                return cid, "qualifier-match"
    return None, "ambiguous:" + ",".join(candidates)


def process_file(path, jbil_index, label_by_id, args, ts):
    speaker = os.path.basename(path)[: -len(".parse.json")]
    if args.speaker and speaker != args.speaker:
        return 0, 0
    with open(path) as fh:
        data = json.load(fh)
    concept_iv = (((data.get("tiers") or {}).get("concept") or {}).get("intervals") or [])
    will_change = []
    will_skip = []
    for iv in concept_iv:
        prefix = str(iv.get("audition_prefix") or "").strip()
        cid = str(iv.get("concept_id") or "").strip()
        if not prefix or not cid:
            continue
        if args.prefix and prefix != args.prefix:
            continue
        new_id, reason = expected_concept_id(prefix, cid, jbil_index, label_by_id)
        if reason in ("already-correct", "no-jbil-row"):
            continue
        if new_id:
            will_change.append((iv, new_id))
        else:
            will_skip.append((iv, reason))
    if not will_change and not will_skip:
        return 0, 0
    print(f"== {speaker}: retag {len(will_change)}  skip {len(will_skip)} ==")
    for iv, new in will_change:
        old = str(iv.get("concept_id"))
        s = iv.get("start") or 0.0
        print(
            f"  cue#{iv.get('audition_prefix'):>3}  t={s:>9.3f}s  "
            f"{old} ({label_by_id.get(old, '?')!r}) -> {new} ({label_by_id.get(new, '?')!r})"
        )
    for iv, reason in will_skip:
        old = str(iv.get("concept_id"))
        print(
            f"  cue#{iv.get('audition_prefix'):>3}  SKIP ({reason})  "
            f"tagged={old}({label_by_id.get(old, '?')!r})"
        )
    if args.apply and will_change:
        bak = f"{path}.bak-pre-jbil-retag-{ts}"
        with open(bak, "w") as bh:
            json.dump(data, bh, indent=2, ensure_ascii=False)
        anchors = []
        for iv, new in will_change:
            anchors.append((iv.get("start"), iv.get("end"), new))
            iv["concept_id"] = new
            iv["text"] = label_by_id.get(new, iv.get("text"))
        # propagate to companion tiers by exact (start,end) match
        for tier_name in ("ipa", "ortho", "ortho_words", "ipa_phone"):
            tier = (data.get("tiers") or {}).get(tier_name) or {}
            for tiv in tier.get("intervals") or []:
                if "conceptId" not in tiv:
                    continue
                ts_, te_ = tiv.get("start") or 0.0, tiv.get("end") or 0.0
                for s, e, new in anchors:
                    if abs(ts_ - (s or 0.0)) < 1e-3 and abs(te_ - (e or 0.0)) < 1e-3:
                        tiv["conceptId"] = new
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"  -> wrote {path}  (backup: {bak})")
    return len(will_change), len(will_skip)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit changes (default: dry-run)")
    ap.add_argument("--speaker", help="restrict to one speaker (e.g. Mand01)")
    ap.add_argument("--prefix", help="restrict to one audition cue number")
    ap.add_argument("--workspace", default=WORKSPACE)
    args = ap.parse_args()

    jbil_index, label_by_id = build_jbil_index(args.workspace)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S")
    paths = sorted(
        p for p in glob.glob(os.path.join(args.workspace, "annotations", "*.parse.json"))
        if ".bak" not in p
    )

    total_apply = total_skip = 0
    for path in paths:
        a, s = process_file(path, jbil_index, label_by_id, args, ts)
        total_apply += a
        total_skip += s

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n{mode}: retag {total_apply}, skip {total_skip} (ambiguous; need source-CSV review)")


if __name__ == "__main__":
    main()
