"""Characterisation tests for the recurring PARSE IPA threading failure.

These tests document the current failure mode rather than fixing it:

- WSL forces wav2vec2 IPA alignment onto CPU.
- The CPU branch of ``Aligner.load()`` configures PyTorch's global thread
  settings.
- The real repository code path raises the exact observed RuntimeError once
  PyTorch considers inter-op thread configuration frozen for the process.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ai import forced_align as fa


class _FakeTokenizer:
    pad_token = "<pad>"

    @classmethod
    def from_pretrained(cls, model_name: str) -> "_FakeTokenizer":
        return cls()

    def get_vocab(self) -> dict[str, int]:
        return {"<pad>": 0, "a": 1}


class _FakeFeatureExtractor:
    @classmethod
    def from_pretrained(cls, model_name: str) -> "_FakeFeatureExtractor":
        return cls()


class _FakeProcessor:
    def __init__(self, feature_extractor=None, tokenizer=None) -> None:
        self.feature_extractor = feature_extractor
        self.tokenizer = tokenizer

    @classmethod
    def from_pretrained(cls, model_name: str) -> "_FakeProcessor":
        return cls(feature_extractor=_FakeFeatureExtractor(), tokenizer=_FakeTokenizer())


class _FakeModel:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def to(self, device: str) -> "_FakeModel":
        self._events.append(("to", device))
        return self

    def eval(self) -> "_FakeModel":
        self._events.append(("eval", None))
        return self


class _FakeModelFactory:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def from_pretrained(self, model_name: str) -> _FakeModel:
        self._events.append(("from_pretrained", model_name))
        return _FakeModel(self._events)


def _build_fake_torch_module() -> types.ModuleType:
    fake_torch = types.ModuleType("torch")
    fake_torch.calls = []  # type: ignore[attr-defined]

    def _record(name: str):
        def inner(value: int) -> None:
            fake_torch.calls.append((name, value))  # type: ignore[attr-defined]

        return inner

    fake_torch.set_num_threads = _record("set_num_threads")  # type: ignore[attr-defined]
    fake_torch.set_num_interop_threads = _record("set_num_interop_threads")  # type: ignore[attr-defined]
    return fake_torch


def _build_fake_transformers_module() -> tuple[types.ModuleType, list[tuple[str, object]]]:
    fake_transformers = types.ModuleType("transformers")
    model_events: list[tuple[str, object]] = []

    fake_transformers.Wav2Vec2CTCTokenizer = _FakeTokenizer  # type: ignore[attr-defined]
    fake_transformers.Wav2Vec2FeatureExtractor = _FakeFeatureExtractor  # type: ignore[attr-defined]
    fake_transformers.Wav2Vec2Processor = _FakeProcessor  # type: ignore[attr-defined]
    fake_transformers.Wav2Vec2ForCTC = _FakeModelFactory(model_events)  # type: ignore[attr-defined]
    return fake_transformers, model_events


def _system_python_has_torch() -> bool:
    python_bin = pathlib.Path("/usr/bin/python3")
    if not python_bin.exists():
        return False
    probe = subprocess.run(
        [str(python_bin), "-c", "import torch"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


REAL_TORCH_SUBPROCESS_AVAILABLE = _system_python_has_torch()


def test_resolve_device_forces_cpu_on_wsl_even_if_cuda_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fa, "_is_wsl", lambda: True)
    assert fa.resolve_device("cuda") == "cpu"
    assert fa.resolve_device(None) == "cpu"


def test_aligner_load_cpu_path_sets_thread_limits_before_model_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fa, "_CPU_THREAD_LIMITS_CONFIGURED", False)
    fake_torch = _build_fake_torch_module()
    fake_transformers, model_events = _build_fake_transformers_module()

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    aligner = fa.Aligner.load(model_name="dummy", device="cpu")

    assert aligner.device == "cpu"
    assert fake_torch.calls[:2] == [  # type: ignore[attr-defined]
        ("set_num_threads", 1),
        ("set_num_interop_threads", 1),
    ]
    assert model_events == [
        ("from_pretrained", "dummy"),
        ("to", "cpu"),
        ("eval", None),
    ]


def test_aligner_load_cpu_path_tolerates_preconfigured_interop_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fa, "_CPU_THREAD_LIMITS_CONFIGURED", False)
    fake_torch = _build_fake_torch_module()

    def _fail(_: int) -> None:
        raise RuntimeError(
            "Error: cannot set number of interop threads after parallel work has started "
            "or set_num_interop_threads called"
        )

    fake_torch.set_num_interop_threads = _fail  # type: ignore[attr-defined]
    fake_transformers, model_events = _build_fake_transformers_module()

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    aligner = fa.Aligner.load(model_name="dummy", device="cpu")

    assert aligner.device == "cpu"
    assert fake_torch.calls == [("set_num_threads", 1)]  # type: ignore[attr-defined]
    assert model_events == [
        ("from_pretrained", "dummy"),
        ("to", "cpu"),
        ("eval", None),
    ]


@pytest.mark.skipif(
    not REAL_TORCH_SUBPROCESS_AVAILABLE,
    reason="requires /usr/bin/python3 with torch installed",
)
def test_real_repo_cpu_load_tolerates_preconfigured_pytorch_interop_threads(tmp_path: pathlib.Path) -> None:
    repo_python = pathlib.Path(__file__).resolve().parents[1]
    script = tmp_path / "forced_align_thread_repro.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import sys
            import types
            import torch

            sys.path.insert(0, {str(repo_python)!r})

            fake_transformers = types.ModuleType('transformers')

            class _FakeTokenizer:
                pad_token = '<pad>'
                @classmethod
                def from_pretrained(cls, model_name):
                    return cls()
                def get_vocab(self):
                    return {{'<pad>': 0, 'a': 1}}

            class _FakeFeatureExtractor:
                @classmethod
                def from_pretrained(cls, model_name):
                    return cls()

            class _FakeProcessor:
                def __init__(self, feature_extractor=None, tokenizer=None):
                    self.feature_extractor = feature_extractor
                    self.tokenizer = tokenizer
                @classmethod
                def from_pretrained(cls, model_name):
                    return cls(feature_extractor=_FakeFeatureExtractor(), tokenizer=_FakeTokenizer())

            class _FakeModel:
                @classmethod
                def from_pretrained(cls, model_name):
                    return cls()
                def to(self, device):
                    return self
                def eval(self):
                    return self

            fake_transformers.Wav2Vec2CTCTokenizer = _FakeTokenizer
            fake_transformers.Wav2Vec2FeatureExtractor = _FakeFeatureExtractor
            fake_transformers.Wav2Vec2Processor = _FakeProcessor
            fake_transformers.Wav2Vec2ForCTC = _FakeModel
            sys.modules['transformers'] = fake_transformers

            from ai.forced_align import Aligner

            torch.set_num_interop_threads(1)
            aligner = Aligner.load(model_name='dummy', device='cpu')
            print('ALIGNER_DEVICE', getattr(aligner, 'device', '?'))
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["/usr/bin/python3", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "ALIGNER_DEVICE cpu" in combined
    assert "cannot set number of interop threads" not in combined
