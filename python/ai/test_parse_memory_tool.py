"""Tests for parse_memory_read / parse_memory_upsert_section chat tools."""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ai.chat_tools import ParseChatTools, WRITE_ALLOWED_TOOL_NAMES


def _tools(tmp_path) -> ParseChatTools:
    return ParseChatTools(project_root=tmp_path)


def test_memory_read_returns_not_exists_when_file_missing(tmp_path) -> None:
    result = _tools(tmp_path).execute("parse_memory_read", {})["result"]
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["content"] == ""


def test_memory_upsert_creates_file_with_header_and_section(tmp_path) -> None:
    tools = _tools(tmp_path)

    payload = tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01: /mnt/c/...", "dryRun": False},
    )["result"]
    assert payload["ok"] is True
    assert payload["action"] == "create"

    memory = (tmp_path / "parse-memory.md").read_text(encoding="utf-8")
    assert memory.startswith("# PARSE chat memory")
    assert "## Speakers" in memory
    assert "Faili01" in memory


def test_memory_upsert_replaces_existing_section_without_touching_others(tmp_path) -> None:
    tools = _tools(tmp_path)

    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Preferences", "body": "- terse tone", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- Faili01\n- Kalh01", "dryRun": False},
    )

    memory = (tmp_path / "parse-memory.md").read_text(encoding="utf-8")
    # Preferences section untouched
    assert "- terse tone" in memory
    # Speakers section now has both entries
    assert "- Faili01" in memory
    assert "- Kalh01" in memory
    # Section heading appears exactly once
    assert memory.count("## Speakers") == 1


def test_memory_upsert_dry_run_does_not_write(tmp_path) -> None:
    tools = _tools(tmp_path)

    preview = tools.execute(
        "parse_memory_upsert_section",
        {"section": "Notes", "body": "hello", "dryRun": True},
    )["result"]
    assert preview["dryRun"] is True
    assert not (tmp_path / "parse-memory.md").exists()


def test_memory_read_section_filter_returns_just_that_block(tmp_path) -> None:
    tools = _tools(tmp_path)

    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Speakers", "body": "- A", "dryRun": False},
    )
    tools.execute(
        "parse_memory_upsert_section",
        {"section": "Preferences", "body": "- terse", "dryRun": False},
    )

    result = tools.execute("parse_memory_read", {"section": "Speakers"})["result"]
    assert result["ok"] is True
    assert "## Speakers" in result["content"]
    assert "Preferences" not in result["content"]


def test_memory_tools_are_write_allowlisted() -> None:
    # parse_memory_read is read-only; the upsert tool must be in the write allowlist.
    assert "parse_memory_upsert_section" in WRITE_ALLOWED_TOOL_NAMES
    assert "parse_memory_read" not in WRITE_ALLOWED_TOOL_NAMES


def test_onboard_speaker_import_is_write_allowlisted() -> None:
    assert "onboard_speaker_import" in WRITE_ALLOWED_TOOL_NAMES


def test_onboard_speaker_dry_run_reports_plan_without_callback(tmp_path) -> None:
    import wave

    external_root = tmp_path / "external"
    external_root.mkdir()
    wav = external_root / "spk1.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(
        project_root=project_root,
        external_read_roots=[external_root],
    )

    result = tools.execute(
        "onboard_speaker_import",
        {"speaker": "Speaker01", "sourceWav": str(wav), "dryRun": True},
    )["result"]
    assert result["ok"] is True
    assert result["plan"]["speaker"] == "Speaker01"
    assert result["plan"]["isPrimary"] is True
    assert result["plan"]["wavDest"].endswith("Speaker01/spk1.wav")


def test_onboard_speaker_rejects_source_outside_allowed_roots(tmp_path) -> None:
    import wave

    import pytest

    from ai.chat_tools import ChatToolValidationError

    stray_root = tmp_path / "stray"
    stray_root.mkdir()
    wav = stray_root / "spk.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(project_root=project_root)  # no external_read_roots

    with pytest.raises(
        ChatToolValidationError,
        match=r"outside allowed read roots.*PARSE_EXTERNAL_READ_ROOTS",
    ):
        tools.execute(
            "onboard_speaker_import",
            {"speaker": "Speaker01", "sourceWav": str(wav), "dryRun": True},
        )


def test_external_read_wildcard_allows_any_absolute_path(tmp_path) -> None:
    import wave

    stray_root = tmp_path / "stray"
    stray_root.mkdir()
    wav = stray_root / "Faili_M_1984.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    # PARSE_EXTERNAL_READ_ROOTS="*" → wildcard mode
    tools = ParseChatTools(project_root=project_root, external_read_roots=["*"])

    result = tools.execute(
        "read_audio_info", {"sourceWav": str(wav)}
    )["result"]
    assert result["ok"] is True
    assert result["sampleRateHz"] == 16000


