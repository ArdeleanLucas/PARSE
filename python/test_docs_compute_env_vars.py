"""Trip-wires preventing compute.md from drifting away from chunking/runtime knobs."""

from __future__ import annotations

from pathlib import Path

DOC_PATH = Path("docs/architecture/compute.md")

# Human-curated: adding or renaming a chunking/runtime env var requires updating
# both docs/architecture/compute.md and this expected set in the same PR.
EXPECTED_ENV_VARS = {
    "PARSE_STT_DEFAULT_CHUNK_MINUTES",
    "PARSE_ORTH_DEFAULT_CHUNK_MINUTES",
    "PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC",
}

RETIRED_ENV_VARS: set[str] = set()

EXPECTED_SUBPROCESS_FUNCS = {
    "_compute_speaker_ortho_in_subprocess",
    "_compute_full_pipeline_ipa_in_subprocess",
}


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_compute_md_mentions_every_parse_chunking_env_var() -> None:
    text = _doc_text()

    missing = sorted(name for name in EXPECTED_ENV_VARS if name not in text)

    assert not missing, (
        "env vars referenced in code but missing from docs/architecture/compute.md: "
        f"{missing}. Update the doc and add a 'When chunking fires' row if applicable."
    )


def test_compute_md_does_not_mention_retired_env_vars() -> None:
    text = _doc_text()

    stale = sorted(name for name in RETIRED_ENV_VARS if name in text)

    assert not stale, f"docs/architecture/compute.md references retired env vars: {stale}. Remove or update them."


def test_compute_md_mentions_every_subprocess_entry_function() -> None:
    text = _doc_text()

    missing = sorted(name for name in EXPECTED_SUBPROCESS_FUNCS if name not in text)

    assert not missing, f"subprocess entry functions missing from docs/architecture/compute.md: {missing}"
