"""Tee helper for multiprocessing.spawn child entry functions.

PARSE compute children are spawned via ``multiprocessing.get_context("spawn")``
and historically rebound ``sys.stdout``/``sys.stderr`` to a per-job logfile so
``faulthandler`` could capture segfault tracebacks and the parent could tail
the file on OOM/timeout.

Use ``install_child_tee(log_path)`` at the top of compute child entry
functions. It opens the child log, dups inherited fd 1/2, and rebinds
``sys.stdout``/``sys.stderr`` to a tee so logs still flow to the parent
terminal.
"""

from __future__ import annotations

import faulthandler
import os
import sys
from typing import IO, Any, Tuple


class _Tee:
    """Write-side tee for text streams.

    Per-stream write/flush errors are swallowed so one closed destination does
    not crash the compute child.
    """

    def __init__(self, *streams: Any) -> None:
        self._streams = tuple(streams)

    def write(self, data: str) -> int:
        text = data if isinstance(data, str) else str(data)
        n = 0
        for stream in self._streams:
            try:
                wrote = stream.write(text)
                if isinstance(wrote, int):
                    n = wrote
                stream.flush()
            except Exception:
                pass
        return n or len(text)

    def flush(self) -> None:
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("Tee has no single fileno")


def install_child_tee(log_path: str) -> Tuple[IO[str], IO[str], IO[str]]:
    """Rebind child stdout/stderr to tee writes to log and inherited fds.

    Returns ``(log_fh, inherited_out, inherited_err)`` so callers may keep
    handles alive and/or close them on shutdown.
    """
    log_fh = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")

    inherited_out = os.fdopen(
        os.dup(1), "w", buffering=1, encoding="utf-8", errors="replace"
    )
    inherited_err = os.fdopen(
        os.dup(2), "w", buffering=1, encoding="utf-8", errors="replace"
    )

    sys.stdout = _Tee(log_fh, inherited_out)
    sys.stderr = _Tee(log_fh, inherited_err)

    # faulthandler needs a real fd; keep it on the dedicated logfile.
    faulthandler.enable(file=log_fh, all_threads=True)

    return log_fh, inherited_out, inherited_err


__all__ = ["install_child_tee", "_Tee"]