def test_onboard_speaker_flags_virtual_timeline_on_second_source(tmp_path) -> None:
    """When a speaker already has a registered WAV, a second onboarding call
    must surface virtualTimelineRequired=true + an explanatory note so the
    agent raises the gap rather than silently writing two disjoint sources."""
    import json
    import wave

    external_root = tmp_path / "Thesis"
    external_root.mkdir()

    def make_wav(name: str) -> pathlib.Path:
        wav = external_root / name
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 8000)
        return wav

    wav_a = make_wav("Mand_M_1962_01.wav")
    wav_b = make_wav("Mand_M_1962_02.wav")

    project_root = tmp_path / "proj"
    project_root.mkdir()

    # Seed source_index.json as if Mand_M_1962_01.wav was already onboarded.
    (project_root / "source_index.json").write_text(
        json.dumps(
            {
                "speakers": {
                    "Mand01": {
                        "source_wavs": [
                            {
                                "filename": "Mand_M_1962_01.wav",
                                "path": "audio/original/Mand01/Mand_M_1962_01.wav",
                                "is_primary": True,
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    first_result = tools.execute(
        "onboard_speaker_import",
        {"speaker": "Mand01", "sourceWav": str(wav_a), "dryRun": True},
    )["result"]
    # wav_a is already registered → no count increase, no virtual-timeline flag.
    assert first_result["plan"]["alreadyRegistered"] is True
    assert first_result["plan"]["projectedSourceCount"] == 1
    assert first_result["plan"]["virtualTimelineRequired"] is False

    second_result = tools.execute(
        "onboard_speaker_import",
        {"speaker": "Mand01", "sourceWav": str(wav_b), "dryRun": True},
    )["result"]
    assert second_result["plan"]["projectedSourceCount"] == 2
    assert second_result["plan"]["virtualTimelineRequired"] is True
    assert "virtual timeline" in second_result["plan"]["virtualTimelineNote"].lower()


def test_import_processed_speaker_is_write_allowlisted() -> None:
    assert "import_processed_speaker" in WRITE_ALLOWED_TOOL_NAMES


def _write_test_wav(path: pathlib.Path) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)


def _write_processed_fixture(root: pathlib.Path, speaker: str = "Fail02") -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    import json

    wav = root / "Audio_Working" / speaker / "speaker.wav"
    _write_test_wav(wav)

    annotation = root / "annotations" / f"{speaker}.json"
    annotation.parent.mkdir(parents=True, exist_ok=True)
    annotation.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "southern-kurdish-dialect-comparison",
                "speaker": speaker,
                "source_audio": f"audio/working/{speaker}/speaker.wav",
                "source_audio_duration_sec": 2.0,
                "metadata": {"language_code": "sdh", "timestamps_source": "processed"},
                "tiers": {
                    "ipa": {"display_order": 1, "intervals": [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.0, "end": 2.0, "text": "b"}]},
                    "ortho": {"display_order": 2, "intervals": [{"start": 0.0, "end": 1.0, "text": "ash"}, {"start": 1.0, "end": 2.0, "text": "bark"}]},
                    "concept": {"display_order": 3, "intervals": [{"start": 0.0, "end": 1.0, "text": "1: ash"}, {"start": 1.0, "end": 2.0, "text": "2: bark"}]},
                    "speaker": {"display_order": 4, "intervals": [{"start": 0.0, "end": 1.0, "text": speaker}, {"start": 1.0, "end": 2.0, "text": speaker}]},
                },
            }
        ),
        encoding="utf-8",
    )

    peaks = root / "peaks" / f"{speaker}.json"
    peaks.parent.mkdir(parents=True, exist_ok=True)
    peaks.write_text(json.dumps({"duration": 2.0, "peaks": [0, 1, 0, -1]}), encoding="utf-8")
    return wav, annotation, peaks


def test_import_processed_speaker_dry_run_reports_plan(tmp_path) -> None:
    external_root = tmp_path / "Thesis"
    wav, annotation, peaks = _write_processed_fixture(external_root)
    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])
    result = tools.execute(
        "import_processed_speaker",
        {
            "speaker": "Fail02",
            "workingWav": str(wav),
            "annotationJson": str(annotation),
            "peaksJson": str(peaks),
            "dryRun": True,
        },
    )["result"]

    assert result["ok"] is True
    assert result["plan"]["speaker"] == "Fail02"
    assert result["plan"]["conceptCount"] == 2
    assert result["plan"]["audioDest"].endswith("audio/working/Fail02/speaker.wav")
    assert result["plan"]["annotationDest"].endswith("annotations/Fail02.json")
    assert result["plan"]["peaksDest"].endswith("peaks/Fail02.json")
    assert result["plan"]["languageCode"] == "sdh"


