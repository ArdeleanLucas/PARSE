"""Tests for per-project stage->model binding consumption at compute time.

These tests prove the deferred §9.4 follow-up: the binding stored in
``project.json["models"]`` is now actually CONSULTED during model resolution at
the two provider call sites (``LocalWhisperProvider`` for stt/ortho and
``Aligner.load`` for ipa).

All tests are hermetic. Model roots are fabricated in tmp dirs and pointed at via
``PARSE_BUNDLED_MODELS`` env monkeypatching. The active project root is the cwd
(mirroring ``server._project_root()``), so ``Path.cwd`` is monkeypatched to a tmp
dir carrying a real ``project.json`` with a ``models`` binding block. No torch /
no real model loads — providers are constructed lazily (model load is deferred),
and the aligner's transformers/torch imports are stubbed.
"""
from __future__ import annotations

import json
import pathlib
import sys
import types as _types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import model_registry


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_model(root: pathlib.Path, model_id: str, stage: str, fmt: str) -> pathlib.Path:
    model_dir = root / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "id": model_id,
        "name": "Name of {0}".format(model_id),
        "stage": stage,
        "format": fmt,
        "engine": "some-engine",
        "languages": ["*"],
        "entrypoint": ".",
        "version": "1.0.0",
        "source": {"type": "", "ref": ""},
    }
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return model_dir


def _project_with_binding(project_dir: pathlib.Path, models: dict) -> None:
    """Write a real project.json carrying a ``models`` stage->id binding block."""
    project_dir.mkdir(parents=True, exist_ok=True)
    payload = {"name": project_dir.name, "version": 1, "speakers": {}, "models": models}
    (project_dir / "project.json").write_text(json.dumps(payload), encoding="utf-8")


def _use_project_root(monkeypatch, project_dir: pathlib.Path) -> None:
    """Point cwd (the project root the providers read) at ``project_dir``.

    The providers call ``Path.cwd()`` where ``Path`` is ``pathlib.Path``;
    patching ``pathlib.Path.cwd`` covers every call site hermetically.
    """
    resolved = project_dir.resolve()
    monkeypatch.setattr(pathlib.Path, "cwd", classmethod(lambda cls: resolved))


def _stt_config():
    return {"stt": {"model_path": "", "device": "cpu", "compute_type": "int8"}}


# --------------------------------------------------------------------------- #
# 1. Binding disambiguates two same-stage stt models (LocalWhisperProvider)
# --------------------------------------------------------------------------- #

def test_binding_disambiguates_two_stt_models(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "stt-a", "stt", "faster-whisper-ct2")
    chosen = _write_model(bundled, "stt-b", "stt", "faster-whisper-ct2")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    project = tmp_path / "project"
    _project_with_binding(project, {"stt": "stt-b"})
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    # Without the binding, two installed stt models are ambiguous -> None -> "".
    # The binding selects stt-b, so model_path resolves to its entrypoint.
    assert provider.model_path == str(chosen.resolve())


# --------------------------------------------------------------------------- #
# 2. No binding + single installed -> still resolves (unchanged from #684)
# --------------------------------------------------------------------------- #

