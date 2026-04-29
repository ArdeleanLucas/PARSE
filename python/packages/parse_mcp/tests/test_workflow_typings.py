import pathlib
import sys
from typing import get_args, get_origin, Literal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from parse_mcp._schema import RUN_FULL_ANNOTATION_PIPELINE_INPUT_SCHEMA, build_args_model
from parse_mcp.models import PipelineRunMode, RunFullAnnotationPipelineInput


def test_build_args_model_preserves_run_mode_enum_for_workflow_inputs() -> None:
    model = build_args_model(
        "RunFullAnnotationPipelineArgs",
        RUN_FULL_ANNOTATION_PIPELINE_INPUT_SCHEMA,
    )

    run_mode_field = model.model_fields["run_mode"]
    assert get_origin(run_mode_field.annotation) is Literal
    assert get_args(run_mode_field.annotation) == ("full", "concept-windows", "edited-only")

    args = model(
        speaker_id="Fail02",
        concept_list=["1"],
        run_mode="edited-only",
        concept_ids=["2", "3"],
        dryRun=True,
    )
    assert args.run_mode == "edited-only"
    assert args.concept_ids == ["2", "3"]

    defaulted = model(speaker_id="Fail02", concept_list=["1"])
    assert defaulted.run_mode == "full"
    assert defaulted.concept_ids is None


def test_public_run_full_annotation_pipeline_input_typing_round_trips() -> None:
    assert get_origin(PipelineRunMode) is Literal
    assert get_args(PipelineRunMode) == ("full", "concept-windows", "edited-only")

    payload = RunFullAnnotationPipelineInput(
        speaker_id="Fail02",
        concept_list=["1"],
        run_mode="concept-windows",
        concept_ids=["2"],
        dryRun=True,
    ).to_arguments()

    assert payload == {
        "speaker_id": "Fail02",
        "concept_list": ["1"],
        "run_mode": "concept-windows",
        "concept_ids": ["2"],
        "dryRun": True,
    }
