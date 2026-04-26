from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from ..chat_tools import (
    ChatToolExecutionError,
    ChatToolSpec,
    ChatToolValidationError,
    TOKEN_RE,
    _coerce_float,
    _concept_sort_key,
    _normalize_concept_id,
    _normalize_space,
    _utc_now_iso,
    cognate_compute_module,
    cross_speaker_match_module,
)

if TYPE_CHECKING:
    from ..chat_tools import ParseChatTools


COMPARATIVE_TOOL_NAMES = (
    "cognate_compute_preview",
    "cross_speaker_match_preview",
)


COMPARATIVE_TOOL_SPECS: Dict[str, ChatToolSpec] = {
    "cognate_compute_preview": ChatToolSpec(
                    name="cognate_compute_preview",
                    description=(
                        "Compute a read-only cognate/similarity preview from annotations. "
                        "Does not write parse-enrichments.json."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speakers": {
                                "type": "array",
                                "maxItems": 300,
                                "items": {"type": "string", "minLength": 1, "maxLength": 200},
                            },
                            "conceptIds": {
                                "type": "array",
                                "maxItems": 500,
                                "items": {"type": "string", "minLength": 1, "maxLength": 64},
                            },
                            "threshold": {"type": "number", "minimum": 0.01, "maximum": 2.0},
                            "contactLanguages": {
                                "type": "array",
                                "maxItems": 20,
                                "items": {"type": "string", "minLength": 1, "maxLength": 16},
                            },
                            "includeSimilarity": {"type": "boolean"},
                            "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                        },
                    },
                ),
    "cross_speaker_match_preview": ChatToolSpec(
                    name="cross_speaker_match_preview",
                    description=(
                        "Compute read-only cross-speaker match candidates from STT output and existing "
                        "annotations. Accepts sttJobId or inline sttSegments."
                    ),
                    parameters={
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speaker": {"type": "string", "minLength": 1, "maxLength": 200},
                            "sttJobId": {"type": "string", "minLength": 1, "maxLength": 128},
                            "sttSegments": {
                                "type": "array",
                                "maxItems": 20000,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "properties": {
                                        "start": {"type": "number"},
                                        "end": {"type": "number"},
                                        "startSec": {"type": "number"},
                                        "endSec": {"type": "number"},
                                        "text": {"type": "string"},
                                        "ipa": {"type": "string"},
                                        "ortho": {"type": "string"},
                                    },
                                },
                            },
                            "topK": {"type": "integer", "minimum": 1, "maximum": 20},
                            "minConfidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "maxConcepts": {"type": "integer", "minimum": 1, "maximum": 500},
                        },
                    },
                ),
}


