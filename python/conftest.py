"""Shared pytest fixtures for PARSE backend regression tests."""

from __future__ import annotations

import os
import pathlib
import urllib.error
import urllib.request

import pytest

_LONG_AUDIO_FILENAME = "parse_long_audio_001.wav"
_LONG_AUDIO_ENV_URL = "PARSE_LONG_AUDIO_URL"
_LONG_AUDIO_ENV_RUN = "PARSE_RUN_LONG_AUDIO"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-long-audio",
        action="store_true",
        default=False,
        help="run long_audio tests that load real STT models and minutes-long WAV fixtures",
    )


def _long_audio_enabled(config: pytest.Config) -> bool:
    if config.getoption("--run-long-audio", default=False):
        return True
    return str(os.environ.get(_LONG_AUDIO_ENV_RUN, "")).strip().lower() in {"1", "true", "yes", "on"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _long_audio_enabled(config):
        return
    skip_long_audio = pytest.mark.skip(
        reason="long_audio test skipped by default; pass --run-long-audio or set PARSE_RUN_LONG_AUDIO=1"
    )
    for item in items:
        if "long_audio" in item.keywords:
            item.add_marker(skip_long_audio)


def _repo_long_audio_asset() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "tests" / "assets" / "long_audio" / _LONG_AUDIO_FILENAME


def _cached_long_audio_asset() -> pathlib.Path:
    return pathlib.Path("/tmp/parse-long-audio") / _LONG_AUDIO_FILENAME


def _download_long_audio_asset(url: str, target: pathlib.Path) -> pathlib.Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = target.with_suffix(target.suffix + ".tmp")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PARSE-long-audio-regression/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, tmp_target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        tmp_target.replace(target)
    except (OSError, urllib.error.URLError) as exc:
        try:
            tmp_target.unlink()
        except OSError:
            pass
        pytest.skip(f"could not download long audio asset from {_LONG_AUDIO_ENV_URL}: {exc}")
    return target


@pytest.fixture(scope="session")
def long_audio_asset_path(pytestconfig: pytest.Config) -> pathlib.Path:
    """Return the approved real-WAV fixture path, downloading Plan B on demand.

    Resolution order:
    1. committed repo asset under ``python/tests/assets/long_audio/``;
    2. cached ``/tmp/parse-long-audio/`` asset;
    3. ``PARSE_LONG_AUDIO_URL`` download when long-audio tests are explicitly enabled.
    """
    candidates = (_repo_long_audio_asset(), _cached_long_audio_asset())
    for path in candidates:
        if path.exists():
            print(f"[long_audio] using asset: {path}")
            return path

    if _long_audio_enabled(pytestconfig):
        url = str(os.environ.get(_LONG_AUDIO_ENV_URL, "")).strip()
        if url:
            path = _download_long_audio_asset(url, _cached_long_audio_asset())
            print(f"[long_audio] using downloaded asset: {path}")
            return path

    pytest.skip("long audio asset not present; set PARSE_LONG_AUDIO_URL or commit asset")
