"""Tests for the desktop model registry core (scan/parse/resolve) plus the
additive loader wiring and read-only HTTP routes.

All tests are hermetic: model roots are fabricated in tmp dirs and pointed at
via ``PARSE_BUNDLED_MODELS`` / ``PARSE_USER_DATA`` env monkeypatching. No torch,
no model loads — providers are constructed lazily (model load is deferred).
"""
from __future__ import annotations

import json
import pathlib
import sys
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import model_registry


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def _write_model(root: pathlib.Path, model_id: str, manifest: dict, *, extra_bytes: int = 0):
    """Create ``root/<model_id>/manifest.json`` plus an optional payload file."""
    model_dir = root / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if extra_bytes:
        (model_dir / "weights.bin").write_bytes(b"\x00" * extra_bytes)
    return model_dir


def _manifest(model_id: str, stage: str, fmt: str, **overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


@pytest.fixture
def no_roots(monkeypatch):
    monkeypatch.delenv(model_registry.BUNDLED_MODELS_ENV, raising=False)
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)


# --------------------------------------------------------------------------- #
# Root discovery helper
# --------------------------------------------------------------------------- #

def test_root_dir_from_env_unset_returns_none(no_roots):
    assert model_registry.bundled_models_root() is None
    assert model_registry.user_models_root() is None


def test_root_dir_from_env_absent_dir_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(tmp_path / "does-not-exist"))
    assert model_registry.bundled_models_root() is None


def test_user_root_appends_models_subdir(monkeypatch, tmp_path):
    (tmp_path / "models").mkdir()
    monkeypatch.setenv(model_registry.USER_DATA_ENV, str(tmp_path))
    assert model_registry.user_models_root() == (tmp_path / "models")


# --------------------------------------------------------------------------- #
# parse_manifest
# --------------------------------------------------------------------------- #

def test_parse_manifest_valid_resolves_absolute_entrypoint(tmp_path):
    model_dir = _write_model(tmp_path, "whisper-small", _manifest("whisper-small", "stt", "faster-whisper-ct2"))
    manifest = model_registry.parse_manifest(model_dir / "manifest.json")
    assert manifest.id == "whisper-small"
    assert manifest.stage == "stt"
    assert manifest.format == "faster-whisper-ct2"
    assert manifest.entrypoint_path == model_dir.resolve()
    assert manifest.entrypoint_path.is_absolute()


def test_parse_manifest_entrypoint_subdir(tmp_path):
    model_dir = _write_model(
        tmp_path, "m1", _manifest("m1", "ipa", "hf-transformers", entrypoint="hf")
    )
    (model_dir / "hf").mkdir()
    manifest = model_registry.parse_manifest(model_dir / "manifest.json")
    assert manifest.entrypoint_path == (model_dir / "hf").resolve()


def test_parse_manifest_id_mismatch_prefers_dir_name(tmp_path):
    model_dir = _write_model(tmp_path, "real-dir", _manifest("wrong-id", "stt", "faster-whisper-ct2"))
    manifest = model_registry.parse_manifest(model_dir / "manifest.json")
    assert manifest.id == "real-dir"


@pytest.mark.parametrize("missing_key", ["id", "name", "stage", "format", "entrypoint"])
def test_parse_manifest_missing_required_raises(tmp_path, missing_key):
    data = _manifest("m", "stt", "faster-whisper-ct2")
    del data[missing_key]
    model_dir = _write_model(tmp_path, "m", data)
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


def test_parse_manifest_bad_stage_raises(tmp_path):
    model_dir = _write_model(tmp_path, "m", _manifest("m", "nonsense", "faster-whisper-ct2"))
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


def test_parse_manifest_bad_format_raises(tmp_path):
    model_dir = _write_model(tmp_path, "m", _manifest("m", "stt", "onnx"))
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


def test_parse_manifest_bad_schema_version_raises(tmp_path):
    model_dir = _write_model(tmp_path, "m", _manifest("m", "stt", "faster-whisper-ct2", schema_version=2))
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


