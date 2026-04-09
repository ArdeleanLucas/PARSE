"""Tests for contact_lexeme_fetcher.fetch_and_merge merge semantics."""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure `compare.*` imports resolve when running from repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from compare import contact_lexeme_fetcher
from compare.providers import registry as registry_module


def _write_concepts_csv(path: Path, concepts: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concept_en"])
        writer.writeheader()
        for concept_en in concepts:
            writer.writerow({"concept_en": concept_en})


def _write_json(path: Path, payload: Dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_fetch_and_merge_non_overwrite_preserves_existing_forms(monkeypatch, tmp_path: Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    config_path = tmp_path / "sil_contact_languages.json"

    _write_concepts_csv(concepts_path, ["water", "fire"])
    _write_json(
        config_path,
        {
            "ckb": {
                "name": "Sorani Kurdish",
                "concepts": {
                    "water": ["aw_old"],
                    "fire": [],
                },
            }
        },
    )

    calls: List[Dict[str, List[str]]] = []

    class StubRegistry:
        def __init__(self, ai_config: Optional[Dict] = None) -> None:
            del ai_config

        def fetch_all(
            self,
            concepts: List[str],
            language_codes: List[str],
            language_meta: Dict,
            priority_order=None,
            stop_on_first_hit: bool = True,
            progress_callback=None,
        ) -> Dict[str, Dict[str, List[str]]]:
            del language_meta, stop_on_first_hit, progress_callback
            calls.append(
                {
                    "concepts": list(concepts),
                    "language_codes": list(language_codes),
                    "priority_order": list(priority_order or []),
                }
            )
            return {
                "ckb": {
                    "water": ["aw_new"],
                    "fire": ["agir"],
                }
            }

    monkeypatch.setattr(registry_module, "ProviderRegistry", StubRegistry)

    filled = contact_lexeme_fetcher.fetch_and_merge(
        concepts_path=concepts_path,
        config_path=config_path,
        language_codes=["ckb"],
        providers=["stub_provider"],
        overwrite=False,
    )

    assert calls == [
        {
            "concepts": ["fire"],
            "language_codes": ["ckb"],
            "priority_order": ["stub_provider"],
        }
    ]
    assert filled == {"ckb": 1}

    updated = _read_json(config_path)
    assert updated["ckb"]["concepts"]["water"] == ["aw_old"]
    assert updated["ckb"]["concepts"]["fire"] == ["agir"]


def test_fetch_and_merge_overwrite_replaces_existing_forms(monkeypatch, tmp_path: Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    config_path = tmp_path / "sil_contact_languages.json"

    _write_concepts_csv(concepts_path, ["water", "fire"])
    _write_json(
        config_path,
        {
            "ckb": {
                "name": "Sorani Kurdish",
                "concepts": {
                    "water": ["aw_old"],
                    "fire": ["agir_old"],
                },
            }
        },
    )

    observed_concepts: List[str] = []

    class StubRegistry:
        def __init__(self, ai_config: Optional[Dict] = None) -> None:
            del ai_config

        def fetch_all(
            self,
            concepts: List[str],
            language_codes: List[str],
            language_meta: Dict,
            priority_order=None,
            stop_on_first_hit: bool = True,
            progress_callback=None,
        ) -> Dict[str, Dict[str, List[str]]]:
            del language_codes, language_meta, priority_order, stop_on_first_hit, progress_callback
            observed_concepts.extend(concepts)
            return {
                "ckb": {
                    "water": ["aw_new"],
                    "fire": ["agir_new"],
                }
            }

    monkeypatch.setattr(registry_module, "ProviderRegistry", StubRegistry)

    filled = contact_lexeme_fetcher.fetch_and_merge(
        concepts_path=concepts_path,
        config_path=config_path,
        language_codes=["ckb"],
        overwrite=True,
    )

    assert observed_concepts == ["fire", "water"]
    assert filled == {"ckb": 2}

    updated = _read_json(config_path)
    assert updated["ckb"]["concepts"]["water"] == ["aw_new"]
    assert updated["ckb"]["concepts"]["fire"] == ["agir_new"]


def test_fetch_and_merge_language_filtering_updates_only_requested_languages(monkeypatch, tmp_path: Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    config_path = tmp_path / "sil_contact_languages.json"

    _write_concepts_csv(concepts_path, ["water"])
    _write_json(
        config_path,
        {
            "ckb": {
                "name": "Sorani Kurdish",
                "concepts": {"water": []},
            },
            "fa": {
                "name": "Persian",
                "concepts": {"water": []},
            },
        },
    )

    seen_language_codes: List[str] = []

    class StubRegistry:
        def __init__(self, ai_config: Optional[Dict] = None) -> None:
            del ai_config

        def fetch_all(
            self,
            concepts: List[str],
            language_codes: List[str],
            language_meta: Dict,
            priority_order=None,
            stop_on_first_hit: bool = True,
            progress_callback=None,
        ) -> Dict[str, Dict[str, List[str]]]:
            del concepts, language_meta, priority_order, stop_on_first_hit, progress_callback
            seen_language_codes.extend(language_codes)
            return {
                "ckb": {"water": ["aw"]},
                "fa": {"water": ["ab"]},
            }

    monkeypatch.setattr(registry_module, "ProviderRegistry", StubRegistry)

    filled = contact_lexeme_fetcher.fetch_and_merge(
        concepts_path=concepts_path,
        config_path=config_path,
        language_codes=["ckb"],
        overwrite=False,
    )

    assert seen_language_codes == ["ckb"]
    assert filled == {"ckb": 1}

    updated = _read_json(config_path)
    assert updated["ckb"]["concepts"]["water"] == ["aw"]
    assert updated["fa"]["concepts"]["water"] == []


def test_fetch_and_merge_no_missing_concepts_skips_fetch_call(monkeypatch, tmp_path: Path) -> None:
    concepts_path = tmp_path / "concepts.csv"
    config_path = tmp_path / "sil_contact_languages.json"

    _write_concepts_csv(concepts_path, ["water"])
    original_config = {
        "ckb": {
            "name": "Sorani Kurdish",
            "concepts": {"water": ["aw"]},
        }
    }
    _write_json(config_path, original_config)

    init_calls: List[int] = []
    fetch_calls: List[int] = []

    class StubRegistry:
        def __init__(self, ai_config: Optional[Dict] = None) -> None:
            del ai_config
            init_calls.append(1)

        def fetch_all(
            self,
            concepts: List[str],
            language_codes: List[str],
            language_meta: Dict,
            priority_order=None,
            stop_on_first_hit: bool = True,
            progress_callback=None,
        ) -> Dict[str, Dict[str, List[str]]]:
            del concepts, language_codes, language_meta, priority_order, stop_on_first_hit, progress_callback
            fetch_calls.append(1)
            raise AssertionError("fetch_all should not be called when nothing needs fill")

    monkeypatch.setattr(registry_module, "ProviderRegistry", StubRegistry)

    filled = contact_lexeme_fetcher.fetch_and_merge(
        concepts_path=concepts_path,
        config_path=config_path,
        language_codes=["ckb"],
        overwrite=False,
    )

    assert init_calls == [1]
    assert fetch_calls == []
    assert filled == {"ckb": 0}

    updated = _read_json(config_path)
    assert updated == original_config