def test_import_processed_speaker_write_copies_assets_and_builds_workspace_files(tmp_path) -> None:
    import csv
    import json

    external_root = tmp_path / "Thesis"
    wav, annotation, peaks = _write_processed_fixture(external_root)
    project_root = tmp_path / "proj"
    project_root.mkdir()

    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])
    result = tools.execute(
        "import_processed_speaker",
        {
            "speaker": "Fail02",
            "workingWav": str(wav),
            "annotationJson": str(annotation),
            "peaksJson": str(peaks),
            "dryRun": False,
        },
    )["result"]

    assert result["ok"] is True
    assert (project_root / "audio" / "working" / "Fail02" / "speaker.wav").is_file()
    assert (project_root / "annotations" / "Fail02.json").is_file()
    assert (project_root / "peaks" / "Fail02.json").is_file()

    source_index = json.loads((project_root / "source_index.json").read_text(encoding="utf-8"))
    assert source_index["speakers"]["Fail02"]["source_wavs"][0]["path"] == "audio/working/Fail02/speaker.wav"
    assert source_index["speakers"]["Fail02"]["peaks_file"] == "peaks/Fail02.json"

    project_json = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    assert "Fail02" in project_json["speakers"]
    assert project_json["language"]["code"] == "sdh"

    with open(project_root / "concepts.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"id": "1", "concept_en": "ash"},
        {"id": "2", "concept_en": "bark"},
    ]

    imported_annotation = json.loads((project_root / "annotations" / "Fail02.json").read_text(encoding="utf-8"))
    assert imported_annotation["source_audio"] == "audio/working/Fail02/speaker.wav"


def test_import_processed_speaker_assigns_fallback_ids_without_collisions(tmp_path) -> None:
    import csv
    import json

    external_root = tmp_path / "Thesis"
    wav, annotation, peaks = _write_processed_fixture(external_root)
    payload = json.loads(annotation.read_text(encoding="utf-8"))
    payload["tiers"]["concept"]["intervals"] = [
        {"start": 0.0, "end": 1.0, "text": "free concept"},
        {"start": 1.0, "end": 2.0, "text": "1: ash"},
        {"start": 2.0, "end": 3.0, "text": "another free concept"},
    ]
    annotation.write_text(json.dumps(payload), encoding="utf-8")

    project_root = tmp_path / "proj"
    project_root.mkdir()
    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])

    result = tools.execute(
        "import_processed_speaker",
        {
            "speaker": "Fail02",
            "workingWav": str(wav),
            "annotationJson": str(annotation),
            "peaksJson": str(peaks),
            "dryRun": False,
        },
    )["result"]

    assert result["ok"] is True
    with open(project_root / "concepts.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"id": "1", "concept_en": "ash"},
        {"id": "2", "concept_en": "free concept"},
        {"id": "3", "concept_en": "another free concept"},
    ]


def test_import_processed_speaker_preserves_existing_concepts_when_free_text_lacks_ids(tmp_path) -> None:
    import csv
    import json

    external_root = tmp_path / "Thesis"
    wav, annotation, peaks = _write_processed_fixture(external_root)
    payload = json.loads(annotation.read_text(encoding="utf-8"))
    payload["tiers"]["concept"]["intervals"] = [
        {"start": 0.0, "end": 1.0, "text": "ash"},
        {"start": 1.0, "end": 2.0, "text": "bark"},
    ]
    annotation.write_text(json.dumps(payload), encoding="utf-8")

    project_root = tmp_path / "proj"
    project_root.mkdir()
    with open(project_root / "concepts.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "concept_en"])
        writer.writeheader()
        writer.writerow({"id": "1", "concept_en": "water"})

    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])
    result = tools.execute(
        "import_processed_speaker",
        {
            "speaker": "Fail02",
            "workingWav": str(wav),
            "annotationJson": str(annotation),
            "peaksJson": str(peaks),
            "dryRun": False,
        },
    )["result"]

    assert result["ok"] is True
    with open(project_root / "concepts.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"id": "1", "concept_en": "water"},
        {"id": "2", "concept_en": "ash"},
        {"id": "3", "concept_en": "bark"},
    ]


def test_import_processed_speaker_preserves_existing_sources_and_clears_stale_optional_metadata(tmp_path) -> None:
    import json

    external_root = tmp_path / "Thesis"
    wav, annotation, _ = _write_processed_fixture(external_root)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "source_index.json").write_text(
        json.dumps(
            {
                "speakers": {
                    "Fail02": {
                        "source_wavs": [
                            {
                                "filename": "speaker.wav",
                                "path": "audio/original/Fail02/speaker.wav",
                                "is_primary": True,
                            }
                        ],
                        "peaks_file": "peaks/stale.json",
                        "legacy_transcript_csv": "imports/legacy/Fail02/stale.csv",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    tools = ParseChatTools(project_root=project_root, external_read_roots=[external_root])
    result = tools.execute(
        "import_processed_speaker",
        {
            "speaker": "Fail02",
            "workingWav": str(wav),
            "annotationJson": str(annotation),
            "dryRun": False,
        },
    )["result"]

    assert result["ok"] is True
    source_index = json.loads((project_root / "source_index.json").read_text(encoding="utf-8"))
    source_paths = [entry["path"] for entry in source_index["speakers"]["Fail02"]["source_wavs"]]
    primary_paths = [
        entry["path"]
        for entry in source_index["speakers"]["Fail02"]["source_wavs"]
        if entry.get("is_primary") is True
    ]
    assert "audio/original/Fail02/speaker.wav" in source_paths
    assert "audio/working/Fail02/speaker.wav" in source_paths
    assert primary_paths == ["audio/working/Fail02/speaker.wav"]
    assert "peaks_file" not in source_index["speakers"]["Fail02"]
    assert "legacy_transcript_csv" not in source_index["speakers"]["Fail02"]
