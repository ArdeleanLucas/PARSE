#!/usr/bin/env python3
"""Standalone reproduction for the PC's Tier 3 threading wedge.

Context: running ``_compute_speaker_ipa`` in the server's ``threading.Thread``
background worker wedges on Windows python.exe between
``[IPA] enter _compute_speaker_ipa`` and ``[IPA] loaded annotation_path``
(or later — Windows pipe buffering may hide intermediate prints).
Running the same code in the main thread (standalone) completes
successfully.

This script isolates the variable: do Tier 3 on Fail02, but from a
``threading.Thread`` (not the main thread). If the thread wedges, we
have confirmed the threading model is the root cause and the fix is
to move compute to a subprocess. If the thread completes, the wedge
is specific to the HTTP server's thread pool / GIL interaction.

Usage::

    python scripts/threading_repro.py \\
        --speaker Fail02 \\
        --checkpoint /tmp/parse_threading_repro.log

Output goes to BOTH stdout AND the ``--checkpoint`` file via
``os.write + os.fsync``. The checkpoint file is the reliable record
if pipe buffering swallows stdout on crash.

Exit codes:
    0 — thread completed successfully
    1 — thread raised an exception (caught and logged)
    2 — thread never finished within ``--timeout`` (the wedge)
    3 — setup error before the thread was launched
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Buffer-free checkpoint logger — duplicates into both stdout and the
# file passed in ``--checkpoint``. ``os.write + os.fsync`` bypasses every
# layer of Python / C / OS buffering that could swallow a line before the
# process dies.
# ---------------------------------------------------------------------------

_CKPT_FD: int | None = None
_CKPT_LOCK = threading.Lock()


def _ckpt_init(path: str) -> None:
    global _CKPT_FD
    _CKPT_FD = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)


def ckpt(label: str, **kv: object) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    thread = threading.current_thread().name
    parts = [now, thread, str(os.getpid()), label]
    for key, value in kv.items():
        try:
            parts.append("{0}={1}".format(key, value))
        except Exception:
            parts.append("{0}=?".format(key))
    line = "\t".join(parts) + "\n"
    # stdout (for the user tailing) — also flushed aggressively.
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        pass
    # Direct write → fsync to the checkpoint file.
    with _CKPT_LOCK:
        if _CKPT_FD is not None:
            try:
                os.write(_CKPT_FD, line.encode("utf-8", errors="replace"))
                try:
                    os.fsync(_CKPT_FD)
                except OSError:
                    pass
            except Exception:
                pass


# ---------------------------------------------------------------------------
# The actual Tier 3 work — lifted from _compute_speaker_ipa, without any
# of the job-runner / HTTP bookkeeping. Only the audio + model calls.
# ---------------------------------------------------------------------------


def tier3_worker(speaker: str, project_root: str, result_holder: dict) -> None:
    """Run standalone Tier 3 end-to-end in this thread. Writes intermediate
    timings via ``ckpt``. Stores final result in ``result_holder``.
    """
    try:
        ckpt("WORKER.entry", speaker=speaker, project_root=project_root)

        # Mirror the import order the server uses so the bug (if import-
        # order-sensitive) surfaces identically.
        ckpt("WORKER.import_server_begin")
        sys.path.insert(0, os.path.join(project_root, "python"))
        os.chdir(project_root)
        import server  # noqa: E402
        ckpt("WORKER.import_server_done")

        ckpt("WORKER.resolve_audio_begin")
        audio_path = server._pipeline_audio_path_for_speaker(speaker)
        ckpt("WORKER.resolve_audio_done", audio_path=str(audio_path))

        ckpt("WORKER.import_forced_align_begin")
        from ai.forced_align import _load_audio_mono_16k, Aligner  # noqa: E402
        ckpt("WORKER.import_forced_align_done")

        ckpt("WORKER.load_audio_begin")
        t0 = time.time()
        audio = _load_audio_mono_16k(audio_path)
        ckpt(
            "WORKER.load_audio_done",
            elapsed=round(time.time() - t0, 2),
            numel=int(audio.numel()),
        )

        ckpt("WORKER.aligner_load_begin")
        t0 = time.time()
        aligner = Aligner.load()
        ckpt(
            "WORKER.aligner_load_done",
            elapsed=round(time.time() - t0, 2),
            device=getattr(aligner, "device", "?"),
        )

        # Try one transcribe_slice call so we exercise the full Tier 3
        # path (not just loading). Slice the first second of audio.
        import ai.ipa_transcribe as it  # noqa: E402

        ckpt("WORKER.transcribe_slice_begin")
        t0 = time.time()
        ipa = it.transcribe_slice(audio, 0.0, 1.0, aligner)
        ckpt(
            "WORKER.transcribe_slice_done",
            elapsed=round(time.time() - t0, 2),
            ipa_len=len(str(ipa or "")),
        )

        result_holder["ok"] = True
        result_holder["ipa_sample"] = str(ipa or "")[:120]
        ckpt("WORKER.ok")
    except Exception as exc:
        ckpt("WORKER.exc", exc_type=type(exc).__name__, exc=str(exc)[:200])
        result_holder["ok"] = False
        result_holder["error"] = str(exc)
        result_holder["traceback"] = traceback.format_exc()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--speaker",
        default="Fail02",
        help="Speaker ID to probe (default: Fail02)",
    )
    parser.add_argument(
        "--project-root",
        default=os.environ.get("PARSE_PROJECT_ROOT", os.getcwd()),
        help="PARSE project root (annotations/, audio/, config/). "
             "Defaults to $PARSE_PROJECT_ROOT or cwd.",
    )
    parser.add_argument(
        "--checkpoint",
        default="/tmp/parse_threading_repro.log",
        help="Buffer-free log file path.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for the worker thread before declaring a wedge (default 600).",
    )
    args = parser.parse_args()

    try:
        _ckpt_init(args.checkpoint)
    except Exception as exc:
        print("[setup-error] can't open checkpoint log {0}: {1}".format(args.checkpoint, exc))
        return 3

    ckpt("MAIN.start", speaker=args.speaker, project_root=args.project_root, timeout=args.timeout)

    result_holder: dict = {}
    worker = threading.Thread(
        target=tier3_worker,
        name="tier3-repro-worker",
        args=(args.speaker, args.project_root, result_holder),
        daemon=True,
    )
    worker.start()
    ckpt("MAIN.worker_started", worker_ident=worker.ident)

    # Poll join so MAIN can emit periodic heartbeats — makes it clear
    # that the main thread isn't the one wedging.
    deadline = time.time() + args.timeout
    heartbeat_every = 15.0
    next_heartbeat = time.time() + heartbeat_every

    while worker.is_alive():
        now = time.time()
        if now >= deadline:
            ckpt(
                "MAIN.WEDGE",
                elapsed=round(args.timeout, 1),
                note="worker thread did not return within --timeout; threading model confirmed as cause",
            )
            return 2
        if now >= next_heartbeat:
            ckpt("MAIN.heartbeat", elapsed=round(now - (deadline - args.timeout), 1))
            next_heartbeat = now + heartbeat_every
        worker.join(timeout=1.0)

    # Worker returned (or died).
    if result_holder.get("ok") is True:
        ckpt("MAIN.ok", ipa_sample=result_holder.get("ipa_sample", ""))
        return 0
    error = result_holder.get("error", "no-error-recorded")
    ckpt("MAIN.worker_failed", error=error)
    tb = result_holder.get("traceback", "")
    if tb:
        # Multi-line traceback — write as one line with literal \n so
        # the checkpoint log stays one-entry-per-line.
        ckpt("MAIN.worker_traceback", tb=tb.replace("\n", " | "))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
