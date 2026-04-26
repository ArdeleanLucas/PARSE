import http.server
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def test_bounded_thread_http_server_close_tolerates_missing_pool(monkeypatch) -> None:
    instance = server._BoundedThreadHTTPServer.__new__(server._BoundedThreadHTTPServer)
    called = {"base": 0}

    def fake_base_close(self) -> None:
        called["base"] += 1

    monkeypatch.setattr(http.server.HTTPServer, "server_close", fake_base_close)

    server._BoundedThreadHTTPServer.server_close(instance)

    assert called["base"] == 1


def test_bounded_thread_http_server_close_shuts_down_pool_when_present(monkeypatch) -> None:
    instance = server._BoundedThreadHTTPServer.__new__(server._BoundedThreadHTTPServer)
    called = {"base": 0, "shutdown": 0}

    class _FakePool:
        def shutdown(self, wait: bool = True) -> None:
            called["shutdown"] += 1
            assert wait is False

    def fake_base_close(self) -> None:
        called["base"] += 1

    instance._pool = _FakePool()
    monkeypatch.setattr(http.server.HTTPServer, "server_close", fake_base_close)

    server._BoundedThreadHTTPServer.server_close(instance)

    assert called == {"base": 1, "shutdown": 1}
