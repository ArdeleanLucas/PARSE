from __future__ import annotations

from pathlib import Path


REQUIRED_PACKAGES = {
    "websockets",
    "fastapi",
    "torch",
    "torchaudio",
    "faster-whisper",
    "silero-vad",
    "transformers",
    "openai",
    "pydantic",
    "requests",
    "pytest",
    "ruff",
}


def _requirements_path() -> Path:
    return Path(__file__).resolve().parent / "requirements.txt"


def _declared_packages(path: Path) -> set[str]:
    packages: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        package = line.split(";", 1)[0].split("[", 1)[0].split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].strip()
        if package:
            packages.add(package)
    return packages


def test_python_requirements_manifest_exists_and_declares_minimum_packages() -> None:
    path = _requirements_path()
    assert path.exists(), "python/requirements.txt should exist"

    declared = _declared_packages(path)
    missing = REQUIRED_PACKAGES - declared
    assert not missing, f"python/requirements.txt missing expected packages: {sorted(missing)}"


def test_python_requirements_manifest_is_grouped_with_comments() -> None:
    content = _requirements_path().read_text(encoding="utf-8")
    assert "# --- Web runtime ---" in content
    assert "# --- Speech & alignment ---" in content
    assert "# --- Chat providers ---" in content
    assert "# --- Dev / test ---" in content
