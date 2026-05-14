import contextlib
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import server


def _capture_handle_error_output(httpd: server._BoundedThreadHTTPServer, exc: Exception) -> str:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            raise exc
        except Exception:
            httpd.handle_error(None, ("127.0.0.1", 0))
    return stderr.getvalue()


def test_bounded_thread_http_server_silences_benign_client_disconnects() -> None:
    httpd = server._BoundedThreadHTTPServer(("127.0.0.1", 0), server.RangeRequestHandler)
    httpd.server_close()

    for exc_type in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        assert _capture_handle_error_output(httpd, exc_type("client disconnected")) == ""


def test_bounded_thread_http_server_preserves_tracebacks_for_unexpected_errors() -> None:
    httpd = server._BoundedThreadHTTPServer(("127.0.0.1", 0), server.RangeRequestHandler)
    httpd.server_close()

    output = _capture_handle_error_output(httpd, RuntimeError("test"))

    assert "Traceback" in output
    assert "RuntimeError: test" in output
