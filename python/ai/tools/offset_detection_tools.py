from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..chat_tools import (
    SPEAKER_PATTERN,
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


OFFSET_DETECTION_TOOL_NAMES = (
    "detect_timestamp_offset",
    "detect_timestamp_offset_from_pair",
)


OFFSET_DETECTION_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "detect_timestamp_offset": ChatToolSpec(
        name="detect_timestamp_offset",
        description=(
            "Detect a constant timestamp offset between a speaker's annotation "
            "intervals and STT segments for the same audio. Uses monotonic "
            "anchor-segment alignment (chosen matches must visit anchors and "
            "segments in increasing time order) so false matches to similar-"
            "sounding words elsewhere in the recording can't elect the wrong "
            "direction. Anchors are sampled across the timeline by quantile "
            "by default — pass anchorDistribution='earliest' to use the legacy "
            "first-N selection. Read-only; returns offsetSec, confidence, "
            "spreadSec, direction, warnings, and the matched anchor↔segment "
            "pairs so callers can sanity-check before applying."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "sttJobId": {"type": "string", "minLength": 1, "maxLength": 128},
                "nAnchors": {"type": "integer", "minimum": 2, "maximum": 50},
                "bucketSec": {"type": "number", "minimum": 0.1, "maximum": 30.0},
                "minMatchScore": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "anchorDistribution": {"type": "string", "enum": ["quantile", "earliest"]},
            },
        },
    ),
    "detect_timestamp_offset_from_pair": ChatToolSpec(
        name="detect_timestamp_offset_from_pair",
        description=(
            "Compute a timestamp offset from one or more trusted "
            "(csvTime, audioTime) pairs — no STT, no statistics-on-text, "
            "no false matches. Use this when the user (or you) already "
            "knows where one or more lexemes actually are in the audio.\n\n"
            "Two argument shapes are accepted:\n"
            " - Single pair: pass speaker + audioTimeSec + (csvTimeSec OR conceptId)\n"
            " - Multiple pairs: pass speaker + pairs=[{...}, {...}]. With "
            "two or more pairs the offset is the median of per-pair offsets, "
            "and the response carries the MAD spread plus warnings if any "
            "pair disagrees with the consensus by more than ~2 s.\n\n"
            "The response shape is the same as detect_timestamp_offset, so "
            "the offsetSec can be passed straight into apply_timestamp_offset."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker"],
            "properties": {
                "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                "audioTimeSec": {"type": "number", "minimum": 0.0},
                "csvTimeSec": {"type": "number", "minimum": 0.0},
                "conceptId": {"type": "string", "minLength": 1, "maxLength": 128},
                "pairs": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 32,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["audioTimeSec"],
                        "properties": {
                            "audioTimeSec": {"type": "number", "minimum": 0.0},
                            "csvTimeSec": {"type": "number", "minimum": 0.0},
                            "conceptId": {"type": "string", "minLength": 1, "maxLength": 128},
                        },
                    },
                },
            },
        },
    ),
}


def _collect_offset_anchor_intervals(record: Any) -> List[Dict[str, Any]]:
    if not isinstance(record, dict):
        return []
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return []
    for tier_key in ("ortho", "ipa", "concept"):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue
        collected: List[Dict[str, Any]] = []
        for raw in intervals:
            if not isinstance(raw, dict):
                continue
            start = raw.get("start", raw.get("xmin"))
            end = raw.get("end", raw.get("xmax"))
            text = raw.get("text")
            try:
                start_f = float(start) if start is not None else None
                end_f = float(end) if end is not None else None
            except (TypeError, ValueError):
                continue
            if start_f is None or end_f is None or end_f < start_f:
                continue
            if not str(text or "").strip():
                continue
            collected.append({"start": start_f, "end": end_f, "text": str(text).strip()})
        if collected:
            return collected
    return []


