import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_tier1_boundaries as mod


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_pairs_discovers_flat_and_nested_workspace_layouts(tmp_path: pathlib.Path) -> None:
    stt_dir = tmp_path / "stt_output"
    _write_json(stt_dir / "Fail01.stt.json", {"segments": []})
    _write_json(stt_dir / "Fail01.aligned.json", {"segments": []})
    _write_json(stt_dir / "Kalh01" / "stt.json", {"segments": []})
    _write_json(stt_dir / "Kalh01" / "aligned.json", {"segments": []})

    pairs = mod._resolve_pairs(tmp_path, None, None)

    assert [(label, stt.name, aligned.name) for label, stt, aligned in pairs] == [
        ("Fail01", "Fail01.stt.json", "Fail01.aligned.json"),
        ("Kalh01", "stt.json", "aligned.json"),
    ]


def test_analyse_pair_reports_boundary_shift_confidence_and_fallbacks(tmp_path: pathlib.Path) -> None:
    stt_path = tmp_path / "Fail01.stt.json"
    aligned_path = tmp_path / "Fail01.aligned.json"
    _write_json(
        stt_path,
        {
            "segments": [
                {
                    "words": [
                        {"word": "awa", "start": 1.0, "end": 1.4},
                        {"word": "test", "start": 1.4, "end": 2.0},
                    ]
                }
            ]
        },
    )
    _write_json(
        aligned_path,
        {
            "segments": [
                {
                    "words": [
                        {
                            "word": "awa",
                            "start": 1.03,
                            "end": 1.41,
                            "confidence": 0.93,
                            "method": "forced-align",
                        },
                        {
                            "word": "test",
                            "start": 1.62,
                            "end": 2.0,
                            "confidence": 0.42,
                            "method": "proportional-fallback",
                        },
                        {
                            "word": "extra",
                            "start": 2.05,
                            "end": 2.2,
                            "confidence": 0.35,
                            "method": "proportional-fallback",
                        },
                    ]
                }
            ],
            "alignment": {"methodCounts": {"forced-align": 1, "proportional-fallback": 2}},
        },
    )

    result = mod.analyse_pair(stt_path, aligned_path, padding_ms=100.0)

    assert result["paired_words"] == 2
    assert result["unpaired_aligned_words"] == 1
    assert result["tier1_total_words"] == 2
    assert result["confidence"]["n"] == 3
    assert result["confidence_below_0.6_pct"] == 66.67
    assert result["max_edge_shift_over_padding_pct"] == 50.0
    assert result["method_counts_artifact"] == {"forced-align": 1, "proportional-fallback": 2}
    assert result["method_pct_artifact"] == {"forced-align": 33.33, "proportional-fallback": 66.67}
    assert result["method_counts_walked"] == {"forced-align": 1, "proportional-fallback": 2}
    assert result["max_edge_shift_ms"]["max"] == 220.0
    assert result["onset_shift_ms"]["median"] == 125.0


def test_main_writes_json_report_for_explicit_pair(tmp_path: pathlib.Path, capsys) -> None:
    stt_path = tmp_path / "Fail02.stt.json"
    aligned_path = tmp_path / "Fail02.aligned.json"
    json_out = tmp_path / "report.json"
    _write_json(stt_path, {"segments": [{"words": [{"word": "yek", "start": 0.0, "end": 0.5}]}]})
    _write_json(
        aligned_path,
        {
            "segments": [
                {"words": [{"word": "yek", "start": 0.01, "end": 0.5, "confidence": 0.8, "method": "forced-align"}]}
            ],
            "alignment": {"methodCounts": {"forced-align": 1}},
        },
    )

    exit_code = mod.main([
        "--stt",
        str(stt_path),
        "--aligned",
        str(aligned_path),
        "--json-out",
        str(json_out),
    ])

    stdout = capsys.readouterr().out
    payload = json.loads(json_out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Fail02" in stdout
    assert payload["per_pair"][0]["paired_words"] == 1
    assert payload["aggregate"]["total_paired_words"] == 1
