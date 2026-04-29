import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import parse_mcp


def test_package_exports_public_entrypoints() -> None:
    assert hasattr(parse_mcp, "ParseMcpClient")
    assert hasattr(parse_mcp, "build_langchain_tools")
    assert hasattr(parse_mcp, "build_llamaindex_tools")
    assert hasattr(parse_mcp, "build_crewai_tools")
    assert hasattr(parse_mcp, "ApplyTimestampOffsetResult")


def test_apply_timestamp_offset_result_typed_model_preserves_shifted_concepts() -> None:
    payload = {
        "speaker": "Fail01",
        "appliedOffsetSec": 0.187,
        "shiftedIntervals": 9358,
        "shiftedConcepts": 521,
        "protectedIntervals": 11,
        "protectedLexemes": 1,
    }

    result = parse_mcp.ApplyTimestampOffsetResult.from_payload(payload)

    assert result.speaker == "Fail01"
    assert result.appliedOffsetSec == 0.187
    assert result.shiftedIntervals == 9358
    assert result.shiftedConcepts == 521
    assert result.protectedIntervals == 11
    assert result.protectedLexemes == 1