def _format_offset_detect_payload(
    tools: "ParseChatTools",
    *,
    speaker: str,
    offset_sec: float,
    confidence: float,
    n_matched: int,
    total_anchors: int,
    total_segments: int,
    method: str,
    spread_sec: float,
    matches: List[Dict[str, Any]],
    anchor_distribution: str,
    annotation_path: Optional[Path],
) -> Dict[str, Any]:
    if abs(offset_sec) < 1e-3:
        direction = "none"
        direction_label = "no shift needed"
    elif offset_sec > 0:
        direction = "later"
        direction_label = "{0:.3f} s later (toward the end)".format(offset_sec)
    else:
        direction = "earlier"
        direction_label = "{0:.3f} s earlier (toward the start)".format(abs(offset_sec))

    reliable = bool(
        n_matched >= 3 and confidence >= 0.5 and (spread_sec <= 2.0 or n_matched == 1)
    )
    warnings: List[str] = []
    if n_matched < 3 and method != "manual_pair":
        warnings.append(
            "Only {0} anchor match{1} were found — apply with caution.".format(
                n_matched, "" if n_matched == 1 else "es"
            )
        )
    if spread_sec > 2.0:
        warnings.append(
            "Match offsets disagree by ±{0:.2f}s — the detected value may be noisy.".format(spread_sec)
        )
    if confidence < 0.5 and method != "manual_pair":
        warnings.append(
            "Low confidence; consider re-running STT or using "
            "detect_timestamp_offset_from_pair with a manual single-anchor pair."
        )
    if method == "bucket_vote":
        warnings.append(
            "Monotonic alignment failed; fell back to bucket vote which is more vulnerable to false matches."
        )

    payload: Dict[str, Any] = {
        "readOnly": True,
        "speaker": speaker,
        "offsetSec": float(offset_sec),
        "confidence": float(confidence),
        "nAnchors": int(n_matched),
        "totalAnchors": int(total_anchors),
        "totalSegments": int(total_segments),
        "method": method,
        "spreadSec": float(spread_sec),
        "direction": direction,
        "directionLabel": direction_label,
        "anchorDistribution": anchor_distribution,
        "reliable": reliable,
        "warnings": warnings,
        "matches": matches,
    }
    if annotation_path is not None:
        try:
            payload["annotationPath"] = str(annotation_path.relative_to(tools.project_root))
        except ValueError:
            payload["annotationPath"] = str(annotation_path)
    return payload


