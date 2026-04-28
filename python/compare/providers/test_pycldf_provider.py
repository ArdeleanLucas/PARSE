from __future__ import annotations

import sys
from pathlib import Path

try:
    from .pycldf_provider import PycldfProvider
except ImportError:  # pragma: no cover -- direct-invoke fallback
    from pycldf_provider import PycldfProvider  # type: ignore


class _FakeDataset:
    def __init__(self) -> None:
        self._tables = {
            "LanguageTable": [
                {"ID": "avar", "Name": "Avar"},
                {"ID": "dargwa", "Name": "Dargwa"},
                {"ID": "tatar", "Name": "Tatar"},
                {"ID": "marathi", "Name": "Marathi"},
                {"ID": "aragonese", "Name": "Aragonese"},
                {"ID": "ara", "Name": "Arabic"},
                {"ID": "arb", "Name": "Standard Arabic"},
                {"ID": "msa-lower", "Name": "arabic"},
                {"ID": "afar", "Name": "Afar"},
                {"ID": "pes", "Name": "Persian"},
            ],
            "ParameterTable": [
                {"ID": "fire", "Name": "fire"},
                {"ID": "water", "Name": "water"},
            ],
            "FormTable": [
                {"Language_ID": "avar", "Parameter_ID": "fire", "Form": "цӀа"},
                {"Language_ID": "dargwa", "Parameter_ID": "fire", "Form": "цIа"},
                {"Language_ID": "tatar", "Parameter_ID": "fire", "Form": "ут"},
                {"Language_ID": "marathi", "Parameter_ID": "fire", "Form": "आग"},
                {"Language_ID": "aragonese", "Parameter_ID": "fire", "Form": "fuego"},
                {"Language_ID": "ara", "Parameter_ID": "fire", "Form": "نار"},
                {"Language_ID": "arb", "Parameter_ID": "fire", "Form": "نَار"},
                {"Language_ID": "msa-lower", "Parameter_ID": "fire", "Form": "نارٌ"},
                {"Language_ID": "afar", "Parameter_ID": "water", "Form": "biyo"},
                {"Language_ID": "pes", "Parameter_ID": "water", "Form": "آب"},
            ],
        }

    def get(self, name):
        return self._tables.get(name)


class _FakePycldfModule:
    class Dataset:
        @staticmethod
        def from_metadata(_path: str):
            return _FakeDataset()


def _stub_provider() -> PycldfProvider:
    provider = PycldfProvider()
    provider._find_metadata_files = lambda: [Path("/tmp/fake-metadata.json")]  # type: ignore[assignment]
    return provider


def test_fetch_for_arabic_excludes_substring_collisions(monkeypatch):
    monkeypatch.setitem(sys.modules, "pycldf", _FakePycldfModule)
    provider = _stub_provider()

    results = list(provider.fetch(["fire"], ["ar"], {}))

    assert len(results) == 1
    assert results[0].forms == ["نار", "نَار", "نارٌ"]
    assert "цӀа" not in results[0].forms  # Avar
    assert "цIа" not in results[0].forms  # Dargwa
    assert "ут" not in results[0].forms   # Tatar
    assert "आग" not in results[0].forms   # Marathi
    assert "fuego" not in results[0].forms  # Aragonese


def test_fetch_for_persian_excludes_afar_collision(monkeypatch):
    monkeypatch.setitem(sys.modules, "pycldf", _FakePycldfModule)
    provider = _stub_provider()

    results = list(provider.fetch(["water"], ["fa"], {}))

    assert len(results) == 1
    assert results[0].forms == ["آب"]
    assert "biyo" not in results[0].forms
