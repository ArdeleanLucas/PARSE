"""Persistent compute worker for PARSE.

One long-lived Python process that pre-loads wav2vec2 once and serves
compute jobs from the parent HTTP server via multiprocessing queues.
Addresses the root cause of the WSL2 instability treated symptomatically
by PRs #162-169: repeated ``Aligner.load()`` + torch/CUDA context churn
inside the server process.

Architecture
------------
Parent (HTTP server):
    WorkerHandle.start()   -> spawns this file's ``worker_main`` in an
                              mp.Process with two Queues.
    WorkerHandle.submit()  -> puts a job on the job queue.
    A monitor thread drains the event queue and calls the server's
    existing ``_set_job_progress`` / ``_set_job_complete`` /
    ``_set_job_error``, so polling endpoints see no behavioural change.

Child (worker_main):
    1. Pre-load Aligner (once, reused for every job).
    2. Patch ``server._set_job_progress`` / ``_complete`` / ``_error``
       to emit events instead of touching the child's empty ``_jobs``.
    3. Loop: pop a job, dispatch to the matching compute function
       (same routing table as ``_compute_subprocess_entry``), emit
       result/error.

Feature flag
------------
Set ``PARSE_USE_PERSISTENT_WORKER=true`` OR pass
``--compute-mode=persistent`` to opt in. Default remains legacy thread
mode; rollback is ``unset PARSE_USE_PERSISTENT_WORKER`` or
``--compute-mode=thread``.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional


# =====================================================================
# Parent-side: WorkerHandle
# =====================================================================


class WorkerHandle:
    """Parent-side owner of the persistent compute worker process.

    Thread-safe. One instance per server. Lifecycle: ``start()`` ->
    many ``submit()`` calls -> ``shutdown()`` at server exit.

    The ``on_progress`` / ``on_complete`` / ``on_error`` callbacks are
    the server's existing ``_set_job_progress`` / ``_set_job_complete``
    / ``_set_job_error`` — plugging them into the monitor loop keeps
    the status polling surface identical to thread mode.
    """

    def __init__(
        self,
        on_progress: Callable[..., None],
        on_complete: Callable[..., None],
        on_error: Callable[[str, str], None],
    ) -> None:
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._ctx = multiprocessing.get_context("spawn")
        self._job_queue: Optional[Any] = None
        self._event_queue: Optional[Any] = None
        self._process: Optional[Any] = None
        self._monitor: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._in_flight: Dict[str, float] = {}

    # -- lifecycle ------------------------------------------------------

    def start(self, ready_timeout: float = 180.0) -> bool:
        """Spawn the worker process and block until it reports ready.

        Aligner.load() takes 30-120 s cold (model download + weight
        load + CPU tensor init). 180 s leaves headroom. Returns True
        on success; False if the worker never signalled ready — caller
        should treat that as fatal rather than silently degrading.
        """
        with self._lock:
            if self._process is not None and self._process.is_alive():
                return True
            self._job_queue = self._ctx.Queue()
            self._event_queue = self._ctx.Queue()
            self._process = self._ctx.Process(
                target=worker_main,
                name="parse-compute-worker",
                args=(self._job_queue, self._event_queue),
                daemon=True,
            )
            self._process.start()
            self._monitor = threading.Thread(
                target=self._monitor_loop,
                name="parse-worker-monitor",
                daemon=True,
            )
            self._monitor.start()

        if not self._ready.wait(timeout=ready_timeout):
            print(
                "[WORKER] persistent worker did not signal ready within {0}s".format(
                    ready_timeout
                ),
                file=sys.stderr,
                flush=True,
            )
            return False
        return True

    def submit(self, job_id: str, compute_type: str, payload: Dict[str, Any]) -> None:
        if self._job_queue is None:
            raise RuntimeError("Persistent worker not started")
        self._in_flight[job_id] = time.time()
        self._job_queue.put(
            {
                "kind": "job",
                "job_id": job_id,
                "compute_type": compute_type,
                "payload": payload,
            }
        )

    def shutdown(self, timeout: float = 10.0) -> None:
        with self._lock:
            if self._job_queue is not None:
                try:
                    self._job_queue.put({"kind": "shutdown"})
                except Exception:
                    pass
            proc = self._process
        if proc is not None:
            proc.join(timeout=timeout)
            if proc.is_alive():
                try:
                    proc.terminate()
                    proc.join(timeout=5.0)
                except Exception:
                    pass

    def is_alive(self) -> bool:
        return bool(self._process is not None and self._process.is_alive())

    def process_pid(self) -> Optional[int]:
        if self._process is None:
            return None
        return self._process.pid

    def in_flight_count(self) -> int:
        """Number of jobs submitted to the worker that have not yet emitted
        a terminal (complete/error) event. Cheap — plain ``len`` on a dict."""
        return len(self._in_flight)

    # -- event-pump -----------------------------------------------------

    def _monitor_loop(self) -> None:
        """Drain the event queue into the parent's job-state functions.

        Runs forever on a daemon thread. Uses a 1 s poll so we can
        detect a dead worker even when the event queue is idle.
        """
        assert self._event_queue is not None
        while True:
            try:
                event = self._event_queue.get(timeout=1.0)
            except Exception:
                if self._process is not None and not self._process.is_alive():
                    self._mark_survivors_errored(
                        "Persistent compute worker exited unexpectedly."
                    )
                    print(
                        "[WORKER] process died unexpectedly", file=sys.stderr, flush=True
                    )
                    return
                continue

            if not isinstance(event, dict):
                continue
            kind = event.get("kind")
            if kind == "ready":
                self._ready.set()
                continue
            if kind == "shutdown_ack":
                return

            job_id = event.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                continue

            try:
                if kind == "progress":
                    self._on_progress(
                        job_id,
                        float(event.get("progress", 0.0) or 0.0),
                        message=event.get("message"),
                        segments_processed=event.get("segments_processed"),
                        total_segments=event.get("total_segments"),
                    )
                elif kind == "complete":
                    self._in_flight.pop(job_id, None)
                    self._on_complete(
                        job_id,
                        event.get("result"),
                        message=event.get("message") or "Compute complete",
                    )
                elif kind == "error":
                    self._in_flight.pop(job_id, None)
                    err = str(event.get("error") or "Unknown worker error")
                    tb = str(event.get("traceback") or "")
                    if tb:
                        err = "{0}\n{1}".format(err, tb)
                    self._on_error(job_id, err)
            except Exception as exc:
                print(
                    "[WORKER] monitor handler failed ({0}): {1}".format(kind, exc),
                    file=sys.stderr,
                    flush=True,
                )

    def _mark_survivors_errored(self, message: str) -> None:
        for job_id in list(self._in_flight.keys()):
            self._in_flight.pop(job_id, None)
            try:
                self._on_error(job_id, message)
            except Exception:
                pass


# =====================================================================
# Child-side: worker_main
# =====================================================================


def _emit(event_queue: Any, kind: str, **kw: Any) -> None:
    try:
        event_queue.put({"kind": kind, **kw})
    except Exception:
        # Event delivery is best-effort. A failed emit never kills
        # the worker — the next job still runs.
        pass


def _install_parent_emitters(event_queue: Any) -> None:
    """Replace server's three job-state functions with queue emitters.

    Every compute function calls ``_set_job_progress`` via the module's
    global namespace, so patching the ``server`` module's bindings
    redirects all progress flow with zero changes to the compute bodies.
    The child's own ``_jobs`` dict stays empty — we never touch it.
    """
    import server as server_mod

    def _patched_progress(
        job_id,
        progress,
        message=None,
        segments_processed=None,
        total_segments=None,
    ):
        _emit(
            event_queue,
            "progress",
            job_id=job_id,
            progress=progress,
            message=message,
            segments_processed=segments_processed,
            total_segments=total_segments,
        )

    def _patched_complete(
        job_id,
        result,
        message=None,
        segments_processed=None,
        total_segments=None,
    ):
        _emit(
            event_queue,
            "complete",
            job_id=job_id,
            result=result,
            message=message,
            segments_processed=segments_processed,
            total_segments=total_segments,
        )

    def _patched_error(job_id, error_message):
        _emit(event_queue, "error", job_id=job_id, error=str(error_message))

    server_mod._set_job_progress = _patched_progress
    server_mod._set_job_complete = _patched_complete
    server_mod._set_job_error = _patched_error


def _install_aligner_preload() -> Any:
    """Load the wav2vec2 Aligner once and expose it to forced_align.

    Explicitly resolves device (honours WSL force-CPU / CUDA_VISIBLE_DEVICES etc.)
    and logs the final device. Helpful when we start testing GPU in persistent mode.
    """
    from ai.forced_align import Aligner, resolve_device
    from ai import forced_align as fa

    device = resolve_device(None)  # respects all WSL/PM2 force-CPU guards
    aligner = Aligner.load()
    print(
        f"[WORKER] Aligner pre-loaded on {getattr(aligner, 'device', device)}",
        file=sys.stderr, flush=True
    )
    fa._PRELOADED_ALIGNER = aligner
    return aligner


def _dispatch(
    server_mod: Any, compute_type: str, job_id: str, payload: Dict[str, Any]
) -> Any:
    """Routing table — mirrors ``_compute_subprocess_entry`` exactly.

    Keep these branches in sync with server.py's ``_run_compute_job``
    and ``_compute_subprocess_entry``. All three dispatchers must agree
    on the alias set so the same compute_type works across modes.
    """
    normalized = (compute_type or "").strip().lower()
    if normalized in {"cognates", "similarity"}:
        return server_mod._compute_cognates(job_id, payload)
    if normalized == "contact-lexemes":
        return server_mod._compute_contact_lexemes(job_id, payload)
    if normalized in {"ipa_only", "ipa-only", "ipa"}:
        return server_mod._compute_speaker_ipa(job_id, payload)
    if normalized in {"ortho", "ortho_only", "ortho-only"}:
        return server_mod._compute_speaker_ortho(job_id, payload)
    if normalized in {"forced_align", "forced-align", "align"}:
        return server_mod._compute_speaker_forced_align(job_id, payload)
    if normalized in {"full_pipeline", "full-pipeline", "pipeline"}:
        return server_mod._compute_full_pipeline(job_id, payload)
    if normalized in {"train_ipa_model", "train-ipa-model", "train_ipa"}:
        return server_mod._compute_training_job(job_id, payload)
    raise RuntimeError("Unsupported compute type: {0}".format(normalized))


def worker_main(job_queue: Any, event_queue: Any) -> None:
    """Persistent compute worker entry point.

    Runs until it receives a shutdown sentinel, its parent dies, or an
    unrecoverable import error occurs at startup.
    """
    # Dedicated stderr log so worker output doesn't intermix with the
    # parent's /tmp/parse_api_stderr.log and so post-mortems are clean.
    try:
        sys.stderr = open(
            "/tmp/parse-compute-worker.stderr.log", "w", encoding="utf-8"
        )
    except Exception:
        pass

    print(
        "[WORKER] persistent compute worker starting (pid={0})".format(os.getpid()),
        file=sys.stderr,
        flush=True,
    )

    try:
        _install_aligner_preload()
    except Exception as exc:
        print(
            "[WORKER] Aligner.load() failed at startup: {0}\n{1}".format(
                exc, traceback.format_exc()
            ),
            file=sys.stderr,
            flush=True,
        )
        # Do NOT emit ready — parent's wait() will time out and report.
        return

    try:
        import server as server_mod  # noqa: F401
    except Exception as exc:
        print(
            "[WORKER] import server failed: {0}\n{1}".format(
                exc, traceback.format_exc()
            ),
            file=sys.stderr,
            flush=True,
        )
        return

    _install_parent_emitters(event_queue)
    _emit(event_queue, "ready")
    print("[WORKER] ready — entering job loop", file=sys.stderr, flush=True)

    while True:
        try:
            msg = job_queue.get()
        except (EOFError, OSError):
            break
        if not isinstance(msg, dict):
            continue
        if msg.get("kind") == "shutdown":
            _emit(event_queue, "shutdown_ack")
            break

        job_id = str(msg.get("job_id") or "")
        compute_type = str(msg.get("compute_type") or "")
        payload = msg.get("payload") or {}
        if not job_id or not compute_type:
            continue

        print(
            "[WORKER] dispatching job_id={0} type={1}".format(job_id, compute_type),
            file=sys.stderr,
            flush=True,
        )
        try:
            result = _dispatch(server_mod, compute_type, job_id, payload)
            _emit(
                event_queue,
                "complete",
                job_id=job_id,
                result=result,
                message="Compute complete",
            )
            print(
                "[WORKER] completed job_id={0}".format(job_id),
                file=sys.stderr,
                flush=True,
            )
        except Exception as exc:
            print(
                "[WORKER] job_id={0} failed: {1}".format(job_id, exc),
                file=sys.stderr,
                flush=True,
            )
            _emit(
                event_queue,
                "error",
                job_id=job_id,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            # Keep the worker alive — next job gets a fresh try.


__all__ = ["WorkerHandle", "worker_main"]
