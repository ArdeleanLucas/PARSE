#!/usr/bin/env python3
"""Generate ORTH transcriptions for legacy coarse-transcript workspaces.

This helper is thesis-specific, but it now follows the same runtime truth as
PARSE's supported ORTH pipeline:
- ``ortho.model_path`` must be a local CTranslate2 directory
- HuggingFace repo ids like ``razhan/whisper-base-sdh`` are rejected
- CUDA is preferred, then CPU fallback uses the same CT2 directory

The script still targets the old ``coarse_transcripts`` + ``Audio_Processed``
layout under ``--thesis-dir``. It is *not* the main supported PARSE workflow;
it is only a legacy helper that now respects the current ORTH contract instead
of teaching the opposite one.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from ai.provider import (  # noqa: E402
    _DEFAULT_AI_CONFIG,
    _looks_like_hf_repo_id,
    load_ai_config,
    resolve_ai_config_path,
)


ORTH_EMPTY_MESSAGE = (
    "[ORTH config error] ortho.model_path is empty in ai_config.json. "
    "Set an explicit local CT2 directory under 'ortho.model_path' — for example, "
    "convert razhan/whisper-base-sdh with `ct2-transformers-converter --model "
    "razhan/whisper-base-sdh --output_dir /path/to/razhan-ct2` and point the script "
    "or ai_config.json at that output directory."
)


ORTH_HF_ID_MESSAGE = (
    "[ORTH config error] ortho.model_path '{value}' looks like a HuggingFace repo id. "
    "faster-whisper requires CTranslate2 format, not HF Transformers — convert first "
    "with `ct2-transformers-converter --model {value} --output_dir /path/to/<name>-ct2` "
    "and point ortho.model_path at the CT2 output directory."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speaker', help='Speaker ID (e.g. Kalh01)')
    parser.add_argument('--all', action='store_true', help='Process all speakers')
    parser.add_argument('--thesis-dir', default='/mnt/c/Users/Lucas/Thesis', help='Legacy thesis workspace root')
    parser.add_argument(
        '--model-path',
        help='Explicit local CT2 model directory for ORTH. Overrides ai_config.json.',
    )
    parser.add_argument(
        '--ai-config',
        type=Path,
        help='Optional path to ai_config.json. Defaults to the normal PARSE config resolution.',
    )
    return parser


def resolve_ortho_config(
    explicit_model_path: Optional[str],
    config_path: Optional[Path],
) -> dict:
    resolved_config_path = resolve_ai_config_path(config_path)
    if resolved_config_path.exists():
        config = load_ai_config(resolved_config_path)
    else:
        config = copy.deepcopy(_DEFAULT_AI_CONFIG)

    ortho_block = config.get('ortho') if isinstance(config, dict) else {}
    ortho_config = dict(ortho_block) if isinstance(ortho_block, dict) else {}

    value = str(explicit_model_path or ortho_config.get('model_path', '') or '').strip()
    if not value:
        raise SystemExit(ORTH_EMPTY_MESSAGE)

    if _looks_like_hf_repo_id(value):
        raise SystemExit(ORTH_HF_ID_MESSAGE.format(value=value))

    ortho_config['model_path'] = os.path.expanduser(value)
    return ortho_config


def resolve_ortho_model_path(
    explicit_model_path: Optional[str],
    config_path: Optional[Path],
) -> str:
    return str(resolve_ortho_config(explicit_model_path, config_path)['model_path'])


def build_transcribe_kwargs(ortho_config: dict) -> dict:
    language = str(ortho_config.get('language', '') or '').strip() or None
    try:
        beam_size = max(1, int(ortho_config.get('beam_size', 5) or 5))
    except (TypeError, ValueError):
        beam_size = 5

    vad_filter = bool(ortho_config.get('vad_filter', True))
    kwargs = {
        'language': language,
        'beam_size': beam_size,
        'vad_filter': vad_filter,
        'condition_on_previous_text': bool(ortho_config.get('condition_on_previous_text', False)),
    }

    vad_parameters = ortho_config.get('vad_parameters')
    if vad_filter and isinstance(vad_parameters, dict) and vad_parameters:
        kwargs['vad_parameters'] = dict(vad_parameters)

    ratio_raw = ortho_config.get('compression_ratio_threshold', 1.8)
    try:
        compression_ratio_threshold = float(ratio_raw) if ratio_raw is not None else None
    except (TypeError, ValueError):
        compression_ratio_threshold = 1.8
    if compression_ratio_threshold is not None:
        kwargs['compression_ratio_threshold'] = compression_ratio_threshold

    initial_prompt = str(ortho_config.get('initial_prompt', '') or '').strip()
    if initial_prompt:
        kwargs['initial_prompt'] = initial_prompt

    return kwargs


def _load_whisper_model(model_path: str):
    from faster_whisper import WhisperModel

    last_error = None
    for device, compute_type in (("cuda", "float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(model_path, device=device, compute_type=compute_type)
            print(f"Using {device.upper()} ({model_path})")
            return model, device
        except Exception as exc:  # preserve fallback behavior but only for the same CT2 path
            last_error = exc
    raise last_error  # type: ignore[misc]


def _collect_speakers(args: argparse.Namespace, processed_dir: str, transcript_dir: str) -> list[str]:
    if args.all:
        speakers: list[str] = []
        for directory in os.listdir(processed_dir):
            if not directory.endswith('_process'):
                continue
            speaker = directory.replace('_process', '')
            seg_dir = os.path.join(processed_dir, directory, 'segments')
            transcript_file = os.path.join(transcript_dir, f'{speaker}.json')
            if os.path.isdir(seg_dir) and os.path.isfile(transcript_file):
                speakers.append(speaker)
        print(f"Found {len(speakers)} speakers: {speakers}")
        return speakers

    if args.speaker:
        return [args.speaker]

    raise SystemExit('Specify --speaker or --all')


def _transcribe_all_wavs(
    model,
    model_device: str,
    model_path: str,
    all_wavs: Sequence[str],
    transcribe_kwargs: dict,
) -> dict[str, str]:
    from faster_whisper import WhisperModel

    wav_to_ortho: dict[str, str] = {}
    start_time = time.time()

    for index, wav_path in enumerate(all_wavs, start=1):
        try:
            try:
                segments_out, _info = model.transcribe(wav_path, **transcribe_kwargs)
            except Exception as exc:
                if model_device != 'cuda':
                    raise
                print(f"  CUDA inference failed, switching to CPU: {exc}")
                model = WhisperModel(model_path, device='cpu', compute_type='int8')
                model_device = 'cpu'
                segments_out, _info = model.transcribe(wav_path, **transcribe_kwargs)

            texts = [segment.text for segment in segments_out]
            wav_to_ortho[os.path.basename(wav_path)] = ' '.join(texts).strip()
        except Exception as exc:
            wav_to_ortho[os.path.basename(wav_path)] = ''
            print(f"  WARNING: Failed on {os.path.basename(wav_path)}: {exc}")

        if index % 50 == 0:
            elapsed = time.time() - start_time
            rate = index / elapsed if elapsed else 0.0
            print(f"  {index}/{len(all_wavs)} done ({rate:.1f} files/sec)")

    elapsed = time.time() - start_time
    print(f"  Transcribed {len(all_wavs)} files in {elapsed:.1f}s")
    return wav_to_ortho


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ortho_config = resolve_ortho_config(args.model_path, args.ai_config)
    model_path = str(ortho_config['model_path'])
    model, model_device = _load_whisper_model(model_path)
    transcribe_kwargs = build_transcribe_kwargs(ortho_config)

    transcript_dir = os.path.join(args.thesis_dir, 'coarse_transcripts')
    processed_dir = os.path.join(args.thesis_dir, 'Audio_Processed')
    speakers = _collect_speakers(args, processed_dir, transcript_dir)

    for speaker in speakers:
        print(f"\n{'=' * 60}")
        print(f"Processing {speaker}...")

        transcript_path = os.path.join(transcript_dir, f'{speaker}.json')
        with open(transcript_path, encoding='utf-8') as handle:
            transcript = json.load(handle)

        segments = transcript['segments']
        print(f"  {len(segments)} segments in transcript")

        process_dir = os.path.join(processed_dir, f'{speaker}_process')
        csv_path = os.path.join(process_dir, f'{speaker}_transcriptions.csv')
        seg_dir = os.path.join(process_dir, 'segments')

        ipa_to_wav: dict[str, list[str]] = {}
        if os.path.isfile(csv_path):
            with open(csv_path, newline='', encoding='utf-8') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    ipa = row.get('ipa', '').strip()
                    lexeme_id = row.get('lexeme_id', '').strip()
                    wav_name = f"{lexeme_id}.wav"
                    wav_path = os.path.join(seg_dir, wav_name)
                    if ipa and os.path.isfile(wav_path):
                        ipa_to_wav.setdefault(ipa, []).append(wav_path)
            print(f"  {len(ipa_to_wav)} unique IPA forms mapped to WAV files")

        all_wavs = sorted(
            [os.path.join(seg_dir, filename) for filename in os.listdir(seg_dir) if filename.endswith('.wav')]
        ) if os.path.isdir(seg_dir) else []
        print(f"  {len(all_wavs)} segment WAV files found")

        wav_to_ortho = _transcribe_all_wavs(model, model_device, model_path, all_wavs, transcribe_kwargs)

        if os.path.isfile(csv_path):
            csv_rows = []
            with open(csv_path, newline='', encoding='utf-8') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    csv_rows.append(row)

            if len(csv_rows) == len(segments):
                for segment, row in zip(segments, csv_rows):
                    lexeme_id = row.get('lexeme_id', '').strip()
                    wav_name = f"{lexeme_id}.wav"
                    segment['ortho'] = wav_to_ortho.get(wav_name, '')
                print(f"  Mapped {len(segments)} ortho values (1:1 CSV-transcript alignment)")
            else:
                print(f"  WARNING: CSV has {len(csv_rows)} rows but transcript has {len(segments)} segments")
                matched = 0
                for segment in segments:
                    ipa = segment.get('text', '')
                    wavs = ipa_to_wav.get(ipa, [])
                    if wavs:
                        wav_name = os.path.basename(wavs[0])
                        segment['ortho'] = wav_to_ortho.get(wav_name, '')
                        matched += 1
                print(f"  Matched {matched}/{len(segments)} by IPA text")
        else:
            print("  No CSV found — cannot map ortho to transcript segments")

        with open(transcript_path, 'w', encoding='utf-8') as handle:
            json.dump(transcript, handle, ensure_ascii=False, indent=2)
        print(f"  Saved updated transcript to {transcript_path}")

        print("\n  First 5 segments:")
        for segment in segments[:5]:
            print(
                f"    {segment.get('text', ''):15s}  "
                f"ortho={segment.get('ortho', ''):20s}  "
                f"{segment['start']:.1f}-{segment['end']:.1f}s"
            )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
