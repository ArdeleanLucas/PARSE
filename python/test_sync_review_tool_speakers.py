import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_review_tool.sh"


def _make_fake_python(bin_dir: Path, capture_path: Path) -> Path:
    fake_python = bin_dir / "python3"
    fake_python.write_text(
        f"#!{sys.executable}\n"
        + """
import json
import os
import sys
from pathlib import Path

capture = Path(os.environ["SYNC_REVIEW_TOOL_CAPTURE"])
args = sys.argv[1:]
if args and args[0] == "-c":
    print("ok")
    raise SystemExit(0)
if args and args[0].endswith("export_review_data.py") and "--help" in args:
    print("usage: export_review_data.py --workspace WORKSPACE --out OUT --contact-config PATH --speakers SPEAKER [SPEAKER ...]")
    raise SystemExit(0)

with capture.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")

out_dir = None
for index, arg in enumerate(args):
    if arg == "--out" and index + 1 < len(args):
        out_dir = Path(args[index + 1])
        break
if out_dir is not None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review_data.json").write_text(json.dumps({"args": args}, indent=2), encoding="utf-8")

print(json.dumps({"analytical_coverage": {"arabic": 1, "persian": 1}}))
""".lstrip(),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return fake_python


def _init_review_clone(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "parse-tests@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "PARSE Tests"], check=True)
    (path / "README.md").write_text("review tool fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


def _run_sync(tmp_path: Path, speakers: str | None) -> list[str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_dir = workspace / "config"
    config_dir.mkdir()
    (config_dir / "sil_contact_languages.json").write_text("{}\n", encoding="utf-8")

    review_clone = tmp_path / "review_tool"
    review_clone.mkdir()
    _init_review_clone(review_clone)

    capture_path = tmp_path / "captured-args.jsonl"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_fake_python(bin_dir, capture_path)

    env = os.environ.copy()
    env.update(
        {
            "PARSE_WORKSPACE": str(workspace),
            "REVIEW_TOOL_CLONE": str(review_clone),
            "SYNC_REVIEW_TOOL_CAPTURE": str(capture_path),
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        }
    )
    if speakers is None:
        env.pop("SPEAKERS", None)
    else:
        env["SPEAKERS"] = speakers

    subprocess.run(["bash", str(SCRIPT)], cwd=REPO_ROOT, env=env, check=True)

    calls = [json.loads(line) for line in capture_path.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 1
    return calls[0]


def test_sync_review_tool_forwards_speakers_env_var(tmp_path: Path) -> None:
    args = _run_sync(tmp_path, speakers="Fail01 Saha01")

    assert "--speakers" in args
    speakers_index = args.index("--speakers")
    assert args[speakers_index : speakers_index + 3] == ["--speakers", "Fail01", "Saha01"]


def test_sync_review_tool_omits_speakers_when_unset(tmp_path: Path) -> None:
    args = _run_sync(tmp_path, speakers=None)

    assert "--speakers" not in args