def _find_concept_interval(record: Any, concept_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(record, dict) or not concept_id:
        return None
    needle = str(concept_id).strip()
    if not needle:
        return None
    tiers = record.get("tiers")
    if not isinstance(tiers, dict):
        return None
    for tier_key in ("concept", "ortho", "ipa"):
        tier = tiers.get(tier_key)
        if not isinstance(tier, dict):
            continue
        intervals = tier.get("intervals")
        if not isinstance(intervals, list):
            continue
        for raw in intervals:
            if not isinstance(raw, dict):
                continue
            start = raw.get("start", raw.get("xmin"))
            text = str(raw.get("text") or "").strip()
            cid = str(raw.get("concept_id") or raw.get("conceptId") or "").strip()
            if cid != needle and text != needle:
                continue
            try:
                start_f = float(start) if start is not None else None
            except (TypeError, ValueError):
                continue
            if start_f is None or start_f < 0:
                continue
            return {"start": start_f, "text": text}
    return None


def tool_detect_timestamp_offset(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from compare import (
            anchors_from_intervals,
            detect_offset_detailed,
            load_rules_from_file,
            segments_from_raw,
        )
    except Exception as exc:
        raise ChatToolExecutionError(
            "compare/offset_detect.py is not importable: {0}".format(exc)
        ) from exc

    speaker_raw = str(args.get("speaker") or "").strip()
    if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
        raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
    speaker = speaker_raw

    annotation_path = tools._annotation_path_for_speaker(speaker)
    if annotation_path is None or not annotation_path.is_file():
        raise ChatToolValidationError(
            "No annotation file found for speaker '{0}'".format(speaker)
        )

    try:
        record = json.loads(annotation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc)) from exc

    intervals = _collect_offset_anchor_intervals(record)
    if not intervals:
        raise ChatToolValidationError(
            "Speaker '{0}' has no annotated intervals to use as offset anchors".format(speaker)
        )

    n_anchors = max(2, min(50, int(args.get("nAnchors") or 12)))
    bucket_sec = max(0.1, float(args.get("bucketSec") or 1.0))
    min_match_score = max(0.0, min(1.0, float(args.get("minMatchScore") or 0.56)))
    distribution = str(args.get("anchorDistribution") or "quantile").strip().lower()
    if distribution not in {"quantile", "earliest"}:
        distribution = "quantile"

    stt_segments: Optional[List[Any]] = None
    stt_job_id = str(args.get("sttJobId") or "").strip()
    if stt_job_id:
        if tools._get_job_snapshot is None:
            raise ChatToolExecutionError("Job snapshot callback is unavailable")
        snapshot = tools._get_job_snapshot(stt_job_id)
        if snapshot is None:
            raise ChatToolValidationError("Unknown sttJobId")
        if snapshot.get("type") != "stt":
            raise ChatToolValidationError("sttJobId is not an STT job")
        if snapshot.get("status") != "complete":
            raise ChatToolValidationError("STT job has not completed")
        result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
        seg_payload = result.get("segments")
        if isinstance(seg_payload, list):
            stt_segments = seg_payload

    if stt_segments is None:
        raise ChatToolValidationError(
            "sttJobId is required for detect_timestamp_offset; pass the jobId of a "
            "completed stt_start run for this speaker, or call "
            "detect_timestamp_offset_from_pair if you already know one true "
            "(csvTime, audioTime) pair."
        )

    rules_path = tools.phonetic_rules_path
    try:
        rules = load_rules_from_file(rules_path) if rules_path.exists() else []
    except Exception:
        rules = []

    anchors = anchors_from_intervals(intervals, n_anchors, distribution=distribution)
    if not anchors:
        raise ChatToolValidationError("No usable anchors with both timestamp and text in annotation")
    segments = segments_from_raw(stt_segments)
    if not segments:
        raise ChatToolValidationError("STT input contained no usable segments")

    try:
        detailed = detect_offset_detailed(
            anchors=anchors,
            segments=segments,
            rules=rules,
            bucket_sec=bucket_sec,
            min_match_score=min_match_score,
        )
    except ValueError as exc:
        raise ChatToolExecutionError(str(exc)) from exc

    return _format_offset_detect_payload(
        tools,
        speaker=speaker,
        offset_sec=float(detailed.offset_sec),
        confidence=float(detailed.confidence),
        n_matched=int(detailed.n_matched),
        total_anchors=len(anchors),
        total_segments=len(segments),
        method=detailed.method,
        spread_sec=float(detailed.spread_sec),
        matches=list(detailed.matches),
        anchor_distribution=distribution,
        annotation_path=annotation_path,
    )


def tool_detect_timestamp_offset_from_pair(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
    import math as _math
    import statistics as _statistics

    speaker_raw = str(args.get("speaker") or "").strip()
    if not speaker_raw or not SPEAKER_PATTERN.match(speaker_raw):
        raise ChatToolValidationError("speaker is required and must match {0}".format(SPEAKER_PATTERN.pattern))
    speaker = speaker_raw

    annotation_path = tools._annotation_path_for_speaker(speaker)
    record_cache: Optional[Dict[str, Any]] = None

    def _record() -> Dict[str, Any]:
        nonlocal record_cache
        if record_cache is None:
            if annotation_path is None or not annotation_path.is_file():
                raise ChatToolValidationError(
                    "No annotation file found for speaker '{0}'".format(speaker)
                )
            try:
                record_cache = json.loads(annotation_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ChatToolExecutionError("Failed to read annotation: {0}".format(exc)) from exc
        return record_cache

    if "pairs" in args and args["pairs"] is not None:
        raw_pairs = args["pairs"] if isinstance(args["pairs"], list) else []
        if not raw_pairs:
            raise ChatToolValidationError("pairs must be a non-empty array")
    else:
        raw_pairs = [{
            "audioTimeSec": args.get("audioTimeSec"),
            "csvTimeSec": args.get("csvTimeSec"),
            "conceptId": args.get("conceptId"),
        }]

    matches: List[Dict[str, Any]] = []
    offsets: List[float] = []

    for raw in raw_pairs:
        if not isinstance(raw, dict):
            raise ChatToolValidationError("Each pair must be a JSON object")
        try:
            audio_time = float(raw.get("audioTimeSec"))
        except (TypeError, ValueError):
            raise ChatToolValidationError("audioTimeSec is required for every pair")
        if not _math.isfinite(audio_time) or audio_time < 0:
            raise ChatToolValidationError("audioTimeSec must be finite and non-negative")

        anchor_csv_time: Optional[float] = None
        anchor_label: Optional[str] = None

        csv_raw = raw.get("csvTimeSec")
        concept_raw = raw.get("conceptId")
        if csv_raw is not None and (not isinstance(csv_raw, str) or csv_raw != ""):
            try:
                anchor_csv_time = float(csv_raw)
            except (TypeError, ValueError):
                raise ChatToolValidationError("csvTimeSec must be a number when provided")
            if not _math.isfinite(anchor_csv_time) or anchor_csv_time < 0:
                raise ChatToolValidationError("csvTimeSec must be finite and non-negative")
            anchor_label = "csvTimeSec={0:.3f}s".format(anchor_csv_time)
        elif concept_raw is not None and str(concept_raw).strip():
            concept_id = str(concept_raw).strip()
            interval = _find_concept_interval(_record(), concept_id)
            if interval is None:
                raise ChatToolValidationError(
                    "No annotation interval found for concept '{0}'".format(concept_id)
                )
            anchor_csv_time = float(interval["start"])
            anchor_label = "concept '{0}' @ {1:.3f}s".format(concept_id, anchor_csv_time)
        else:
            raise ChatToolValidationError("Each pair needs either csvTimeSec or conceptId")

        offset_sec = round(audio_time - float(anchor_csv_time), 3)
        offsets.append(offset_sec)
        matches.append(
            {
                "anchor_index": -1,
                "anchor_text": anchor_label or "",
                "anchor_start": float(anchor_csv_time),
                "segment_index": -1,
                "segment_text": "(user-supplied audio time)",
                "segment_start": float(audio_time),
                "score": 1.0,
                "offset_sec": offset_sec,
            }
        )

    median_offset = round(_statistics.median(offsets), 3)
    if len(offsets) >= 2:
        deviations = [abs(o - median_offset) for o in offsets]
        spread = round(_statistics.median(deviations), 3)
        max_deviation = max(deviations)
        confidence = max(0.5, min(0.99, 0.99 - (max_deviation / 60.0)))
    else:
        spread = 0.0
        confidence = 0.99

    return _format_offset_detect_payload(
        tools,
        speaker=speaker,
        offset_sec=median_offset,
        confidence=float(confidence),
        n_matched=len(matches),
        total_anchors=len(matches),
        total_segments=0,
        method="manual_pair",
        spread_sec=float(spread),
        matches=matches,
        anchor_distribution="manual",
        annotation_path=annotation_path,
    )


OFFSET_DETECTION_TOOL_HANDLERS = {
    "detect_timestamp_offset": tool_detect_timestamp_offset,
    "detect_timestamp_offset_from_pair": tool_detect_timestamp_offset_from_pair,
}
