#!/usr/bin/env python3
"""PARSE chat orchestration (OpenAI + strict PARSE-native tools).

This orchestrator is intentionally read-only in MVP:
- no annotation/config/enrichment writes
- no arbitrary shell/file tools
- no file attachments
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .chat_tools import ChatToolError, ParseChatTools, WRITE_ALLOWED_TOOL_NAMES
from .provider import OpenAIChatRuntime


_MUTATION_REQUEST_RE = re.compile(
    r"\b(write|save|update|edit|modify|patch|delete|remove|rename|apply|commit|overwrite|import|create|add)\b",
    flags=re.IGNORECASE,
)
_ATTACHMENT_REQUEST_RE = re.compile(
    r"\b(attach|attachment|upload|drag[- ]?and[- ]?drop|paste\s+file|drop\s+file)\b",
    flags=re.IGNORECASE,
)
_WRITE_CLAIM_RE = re.compile(
    r"\b(i|we)\s+(updated|saved|edited|modified|changed|deleted|removed|wrote|applied|renamed|created|added)\b",
    flags=re.IGNORECASE,
)
READ_ONLY_NOTICE = (
    "This PARSE assistant build is mostly read-only. I can inspect data and draft previews, "
    "but only specific allowlisted tools may write dedicated support files; annotations and enrichments remain read-only from chat."
)
_ATTACHMENTS_NOTICE = "This build also does not support file/context attachments."


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
        self.read_only = bool(chat_config.get("read_only", True))
        self.attachments_supported = bool(chat_config.get("attachments_supported", False))

        # Chat MVP is intentionally locked to read-only + no attachments.
        if not self.read_only:
            self.read_only = True
        if self.attachments_supported:
            self.attachments_supported = False

        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        tool_lines = "\n".join(["- {0}".format(name) for name in self.tools.tool_names()])
        return (
            "You are the built-in PARSE AI toolbox assistant.\n"
            "\n"
            "Hard constraints (must follow):\n"
            "1) READ-ONLY MVP: do not mutate project state. No annotation writes, no config writes, no enrichments writes, no file overwrites.\n"
            "   Exception: contact_lexeme_lookup and tag tools are allowed to write their respective data files.\n"
            "2) Only use allowlisted PARSE-native tools. Never invent tools and never request shell access.\n"
            "3) No file/context attachments are supported in this MVP.\n"
            "4) If asked to apply changes, explicitly state the environment is mostly read-only and provide a preview plan unless an allowlisted write-capable tool is the correct path.\n"
            "5) Never imply a write happened unless an allowlisted write-capable tool explicitly reports a persisted write.\n"
            "6) Be transparent: if a tool is placeholder/unavailable, say so clearly.\n"
            "\n"
            "Available tools:\n"
            "{0}\n"
            "\n"
            "External data fetching:\n"
            "- contact_lexeme_lookup can fetch reference forms (IPA) for ANY language from third-party sources\n"
            "  (CLDF datasets, ASJP, Wikidata, Wiktionary, Grokipedia LLM, literature)\n"
            "- Use it when the user needs Arabic, Persian, Sorani, or other reference language data\n"
            "- After fetching, use cognate_compute_preview with contactLanguages to compare\n"
            "\n"
            "Response style:\n"
            "- concise, technical, and accurate\n"
            "- when using tools, summarize what was checked\n"
            "- keep read-only limitations explicit when relevant\n"
            "- Use readable Markdown with short headings, bullets, and blank lines between sections\n"
            "- Never wrap the entire reply in a code fence unless the user explicitly asked for raw copy-paste output\n"
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

    def _latest_user_text(self, session_messages: Sequence[Mapping[str, Any]]) -> str:
        for row in reversed(session_messages):
            role = str(row.get("role") or "").strip().lower()
            if role != "user":
                continue
            return str(row.get("content") or "").strip()
        return ""

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

    def _contains_read_only_notice(self, text: str) -> bool:
        lowered = str(text or "").lower()
        return (
            "read-only" in lowered
            or "read only" in lowered
            or "cannot apply" in lowered
            or "can't apply" in lowered
            or "cannot write" in lowered
            or "can't write" in lowered
        )

    def _contains_attachments_notice(self, text: str) -> bool:
        lowered = str(text or "").lower()
        return "attachment" in lowered or "upload" in lowered or "file/context" in lowered

    def _write_applied_tool_names(self, tool_trace: Sequence[Mapping[str, Any]]) -> List[str]:
        names: List[str] = []
        for entry in tool_trace:
            tool_name = str(entry.get("tool") or "").strip()
            if not tool_name:
                continue
            if tool_name not in WRITE_ALLOWED_TOOL_NAMES:
                continue
            if not bool(entry.get("ok", False)):
                continue
            if bool(entry.get("readOnly", True)):
                continue
            if tool_name not in names:
                names.append(tool_name)
        return names

    def _apply_read_only_guard(
        self,
        assistant_text: str,
        latest_user_text: str,
        used_tool_names: Optional[Sequence[str]] = None,
    ) -> str:
        text = str(assistant_text or "").strip()
        user_text = str(latest_user_text or "").strip()
        used_tools = {
            str(tool_name or "").strip()
            for tool_name in (used_tool_names or [])
            if str(tool_name or "").strip()
        }
        write_allowed_tool_used = bool(used_tools.intersection(WRITE_ALLOWED_TOOL_NAMES))

        if not text:
            text = READ_ONLY_NOTICE

        if (
            _WRITE_CLAIM_RE.search(text)
            and not write_allowed_tool_used
            and not self._contains_read_only_notice(text)
        ):
            text = "{0}\n\n{1}".format(text, READ_ONLY_NOTICE)

        if (
            user_text
            and _MUTATION_REQUEST_RE.search(user_text)
            and not write_allowed_tool_used
        ):
            if not self._contains_read_only_notice(text):
                text = "{0}\n\n{1}".format(READ_ONLY_NOTICE, text)

        if user_text and _ATTACHMENT_REQUEST_RE.search(user_text):
            if not self._contains_attachments_notice(text):
                text = "{0}\n\n{1}".format(_ATTACHMENTS_NOTICE, text)

        return text

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
        latest_user_text = self._latest_user_text(session_messages)

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
                            "readOnly": bool((tool_result.get("result") or {}).get("readOnly", True)),
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

            used_tool_names = self._write_applied_tool_names(tool_trace)
            final_text = self._apply_read_only_guard(final_text, latest_user_text, used_tool_names=used_tool_names)

            return {
                "sessionId": session_id,
                "assistant": {
                    "role": "assistant",
                    "content": final_text,
                },
                "toolTrace": tool_trace,
                "model": runtime_meta.get("model", self.runtime.model),
                "reasoning": runtime_meta,
                "mode": "read-only",
                "readOnly": self.read_only,
                "attachmentsSupported": self.attachments_supported,
                "readOnlyNotice": READ_ONLY_NOTICE,
            }

        return {
            "sessionId": session_id,
            "assistant": {
                "role": "assistant",
                "content": (
                    "I hit the maximum tool-call rounds for this turn. "
                    "Please narrow the request and try again.\n\n"
                    "{0}".format(READ_ONLY_NOTICE)
                ),
            },
            "toolTrace": tool_trace,
            "model": runtime_meta.get("model", self.runtime.model),
            "reasoning": runtime_meta,
            "mode": "read-only",
            "readOnly": self.read_only,
            "attachmentsSupported": self.attachments_supported,
            "readOnlyNotice": READ_ONLY_NOTICE,
        }


__all__ = ["ChatOrchestrator", "ChatOrchestratorError", "READ_ONLY_NOTICE"]
