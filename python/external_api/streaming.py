"""WebSocket streaming sidecar for PARSE job events.

Additive transport only: the existing HTTP API remains authoritative for start
and poll flows, while this sidecar lets clients subscribe to a single job for
push updates.
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
from typing import Any, Callable, Dict, Optional, Set


def _load_websockets_runtime() -> tuple[Any, type[BaseException]]:
    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError as exc:
        raise RuntimeError(
            "PARSE WebSocket streaming requires the optional 'websockets' package. "
            "It is declared in python/requirements.txt and enables "
            "ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}. "
            "Install with: pip install websockets"
        ) from exc
    return websockets, ConnectionClosed


class JobStreamingSidecar:
    """One-process WebSocket sidecar with a dedicated asyncio loop/thread.

    Clients subscribe per job via ``/ws/jobs/{jobId}``. The sidecar sends an
    initial ``job.snapshot`` event, then broadcasts subsequent envelopes pushed
    in from the synchronous server threads.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        get_snapshot_event: Callable[[str], Optional[Dict[str, Any]]],
    ) -> None:
        self._host = str(host or "127.0.0.1")
        self._requested_port = int(port)
        self._port: Optional[int] = None
        self._get_snapshot_event = get_snapshot_event

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._publisher_task: Optional[asyncio.Task[Any]] = None
        self._publish_queue: Optional[asyncio.Queue[Optional[Dict[str, Any]]]] = None
        self._subscribers: Dict[str, Set[Any]] = {}
        self._ready = threading.Event()
        self._startup_exception: Optional[BaseException] = None
        self._connection_closed_exc: Optional[type[BaseException]] = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("WebSocket sidecar has not started yet")
        return int(self._port)

    @property
    def host(self) -> str:
        return self._host

    def start(self, timeout: float = 5.0) -> "JobStreamingSidecar":
        if self.is_running():
            return self

        self._ready.clear()
        self._startup_exception = None
        self._thread = threading.Thread(
            target=self._thread_main,
            name="parse-ws-sidecar",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError("Timed out starting PARSE WebSocket sidecar")
        if self._startup_exception is not None:
            raise RuntimeError(
                "Failed to start PARSE WebSocket sidecar: {0}".format(
                    self._startup_exception
                )
            ) from self._startup_exception
        return self

    def is_running(self) -> bool:
        return bool(
            self._thread is not None
            and self._thread.is_alive()
            and self._loop is not None
            and self._loop.is_running()
        )

    def stop(self, timeout: float = 5.0) -> None:
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_shutdown(), loop)
            future.result(timeout=timeout)
        thread.join(timeout=timeout)
        self._thread = None
        self._loop = None

    def job_url(self, job_id: str) -> str:
        safe_host = self._host
        if safe_host in {"0.0.0.0", "::"}:
            safe_host = "127.0.0.1"
        return "ws://{0}:{1}/ws/jobs/{2}".format(safe_host, self.port, job_id)

    def publish(self, event: Dict[str, Any]) -> None:
        loop = self._loop
        queue = self._publish_queue
        if loop is None or queue is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(queue.put(copy.deepcopy(event)), loop)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_start())
        except BaseException as exc:  # pragma: no cover - startup errors are surfaced to callers
            self._startup_exception = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    async def _async_start(self) -> None:
        self._publish_queue = asyncio.Queue()
        self._publisher_task = asyncio.create_task(self._publisher_loop())
        websockets_mod, connection_closed_exc = _load_websockets_runtime()
        self._connection_closed_exc = connection_closed_exc
        self._server = await websockets_mod.serve(
            self._handle_connection,
            self._host,
            self._requested_port,
        )
        sockets = getattr(self._server, "sockets", None) or []
        if not sockets:
            raise RuntimeError("WebSocket sidecar failed to bind a listening socket")
        self._port = int(sockets[0].getsockname()[1])

    async def _async_shutdown(self) -> None:
        queue = self._publish_queue
        publisher_task = self._publisher_task
        if queue is not None:
            await queue.put(None)
        if publisher_task is not None:
            await publisher_task
            self._publisher_task = None

        subscribers = [conn for group in self._subscribers.values() for conn in group]
        self._subscribers.clear()
        for conn in subscribers:
            try:
                await conn.close(code=1001, reason="PARSE WebSocket sidecar shutdown")
            except Exception:
                pass

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        loop = self._loop
        if loop is not None:
            loop.call_soon(loop.stop)

    async def _publisher_loop(self) -> None:
        assert self._publish_queue is not None
        while True:
            event = await self._publish_queue.get()
            if event is None:
                return
            await self._broadcast(event)

    async def _broadcast(self, event: Dict[str, Any]) -> None:
        job_id = str(event.get("jobId") or "").strip()
        if not job_id:
            return
        recipients = list(self._subscribers.get(job_id, set()))
        if not recipients:
            return
        message = json.dumps(event, ensure_ascii=False, default=str)
        stale = []
        for conn in recipients:
            try:
                await conn.send(message)
            except Exception as exc:
                if (
                    self._connection_closed_exc is not None
                    and isinstance(exc, self._connection_closed_exc)
                ):
                    stale.append(conn)
                    continue
                raise
        if stale:
            live = self._subscribers.get(job_id)
            if live is not None:
                for conn in stale:
                    live.discard(conn)
                if not live:
                    self._subscribers.pop(job_id, None)

    async def _handle_connection(self, conn: Any) -> None:
        job_id = self._job_id_from_path(
            str(getattr(getattr(conn, "request", None), "path", "") or "")
        )
        if not job_id:
            await conn.close(code=1008, reason="Unsupported PARSE stream path")
            return

        subscribers = self._subscribers.setdefault(job_id, set())
        subscribers.add(conn)
        try:
            snapshot = self._get_snapshot_event(job_id)
            if snapshot is None:
                await conn.close(code=1008, reason="Unknown PARSE jobId")
                return
            await conn.send(json.dumps(snapshot, ensure_ascii=False, default=str))
            async for _message in conn:
                # v1 is server-push only; incoming client messages are ignored.
                continue
        except Exception as exc:
            if (
                self._connection_closed_exc is not None
                and isinstance(exc, self._connection_closed_exc)
            ):
                return
            raise
        finally:
            live = self._subscribers.get(job_id)
            if live is not None:
                live.discard(conn)
                if not live:
                    self._subscribers.pop(job_id, None)

    @staticmethod
    def _job_id_from_path(path: str) -> str:
        normalized = str(path or "").strip()
        prefix = "/ws/jobs/"
        if not normalized.startswith(prefix):
            return ""
        job_id = normalized[len(prefix):].strip("/")
        return job_id.strip()
