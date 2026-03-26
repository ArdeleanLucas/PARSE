#!/usr/bin/env python3
"""Orthography -> IPA conversion utility for PARSE.

Single example:
    python ipa_transcribe.py --input "یەک" --language sdh --provider epitran

Batch example:
    python ipa_transcribe.py --input-file words.txt --output-file ipa.txt --language sdh
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .provider import get_ipa_provider, load_ai_config, southern_kurdish_arabic_to_ipa
except ImportError:
    from provider import get_ipa_provider, load_ai_config, southern_kurdish_arabic_to_ipa  # type: ignore


def is_arabic_script(text: str) -> bool:
    """Return True if text likely uses Arabic-script code points."""
    for char in text:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            return True
    return False


def normalize_provider_name(provider_name: Optional[str], config: Dict[str, object]) -> str:
    """Resolve provider name from CLI argument or config."""
    if provider_name:
        value = provider_name.strip().lower()
    else:
        ipa_config = config.get("ipa", {})
        if isinstance(ipa_config, dict):
            raw_provider = ipa_config.get("provider", "epitran")
            value = str(raw_provider).strip().lower() if raw_provider is not None else "epitran"
        else:
            value = "epitran"

    if value in {"", "none", "null"}:
        value = "epitran"

    aliases = {
        "local": "epitran",
        "faster-whisper": "epitran",
        "local-whisper": "epitran",
        "whisper": "epitran",
    }

    normalized = aliases.get(value, value)
    if not normalized:
        raise ValueError("Unsupported IPA provider: {0}".format(value))
    return normalized


def get_factory_provider_name(provider_name: str) -> str:
    """Map IPA provider aliases to provider factory names."""
    if provider_name == "epitran":
        return "local"
    return provider_name


def build_ipa_provider_config(
    base_config: Dict[str, object],
    provider_name: str,
) -> Dict[str, object]:
    """Build config override for IPA provider factory selection."""
    merged_config: Dict[str, object] = dict(base_config)

    ipa_config = merged_config.get("ipa", {})
    if isinstance(ipa_config, dict):
        ipa_override: Dict[str, object] = dict(ipa_config)
    else:
        ipa_override = {}

    ipa_override["provider"] = get_factory_provider_name(provider_name)
    merged_config["ipa"] = ipa_override

    return merged_config


def convert_single_text(
    text: str,
    language: str,
    provider_name: str,
    config: Dict[str, object],
    config_path: Optional[Path] = None,
) -> str:
    """Convert one orthographic token/string to IPA."""
    value = str(text or "").strip()
    if not value:
        return ""

    selected_provider = get_factory_provider_name(provider_name)
    provider_config = build_ipa_provider_config(config, provider_name)

    try:
        provider = get_ipa_provider(provider_config)
    except ValueError as exc:
        print(
            "[WARN] Unsupported provider '{0}', falling back locally: {1}".format(
                selected_provider,
                exc,
            ),
            file=sys.stderr,
        )
        local_config = build_ipa_provider_config(config, "epitran")
        provider = get_ipa_provider(local_config)
        selected_provider = "local"

    ipa = ""
    try:
        ipa = provider.to_ipa(value, language)
        if ipa:
            return ipa
    except Exception as exc:
        print(
            "[WARN] IPA conversion failed with provider '{0}', falling back locally: {1}".format(
                selected_provider,
                exc,
            ),
            file=sys.stderr,
        )

    if selected_provider != "local":
        local_config = build_ipa_provider_config(config, "epitran")
        local_provider = get_ipa_provider(local_config)
        local_ipa = local_provider.to_ipa(value, language)
        if local_ipa:
            return local_ipa

    if is_arabic_script(value):
        return southern_kurdish_arabic_to_ipa(value)

    return value


def convert_batch(
    input_file: Path,
    output_file: Path,
    language: str,
    provider_name: str,
    config: Dict[str, object],
    config_path: Optional[Path] = None,
) -> int:
    """Convert a newline-delimited text file to IPA line-by-line."""
    input_path = Path(input_file).expanduser().resolve()
    output_path = Path(output_file).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError("Input file not found: {0}".format(input_path))

    lines = input_path.read_text(encoding="utf-8").splitlines()
    output_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            output_lines.append("")
            continue

        output_lines.append(
            convert_single_text(
                text=stripped,
                language=language,
                provider_name=provider_name,
                config=config,
                config_path=config_path,
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return len(output_lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Convert orthographic text to IPA.")

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", help="Inline input text")
    input_group.add_argument("--input-file", help="Path to newline-delimited input file")

    parser.add_argument("--output-file", help="Output path for single or batch mode")
    parser.add_argument("--language", required=True, help="Language code (e.g., sdh, ckb, fa)")
    parser.add_argument(
        "--provider",
        choices=["epitran", "local", "openai"],
        default=None,
        help="IPA backend provider (defaults to config ipa.provider)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to ai_config.json (defaults to config/ai_config.json)",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve() if args.config else None
    config = load_ai_config(config_path)

    try:
        provider_name = normalize_provider_name(args.provider, config)
    except ValueError as exc:
        print("[ERROR] {0}".format(exc), file=sys.stderr)
        return 1

    if args.input_file:
        if not args.output_file:
            print(
                "[ERROR] --output-file is required when using --input-file",
                file=sys.stderr,
            )
            return 1

        try:
            line_count = convert_batch(
                input_file=Path(args.input_file),
                output_file=Path(args.output_file),
                language=args.language,
                provider_name=provider_name,
                config=config,
                config_path=config_path,
            )
        except Exception as exc:
            print("[ERROR] Batch IPA conversion failed: {0}".format(exc), file=sys.stderr)
            return 1

        print(
            "[INFO] Wrote {0} IPA lines to {1}".format(line_count, Path(args.output_file)),
            file=sys.stderr,
        )
        return 0

    try:
        ipa = convert_single_text(
            text=str(args.input),
            language=args.language,
            provider_name=provider_name,
            config=config,
            config_path=config_path,
        )
    except Exception as exc:
        print("[ERROR] IPA conversion failed: {0}".format(exc), file=sys.stderr)
        return 1

    if args.output_file:
        output_path = Path(args.output_file).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ipa + "\n", encoding="utf-8")
        print("[INFO] Wrote IPA to {0}".format(output_path), file=sys.stderr)
    else:
        print(ipa)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