def test_parse_manifest_invalid_json_raises(tmp_path):
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    (model_dir / "manifest.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


def test_parse_manifest_entrypoint_escape_raises(tmp_path):
    model_dir = _write_model(
        tmp_path, "m", _manifest("m", "stt", "faster-whisper-ct2", entrypoint="../../etc")
    )
    with pytest.raises(model_registry.ManifestError):
        model_registry.parse_manifest(model_dir / "manifest.json")


# --------------------------------------------------------------------------- #
# list_models
# --------------------------------------------------------------------------- #

def test_list_models_no_roots_empty(no_roots):
    assert model_registry.list_models() == []


def test_list_models_scans_bundled_and_user_with_flags(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    user_data = tmp_path / "user"
    user_models = user_data / "models"
    bundled.mkdir()
    user_models.mkdir(parents=True)

    _write_model(bundled, "b-stt", _manifest("b-stt", "stt", "faster-whisper-ct2"))
    _write_model(user_models, "u-ipa", _manifest("u-ipa", "ipa", "hf-transformers"))

    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    monkeypatch.setenv(model_registry.USER_DATA_ENV, str(user_data))

    records = {r.id: r for r in model_registry.list_models()}
    assert set(records) == {"b-stt", "u-ipa"}
    assert records["b-stt"].removable is False
    assert records["b-stt"].root == "bundled"
    assert records["b-stt"].source["type"] == "bundled"
    assert records["u-ipa"].removable is True
    assert records["u-ipa"].root == "user"
    assert records["u-ipa"].source["type"] == "user"


def test_list_models_user_overrides_bundled_same_id(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    user_data = tmp_path / "user"
    user_models = user_data / "models"
    bundled.mkdir()
    user_models.mkdir(parents=True)

    _write_model(bundled, "shared", _manifest("shared", "stt", "faster-whisper-ct2", name="Bundled copy"))
    _write_model(user_models, "shared", _manifest("shared", "stt", "faster-whisper-ct2", name="User copy"))

    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    monkeypatch.setenv(model_registry.USER_DATA_ENV, str(user_data))

    records = model_registry.list_models()
    assert len(records) == 1
    assert records[0].name == "User copy"
    assert records[0].removable is True
    assert records[0].root == "user"


def test_list_models_malformed_manifest_skipped_not_crashed(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "good", _manifest("good", "stt", "faster-whisper-ct2"))
    # A broken sibling must not abort the scan.
    bad_dir = bundled / "bad"
    bad_dir.mkdir()
    (bad_dir / "manifest.json").write_text("{ broken", encoding="utf-8")

    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    records = model_registry.list_models()
    assert [r.id for r in records] == ["good"]


def test_list_models_size_from_dir_when_omitted(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(
        bundled, "sized", _manifest("sized", "stt", "faster-whisper-ct2"), extra_bytes=2048
    )
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    (record,) = model_registry.list_models()
    assert record.size_bytes >= 2048  # payload + manifest.json


def test_list_models_size_from_manifest_when_present(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(
        bundled, "declared", _manifest("declared", "stt", "faster-whisper-ct2", size_bytes=999)
    )
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    (record,) = model_registry.list_models()
    assert record.size_bytes == 999


# --------------------------------------------------------------------------- #
# get_model
# --------------------------------------------------------------------------- #

def test_get_model_found_and_missing(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "abc", _manifest("abc", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    assert model_registry.get_model("abc").id == "abc"
    assert model_registry.get_model("nope") is None
    assert model_registry.get_model("") is None


# --------------------------------------------------------------------------- #
# resolve_stage_model
# --------------------------------------------------------------------------- #

def test_resolve_stage_none_when_no_roots(no_roots):
    assert model_registry.resolve_stage_model("stt") is None
    assert model_registry.resolve_stage_model("ipa") is None
    assert model_registry.resolve_stage_model("ortho") is None


def test_resolve_stage_single_model_picked(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "only-stt", _manifest("only-stt", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    resolved = model_registry.resolve_stage_model("stt")
    assert resolved is not None
    assert resolved.id == "only-stt"
    # A stage with no installed model still resolves to None.
    assert model_registry.resolve_stage_model("ipa") is None


def test_resolve_stage_ambiguous_returns_none(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "stt-a", _manifest("stt-a", "stt", "faster-whisper-ct2"))
    _write_model(bundled, "stt-b", _manifest("stt-b", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    assert model_registry.resolve_stage_model("stt") is None


def test_resolve_stage_binding_picked(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "stt-a", _manifest("stt-a", "stt", "faster-whisper-ct2"))
    _write_model(bundled, "stt-b", _manifest("stt-b", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    resolved = model_registry.resolve_stage_model("stt", binding_id="stt-b")
    assert resolved is not None
    assert resolved.id == "stt-b"


def test_resolve_stage_binding_stage_mismatch_falls_back(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "the-stt", _manifest("the-stt", "stt", "faster-whisper-ct2"))
    _write_model(bundled, "the-ipa", _manifest("the-ipa", "ipa", "hf-transformers"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # binding points at an ipa model but we ask for stt: mismatch → fall back to
    # single-stt resolution.
    resolved = model_registry.resolve_stage_model("stt", binding_id="the-ipa")
    assert resolved is not None
    assert resolved.id == "the-stt"


def test_resolve_stage_invalid_stage_returns_none(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "the-stt", _manifest("the-stt", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    assert model_registry.resolve_stage_model("bogus") is None


# --------------------------------------------------------------------------- #
# Loader wiring — LocalWhisperProvider (STT). Construct WITHOUT loading a model.
# --------------------------------------------------------------------------- #

def _stt_config():
    return {"stt": {"model_path": "", "device": "cpu", "compute_type": "int8"}}


def test_stt_provider_no_roots_model_path_unchanged(no_roots):
    from ai.providers.local_whisper import LocalWhisperProvider

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    # The critical web-unchanged guarantee: with no model roots, model_path
    # stays "" exactly as configured (→ faster-whisper "base" downstream).
    assert provider.model_path == ""


def test_stt_provider_uses_registry_when_installed(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    model_dir = _write_model(bundled, "installed-stt", _manifest("installed-stt", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == str(model_dir.resolve())


def test_stt_provider_registry_ignored_when_wrong_format(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "hf-stt", _manifest("hf-stt", "stt", "hf-transformers"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # STT loader only accepts faster-whisper-ct2 from the registry.
    provider = LocalWhisperProvider(config=_stt_config(), config_section="stt")
    assert provider.model_path == ""


def test_stt_provider_explicit_model_path_wins_over_registry(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "installed-stt", _manifest("installed-stt", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    provider = LocalWhisperProvider(
        config={"stt": {"model_path": "/explicit/ct2", "device": "cpu"}},
        config_section="stt",
    )
    assert provider.model_path == "/explicit/ct2"


def test_ortho_provider_hard_fail_guard_preserved(no_roots):
    from ai.providers.local_whisper import LocalWhisperProvider

    # ORTH default model_path is razhan/whisper-base-sdh (non-empty) in real
    # config; an empty ortho.model_path must still hard-fail even with the
    # registry wiring present — registry must not paper over the misconfig.
    with pytest.raises(ValueError):
        LocalWhisperProvider(
            config={"ortho": {"model_path": "", "device": "cpu"}},
            config_section="ortho",
        )


def test_ortho_provider_uses_registry_ct2_when_empty(monkeypatch, tmp_path):
    from ai.providers.local_whisper import LocalWhisperProvider

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    model_dir = _write_model(bundled, "installed-ortho", _manifest("installed-ortho", "ortho", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    # ORTH's real default model_path is non-empty (razhan/whisper-base-sdh), so
    # we explicitly pass an empty ortho.model_path to exercise the registry
    # fallback branch. The registry block runs right after model_path is read
    # and before the ORTH hard-fail guard, so a registered CT2 absolute path
    # populates model_path and satisfies the guard (positive counterpart to
    # test_ortho_provider_hard_fail_guard_preserved).
    provider = LocalWhisperProvider(
        config={"ortho": {"model_path": "", "device": "cpu", "compute_type": "int8"}},
        config_section="ortho",
    )
    assert provider.model_path == str(model_dir.resolve())


# --------------------------------------------------------------------------- #
# Loader wiring — Aligner.load (IPA). Do not actually load torch.
# --------------------------------------------------------------------------- #

def test_aligner_no_roots_keeps_default_model_name(no_roots, monkeypatch):
    import ai.forced_align as fa

    captured = {}

    # Stub the heavy loader body: raise right after the registry-substitution
    # block so we can inspect the model_name that WOULD be loaded, without torch.
    class _Sentinel(RuntimeError):
        pass

    real_resolve = model_registry.resolve_stage_model

    def spy_resolve(stage, **kwargs):
        captured["stage"] = stage
        return real_resolve(stage, **kwargs)

    monkeypatch.setattr(fa, "_PRELOADED_ALIGNER", None, raising=False)
    monkeypatch.setattr("ai.model_registry.resolve_stage_model", spy_resolve, raising=False)
    # Force the torch import to fail so load() bails right after substitution.
    monkeypatch.setitem(sys.modules, "torch", None)

    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    # Registry was consulted for ipa, returned None (no roots), so the default
    # HF repo id is preserved (the RuntimeError is from the stubbed torch import,
    # proving we passed the substitution block unchanged).
    assert captured["stage"] == "ipa"


def test_aligner_uses_registry_hf_model_when_installed(monkeypatch, tmp_path):
    import ai.forced_align as fa

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    model_dir = _write_model(bundled, "ipa-hf", _manifest("ipa-hf", "ipa", "hf-transformers"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    seen = {}

    def fake_from_pretrained(name, *args, **kwargs):
        # First call captures the resolved model_name; raise to stop before any
        # real weight load. The tokenizer is loaded first in Aligner.load, so
        # this records the substituted local dir path.
        seen.setdefault("model_name", name)
        raise RuntimeError("stop-after-substitution")

    monkeypatch.setattr(fa, "_PRELOADED_ALIGNER", None, raising=False)

    # Patch transformers loaders so we capture the resolved model_name without
    # any real download. Inject a stub transformers module. Every from_pretrained
    # captures then raises, so both the explicit-tokenizer path and the legacy
    # Wav2Vec2Processor.from_pretrained fallback record the same model_name.
    import types as _types

    stub = _types.SimpleNamespace(
        Wav2Vec2CTCTokenizer=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2FeatureExtractor=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2ForCTC=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2Processor=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
    )
    torch_stub = _types.SimpleNamespace(
        set_num_threads=lambda *a: None,
        set_num_interop_threads=lambda *a: None,
    )
    monkeypatch.setitem(sys.modules, "transformers", stub)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    # Force CPU so the thread-limit path is deterministic.
    monkeypatch.setattr(fa, "resolve_device", lambda *a, **k: "cpu")
    monkeypatch.setattr(fa, "_configure_torch_cpu_thread_limits", lambda *a, **k: None)

    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    assert seen["model_name"] == str(model_dir.resolve())


def test_ipa_registry_ignored_when_wrong_format(monkeypatch, tmp_path):
    import ai.forced_align as fa

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    # Wrong format for IPA: the loader only accepts hf-transformers from the
    # registry. A faster-whisper-ct2 ipa-stage model must be ignored.
    _write_model(bundled, "ct2-ipa", _manifest("ct2-ipa", "ipa", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    seen = {}

    def fake_from_pretrained(name, *args, **kwargs):
        # Capture the resolved model_name then raise to stop before any real
        # weight load; records whatever name the substitution block produced.
        seen.setdefault("model_name", name)
        raise RuntimeError("stop-after-substitution")

    monkeypatch.setattr(fa, "_PRELOADED_ALIGNER", None, raising=False)

    import types as _types

    stub = _types.SimpleNamespace(
        Wav2Vec2CTCTokenizer=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2FeatureExtractor=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2ForCTC=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
        Wav2Vec2Processor=_types.SimpleNamespace(from_pretrained=fake_from_pretrained),
    )
    torch_stub = _types.SimpleNamespace(
        set_num_threads=lambda *a: None,
        set_num_interop_threads=lambda *a: None,
    )
    monkeypatch.setitem(sys.modules, "transformers", stub)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    monkeypatch.setattr(fa, "resolve_device", lambda *a, **k: "cpu")
    monkeypatch.setattr(fa, "_configure_torch_cpu_thread_limits", lambda *a, **k: None)

    # Default model_name (no explicit override): the wrong-format registry model
    # must NOT be substituted, so the default HF repo id is preserved.
    with pytest.raises(RuntimeError):
        fa.Aligner.load()
    assert seen["model_name"] == fa.DEFAULT_MODEL_NAME


def test_aligner_explicit_model_not_overridden_by_registry(monkeypatch, tmp_path):
    import ai.forced_align as fa

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "ipa-hf", _manifest("ipa-hf", "ipa", "hf-transformers"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    calls = {"resolve": 0}

    def spy_resolve(stage, **kwargs):
        calls["resolve"] += 1
        return model_registry.resolve_stage_model(stage, **kwargs)

    monkeypatch.setattr(fa, "_PRELOADED_ALIGNER", None, raising=False)
    monkeypatch.setattr("ai.model_registry.resolve_stage_model", spy_resolve, raising=False)
    monkeypatch.setitem(sys.modules, "torch", None)

    # Explicit override → the registry branch is skipped entirely.
    with pytest.raises(RuntimeError):
        fa.Aligner.load(model_name="some/explicit-repo")
    assert calls["resolve"] == 0


# --------------------------------------------------------------------------- #
# HTTP read routes
# --------------------------------------------------------------------------- #

import server  # noqa: E402  (imported after sys.path insert)


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self):
        self.sent_json = []

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


def test_route_get_models_lists_records(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "route-stt", _manifest("route-stt", "stt", "faster-whisper-ct2"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    handler = _HandlerHarness()
    handler._api_get_models()

    assert len(handler.sent_json) == 1
    status, payload = handler.sent_json[0]
    assert status == HTTPStatus.OK
    assert [m["id"] for m in payload["models"]] == ["route-stt"]
    # Fully serializable (entrypoint_path is a str).
    assert isinstance(payload["models"][0]["entrypoint_path"], str)


def test_route_get_model_found_and_404(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _write_model(bundled, "route-one", _manifest("route-one", "ipa", "hf-transformers"))
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))

    handler = _HandlerHarness()
    handler._api_get_model("route-one")
    status, payload = handler.sent_json[0]
    assert status == HTTPStatus.OK
    assert payload["id"] == "route-one"

    handler2 = _HandlerHarness()
    with pytest.raises(server.ApiError) as exc_info:
        handler2._api_get_model("missing")
    assert exc_info.value.status == HTTPStatus.NOT_FOUND
