from __future__ import annotations

import json
from typing import Any, Callable, Dict


def serialize_tool_result(result: Any) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def execute_and_serialize(executor: Callable[[str, Dict[str, Any]], Any], tool_name: str, args: Dict[str, Any]) -> str:
    return serialize_tool_result(executor(tool_name, args))


__all__ = ["serialize_tool_result", "execute_and_serialize"]
