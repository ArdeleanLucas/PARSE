#!/usr/bin/env python3
"""Benchmark Tier 1 (STT) word-boundary accuracy via Tier 2 refinement deltas.

Aggregates existing `.stt.json` and `.aligned.json` artifacts in a workspace
(or an explicit pair) and reports:

    1. confidence distribution from forced-alignment CTC scores (aligned `confidence` field)
    2. onset/offset boundary shift between Tier 1 and Tier 2 in ms,
       and the fraction of words whose worst edge shift exceeds --padding-ms
       (the same pad currently applied at forced_align.py:_slice_window)
    3. method-count histogram straight from `alignment.methodCounts`
       (proportional-fallback rate = Tier 2 failure rate)

No ground truth required; no pipeline re-runs. Read-only over JSON artifacts.

Usage:
    # Whole workspace (resolves <workspace>/stt_output/<speaker>.stt.json
    # and sibling .aligned.json):
    python scripts/benchmark_tier1_boundaries.py --workspace /path/to/workspace

    # Single pair:
    python scripts/benchmark_tier1_boundaries.py \\
        --stt stt_output/Fail02.stt.json \\
        --aligned stt_output/Fail02.aligned.json

    # Custom padding threshold (default 100 ms = forced_align.py default):
    python scripts/benchmark_tier1_boundaries.py --workspace . --padding-ms 150

    # Save full per-pair JSON for downstream plotting:
    python scripts/benchmark_tier1_boundaries.py --workspace . --json-out results.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_words(artifact: Dict[str, Any]) -> Iterable[Tuple[int, int, Dict[str, Any]]]:
    """Yield (seg_idx, word_idx, word_dict) for every nested word in a STT/aligned artifact."""
    for seg_idx, seg in enumerate(artifact.get("segments") or []):
        words = seg.get("words") if isinstance(seg, dict) else None
        if not isinstance(words, list):
            continue
        for word_idx, w in enumerate(words):
            if isinstance(w, dict):
                yield seg_idx, word_idx, w


def _resolve_pairs(
    workspace: Optional[Path],
    explicit_stt: Optional[Path],
    explicit_aligned: Optional[Path],
) -> List[Tuple[str, Path, Path]]:
    """Return list of (label, stt_path, aligned_path) tuples."""
    if explicit_stt and explicit_aligned:
        return [(explicit_stt.stem.removesuffix(".stt"), explicit_stt, explicit_aligned)]

    if not workspace:
        return []

    stt_dir = workspace / "stt_output"
    if not stt_dir.is_dir():
        return []

    pairs: List[Tuple[str, Path, Path]] = []
    # Layout A: <speaker>.stt.json + <speaker>.aligned.json (server.py:4578, 4626)
    for stt_path in sorted(stt_dir.glob("*.stt.json")):
        speaker = stt_path.name[: -len(".stt.json")]
        aligned_path = stt_dir / f"{speaker}.aligned.json"
        if aligned_path.is_file():
            pairs.append((speaker, stt_path, aligned_path))

    # Layout B: <speaker>/stt.json + <speaker>/aligned.json (server.py:4579 fallback)
    for sub in sorted(p for p in stt_dir.iterdir() if p.is_dir()):
        stt_path = sub / "stt.json"
        aligned_path = sub / "aligned.json"
        if stt_path.is_file() and aligned_path.is_file():
            pairs.append((sub.name, stt_path, aligned_path))

    return pairs


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _summarise(values: List[float], label: str) -> Dict[str, Any]:
    if not values:
        return {"label": label, "n": 0}
    return {
        "label": label,
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "p10": round(_percentile(values, 10) or 0.0, 4),
        "p25": round(_percentile(values, 25) or 0.0, 4),
        "p75": round(_percentile(values, 75) or 0.0, 4),
        "p90": round(_percentile(values, 90) or 0.0, 4),
        "p95": round(_percentile(values, 95) or 0.0, 4),
        "max": round(max(values), 4),
        "min": round(min(values), 4),
    }


def analyse_pair(
    stt_path: Path,
    aligned_path: Path,
    padding_ms: float,
) -> Dict[str, Any]:
    stt = _load_json(stt_path)
    aligned = _load_json(aligned_path)

    # Index Tier 1 words by (seg_idx, word_idx)
    tier1_index: Dict[Tuple[int, int], Dict[str, Any]] = {
        (si, wi): w for si, wi, w in _iter_words(stt)
    }

    confidences: List[float] = []
    onset_shifts_ms: List[float] = []
    offset_shifts_ms: List[float] = []
    max_edge_shifts_ms: List[float] = []
    paired = 0
    unpaired_aligned = 0
    methods_walked: Dict[str, int] = {}

    for si, wi, w2 in _iter_words(aligned):
        method = str(w2.get("method") or "unknown")
        methods_walked[method] = methods_walked.get(method, 0) + 1

        c = w2.get("confidence")
        if isinstance(c, (int, float)):
            confidences.append(float(c))

        w1 = tier1_index.get((si, wi))
        if not w1:
            unpaired_aligned += 1
            continue
        s1, e1 = w1.get("start"), w1.get("end")
        s2, e2 = w2.get("start"), w2.get("end")
        if not all(isinstance(v, (int, float)) for v in (s1, e1, s2, e2)):
            continue
        on_ms = abs(float(s2) - float(s1)) * 1000.0
        off_ms = abs(float(e2) - float(e1)) * 1000.0
        onset_shifts_ms.append(on_ms)
        offset_shifts_ms.append(off_ms)
        max_edge_shifts_ms.append(max(on_ms, off_ms))
        paired += 1

    method_counts_meta = (aligned.get("alignment") or {}).get("methodCounts") or {}
    total_method = sum(method_counts_meta.values()) if method_counts_meta else 0
    method_pct = (
        {k: round(100.0 * v / total_method, 2) for k, v in method_counts_meta.items()}
        if total_method
        else {}
    )

    over_pad = sum(1 for v in max_edge_shifts_ms if v > padding_ms)
    over_pad_pct = round(100.0 * over_pad / len(max_edge_shifts_ms), 2) if max_edge_shifts_ms else 0.0

    low_conf_06 = (
        round(100.0 * sum(1 for c in confidences if c < 0.6) / len(confidences), 2)
        if confidences
        else None
    )
    low_conf_05 = (
        round(100.0 * sum(1 for c in confidences if c < 0.5) / len(confidences), 2)
        if confidences
        else None
    )

    return {
        "stt_path": str(stt_path),
        "aligned_path": str(aligned_path),
        "paired_words": paired,
        "unpaired_aligned_words": unpaired_aligned,
        "tier1_total_words": len(tier1_index),
        "confidence": _summarise(confidences, "confidence"),
        "confidence_below_0.6_pct": low_conf_06,
        "confidence_below_0.5_pct": low_conf_05,
        "onset_shift_ms": _summarise(onset_shifts_ms, "onset_shift_ms"),
        "offset_shift_ms": _summarise(offset_shifts_ms, "offset_shift_ms"),
        "max_edge_shift_ms": _summarise(max_edge_shifts_ms, "max_edge_shift_ms"),
        "padding_ms": padding_ms,
        "max_edge_shift_over_padding_pct": over_pad_pct,
        "method_counts_artifact": method_counts_meta,
        "method_pct_artifact": method_pct,
        "method_counts_walked": methods_walked,
    }


def _format_summary_table(per_pair: List[Dict[str, Any]], padding_ms: float) -> str:
    lines: List[str] = []
    header = (
        f"{'speaker':<24} {'n':>6} {'conf_med':>9} {'<0.6%':>7} "
        f"{'onset_p90':>10} {'offset_p90':>11} {'edge_p90':>9} "
        f"{'>'+str(int(padding_ms))+'ms%':>9} {'fallback%':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in per_pair:
        speaker = Path(r["stt_path"]).name.replace(".stt.json", "")[:24]
        n = r["paired_words"]
        conf_med = r["confidence"].get("median")
        low = r["confidence_below_0.6_pct"]
        on90 = r["onset_shift_ms"].get("p90")
        off90 = r["offset_shift_ms"].get("p90")
        edge90 = r["max_edge_shift_ms"].get("p90")
        over = r["max_edge_shift_over_padding_pct"]
        fb = r["method_pct_artifact"].get("proportional-fallback", 0.0)
        lines.append(
            f"{speaker:<24} {n:>6} "
            f"{(f'{conf_med:.3f}' if conf_med is not None else '-'):>9} "
            f"{(f'{low:.1f}' if low is not None else '-'):>7} "
            f"{(f'{on90:.1f}' if on90 is not None else '-'):>10} "
            f"{(f'{off90:.1f}' if off90 is not None else '-'):>11} "
            f"{(f'{edge90:.1f}' if edge90 is not None else '-'):>9} "
            f"{over:>8.1f}% "
            f"{fb:>9.1f}%"
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", type=Path, help="PARSE workspace root containing stt_output/")
    p.add_argument("--stt", type=Path, help="Explicit Tier 1 .stt.json (use with --aligned)")
    p.add_argument("--aligned", type=Path, help="Explicit Tier 2 .aligned.json (use with --stt)")
    p.add_argument(
        "--padding-ms",
        type=float,
        default=100.0,
        help="Edge-shift threshold; matches forced_align _slice_window pad (default 100)",
    )
    p.add_argument("--json-out", type=Path, help="Write full structured results to this path")
    args = p.parse_args(argv)

    if not args.workspace and not (args.stt and args.aligned):
        p.error("provide --workspace OR both --stt and --aligned")

    pairs = _resolve_pairs(args.workspace, args.stt, args.aligned)
    if not pairs:
        print("No (.stt.json, .aligned.json) pairs found.", file=sys.stderr)
        if args.workspace:
            print(f"  Looked under: {args.workspace / 'stt_output'}", file=sys.stderr)
        return 2

    per_pair: List[Dict[str, Any]] = []
    for label, stt_path, aligned_path in pairs:
        try:
            per_pair.append(analyse_pair(stt_path, aligned_path, args.padding_ms))
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {label}: {exc}", file=sys.stderr)

    aggregate = {
        "padding_ms": args.padding_ms,
        "pair_count": len(per_pair),
        "total_paired_words": sum(r["paired_words"] for r in per_pair),
    }

    print(f"# Tier 1 boundary benchmark — {aggregate['pair_count']} speaker(s), "
          f"{aggregate['total_paired_words']} paired words, padding={args.padding_ms} ms\n")
    print(_format_summary_table(per_pair, args.padding_ms))
    print()
    print("Legend:")
    print("  conf_med           median CTC confidence (Tier 2)")
    print("  <0.6%              % of words with confidence < 0.6")
    print("  onset/offset_p90   p90 |Tier2 - Tier1| boundary shift in ms")
    print("  edge_p90           p90 of max(onset, offset) shift per word")
    print(f"  >{int(args.padding_ms)}ms%             % of words whose worst-edge shift > padding (truncation risk)")
    print("  fallback%          % of words using proportional-fallback (alignment failed)")

    if args.json_out:
        args.json_out.write_text(
            json.dumps({"aggregate": aggregate, "per_pair": per_pair}, indent=2),
            encoding="utf-8",
        )
        print(f"\nFull results: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
