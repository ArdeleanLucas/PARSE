"""Tests for read_text_preview chat tool."""

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat_tools import ParseChatTools


def _build_project(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "ai_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "annotations").mkdir(parents=True, exist_ok=True)
    (tmp_path / "audio").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_read_text_preview_in_allowlist(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    tools = ParseChatTools(project_root=project)

    assert "read_text_preview" in tools.tool_names()
    schemas = tools.openai_tool_schemas()
    names = [item["function"]["name"] for item in schemas]
    assert "read_text_preview" in names


def test_read_text_preview_reads_markdown_in_project_root(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    md_path = project / "notes.md"
    md_path.write_text("# Title\n\nLine one\nLine two\n", encoding="utf-8")

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_text_preview", {"path": "notes.md", "startLine": 1, "maxLines": 3})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert inner["path"].endswith("notes.md")
    assert "# Title" in inner["content"]


def test_read_text_preview_reads_markdown_from_docs_root(tmp_path: Path) -> None:
    project = _build_project(tmp_path / "proj")
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    doc_file = docs / "methodology.md"
    doc_file.write_text("## Methods\nSome text\n", encoding="utf-8")

    tools = ParseChatTools(project_root=project, docs_root=docs)
    result = tools.execute("read_text_preview", {"path": str(doc_file)})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is True
    assert "## Methods" in inner["content"]


def test_read_text_preview_rejects_non_text_extension(tmp_path: Path) -> None:
    project = _build_project(tmp_path)
    bad_path = project / "data.json"
    bad_path.write_text('{"a": 1}', encoding="utf-8")

    tools = ParseChatTools(project_root=project)
    result = tools.execute("read_text_preview", {"path": "data.json"})

    assert result["ok"] is True
    inner = result["result"]
    assert inner["ok"] is False
    assert "Unsupported file type" in inner["error"]
