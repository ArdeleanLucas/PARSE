#!/usr/bin/env python3
"""PARSE chat orchestration (OpenAI + strict PARSE-native tools).

This orchestrator is intentionally read-only in MVP:
- no annotation/config/enrichment writes
- no arbitrary shell/file tools
- no file attachments
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .chat_tools import ChatToolError, ParseChatTools
from .provider import OpenAIChatRuntime


class ChatOrchestratorError(Exception):
    """Raised when the chat orchestrator cannot complete a run."""


class ChatOrchestrator:
    """Server-side chat orchestrator with bounded function-calling."""

    def __init__(
        self,
        project_root: Path,
        tools: ParseChatTools,
        config_path: Optional[Path] = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.tools = tools
        self.runtime = OpenAIChatRuntime(config_path=config_path)

        chat_config = self.runtime.chat_config
        self.max_tool_rounds = max(1, int(chat_config.get("max_tool_rounds", 4) or 4))
        self.max_history_messages = max(1, int(chat_config.get("max_history_messages", 24) or 24))
        self.max_tool_result_chars = max(1000, int(chat_config.get("max_tool_result_chars", 24000) or 24000))

        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        tool_lines = "\n".join(["- {0}".format(name) for name in self.tools.tool_names()])
        return (
            "You are the built-in PARSE AI toolbox assistant.\n"
            "\n"
            "Hard constraints (must follow):\n"
            "1) READ-ONLY MVP: do not mutate project state. No annotation writes, no config writes, no enrichments writes, no file overwrites.\n"
            "2) Only use allowlisted PARSE-native tools. Never invent tools and never request shell access.\n"
            "3) No file/context attachments are supported in this MVP.\n"
            "4) If asked to apply changes, explicitly state this build can only return previews/artifacts.\n"
            "5) Be transparent: if a tool is placeholder/unavailable, say so clearly.\n"
            "\n"
            "Available tools:\n"
            "{0}\n"
            "\n"
            "Response style:\n"
            "- concise, technical, and accurate\n"
            "- when using tools, summarize what was checked\n"
            "- do not claim writes were performed\n"
        ).format(tool_lines)

    def _history_messages(self, session_messages: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for row in session_messages[-self.max_history_messages :]:
            role = str(row.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue

            content = str(row.get("content") or "")
            filtered.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return filtered

    def _extract_message_text(self, message: Any) -> str:
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        chunks.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        chunks.append(item["content"])
                else:
                    text_value = getattr(item, "text", None)
                    if isinstance(text_value, str):
                        chunks.append(text_value)
            return "\n".join([chunk for chunk in chunks if chunk]).strip()

        return str(content or "").strip()

    def _extract_tool_calls(self, message: Any) -> List[Dict[str, str]]:
        raw_calls = getattr(message, "tool_calls", None)
        if not raw_calls:
            return []

        out: List[Dict[str, str]] = []
        for raw_call in raw_calls:
            call_id = ""
            name = ""
            arguments = "{}"

            if isinstance(raw_call, dict):
                call_id = str(raw_call.get("id") or "")
                function_payload = raw_call.get("function")
                if isinstance(function_payload, dict):
                    name = str(function_payload.get("name") or "")
                    arguments = str(function_payload.get("arguments") or "{}")
            else:
                call_id = str(getattr(raw_call, "id", "") or "")
                function_payload = getattr(raw_call, "function", None)
                if function_payload is not None:
                    name = str(getattr(function_payload, "name", "") or "")
                    arguments = str(getattr(function_payload, "arguments", "{}") or "{}")

            if not call_id:
                call_id = "call_{0}".format(uuid.uuid4().hex[:12])

            name = name.strip()
            if not name:
                continue

            out.append(
                {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                }
            )

        return out

    def _assistant_message_with_tool_calls(
        self,
        content: str,
        tool_calls: Sequence[Mapping[str, str]],
    ) -> Dict[str, Any]:
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": str(call.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(call.get("name") or ""),
                        "arguments": str(call.get("arguments") or "{}"),
                    },
                }
                for call in tool_calls
            ],
        }

    def _truncate_tool_content(self, payload: Dict[str, Any]) -> str:
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) <= self.max_tool_result_chars:
            return text

        overflow = len(text) - self.max_tool_result_chars
        clipped = text[: self.max_tool_result_chars]
        return (
            clipped
            + "\n...TRUNCATED..."
            + json.dumps(
                {
                    "truncated": True,
                    "overflowChars": overflow,
                },
                ensure_ascii=False,
            )
        )

    def run(
        self,
        session_id: str,
        session_messages: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Run one assistant turn for an existing session history."""
        if not session_messages:
            raise ChatOrchestratorError("Session has no messages to process")

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": self._system_prompt,
            }
        ]
        messages.extend(self._history_messages(session_messages))

        tool_trace: List[Dict[str, Any]] = []
        runtime_meta: Dict[str, Any] = {}

        for round_index in range(self.max_tool_rounds + 1):
            tools_payload = self.tools.openai_tool_schemas() if round_index < self.max_tool_rounds else None
            tool_choice = "auto" if tools_payload else None

            response, runtime_meta = self.runtime.complete(
                messages=messages,
                tools=tools_payload,
                tool_choice=tool_choice,
            )

            if not getattr(response, "choices", None):
                raise ChatOrchestratorError("LLM returned no choices")

            message = response.choices[0].message
            assistant_text = self._extract_message_text(message)
            tool_calls = self._extract_tool_calls(message)

            if tool_calls and round_index < self.max_tool_rounds:
                messages.append(self._assistant_message_with_tool_calls(assistant_text, tool_calls))

                for call in tool_calls:
                    tool_name = str(call.get("name") or "").strip()
                    raw_args = call.get("arguments") or "{}"

                    try:
                        tool_result = self.tools.execute(tool_name, raw_args)
                    except ChatToolError as exc:
                        tool_result = {
                            "tool": tool_name,
                            "ok": False,
                            "error": str(exc),
                        }
                    except Exception as exc:
                        tool_result = {
                            "tool": tool_name,
                            "ok": False,
                            "error": "Unexpected tool failure: {0}".format(exc),
                        }

                    tool_trace.append(
                        {
                            "callId": call.get("id"),
                            "tool": tool_name,
                            "ok": bool(tool_result.get("ok", False)),
                        }
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(call.get("id") or ""),
                            "name": tool_name,
                            "content": self._truncate_tool_content(tool_result),
                        }
                    )

                continue

            final_text = assistant_text
            if not final_text:
                if tool_trace:
                    final_text = "Tool calls completed, but the model returned no final text."
                else:
                    final_text = "I could not generate a response for this request."

            return {
                "sessionId": session_id,
                "assistant": {
                    "role": "assistant",
                    "content": final_text,
                },
                "toolTrace": tool_trace,
                "model": runtime_meta.get("model", self.runtime.model),
                "reasoning": runtime_meta,
                "readOnly": True,
                "attachmentsSupported": False,
            }

        return {
            "sessionId": session_id,
            "assistant": {
                "role": "assistant",
                "content": (
                    "I hit the maximum tool-call rounds for this turn. "
                    "Please narrow the request and try again."
                ),
            },
            "toolTrace": tool_trace,
            "model": runtime_meta.get("model", self.runtime.model),
            "reasoning": runtime_meta,
            "readOnly": True,
            "attachmentsSupported": False,
        }


__all__ = ["ChatOrchestrator", "ChatOrchestratorError"]