def cognate_compute_preview(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        if cognate_compute_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cognate_compute module is unavailable",
            }

        threshold = _coerce_float(args.get("threshold"), 0.60)
        if threshold <= 0:
            raise ChatToolValidationError("threshold must be > 0")

        include_similarity = bool(args.get("includeSimilarity", True))
        max_concepts = int(args.get("maxConcepts", 40) or 40)

        speaker_values = args.get("speakers")
        speaker_filter: List[str] = []
        if isinstance(speaker_values, list):
            seen: Dict[str, bool] = {}
            for raw_speaker in speaker_values:
                speaker = _normalize_space(raw_speaker)
                if speaker and speaker not in seen:
                    seen[speaker] = True
                    speaker_filter.append(speaker)

        concept_values = args.get("conceptIds")
        concept_filter: List[str] = []
        if isinstance(concept_values, list):
            seen_concepts: Dict[str, bool] = {}
            for raw_concept in concept_values:
                concept_id = _normalize_concept_id(raw_concept)
                if concept_id and concept_id not in seen_concepts:
                    seen_concepts[concept_id] = True
                    concept_filter.append(concept_id)

        contact_override_raw = args.get("contactLanguages")
        contact_override: List[str] = []
        if isinstance(contact_override_raw, list):
            contact_override = [str(item).strip().lower() for item in contact_override_raw if str(item).strip()]

        contact_languages_from_config, refs_by_concept, form_selections_by_concept = cognate_compute_module.load_contact_language_data(
            tools.sil_config_path
        )
        contact_languages = contact_override or contact_languages_from_config

        forms_by_concept, discovered_speakers = cognate_compute_module.load_annotations(tools.annotations_dir)

        speaker_filter_set = set(speaker_filter)
        concept_filter_set = set(concept_filter)

        filtered_forms: Dict[str, List[Any]] = {}
        for raw_concept_id, records in forms_by_concept.items():
            concept_id = _normalize_concept_id(raw_concept_id)
            if not concept_id:
                continue
            if concept_filter_set and concept_id not in concept_filter_set:
                continue

            kept: List[Any] = []
            for record in records:
                speaker = _normalize_space(getattr(record, "speaker", ""))
                if speaker_filter_set and speaker not in speaker_filter_set:
                    continue
                kept.append(record)

            if kept:
                filtered_forms[concept_id] = kept

        if concept_filter:
            selected_concepts = [concept for concept in concept_filter if concept in filtered_forms]
        else:
            selected_concepts = sorted(filtered_forms.keys(), key=_concept_sort_key)

        truncated = len(selected_concepts) > max_concepts
        if truncated:
            selected_concepts = selected_concepts[:max_concepts]
            filtered_forms = {
                concept_id: filtered_forms.get(concept_id, [])
                for concept_id in selected_concepts
                if concept_id in filtered_forms
            }

        concept_specs = [
            cognate_compute_module.ConceptSpec(concept_id=concept_id, label="")
            for concept_id in selected_concepts
        ]

        cognate_sets = cognate_compute_module._compute_cognate_sets_with_lingpy(
            filtered_forms,
            concept_specs,
            threshold,
        )

        similarity: Dict[str, Any] = {}
        if include_similarity:
            similarity = cognate_compute_module.compute_similarity_scores(
                forms_by_concept=filtered_forms,
                concepts=concept_specs,
                contact_languages=contact_languages,
                refs_by_concept=refs_by_concept,
                form_selections_by_concept=form_selections_by_concept,
            )

        if speaker_filter:
            speakers_included = sorted([speaker for speaker in discovered_speakers if speaker in speaker_filter_set])
        else:
            speakers_included = sorted(discovered_speakers)

        preview_payload = {
            "computed_at": _utc_now_iso(),
            "config": {
                "contact_languages": list(contact_languages),
                "speakers_included": speakers_included,
                "concepts_included": selected_concepts,
                "lexstat_threshold": round(float(threshold), 3),
            },
            "cognate_sets": cognate_sets,
            "similarity": similarity,
            "borrowing_flags": {},
            "manual_overrides": {},
        }

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "truncated": truncated,
            "maxConcepts": max_concepts,
            "summary": {
                "conceptCount": len(preview_payload["config"]["concepts_included"]),
                "speakerCount": len(preview_payload["config"]["speakers_included"]),
                "hasSimilarity": include_similarity,
            },
            "enrichmentsPreview": preview_payload,
            "note": "Preview only. parse-enrichments.json was not modified.",
        }


def segments_from_payload(tools: "ParseChatTools", payload: Sequence[Any]) -> List[Any]:
        if cross_speaker_match_module is None:
            return []

        segments: List[Any] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue

            start_sec = _coerce_float(item.get("start", item.get("startSec", 0.0)), 0.0)
            end_sec = _coerce_float(item.get("end", item.get("endSec", start_sec)), start_sec)
            if end_sec < start_sec:
                end_sec = start_sec

            text = _normalize_space(item.get("text"))
            ipa = _normalize_space(item.get("ipa"))
            ortho = _normalize_space(item.get("ortho", text))

            token_source = "{0} {1}".format(ipa, text)
            tokens = [token for token in TOKEN_RE.findall(token_source.lower()) if token]
            deduped_tokens: List[str] = []
            seen: Dict[str, bool] = {}
            for token in tokens:
                if token in seen:
                    continue
                seen[token] = True
                deduped_tokens.append(token)

            segments.append(
                cross_speaker_match_module.SegmentRecord(
                    index=index,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    text=text,
                    ipa=ipa,
                    ortho=ortho,
                    tokens=deduped_tokens,
                )
            )

        segments.sort(key=lambda row: (float(getattr(row, "start_sec", 0.0)), float(getattr(row, "end_sec", 0.0))))
        for new_index, segment in enumerate(segments):
            segment.index = new_index

        return segments