def test_no_binding_single_installed_still_resolves(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    only = _write_model(bundled, "the-only-stt", "stt", "faster-whisper-ct2")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # Project.json with an empty models block -> read_binding returns None for
    # stt -> single-installed resolution, identical to #684.
    project = tmp_path / "project"
    _project_with_binding(project, {})
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == str(only.resolve())


# --------------------------------------------------------------------------- #
# 3. No binding + multiple installed -> None (ambiguous), model_path stays ""
# --------------------------------------------------------------------------- #

def test_no_binding_multiple_installed_is_ambiguous(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "stt-a", "stt", "faster-whisper-ct2")
    _write_model(bundled, "stt-b", "stt", "faster-whisper-ct2")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    project = tmp_path / "project"
    _project_with_binding(project, {})  # no stt binding
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    # Ambiguous with no binding -> resolver None -> model_path unchanged.
    assert provider.model_path == ""


# --------------------------------------------------------------------------- #
# 4. Stale binding (bound id not installed) -> falls through, no error
# --------------------------------------------------------------------------- #

def test_stale_binding_falls_through_gracefully(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    only = _write_model(bundled, "the-only-stt", "stt", "faster-whisper-ct2")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # Binding points at a model that is NOT installed. resolve_stage_model must
    # fall through to single-model resolution without raising.
    project = tmp_path / "project"
    _project_with_binding(project, {"stt": "ghost-model-not-installed"})
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == str(only.resolve())


# --------------------------------------------------------------------------- #
# 4b. Wrong-stage binding (bound id exists but is a DIFFERENT stage) -> ignored
# --------------------------------------------------------------------------- #

def test_wrong_stage_binding_not_honored(monkeypatch, tmp_path):
    """Locks in the ``record.stage == target_stage`` guard through the provider.

    Distinct from the stale-binding case: here the bound id DOES exist, it is
    just registered for the wrong stage. The stt binding points at the ipa
    model's id, so the guard must reject it and fall through to the single
    legitimate stt model -- never the ipa model's entrypoint.
    """
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    only_stt = _write_model(bundled, "the-only-stt", "stt", "faster-whisper-ct2")
    _write_model(bundled, "wrong-stage-ipa", "ipa", "hf-transformers")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # Bind stt -> the IPA model's id. The bound id exists but is stage=ipa, so
    # the record.stage == target_stage guard must skip it.
    project = tmp_path / "project"
    _project_with_binding(project, {"stt": "wrong-stage-ipa"})
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    # Wrong-stage binding ignored -> falls through to the single stt model.
    assert provider.model_path == str(only_stt.resolve())


# --------------------------------------------------------------------------- #
# 5. IPA equivalent for the aligner (bound ipa model used; no binding -> default)
# --------------------------------------------------------------------------- #

def _aligner_from_pretrained_capture(seen):
    def fake(name, *args, **kwargs):
        seen.setdefault("model_name", name)
        raise RuntimeError("stop-after-substitution")
    return fake


def _install_aligner_stubs(monkeypatch, seen):
    import ai.forced_align as fa

    fake = _aligner_from_pretrained_capture(seen)
    stub = _types.SimpleNamespace(
        Wav2Vec2CTCTokenizer=_types.SimpleNamespace(from_pretrained=fake),
        Wav2Vec2FeatureExtractor=_types.SimpleNamespace(from_pretrained=fake),
        Wav2Vec2ForCTC=_types.SimpleNamespace(from_pretrained=fake),
        Wav2Vec2Processor=_types.SimpleNamespace(from_pretrained=fake),
    )
    torch_stub = _types.SimpleNamespace(
        set_num_threads=lambda *a: None,
        set_num_interop_threads=lambda *a: None,
    )
    monkeypatch.setattr(fa, "_PRELOADED_ALIGNER", None, raising=False)
    monkeypatch.setitem(sys.modules, "transformers", stub)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    return fa


def test_aligner_binding_disambiguates_two_ipa_models(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "ipa-a", "ipa", "hf-transformers")
    chosen = _write_model(bundled, "ipa-b", "ipa", "hf-transformers")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    project = tmp_path / "project"
    _project_with_binding(project, {"ipa": "ipa-b"})
    _use_project_root(monkeypatch, project)

    seen: dict = {}
    fa = _install_aligner_stubs(monkeypatch, seen)

    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    # Two ipa models installed; only the binding could disambiguate. The
    # substituted local dir path must be the bound model's entrypoint.
    assert seen["model_name"] == str(chosen.resolve())


def test_aligner_no_binding_keeps_default_model_name(monkeypatch, tmp_path):
    import ai.forced_align as fa_module

    # Two ipa models installed but NO binding -> ambiguous -> resolver None ->
    # DEFAULT_MODEL_NAME preserved (would hit HF download in production).
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "ipa-a", "ipa", "hf-transformers")
    _write_model(bundled, "ipa-b", "ipa", "hf-transformers")
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    project = tmp_path / "project"
    _project_with_binding(project, {})  # no ipa binding
    _use_project_root(monkeypatch, project)

    seen: dict = {}
    fa = _install_aligner_stubs(monkeypatch, seen)

    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    assert seen["model_name"] == fa_module.DEFAULT_MODEL_NAME


# --------------------------------------------------------------------------- #
# 6. Web-mode / no-roots additive guarantee (any binding is inert)
# --------------------------------------------------------------------------- #

def test_web_mode_no_roots_stt_model_path_stays_empty(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    # No model roots at all (the web product). Even a project.json binding is
    # inert because list_models() is empty -> resolver None -> model_path "".
    monkeypatch.delenv(model_registry.BUNDLED_MODELS_ENV, raising=False)
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)

    project = tmp_path / "project"
    _project_with_binding(project, {"stt": "whatever-id"})
    _use_project_root(monkeypatch, project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == ""


def test_web_mode_no_roots_aligner_keeps_default_model_name(monkeypatch, tmp_path):
    import ai.forced_align as fa_module

    monkeypatch.delenv(model_registry.BUNDLED_MODELS_ENV, raising=False)
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)

    project = tmp_path / "project"
    _project_with_binding(project, {"ipa": "whatever-id"})
    _use_project_root(monkeypatch, project)

    seen: dict = {}
    fa = _install_aligner_stubs(monkeypatch, seen)

    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    assert seen["model_name"] == fa_module.DEFAULT_MODEL_NAME


def test_web_mode_no_project_json_stt_model_path_stays_empty(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    # Web product with no project.json at all: read_binding degrades to all-None
    # and (no roots) resolver is None -> model_path "". Byte-identical to today.
    monkeypatch.delenv(model_registry.BUNDLED_MODELS_ENV, raising=False)
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)

    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    _use_project_root(monkeypatch, empty_project)

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == ""
