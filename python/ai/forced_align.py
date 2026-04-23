#!/usr/bin/env python3
"""Tier 2 acoustic forced alignment for PARSE.

Refines the nested ``segments[].words[]`` produced in Tier 1 (Whisper
word_timestamps) into tight per-word and per-phoneme boundaries using
``torchaudio.functional.forced_align`` against
``facebook/wav2vec2-xlsr-53-espeak-cv-ft``.

Pipeline per word:
    1. Slice audio to [start-pad, end+pad] @ 16 kHz.
    2. G2P the orthographic word to an IPA phoneme string (``phonemizer`` +
       espeak-ng, language code ``"ku"``). **G2P output is internal only and
       discarded after alignment — it never becomes the final IPA tier.**
    3. Map the phoneme tokens to vocab IDs via the wav2vec2 processor.
    4. Run CTC on the audio slice, call ``forced_align`` against the token
       sequence, and convert frame indices back to absolute audio seconds.
    5. Emit an ``AlignedWord`` with refined ``start``/``end`` plus optional
       per-phoneme windows.

On any failure (missing phonemes, empty target, model unavailable), fall
back to proportional subdivision inside the original Whisper window so the
pipeline is always safe to call.

CLI:
    python -m ai.forced_align --audio clip.wav --segments stt.json \
        --output aligned.json --language ku
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict

try:
    from .provider import SegmentWithWords, WordSpan
except ImportError:  # pragma: no cover - CLI invocation
    from provider import SegmentWithWords, WordSpan  # type: ignore


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


DEFAULT_MODEL_NAME = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_PAD_MS = 100
DEFAULT_G2P_LANGUAGE = "ku"  # espeak-ng Kurmanji; closest supported for Southern Kurdish
FALLBACK_G2P_LANGUAGE = "fa"  # Persian if Kurdish voice missing in local espeak-ng


class PhonemeSpan(TypedDict, total=False):
    """IPA phoneme with refined start/end (seconds, absolute to full audio)."""

    phoneme: str
    start: float
    end: float


class AlignedWord(TypedDict, total=False):
    """Per-word forced-alignment result.

    Keys are a superset of :class:`WordSpan` so the object is a drop-in
    replacement for the nested ``segments[].words[]`` produced in Tier 1.
    """

    word: str
    start: float            # refined boundary (wav2vec2) or Whisper-fallback
    end: float
    prob: float             # carried over from Whisper if present
    confidence: float       # alignment quality score in [0, 1]
    phonemes: List[PhonemeSpan]
    method: str             # "wav2vec2" | "proportional-fallback"


# ---------------------------------------------------------------------------
# Aligner (lazy-loaded wav2vec2 wrapper)
# ---------------------------------------------------------------------------


@dataclass
class Aligner:
    """Wraps the CTC model + processor used for both Tier 2 alignment and
    Tier 3 acoustic IPA. Load once, reuse for every speaker."""

    model: Any
    processor: Any
    device: str
    vocab: Dict[str, int]
    blank_id: int
    frame_stride_seconds: float

    @classmethod
    def load(
        cls,
        model_name: str = DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
    ) -> "Aligner":
        """Lazy import of torch/transformers so the module is importable
        even in environments that lack them (tests stub ``Aligner.load``).

        Processor construction goes through ``Wav2Vec2CTCTokenizer`` +
        ``Wav2Vec2FeatureExtractor`` explicitly rather than
        ``Wav2Vec2Processor.from_pretrained`` because the latter's
        auto-dispatch breaks on recent transformers versions with:

            TypeError: Received a bool for argument tokenizer, but a
            PreTrainedTokenizerBase was expected.

        (seen on transformers 4.40+ with the PC's kurdish_asr env on
        2026-04-23). The explicit construction is also faster — no
        extra auto-tokenizer discovery round-trip.
        """
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                Wav2Vec2CTCTokenizer,
                Wav2Vec2FeatureExtractor,
                Wav2Vec2ForCTC,
                Wav2Vec2Processor,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Tier 2 forced alignment requires torch + transformers. "
                "Install: pip install torch torchaudio transformers"
            ) from exc

        resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Explicit tokenizer + feature_extractor load. If this path
        # raises, fall back to the legacy auto-dispatch as a last resort
        # so older environments that DO work with from_pretrained still
        # succeed.
        try:
            tokenizer = Wav2Vec2CTCTokenizer.from_pretrained(model_name)
            feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
            processor = Wav2Vec2Processor(
                feature_extractor=feature_extractor,
                tokenizer=tokenizer,
            )
        except Exception:
            processor = Wav2Vec2Processor.from_pretrained(model_name)

        model = Wav2Vec2ForCTC.from_pretrained(model_name).to(resolved_device).eval()

        tokenizer = processor.tokenizer
        vocab = dict(tokenizer.get_vocab())
        pad_token = getattr(tokenizer, "pad_token", "<pad>")
        blank_id = int(vocab.get(pad_token, 0))

        # Wav2Vec2 conv stack has total stride of 320 samples at 16 kHz
        # input (== 20 ms per output frame). Keep as a constant; we
        # recalibrate empirically below via output_len if needed.
        frame_stride_seconds = 320.0 / float(DEFAULT_SAMPLE_RATE)

        return cls(
            model=model,
            processor=processor,
            device=resolved_device,
            vocab=vocab,
            blank_id=blank_id,
            frame_stride_seconds=frame_stride_seconds,
        )

    # ------------------------------------------------------------------
    # Phoneme tokenisation helpers
    # ------------------------------------------------------------------

    def tokens_to_ids(self, phoneme_tokens: Sequence[str]) -> List[int]:
        """Map espeak IPA tokens to model vocab IDs, dropping unknowns.

        The xlsr-53-espeak-cv-ft tokenizer expects single-phoneme tokens
        (e.g. ``"j"``, ``"ɛ"``, ``"k"``). Stress markers (``ˈ``, ``ˌ``) and
        length marks (``ː``) are preserved if in-vocab, stripped otherwise.
        """
        out: List[int] = []
        for tok in phoneme_tokens:
            tok = (tok or "").strip()
            if not tok:
                continue
            if tok in self.vocab:
                out.append(int(self.vocab[tok]))
                continue
            # Retry without suprasegmentals if the raw token missed.
            stripped = tok.replace("ˈ", "").replace("ˌ", "").replace("ː", "").strip()
            if stripped and stripped in self.vocab and stripped != tok:
                out.append(int(self.vocab[stripped]))
        return out

    # ------------------------------------------------------------------
    # Acoustic IPA decoding (Tier 3)
    # ------------------------------------------------------------------

    def transcribe_window(self, audio_16k: Any) -> str:
        """Greedy-decode a mono-16 kHz audio window into an IPA string.

        Used by Tier 3 ``ipa_transcribe`` — runs the same wav2vec2 CTC head
        and returns the collapsed phoneme sequence. Empty string when the
        window is too short or decoding fails.
        """
        import torch  # type: ignore

        if audio_16k is None or int(audio_16k.numel()) < DEFAULT_SAMPLE_RATE // 10:
            return ""

        try:
            with torch.no_grad():
                input_values = self.processor(
                    audio_16k.cpu().numpy(),
                    sampling_rate=DEFAULT_SAMPLE_RATE,
                    return_tensors="pt",
                ).input_values.to(self.device)
                logits = self.model(input_values).logits  # (1, T, C)
                pred_ids = logits.argmax(dim=-1)[0]
            # Tokenizer.decode for CTC models collapses repeats and drops
            # the blank/pad token, which is exactly the greedy-CTC IPA we
            # want for the acoustic tier.
            ipa = self.processor.tokenizer.decode(
                pred_ids, skip_special_tokens=True
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(
                "[WARN] wav2vec2 IPA decode failed: {0}".format(exc),
                file=sys.stderr,
            )
            return ""
        return str(ipa or "").strip()

    # ------------------------------------------------------------------
    # Core alignment call
    # ------------------------------------------------------------------

    def align_window(
        self,
        audio_16k: Any,           # torch.Tensor shape (num_samples,)
        phoneme_tokens: Sequence[str],
    ) -> Optional[Tuple[List[Tuple[int, int]], float]]:
        """Run CTC forced alignment on a single audio window.

        Returns ``(phoneme_frame_spans, score)`` where each span is
        ``(start_frame, end_frame)`` in the model's output grid, or
        ``None`` when alignment is impossible (empty target, too short
        audio, runtime error — caller uses proportional fallback).
        """
        import torch  # type: ignore
        import torchaudio.functional as AF  # type: ignore

        target_ids = self.tokens_to_ids(phoneme_tokens)
        if not target_ids:
            return None

        with torch.no_grad():
            input_values = self.processor(
                audio_16k.cpu().numpy(),
                sampling_rate=DEFAULT_SAMPLE_RATE,
                return_tensors="pt",
            ).input_values.to(self.device)
            logits = self.model(input_values).logits  # (1, T, C)
            log_probs = torch.log_softmax(logits, dim=-1)

        targets = torch.tensor([target_ids], dtype=torch.int32, device=self.device)
        # CTC requires log_probs_len >= targets_len + repeat_blanks. Use a
        # 4-frame buffer to cover near-miss cases where repeats in the phoneme
        # sequence would still violate the constraint. Hitting the kernel with
        # bad inputs causes CUDA errors that destabilise the WSL GPU driver.
        if log_probs.shape[1] < targets.shape[1] + 4:
            return None
        try:
            alignments, scores = AF.forced_align(
                log_probs,
                targets,
                blank=self.blank_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(
                "[WARN] forced_align failed ({0}); caller will fall back.".format(exc),
                file=sys.stderr,
            )
            return None

        # alignments shape: (1, T). Collapse repeated tokens into spans.
        ali = alignments[0].cpu().tolist()
        spans: List[Tuple[int, int]] = []
        current_id: Optional[int] = None
        span_start = 0
        for frame_idx, tok_id in enumerate(ali):
            if tok_id == self.blank_id:
                continue
            if tok_id != current_id:
                if current_id is not None and current_id != self.blank_id:
                    spans.append((span_start, frame_idx))
                current_id = tok_id
                span_start = frame_idx
        if current_id is not None and current_id != self.blank_id:
            spans.append((span_start, len(ali)))

        # We only care about spans matching the target sequence, in order.
        # forced_align returns the best Viterbi path so this is already
        # aligned in order; keep only the first ``len(target_ids)`` spans.
        spans = spans[: len(target_ids)]

        try:
            total_score = float(scores.mean().item())
        except Exception:
            total_score = 0.0

        return spans, total_score


# ---------------------------------------------------------------------------
# G2P (alignment targets only — output discarded after alignment)
# ---------------------------------------------------------------------------


def _g2p_word(word: str, language: str = DEFAULT_G2P_LANGUAGE) -> List[str]:
    """Convert a single orthographic word to a list of IPA phoneme tokens.

    **Internal use only — never persisted, never surfaced as the final IPA
    tier.** Used solely to build CTC targets for ``forced_align``.

    Returns an empty list when phonemizer is unavailable so the caller can
    fall back to proportional subdivision.
    """
    try:
        from phonemizer.backend import EspeakBackend  # type: ignore
    except ImportError:
        return []

    for lang in (language, FALLBACK_G2P_LANGUAGE):
        try:
            backend = EspeakBackend(
                lang,
                preserve_punctuation=False,
                with_stress=True,
            )
        except Exception:
            continue
        try:
            phonemised = backend.phonemize([word], strip=True)
        except Exception:
            continue
        if not phonemised or not phonemised[0]:
            continue
        # espeak emits a single string of IPA glyphs per word; tokenise by
        # character — that matches xlsr-53-espeak-cv-ft's vocabulary shape.
        return [ch for ch in phonemised[0] if not ch.isspace()]
    return []


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def _load_audio_mono_16k(audio_path: Path) -> Any:
    """Load an audio file as a mono 16 kHz torch.Tensor (float32).

    Uses ``soundfile`` as the primary decoder (already a PARSE dependency
    via ``stt_pipeline``) rather than ``torchaudio.load``. torchaudio 2.5+
    dispatches through ``load_with_torchcodec`` by default and raises
    ``TorchCodec is required for load_with_torchcodec`` in environments
    that haven't installed the separate ``torchcodec`` package — which
    was exactly what silently killed the Tier 3 Fail02 run. soundfile
    is libsndfile-backed, works on every platform PARSE supports, and
    doesn't touch torch/CUDA.

    Returned tensor shape is ``(num_samples,)``, dtype float32, at
    exactly :data:`DEFAULT_SAMPLE_RATE`. Multichannel inputs are
    downmixed to mono before resample. Resampling uses
    ``torchaudio.functional.resample`` when available (polyphase,
    reproduces the prior behaviour); if torchaudio is missing or
    broken, falls back to a linear interpolation via ``torch.nn.functional.interpolate``.
    """
    import torch  # type: ignore

    try:
        import soundfile as sf  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Tier 3 audio loading requires the 'soundfile' package. "
            "Install with: pip install soundfile"
        ) from exc

    # Read as float32. ``always_2d=True`` gives a (num_samples, num_channels)
    # ndarray regardless of source shape, which makes the mean-down-to-mono
    # step uniform.
    data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
    # numpy (num_samples, num_channels) → torch (num_channels, num_samples)
    waveform = torch.from_numpy(data.T).contiguous()

    if waveform.ndim == 2 and waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    if sr != DEFAULT_SAMPLE_RATE:
        try:
            import torchaudio.functional as _taf  # type: ignore
            waveform = _taf.resample(waveform, sr, DEFAULT_SAMPLE_RATE)
        except Exception:
            # Last-resort resampler — torch-only, no torchaudio. Works for
            # both up- and down-sampling by reshaping to (N, C, L) so we
            # can use ``interpolate`` with mode="linear".
            orig_len = int(waveform.shape[-1])
            new_len = max(1, int(round(orig_len * DEFAULT_SAMPLE_RATE / float(sr))))
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)
            waveform = torch.nn.functional.interpolate(
                waveform.unsqueeze(0), size=new_len, mode="linear", align_corners=False,
            ).squeeze(0)

    return waveform.squeeze(0).to(torch.float32)


def _slice_window(
    audio: Any,
    start_sec: float,
    end_sec: float,
    pad_ms: int,
) -> Tuple[Any, float]:
    """Return (audio_slice, absolute_slice_start_seconds). Clamps to edges."""
    pad = float(pad_ms) / 1000.0
    slice_start = max(0.0, float(start_sec) - pad)
    slice_end = float(end_sec) + pad
    start_sample = int(round(slice_start * DEFAULT_SAMPLE_RATE))
    end_sample = int(round(slice_end * DEFAULT_SAMPLE_RATE))
    end_sample = min(end_sample, int(audio.shape[0]))
    if end_sample <= start_sample:
        return audio[0:0], slice_start
    return audio[start_sample:end_sample], slice_start


# ---------------------------------------------------------------------------
# Proportional fallback
# ---------------------------------------------------------------------------


def _proportional_fallback(word_span: WordSpan, phoneme_count: int) -> AlignedWord:
    """Subdivide the Whisper window evenly when forced alignment is unavailable."""
    text = str(word_span.get("word", "") or "")
    start = float(word_span.get("start", 0.0) or 0.0)
    end = float(word_span.get("end", start) or start)
    prob = float(word_span.get("prob", 0.0) or 0.0) if "prob" in word_span else 0.0

    result: AlignedWord = {
        "word": text,
        "start": start,
        "end": end,
        "confidence": prob,
        "method": "proportional-fallback",
    }
    if prob:
        result["prob"] = prob
    if phoneme_count > 0 and end > start:
        width = (end - start) / float(phoneme_count)
        phonemes: List[PhonemeSpan] = []
        for idx in range(phoneme_count):
            phonemes.append(
                {
                    "phoneme": "",  # phoneme label discarded per plan
                    "start": start + idx * width,
                    "end": start + (idx + 1) * width,
                }
            )
        result["phonemes"] = phonemes
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def align_word(
    audio_full: Any,
    word_span: WordSpan,
    aligner: Optional[Aligner],
    *,
    language: str = DEFAULT_G2P_LANGUAGE,
    pad_ms: int = DEFAULT_PAD_MS,
    emit_phonemes: bool = True,
) -> AlignedWord:
    """Align one WordSpan. Returns an AlignedWord — never raises."""
    text = str(word_span.get("word", "") or "").strip()
    whisper_start = float(word_span.get("start", 0.0) or 0.0)
    whisper_end = float(word_span.get("end", whisper_start) or whisper_start)
    prob = float(word_span.get("prob", 0.0) or 0.0) if "prob" in word_span else 0.0

    if not text or whisper_end <= whisper_start or aligner is None:
        return _proportional_fallback(word_span, phoneme_count=0)

    # G2P is *only* used to build targets; never persisted.
    phoneme_tokens = _g2p_word(text, language=language)
    if not phoneme_tokens:
        return _proportional_fallback(word_span, phoneme_count=0)

    slice_audio, slice_start_sec = _slice_window(
        audio_full, whisper_start, whisper_end, pad_ms=pad_ms
    )
    if slice_audio.numel() < DEFAULT_SAMPLE_RATE // 10:  # <100 ms of audio
        return _proportional_fallback(word_span, phoneme_count=len(phoneme_tokens))

    aligned = aligner.align_window(slice_audio, phoneme_tokens)
    if aligned is None:
        return _proportional_fallback(word_span, phoneme_count=len(phoneme_tokens))

    phoneme_frame_spans, score = aligned
    if not phoneme_frame_spans:
        return _proportional_fallback(word_span, phoneme_count=len(phoneme_tokens))

    frame_dur = aligner.frame_stride_seconds
    first_frame, _ = phoneme_frame_spans[0]
    _, last_frame = phoneme_frame_spans[-1]
    refined_start = slice_start_sec + first_frame * frame_dur
    refined_end = slice_start_sec + last_frame * frame_dur

    # Normalize the Viterbi score (naturally negative log-prob) into [0, 1].
    # score = mean frame log-prob; exp() gives per-frame prob-ish value.
    try:
        import math
        confidence = max(0.0, min(1.0, math.exp(score) if score < 0 else score))
    except Exception:
        confidence = 0.0

    result: AlignedWord = {
        "word": text,
        "start": refined_start,
        "end": refined_end,
        "confidence": confidence,
        "method": "wav2vec2",
    }
    if prob:
        result["prob"] = prob
    if emit_phonemes:
        phonemes: List[PhonemeSpan] = []
        # Truncate/pad to whichever list is shorter to stay robust against
        # tokenisation mismatches.
        n = min(len(phoneme_tokens), len(phoneme_frame_spans))
        for idx in range(n):
            tok = phoneme_tokens[idx]
            start_f, end_f = phoneme_frame_spans[idx]
            phonemes.append(
                {
                    "phoneme": tok,
                    "start": slice_start_sec + start_f * frame_dur,
                    "end": slice_start_sec + end_f * frame_dur,
                }
            )
        if phonemes:
            result["phonemes"] = phonemes
    return result


def align_segments(
    audio_path: Path,
    segments: Sequence[SegmentWithWords],
    *,
    language: str = DEFAULT_G2P_LANGUAGE,
    pad_ms: int = DEFAULT_PAD_MS,
    model_name: str = DEFAULT_MODEL_NAME,
    device: Optional[str] = None,
    emit_phonemes: bool = True,
    aligner: Optional[Aligner] = None,
    audio_tensor: Optional[Any] = None,
) -> List[List[AlignedWord]]:
    """Align every word in every segment.

    Returns a list indexed by segment, inner list indexed by word. Segments
    without a ``words`` key yield an empty inner list (proportional fallback
    is only sensible when Tier 1 produced at least one Whisper word).

    ``audio_tensor`` may be passed by callers that already hold the
    pre-loaded mono-16 kHz tensor (e.g. ``transcribe_words_with_forced_align``)
    to avoid reloading a large file a second time.
    """
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("Audio file not found: {0}".format(path))

    audio_full = audio_tensor if audio_tensor is not None else _load_audio_mono_16k(path)

    # Lazy-load aligner only when there is work to do and caller didn't
    # supply one. A caller (e.g. the MCP job runner) can share a single
    # Aligner across many speakers to avoid reloading the 1.2 GB model.
    local_aligner: Optional[Aligner] = aligner
    needs_aligner = any(seg.get("words") for seg in segments)
    if needs_aligner and local_aligner is None:
        try:
            local_aligner = Aligner.load(model_name=model_name, device=device)
        except RuntimeError as exc:
            print(
                "[WARN] forced_align: {0}. All words will use proportional fallback.".format(exc),
                file=sys.stderr,
            )
            local_aligner = None

    results: List[List[AlignedWord]] = []
    for seg in segments:
        words = seg.get("words") or []
        segment_results: List[AlignedWord] = []
        for word_span in words:
            segment_results.append(
                align_word(
                    audio_full,
                    word_span,
                    local_aligner,
                    language=language,
                    pad_ms=pad_ms,
                    emit_phonemes=emit_phonemes,
                )
            )
        results.append(segment_results)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_segments(path: Path) -> List[SegmentWithWords]:
    """Load segments from a Tier 1 STT artifact JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        return data["segments"]
    if isinstance(data, list):
        return data  # raw list form
    raise ValueError("Unrecognized segment JSON shape in {0}".format(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Tier 2 forced alignment on a Tier 1 STT artifact."
    )
    parser.add_argument("--audio", required=True, help="Input WAV/audio path")
    parser.add_argument("--segments", required=True, help="Tier 1 STT artifact JSON")
    parser.add_argument("--output", required=True, help="Aligned output JSON path")
    parser.add_argument("--language", default=DEFAULT_G2P_LANGUAGE, help="espeak-ng language code")
    parser.add_argument("--pad-ms", type=int, default=DEFAULT_PAD_MS)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--device", default=None, help="cpu|cuda (auto-detect by default)")
    parser.add_argument("--no-phonemes", action="store_true", help="Omit per-phoneme spans")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    segments_path = Path(args.segments).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    segments = _load_segments(segments_path)
    aligned = align_segments(
        audio_path=audio_path,
        segments=segments,
        language=args.language,
        pad_ms=args.pad_ms,
        model_name=args.model,
        device=args.device,
        emit_phonemes=not args.no_phonemes,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"segments": aligned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "[INFO] Aligned {0} segments -> {1}".format(len(aligned), output_path),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