def cross_speaker_match_preview(tools: "ParseChatTools", args: Dict[str, Any]) -> Dict[str, Any]:
        if cross_speaker_match_module is None:
            return {
                "readOnly": True,
                "previewOnly": True,
                "status": "unavailable",
                "message": "compare.cross_speaker_match module is unavailable",
            }

        top_k = int(args.get("topK", 5) or 5)
        min_confidence = _coerce_float(args.get("minConfidence"), 0.35)
        min_confidence = max(0.0, min(1.0, min_confidence))
        max_concepts = int(args.get("maxConcepts", 100) or 100)

        speaker = _normalize_space(args.get("speaker"))
        raw_segments: List[Any] = []
        source_label = ""

        stt_job_id = _normalize_space(args.get("sttJobId"))
        if stt_job_id:
            if tools._get_job_snapshot is None:
                raise ChatToolExecutionError("Job snapshot callback is unavailable")

            snapshot = tools._get_job_snapshot(stt_job_id)
            if snapshot is None:
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": "not_found",
                    "jobId": stt_job_id,
                    "message": "Unknown sttJobId",
                }

            if snapshot.get("type") != "stt":
                raise ChatToolValidationError("sttJobId does not point to an STT job")

            if snapshot.get("status") != "complete":
                return {
                    "readOnly": True,
                    "previewOnly": True,
                    "status": snapshot.get("status"),
                    "jobId": stt_job_id,
                    "progress": snapshot.get("progress"),
                    "message": "STT job is not complete yet",
                }

            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
            if not speaker:
                speaker = _normalize_space(result.get("speaker") or snapshot.get("meta", {}).get("speaker"))

            segments_obj = result.get("segments")
            if isinstance(segments_obj, list):
                raw_segments = segments_obj
                source_label = "sttJob:{0}".format(stt_job_id)

        if not raw_segments:
            inline_segments = args.get("sttSegments")
            if isinstance(inline_segments, list):
                raw_segments = inline_segments
                source_label = "inline"

        if not raw_segments:
            raise ChatToolValidationError("Provide sttJobId or sttSegments")

        if not speaker:
            speaker = "unknown"

        segments = segments_from_payload(tools, raw_segments)
        profiles = cross_speaker_match_module.load_concept_profiles(tools.annotations_dir)
        rules = cross_speaker_match_module.load_rules_from_file(tools.phonetic_rules_path)

        result_payload = cross_speaker_match_module.match_cross_speaker(
            speaker_id=speaker,
            segments=segments,
            profiles=profiles,
            rules=rules,
            top_k=max(1, int(top_k)),
            min_confidence=min_confidence,
        )

        matches = result_payload.get("matches") if isinstance(result_payload, dict) else []
        if not isinstance(matches, list):
            matches = []

        truncated = len(matches) > max_concepts
        if truncated and isinstance(result_payload, dict):
            result_payload["matches"] = matches[:max_concepts]

        return {
            "readOnly": True,
            "previewOnly": True,
            "appliedToProjectState": False,
            "source": source_label,
            "summary": {
                "segmentCount": len(segments),
                "profileCount": len(profiles),
                "matchConceptCount": len(result_payload.get("matches", [])) if isinstance(result_payload, dict) else 0,
                "truncated": truncated,
                "maxConcepts": max_concepts,
            },
            "matchPreview": result_payload,
            "note": "Preview only. No annotation/enrichment writes were performed.",
        }


COMPARATIVE_TOOL_HANDLERS = {
    "cognate_compute_preview": cognate_compute_preview,
    "cross_speaker_match_preview": cross_speaker_match_preview,
}


__all__ = [
    "COMPARATIVE_TOOL_NAMES",
    "COMPARATIVE_TOOL_SPECS",
    "COMPARATIVE_TOOL_HANDLERS",
    "segments_from_payload",
    "cognate_compute_preview",
    "cross_speaker_match_preview",
]
