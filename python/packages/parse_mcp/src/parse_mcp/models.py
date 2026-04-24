from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


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
