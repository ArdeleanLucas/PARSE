from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

PipelineRunMode = Literal["full", "concept-windows", "edited-only"]


def _int_from_payload(payload: Dict[str, Any], key: str, default: int = 0) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_from_payload(payload: Dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class RunFullAnnotationPipelineInput:
    speaker_id: str
    concept_list: List[str]
    run_mode: PipelineRunMode = "full"
    concept_ids: Optional[List[str]] = None
    dryRun: Optional[bool] = None

    def to_arguments(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "speaker_id": self.speaker_id,
            "concept_list": list(self.concept_list),
            "run_mode": self.run_mode,
        }
        if self.concept_ids is not None:
            payload["concept_ids"] = list(self.concept_ids)
        if self.dryRun is not None:
            payload["dryRun"] = bool(self.dryRun)
        return payload


@dataclass
class AffectedConcept:
    concept_id: str
    start: float
    end: float

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "AffectedConcept":
        payload = payload or {}
        return cls(
            concept_id=str(payload.get("concept_id") or ""),
            start=_float_from_payload(payload, "start"),
            end=_float_from_payload(payload, "end"),
        )


@dataclass
class RunFullAnnotationPipelineResult:
    speaker: str
    run_mode: PipelineRunMode = "full"
    affected_concepts: List[AffectedConcept] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "RunFullAnnotationPipelineResult":
        payload = payload or {}
        return cls(
            speaker=str(payload.get("speaker") or payload.get("speaker_id") or ""),
            run_mode=str(payload.get("run_mode") or "full"),  # type: ignore[arg-type]
            affected_concepts=[
                AffectedConcept.from_payload(item)
                for item in (payload.get("affected_concepts") or [])
                if isinstance(item, dict)
            ],
        )


@dataclass
class ApplyTimestampOffsetResult:
    speaker: str
    appliedOffsetSec: float
    shiftedIntervals: int
    shiftedConcepts: int
    protectedIntervals: int
    protectedLexemes: int

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ApplyTimestampOffsetResult":
        payload = payload or {}
        shifted_intervals = _int_from_payload(payload, "shiftedIntervals")
        return cls(
            speaker=str(payload.get("speaker") or ""),
            appliedOffsetSec=_float_from_payload(payload, "appliedOffsetSec"),
            shiftedIntervals=shifted_intervals,
            shiftedConcepts=_int_from_payload(payload, "shiftedConcepts", shifted_intervals),
            protectedIntervals=_int_from_payload(payload, "protectedIntervals"),
            protectedLexemes=_int_from_payload(payload, "protectedLexemes"),
        )


@dataclass
class ParseToolAnnotations:
    readOnlyHint: bool = False
    destructiveHint: bool = False
    openWorldHint: bool = False
    idempotentHint: bool = False

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ParseToolAnnotations":
        return cls(**{key: value for key, value in (payload or {}).items() if key in {"readOnlyHint", "destructiveHint", "openWorldHint", "idempotentHint"}})


@dataclass
class ParseToolMeta:
    x_parse: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ParseToolMeta":
        payload = payload or {}
        return cls(x_parse=dict(payload.get("x-parse") or {}))


@dataclass
class ParseToolSpec:
    name: str
    family: str
    description: str
    parameters: Dict[str, Any]
    annotations: ParseToolAnnotations
    meta: ParseToolMeta

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ParseToolSpec":
        return cls(
            name=str(payload.get("name") or ""),
            family=str(payload.get("family") or "chat"),
            description=str(payload.get("description") or ""),
            parameters=dict(payload.get("parameters") or {}),
            annotations=ParseToolAnnotations.from_payload(dict(payload.get("annotations") or {})),
            meta=ParseToolMeta.from_payload(dict(payload.get("meta") or {})),
        )
