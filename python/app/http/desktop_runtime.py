"""Desktop-runtime hardening helpers (Stage 1 / Gate A).

PARSE ships two runtimes from the same backend code:

* The default web/dev runtime, unchanged: binds ``0.0.0.0`` and replies with a
  wildcard ``Access-Control-Allow-Origin: *``.
* A desktop runtime, gated behind ``PARSE_DESKTOP=1``, that binds loopback and
  reflects only loopback ``Origin`` values so a packaged Electron shell talking
  to a co-located Python backend never advertises an open cross-origin surface.

Everything here is intentionally dependency-free (stdlib ``os`` only and pure
string work) so the health/CORS/host logic can be unit-tested without importing
``server.py`` and its heavy runtime deps (torch, faster-whisper, ...).
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional
from urllib.parse import urlsplit

# Header names the desktop path may need to rewrite.
_ACAO_HEADER = "Access-Control-Allow-Origin"
_VARY_HEADER = "Vary"

# Hostnames that count as loopback for desktop-mode origin reflection.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


def is_desktop_mode() -> bool:
    """True when the server is running in packaged-desktop mode.

    Gated strictly on ``PARSE_DESKTOP == "1"`` so any other value (including the
    common unset case) leaves the default web/dev behavior untouched.
    """
    return os.environ.get("PARSE_DESKTOP") == "1"


def resolve_host(default_host: str) -> str:
    """Resolve the bind host for the current runtime.

    * Desktop mode: default to ``127.0.0.1`` (loopback), but honor an explicit
      ``PARSE_HOST`` override if the operator sets one.
    * Web/dev mode: return ``default_host`` unchanged (``0.0.0.0`` today).
    """
    if not is_desktop_mode():
        return default_host
    override = str(os.environ.get("PARSE_HOST") or "").strip()
    if override:
        return override
    return "127.0.0.1"


def is_loopback_origin(origin: Optional[str]) -> bool:
    """True when ``origin`` is an ``http://`` loopback origin.

    Accepts ``http://127.0.0.1``/``http://localhost``/``http://[::1]`` with an
    optional port. Anything else (other hosts, https, malformed) is rejected.
    """
    if not origin:
        return False
    parts = urlsplit(origin.strip())
    if parts.scheme != "http":
        return False
    host = parts.hostname
    if host is None:
        return False
    return host.lower() in _LOOPBACK_HOSTS


def resolve_cors_headers(
    base_headers: Mapping[str, str],
    *,
    origin: Optional[str] = None,
    desktop: Optional[bool] = None,
) -> Dict[str, str]:
    """Return the CORS headers to emit for a single response.

    In web/dev mode this is ``dict(base_headers)`` verbatim so the wildcard
    ``*`` ships exactly as today. In desktop mode the wildcard is dropped: the
    request ``Origin`` is reflected only when it is loopback, and a ``Vary:
    Origin`` header is added so caches key on the request origin.
    """
    headers = dict(base_headers)
    if desktop is None:
        desktop = is_desktop_mode()
    if not desktop:
        return headers

    # Never advertise a wildcard cross-origin surface from the desktop shell.
    headers.pop(_ACAO_HEADER, None)
    if is_loopback_origin(origin):
        headers[_ACAO_HEADER] = origin.strip()  # type: ignore[union-attr]

    existing_vary = str(headers.get(_VARY_HEADER) or "").strip()
    vary_tokens = [tok.strip() for tok in existing_vary.split(",") if tok.strip()]
    if not any(tok.lower() == "origin" for tok in vary_tokens):
        vary_tokens.append("Origin")
    headers[_VARY_HEADER] = ", ".join(vary_tokens)
    return headers


def build_health_payload() -> Dict[str, object]:
    """Body for ``GET /api/health`` — cheap and side-effect-free."""
    return {"status": "ok", "service": "parse", "desktop": is_desktop_mode()}
