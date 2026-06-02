from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from ai.chat_tools import ParseChatTools
from ai.tools import export_tools
from external_api.catalog import build_mcp_http_catalog

DEFAULT_TAG_ID = "custom-sk-concept-list"


def _make_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace with a multi-survey gloss ('big' in KLQ + JBIL), three speakers, and
    cognate decisions: SpkA->A, SpkB excluded, SpkC->B (borrowed); 'small' undecided."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "project.json").write_text(
        json.dumps(
            {
                "project_id": "appendix-test",
                "speakers": {"SpkA": {}, "SpkB": {}, "SpkC": {}},
                "concepts": {"source": "concepts.csv", "id_column": "id"},
            }
        ),
        encoding="utf-8",
    )
    with (workspace / "concepts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "concept_en", "source_item", "source_survey", "custom_order"],
        )
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "big", "source_item": "4.1", "source_survey": "KLQ", "custom_order": "1"})
        writer.writerow({"id": "2", "concept_en": "big", "source_item": "169", "source_survey": "JBIL", "custom_order": "2"})
        writer.writerow({"id": "3", "concept_en": "small", "source_item": "5.2", "source_survey": "KLQ", "custom_order": "3"})

    annotations = workspace / "annotations"
    annotations.mkdir()
    forms = {
        "SpkA": {"1": ("ɡap", "گەپ"), "3": ("kil", "کیل")},
        "SpkB": {"1": ("ɡap", "دید"), "3": ("kil", "کیل")},
        "SpkC": {"1": ("ɡoːda", "گەوورە"), "3": ("kul", "کول")},
    }
    for speaker, by_id in forms.items():
        intervals = []
        start = 1.0
        for concept_id, (ipa, ortho) in by_id.items():
            intervals.append(
                {"concept_id": concept_id, "start": start, "end": start + 0.5, "ipa": ipa, "ortho": ortho}
            )
            start += 1.0
        (annotations / f"{speaker}.parse.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "speaker": speaker,
                    "source_audio": f"audio/working/{speaker}/{speaker}.wav",
                    "tiers": {"concept": {"type": "interval", "intervals": intervals}},
                    "concept_tags": {"1": [DEFAULT_TAG_ID], "3": [DEFAULT_TAG_ID]},
                }
            ),
            encoding="utf-8",
        )

    (workspace / "parse-enrichments.json").write_text(
        json.dumps(
            {
                "manual_overrides": {
                    "cognate_sets": {"1": {"A": ["SpkA", "SpkB"], "B": ["SpkC"]}},
                    "cognate_decisions": {"1": {"decision": "split", "ts": 1}},
                    "borrowing_flags": {"1": {"SpkC": "Persian shape"}},
                    "speaker_flags": {"1": {"SpkB": True}},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return workspace


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------

def test_concept_appendix_tool_is_registered_for_chat_and_http_catalog(tmp_path: pathlib.Path) -> None:
    assert "export_concept_appendix_md" in export_tools.EXPORT_TOOL_NAMES
    assert "export_concept_appendix_md" in export_tools.EXPORT_TOOL_SPECS
    assert "export_concept_appendix_md" in export_tools.EXPORT_TOOL_HANDLERS

    tools = ParseChatTools(project_root=tmp_path)
    assert "export_concept_appendix_md" in tools.tool_names()
    spec = tools.tool_spec("export_concept_appendix_md")
    assert spec.mutability == "mutating"
    assert spec.parameters["additionalProperties"] is False
    assert set(spec.parameters["properties"]) == {
        "tagId",
        "includeCognates",
        "speakers",
        "conceptIds",
        "outputPath",
        "dryRun",
    }

    catalog = build_mcp_http_catalog(project_root=tmp_path, mode="all")
    assert "export_concept_appendix_md" in {tool["name"] for tool in catalog["tools"]}


# ---------------------------------------------------------------------------
# cognate-annotated export (preview / no outputPath returns full markdown)
# ---------------------------------------------------------------------------

def test_appendix_preview_includes_cognate_matrix_decisions(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute("export_concept_appendix_md", {})

    assert result["ok"] is True
    payload = result["result"]
    assert payload["previewOnly"] is True
    assert payload["speakers"] == 3
    assert payload["concepts"] == 2
    md = payload["markdown"]

    # multi-survey source line is reconstructed from concepts.csv grouping
    assert "**KLQ:** 4.1" in md
    assert "**JBIL:** 169" in md

    # top-level matrix + per-concept verdict
    assert "## Cognate matrix" in md
    assert "**Cognate:** split" in md
    assert "**Cognate:** —" in md  # 'small' has no decision

    # Cog column resolves: SpkA->A, SpkB excluded->?, SpkC->B with borrowing marker
    assert "| Speaker | IPA | ORTH | Cog |" in md
    assert "⟳" in md
    assert "B ⟳" in md
    assert "**Sets:** A = {SpkA}" in md
    assert "excluded: SpkB" in md


def test_appendix_speaker_subset_limits_matrix_and_forms(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"speakers": ["SpkA", "SpkC"]}
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["speakers"] == 2
    md = payload["markdown"]
    assert "**Speakers (2).** SpkA, SpkC." in md
    # SpkB is filtered out entirely — not a matrix column nor a forms row.
    assert "| SpkB |" not in md
    assert "| SpkA |" in md
    assert "| SpkC |" in md


def test_appendix_concept_subset_limits_to_requested_ids(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    # Visible concept menu filtered to just 'big' (id 1) — 'small' (id 3) must drop out,
    # and the export must not fall back to the whole tag.
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"conceptIds": ["1"]}
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["concepts"] == 1
    md = payload["markdown"]
    assert "### 1 · big" in md
    assert "small" not in md


def test_appendix_preserves_caller_concept_order(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    # concepts.csv order is big(1,2) then small(3). Request the reverse order to prove
    # the export mirrors the concept menu's order, not concepts.csv order.
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"conceptIds": ["3", "1"]}
    )
    md = result["result"]["markdown"]
    assert md.index("· small") < md.index("· big")
    assert "### 1 · small" in md
    assert "### 2 · big" in md


def test_appendix_unknown_speaker_returns_invalid_args(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"speakers": ["Nope01"]}
    )
    payload = result["result"]
    assert payload["ok"] is False
    assert payload["error_kind"] == "invalid_args"
    assert "Nope01" in payload["error"]


def test_appendix_excluded_speaker_renders_question_mark_not_letter(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute("export_concept_appendix_md", {})
    md = result["result"]["markdown"]

    big_section = md.split("### 1 · big", 1)[1].split("###", 1)[0]
    spkb_row = next(line for line in big_section.splitlines() if line.startswith("| SpkB |"))
    assert spkb_row.rstrip().endswith("| ? |")  # excluded -> ? even though listed in set A


# ---------------------------------------------------------------------------
# forms-only export (includeCognates=false)
# ---------------------------------------------------------------------------

def test_appendix_forms_only_omits_all_cognate_columns(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"includeCognates": False}
    )
    md = result["result"]["markdown"]

    assert "## Cognate matrix" not in md
    assert "| Cog |" not in md
    assert "**Cognate:**" not in md
    assert "**Sets:**" not in md
    # forms + survey line still present
    assert "### 1 · big" in md
    assert "**KLQ:** 4.1" in md
    assert "| Speaker | IPA | ORTH |" in md


# ---------------------------------------------------------------------------
# write path
# ---------------------------------------------------------------------------

def test_appendix_write_path_writes_markdown_inside_project(tmp_path: pathlib.Path) -> None:
    workspace = _make_workspace(tmp_path)
    result = ParseChatTools(project_root=workspace).execute(
        "export_concept_appendix_md", {"outputPath": "exports/concept-appendix.md"}
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["success"] is True
    out_path = pathlib.Path(payload["outputPath"])
    assert out_path == workspace / "exports" / "concept-appendix.md"
    assert out_path.exists()
    written = out_path.read_text(encoding="utf-8")
    assert written.startswith("# Concept Appendix")
    assert payload["bytes"] == len(written.encode("utf-8"))
