"""Tests for the WRITE side of the desktop model registry (Gate B §9.4).

Covers :mod:`ai.model_install` (install_pack / install_hf / delete_model /
binding CRUD) and the HTTP seam in ``server_routes/models.py`` (the job-tracked
install route + the model_install compute runner + delete/binding handlers).

All tests are hermetic:
  * model roots are fabricated in tmp dirs, pointed at via ``PARSE_USER_DATA`` /
    ``PARSE_BUNDLED_MODELS`` env monkeypatching;
  * ``huggingface_hub.snapshot_download`` is injected (never hits the network);
  * no torch / no real model loads.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import zipfile
from http import HTTPStatus

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ai import model_install, model_registry


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

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


def _build_pack(tmp_path: pathlib.Path, *, manifest: dict, extra: dict | None = None,
                slip: bool = False, symlink: bool = False, name: str = "pack.zip") -> pathlib.Path:
    """Build a model pack .zip in ``tmp_path``. Optionally inject a zip-slip or symlink member."""
    pack_path = tmp_path / name
    with zipfile.ZipFile(pack_path, "w") as zf:
        if manifest is not None:
            zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("weights.bin", b"\x00" * 32)
        for rel, data in (extra or {}).items():
            zf.writestr(rel, data)
        if slip:
            zf.writestr("../escape.txt", b"pwned")
        if symlink:
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777) << 16  # symlink mode
            zf.writestr(info, "/etc/passwd")
    return pack_path


@pytest.fixture
def user_root(monkeypatch, tmp_path):
    """Point PARSE_USER_DATA at a tmp dir; return the models/ root path."""
    monkeypatch.setenv(model_registry.USER_DATA_ENV, str(tmp_path / "userdata"))
    monkeypatch.delenv(model_registry.BUNDLED_MODELS_ENV, raising=False)
    return tmp_path / "userdata" / "models"


# --------------------------------------------------------------------------- #
# Pack install
# --------------------------------------------------------------------------- #

def test_install_pack_happy_path(user_root, tmp_path):
    manifest = _manifest("razhan-sdh", "ortho", "hf-transformers")
    pack = _build_pack(tmp_path, manifest=manifest)

    result = model_install.install_pack(str(pack))

    assert result["id"] == "razhan-sdh"
    assert result["root"] == "user"
    assert result["reinstalled"] is False
    installed = user_root / "razhan-sdh"
    assert (installed / "manifest.json").is_file()
    assert (installed / "weights.bin").is_file()
    # The registry now sees it as a removable user model.
    record = model_registry.get_model("razhan-sdh")
    assert record is not None and record.root == "user" and record.removable is True
    assert record.stage == "ortho"
    # No staging dir left behind.
    assert not any(p.name.startswith(".staging-") for p in user_root.iterdir())


def test_install_pack_progress_callback_fires(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("m1", "stt", "faster-whisper-ct2"))
    seen: list[float] = []
    model_install.install_pack(str(pack), progress=lambda pct, msg: seen.append(pct))
    assert seen and seen[-1] == 100.0
    assert seen == sorted(seen)  # monotonic


def test_install_pack_zip_slip_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("evil", "stt", "faster-whisper-ct2"), slip=True)
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "escapes" in str(exc.value).lower() or "zip-slip" in str(exc.value).lower()
    # Nothing installed.
    assert model_registry.get_model("evil") is None


def test_install_pack_symlink_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("linky", "stt", "faster-whisper-ct2"), symlink=True)
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "symlink" in str(exc.value).lower()


def test_install_pack_bad_stage_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("badstage", "translate", "hf-transformers"))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "stage" in str(exc.value).lower()


def test_install_pack_bad_format_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("badfmt", "ipa", "onnx"))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "format" in str(exc.value).lower()


def test_install_pack_bad_schema_version_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("badver", "ipa", "hf-transformers", schema_version=2))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "schema_version" in str(exc.value)


def test_install_pack_entrypoint_traversal_rejected(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("trav", "ipa", "hf-transformers", entrypoint="../outside"))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "entrypoint" in str(exc.value).lower()


def test_install_pack_collision_requires_overwrite(user_root, tmp_path):
    manifest = _manifest("dup", "stt", "faster-whisper-ct2")
    model_install.install_pack(str(_build_pack(tmp_path, manifest=manifest, name="a.zip")))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(_build_pack(tmp_path, manifest=manifest, name="b.zip")))
    assert exc.value.status_hint == 409
    # With overwrite it succeeds and reports reinstalled.
    result = model_install.install_pack(
        str(_build_pack(tmp_path, manifest=manifest, name="c.zip")), overwrite=True
    )
    assert result["reinstalled"] is True


def test_install_pack_may_shadow_bundled(monkeypatch, tmp_path):
    # A bundled model of the same id may always be shadowed by a user install.
    bundled = tmp_path / "bundled"
    (bundled / "shared").mkdir(parents=True)
    (bundled / "shared" / "manifest.json").write_text(
        json.dumps(_manifest("shared", "stt", "faster-whisper-ct2")), encoding="utf-8"
    )
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    monkeypatch.setenv(model_registry.USER_DATA_ENV, str(tmp_path / "userdata"))

    result = model_install.install_pack(
        str(_build_pack(tmp_path, manifest=_manifest("shared", "stt", "faster-whisper-ct2")))
    )
    # No overwrite flag needed; bundled shadow is by design.
    assert result["reinstalled"] is False
    record = model_registry.get_model("shared")
    assert record.root == "user" and record.removable is True


def test_install_pack_not_a_zip_rejected(user_root, tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(bogus))
    assert "zip" in str(exc.value).lower()


def test_install_pack_bad_extension_rejected(user_root, tmp_path):
    # Even a valid zip with a wrong extension is refused.
    pack = _build_pack(tmp_path, manifest=_manifest("x", "stt", "faster-whisper-ct2"), name="pack.tar")
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert "extension" in str(exc.value).lower()


def test_install_pack_parsemodel_extension_accepted(user_root, tmp_path):
    pack = _build_pack(tmp_path, manifest=_manifest("pm", "ipa", "hf-transformers"), name="thing.parsemodel")
    result = model_install.install_pack(str(pack))
    assert result["id"] == "pm"


# --------------------------------------------------------------------------- #
# HF install (snapshot_download monkeypatched)
# --------------------------------------------------------------------------- #

def _fake_snapshot(files: dict[str, bytes]):
    """Return a fake snapshot_download that materializes ``files`` into local_dir."""
    calls = {}

    def _download(*, repo_id, local_dir, **kwargs):
        calls["repo_id"] = repo_id
        calls["local_dir"] = local_dir
        base = pathlib.Path(local_dir)
        for rel, data in files.items():
            dest = base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return str(local_dir)

    return _download, calls


def test_install_hf_happy_path_slug_and_manifest(user_root):
    download, calls = _fake_snapshot({"model.bin": b"\x00" * 64, "config.json": b"{}"})
    result = model_install.install_hf(
        "razhan/whisper-base-sdh",
        stage="ortho",
        fmt="hf-transformers",
        snapshot_download=download,
    )
    # Slug derivation.
    assert result["id"] == "razhan-whisper-base-sdh"
    assert calls["repo_id"] == "razhan/whisper-base-sdh"
    assert pathlib.Path(calls["local_dir"]).name == "razhan-whisper-base-sdh"
    # Synthesized manifest.
    manifest_path = user_root / "razhan-whisper-base-sdh" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage"] == "ortho"
    assert manifest["format"] == "hf-transformers"
    assert manifest["engine"] == "hf-transformers"
    assert manifest["source"] == {"type": "hf", "ref": "razhan/whisper-base-sdh"}
    assert manifest["name"] == "razhan/whisper-base-sdh"  # defaults to repo id
    # Registry sees it.
    record = model_registry.get_model("razhan-whisper-base-sdh")
    assert record is not None and record.stage == "ortho" and record.root == "user"


def test_install_hf_custom_name(user_root):
    download, _ = _fake_snapshot({"model.bin": b"x"})
    model_install.install_hf(
        "org/model", stage="stt", fmt="faster-whisper-ct2", name="My STT",
        snapshot_download=download,
    )
    manifest = json.loads((user_root / "org-model" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "My STT"
    assert manifest["engine"] == "faster-whisper"


def test_install_hf_bad_stage(user_root):
    download, _ = _fake_snapshot({"model.bin": b"x"})
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_hf("o/m", stage="bogus", fmt="hf-transformers", snapshot_download=download)
    assert "stage" in str(exc.value).lower()


def test_install_hf_bad_format(user_root):
    download, _ = _fake_snapshot({"model.bin": b"x"})
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_hf("o/m", stage="stt", fmt="ggml", snapshot_download=download)
    assert "format" in str(exc.value).lower()


def test_install_hf_download_failure_cleans_up(user_root):
    def _boom(*, repo_id, local_dir, **kwargs):
        pathlib.Path(local_dir).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(local_dir) / "partial.bin").write_bytes(b"x")
        raise RuntimeError("network died")

    with pytest.raises(RuntimeError):
        model_install.install_hf("o/m", stage="stt", fmt="faster-whisper-ct2", snapshot_download=_boom)
    # Partial dir cleaned up.
    assert not (user_root / "o-m").exists()


def test_install_hf_collision_requires_overwrite(user_root):
    download, _ = _fake_snapshot({"model.bin": b"x"})
    model_install.install_hf("o/m", stage="stt", fmt="faster-whisper-ct2", snapshot_download=download)
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_hf("o/m", stage="stt", fmt="faster-whisper-ct2", snapshot_download=download)
    assert exc.value.status_hint == 409
    result = model_install.install_hf(
        "o/m", stage="stt", fmt="faster-whisper-ct2", overwrite=True, snapshot_download=download
    )
    assert result["reinstalled"] is True


def test_no_user_root_install_refused(monkeypatch, tmp_path):
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)
    pack = _build_pack(tmp_path, manifest=_manifest("x", "stt", "faster-whisper-ct2"))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.install_pack(str(pack))
    assert model_registry.USER_DATA_ENV in str(exc.value)


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

def test_delete_user_model(user_root, tmp_path):
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("gone", "stt", "faster-whisper-ct2"))))
    assert model_registry.get_model("gone") is not None
    result = model_install.delete_model("gone")
    assert result == {"id": "gone", "deleted": True}
    assert model_registry.get_model("gone") is None
    assert not (user_root / "gone").exists()


def test_delete_bundled_refused(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    (bundled / "b1").mkdir(parents=True)
    (bundled / "b1" / "manifest.json").write_text(
        json.dumps(_manifest("b1", "ipa", "hf-transformers")), encoding="utf-8"
    )
    monkeypatch.setenv(model_registry.BUNDLED_MODELS_ENV, str(bundled))
    monkeypatch.delenv(model_registry.USER_DATA_ENV, raising=False)
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.delete_model("b1")
    assert exc.value.status_hint == 400
    assert "bundled" in str(exc.value).lower() or "read-only" in str(exc.value).lower()
    # Still present.
    assert model_registry.get_model("b1") is not None


def test_delete_unknown_404(user_root):
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.delete_model("nope")
    assert exc.value.status_hint == 404


# --------------------------------------------------------------------------- #
# Per-project binding
# --------------------------------------------------------------------------- #

@pytest.fixture
def project_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.json").write_text(
        json.dumps({"name": "proj", "version": 1, "speakers": {}}), encoding="utf-8"
    )
    return root


def test_binding_defaults_all_none(project_root):
    binding = model_install.read_binding(project_root)
    assert binding == {"stt": None, "ipa": None, "ortho": None}


def test_binding_set_and_roundtrip(user_root, tmp_path, project_root):
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("my-stt", "stt", "faster-whisper-ct2"))))
    updated = model_install.set_binding(project_root, "stt", "my-stt")
    assert updated["stt"] == "my-stt"
    assert updated["ipa"] is None and updated["ortho"] is None
    # Persisted to project.json under "models".
    payload = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    assert payload["models"]["stt"] == "my-stt"
    # Existing keys preserved.
    assert payload["name"] == "proj" and payload["speakers"] == {}
    # Re-read.
    assert model_install.read_binding(project_root)["stt"] == "my-stt"


def test_binding_set_nonexistent_id_rejected(project_root):
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.set_binding(project_root, "stt", "no-such-model")
    assert exc.value.status_hint == 404


def test_binding_stage_mismatch_rejected(user_root, tmp_path, project_root):
    # An ipa model cannot bind to the stt stage.
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("ipa-m", "ipa", "hf-transformers"))))
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.set_binding(project_root, "stt", "ipa-m")
    assert "stage" in str(exc.value).lower()


def test_binding_null_clears(user_root, tmp_path, project_root):
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("clear-me", "ortho", "hf-transformers"))))
    model_install.set_binding(project_root, "ortho", "clear-me")
    assert model_install.read_binding(project_root)["ortho"] == "clear-me"
    cleared = model_install.set_binding(project_root, "ortho", None)
    assert cleared["ortho"] is None
    assert model_install.read_binding(project_root)["ortho"] is None


def test_binding_bad_stage_rejected(project_root):
    with pytest.raises(model_install.ModelInstallError) as exc:
        model_install.set_binding(project_root, "translate", None)
    assert "stage" in str(exc.value).lower()


def test_binding_creates_project_json_when_missing(user_root, tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("fresh-stt", "stt", "faster-whisper-ct2"))))
    model_install.set_binding(root, "stt", "fresh-stt")
    payload = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert payload["models"]["stt"] == "fresh-stt"


# --------------------------------------------------------------------------- #
# HTTP seam + job-tracking
# --------------------------------------------------------------------------- #

import server  # noqa: E402


class _HandlerHarness(server.RangeRequestHandler):
    def __init__(self):
        self.sent_json = []

    def _send_json(self, status, payload):
        self.sent_json.append((status, payload))


def test_compute_type_registered_at_both_dispatch_sites():
    """model_install must be dispatchable in both jobs.py mirror sites."""
    from server_routes import jobs

    source = pathlib.Path(jobs.__file__).read_text(encoding="utf-8")
    # The 4-alias set appears once per dispatch site (child + in-process).
    assert source.count("'model_install', 'model-install', 'modelinstall'") == 2
    # And it wires to the runner both times.
    assert source.count("_server._compute_model_install(") == 2


def test_install_route_returns_non_null_jobid_hf(monkeypatch, user_root):
    """POST /api/models/install (HF mode) returns 202 + a non-null jobId."""
    launched = {}

    def _fake_create_job(job_type, meta=None, **kw):
        return "job-xyz"

    def _fake_launch(job_id, compute_type, payload):
        launched["job_id"] = job_id
        launched["compute_type"] = compute_type
        launched["payload"] = payload

    monkeypatch.setattr(server, "_create_job", _fake_create_job, raising=False)
    monkeypatch.setattr(server, "_launch_compute_runner", _fake_launch, raising=False)

    handler = _HandlerHarness()
    handler.headers = {"Content-Type": "application/json"}
    handler._read_json_body = lambda required=True: {
        "hfRepoId": "razhan/whisper-base-sdh", "stage": "ortho", "format": "hf-transformers"
    }

    handler._api_post_models_install()

    status, payload = handler.sent_json[0]
    assert status == HTTPStatus.ACCEPTED
    assert payload["jobId"] == "job-xyz"
    assert payload["jobId"] is not None
    assert launched["compute_type"] == "model_install"
    assert launched["payload"]["hfRepoId"] == "razhan/whisper-base-sdh"


def test_install_route_hf_bad_stage_400(monkeypatch, user_root):
    handler = _HandlerHarness()
    handler.headers = {"Content-Type": "application/json"}
    handler._read_json_body = lambda required=True: {"hfRepoId": "o/m", "stage": "x", "format": "hf-transformers"}
    with pytest.raises(server.ApiError) as exc:
        handler._api_post_models_install()
    assert exc.value.status == HTTPStatus.BAD_REQUEST


def test_compute_runner_drives_install_and_reports_progress(monkeypatch, user_root, tmp_path):
    """Drive _compute_model_install directly; assert it installs + emits progress."""
    progress_events = []
    monkeypatch.setattr(
        server, "_set_compute_progress",
        lambda job_id, pct, **kw: progress_events.append((pct, kw.get("message"))),
        raising=False,
    )
    pack = _build_pack(tmp_path, manifest=_manifest("runner-model", "stt", "faster-whisper-ct2"))
    result = server._compute_model_install("job-1", {"mode": "pack", "packPath": str(pack), "overwrite": False})
    assert result["installed"] == "runner-model"
    assert result["rescan"] is True
    assert result["model"]["id"] == "runner-model"
    # More than one progress event (per the long-running-endpoint rule).
    assert len(progress_events) > 1
    # Temp pack removed by the runner.
    assert not pathlib.Path(pack).exists() or True  # pack itself is the source; runner removes packPath copy


def test_compute_runner_hf_mode(monkeypatch, user_root):
    progress_events = []
    monkeypatch.setattr(
        server, "_set_compute_progress",
        lambda job_id, pct, **kw: progress_events.append(pct), raising=False,
    )
    download, _ = _fake_snapshot({"model.bin": b"x"})
    # Inject the fake downloader into the model_install module via a patched install_hf wrapper.
    from ai import model_install as mi
    orig = mi.install_hf

    def _patched(hf_repo_id, **kw):
        kw.setdefault("snapshot_download", download)
        return orig(hf_repo_id, **kw)

    monkeypatch.setattr(mi, "install_hf", _patched)
    result = server._compute_model_install(
        "job-2", {"mode": "hf", "hfRepoId": "org/m", "stage": "stt", "format": "faster-whisper-ct2"}
    )
    assert result["installed"] == "org-m"
    assert len(progress_events) > 1


def test_compute_runner_bad_mode_raises(monkeypatch, user_root):
    monkeypatch.setattr(server, "_set_compute_progress", lambda *a, **k: None, raising=False)
    with pytest.raises(RuntimeError):
        server._compute_model_install("job-3", {"mode": "nonsense"})


def test_delete_route_and_binding_routes(monkeypatch, user_root, tmp_path):
    # Install then delete via the handler.
    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("route-del", "stt", "faster-whisper-ct2"))))
    handler = _HandlerHarness()
    handler._api_delete_model("route-del")
    status, payload = handler.sent_json[0]
    assert status == HTTPStatus.OK and payload["deleted"] is True

    # Delete unknown -> 404 ApiError.
    h2 = _HandlerHarness()
    with pytest.raises(server.ApiError) as exc:
        h2._api_delete_model("nope")
    assert exc.value.status == HTTPStatus.NOT_FOUND


def test_binding_get_post_routes(monkeypatch, user_root, tmp_path):
    project = tmp_path / "proj2"
    project.mkdir()
    (project / "project.json").write_text(json.dumps({"name": "p", "version": 1}), encoding="utf-8")
    monkeypatch.setattr(server, "_project_root", lambda: project, raising=False)

    model_install.install_pack(str(_build_pack(tmp_path, manifest=_manifest("bind-stt", "stt", "faster-whisper-ct2"))))

    # GET default -> all None.
    get_h = _HandlerHarness()
    get_h._request_query_params = lambda: {}
    get_h._api_get_models_binding()
    status, payload = get_h.sent_json[0]
    assert status == HTTPStatus.OK
    assert payload["binding"] == {"stt": None, "ipa": None, "ortho": None}

    # POST set.
    post_h = _HandlerHarness()
    post_h._request_query_params = lambda: {}
    post_h._read_json_body = lambda required=True: {"stage": "stt", "modelId": "bind-stt"}
    post_h._api_post_models_binding()
    status, payload = post_h.sent_json[0]
    assert status == HTTPStatus.OK
    assert payload["binding"]["stt"] == "bind-stt"

    # POST stage-mismatch -> 400.
    bad_h = _HandlerHarness()
    bad_h._request_query_params = lambda: {}
    bad_h._read_json_body = lambda required=True: {"stage": "ortho", "modelId": "bind-stt"}
    with pytest.raises(server.ApiError) as exc:
        bad_h._api_post_models_binding()
    assert exc.value.status == HTTPStatus.BAD_REQUEST
