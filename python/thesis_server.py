"""
thesis_server.py — Range-request-capable HTTP server for the SK Review Tool.

Features:
  - Serves files from the current working directory
  - Supports HTTP Range requests (206 Partial Content)
  - Returns 416 Range Not Satisfiable for invalid/out-of-bounds ranges
  - CORS headers on ALL responses (required for Web Audio API + fetch)
  - Handles OPTIONS preflight requests
  - Binds to 0.0.0.0:8766 (accessible locally and via Tailscale)
  - Windows-compatible stdlib path handling

No external dependencies — stdlib only (Python 3.8+).

Usage:
    cd C:\\Users\\Lucas\\Thesis
    python thesis_server.py
"""

import http.server
import os
import pathlib
import socket
import sys
from http import HTTPStatus

# ── Configuration ────────────────────────────────────────────────────────────

HOST = "0.0.0.0"
PORT = 8766


# ── CORS headers added to every response ─────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Range",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    "Accept-Ranges": "bytes",
}


# ── Request handler ───────────────────────────────────────────────────────────

class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Extends SimpleHTTPRequestHandler with:
      - HTTP Range request support (single range only)
      - CORS headers on every response
      - OPTIONS preflight handling
    """

    # ── Silence default request logging noise (keep for debugging if needed) ──
    # def log_message(self, format, *args):
    #     pass  # Uncomment to suppress access log

    # ── OPTIONS preflight ────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # ── GET / HEAD ───────────────────────────────────────────────────────────

    def do_GET(self):
        """Handle GET with optional Range header."""
        range_header = self.headers.get("Range")
        if range_header:
            self._serve_range(range_header)
        else:
            super().do_GET()

    def do_HEAD(self):
        """Handle HEAD with optional Range header."""
        range_header = self.headers.get("Range")
        if range_header:
            self._serve_range(range_header, head_only=True)
        else:
            super().do_HEAD()

    # ── CORS injection for non-range responses ───────────────────────────────

    def end_headers(self):
        """Inject CORS headers before flushing the header block."""
        self._add_cors_headers()
        super().end_headers()

    def _add_cors_headers(self):
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)

    # ── Range request implementation ─────────────────────────────────────────

    def _parse_single_range(self, range_header: str, file_size: int) -> tuple[int, int]:
        """
        Parse a single HTTP byte range and return (start, end), inclusive.

        Supports:
            Range: bytes=START-END
            Range: bytes=START-
            Range: bytes=-SUFFIX

        Rejects malformed / unsupported multi-range requests.
        Clamps explicit END values that extend past EOF.
        """
        unit, _, ranges_spec = range_header.partition("=")
        if unit.strip().lower() != "bytes":
            raise ValueError(f"Unsupported range unit: {unit!r}")

        ranges_spec = ranges_spec.strip()
        if not ranges_spec:
            raise ValueError("Empty range spec")

        if "," in ranges_spec:
            raise ValueError("Multiple byte ranges are not supported")

        start_str, _, end_str = ranges_spec.partition("-")
        start_str = start_str.strip()
        end_str = end_str.strip()

        if start_str == "" and end_str == "":
            raise ValueError("Empty range spec")

        if start_str == "":
            suffix_length = int(end_str)
            if suffix_length <= 0:
                raise ValueError("Non-positive suffix length")
            start = max(0, file_size - suffix_length)
            end = file_size - 1
            return start, end

        start = int(start_str)
        if start < 0:
            raise ValueError("Negative range start")
        if start >= file_size:
            raise ValueError("Range start beyond EOF")

        if end_str == "":
            end = file_size - 1
        else:
            end = int(end_str)
            if end < start:
                raise ValueError("Range start exceeds range end")
            end = min(end, file_size - 1)

        return start, end

    def _serve_range(self, range_header: str, head_only: bool = False):
        """
        Parse a Range header and serve a 206 Partial Content response.

        Returns 416 for malformed or unsatisfiable ranges.
        """
        path = self.translate_path(self.path)

        if os.path.isdir(path):
            if head_only:
                super().do_HEAD()
            else:
                super().do_GET()
            return

        try:
            file_size = os.path.getsize(path)
        except (OSError, FileNotFoundError):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        try:
            start, end = self._parse_single_range(range_header, file_size)
        except (ValueError, TypeError) as exc:
            self._send_416(file_size, reason=str(exc))
            return

        chunk_size = end - start + 1
        ctype = self.guess_type(path)

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(chunk_size))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        if head_only:
            return

        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                buffer_size = 64 * 1024
                while remaining > 0:
                    to_read = min(buffer_size, remaining)
                    data = f.read(to_read)
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except (OSError, BrokenPipeError):
            pass

    def _send_416(self, file_size: int, reason: str = ""):
        """Send 416 Range Not Satisfiable with Content-Range: bytes */SIZE."""
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", f"bytes */{file_size}")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "0")
        self.end_headers()


# ── Startup ───────────────────────────────────────────────────────────────────

def _get_local_ips():
    """Return a list of non-loopback IPv4 addresses for the banner."""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    return ips


def main():
    serve_dir = pathlib.Path.cwd()
    os.chdir(serve_dir)

    server_address = (HOST, PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, RangeRequestHandler)

    local_ips = _get_local_ips()

    print("=" * 60)
    print("  SK Review Tool — HTTP Server")
    print("=" * 60)
    print(f"  Serving: {serve_dir}")
    print(f"  Port   : {PORT}")
    print()
    print("  URLs:")
    print(f"    http://localhost:{PORT}/review_tool_dev.html")
    for ip in local_ips:
        print(f"    http://{ip}:{PORT}/review_tool_dev.html")
    print()
    print("  Features: Range requests ✓  CORS ✓  Threaded ✓")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
