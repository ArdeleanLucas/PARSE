"""OpenAI device authorization flow for PARSE.

Implements the current OpenAI/Codex CLI auth flow:
1. Request a user code from auth.openai.com
2. User visits the verification URL and enters the code
3. Poll for authorization completion
4. Exchange authorization code for access/refresh tokens
5. Store tokens locally for API use

Tokens are stored in config/auth_tokens.json (gitignored).
"""

import json
import pathlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

# Same client ID used by Codex CLI
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
CHATGPT_API = "https://chatgpt.com/backend-api"

# Cloudflare/OpenAI edge rejects Python-urllib defaults with 530 cf_route_error.
# Mirror Codex/OpenCode by always sending an explicit User-Agent.
USER_AGENT = "opencode/1.3.3"

USERCODE_URL = "{issuer}/api/accounts/deviceauth/usercode".format(issuer=ISSUER)
TOKEN_URL = "{issuer}/api/accounts/deviceauth/token".format(issuer=ISSUER)
OAUTH_TOKEN_URL = "{issuer}/oauth/token".format(issuer=ISSUER)
REDIRECT_URI = "{issuer}/deviceauth/callback".format(issuer=ISSUER)
VERIFICATION_URI = "{issuer}/codex/device".format(issuer=ISSUER)

_TOKEN_FILE = "auth_tokens.json"

# In-memory state for active auth flow
_auth_state: Dict[str, Any] = {}
_auth_lock = threading.Lock()


def _config_dir() -> pathlib.Path:
    """Return the config directory, creating it if needed."""
    d = pathlib.Path.cwd() / "config"
    d.mkdir(exist_ok=True)
    return d


def _token_path() -> pathlib.Path:
    return _config_dir() / _TOKEN_FILE


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _seconds_until_expires(expires_at: str, default: int = 600) -> int:
    expires_at = str(expires_at or "").strip()
    if not expires_at:
        return default

    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        remaining = int(parsed.timestamp() - time.time())
        return max(1, remaining)
    except ValueError:
        return default


def _post_json(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST JSON and return parsed response."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(
            "Auth request failed ({code}): {body}".format(code=e.code, body=error_body)
        )


def _post_form(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST x-www-form-urlencoded and return parsed response."""
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(
            "Auth request failed ({code}): {body}".format(code=e.code, body=error_body)
        )


def load_tokens() -> Optional[Dict[str, Any]]:
    """Load stored tokens from disk. Returns None if not found or expired."""
    path = _token_path()
    if not path.is_file():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            tokens = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Check expiry
    expires = tokens.get("expires", 0)
    if expires and time.time() > expires:
        return None

    access = tokens.get("access_token", "").strip()
    if not access:
        return None

    return tokens


def save_tokens(tokens: Dict[str, Any]) -> None:
    """Save tokens to disk."""
    path = _token_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


def clear_tokens() -> None:
    """Remove stored tokens."""
    path = _token_path()
    if path.is_file():
        path.unlink()


def is_authenticated() -> bool:
    """Check if we have valid tokens."""
    return load_tokens() is not None


def get_access_token() -> Optional[str]:
    """Return the current access token, or None."""
    tokens = load_tokens()
    if tokens:
        return tokens.get("access_token")
    return None


def start_device_auth() -> Dict[str, Any]:
    """Start the device authorization flow.

    Returns dict with:
        - user_code: code the user enters
        - verification_uri: URL to visit
        - interval: polling interval in seconds
        - expires_in: seconds until code expires
    """
    # Matches OpenCode flow: only send client_id (no redirect_uri on this call).
    resp = _post_json(USERCODE_URL, {"client_id": CLIENT_ID})

    device_auth_id = str(resp.get("device_auth_id") or "").strip()
    user_code = str(resp.get("user_code") or "").strip()
    verification_uri = (
        str(resp.get("verification_uri_complete") or resp.get("verification_uri") or "").strip()
        or VERIFICATION_URI
    )
    interval = max(1, _parse_int(resp.get("interval"), 5))
    expires_in = _seconds_until_expires(resp.get("expires_at"), default=600)

    if not user_code or not device_auth_id:
        raise RuntimeError("Failed to get device authorization details from OpenAI auth server")

    with _auth_lock:
        _auth_state.clear()
        _auth_state["device_auth_id"] = device_auth_id
        _auth_state["user_code"] = user_code
        _auth_state["verification_uri"] = verification_uri
        _auth_state["interval"] = interval
        _auth_state["expires_at"] = time.time() + expires_in
        _auth_state["status"] = "pending"
        _auth_state["error"] = None

    return {
        "user_code": user_code,
        "verification_uri": verification_uri,
        "interval": interval,
        "expires_in": expires_in,
    }


def poll_device_auth() -> Dict[str, Any]:
    """Poll for device auth completion.

    Returns dict with:
        - status: 'pending' | 'complete' | 'expired' | 'error'
        - error: error message if status is 'error'
    """
    with _auth_lock:
        device_auth_id = str(_auth_state.get("device_auth_id") or "").strip()
        user_code = str(_auth_state.get("user_code") or "").strip()

        if not device_auth_id or not user_code:
            return {"status": "error", "error": "No active auth flow. Call start first."}

        if _auth_state.get("status") == "complete":
            return {"status": "complete"}

        if time.time() > _auth_state.get("expires_at", 0):
            _auth_state["status"] = "expired"
            return {"status": "expired", "error": "Device code expired. Start a new flow."}

    try:
        resp = _post_json(
            TOKEN_URL,
            {
                "device_auth_id": device_auth_id,
                "user_code": user_code,
            },
        )
    except RuntimeError as e:
        error_str = str(e)
        error_lower = error_str.lower()

        # OpenCode treats 403/404 as expected while waiting for user confirmation.
        if (
            "(403)" in error_lower
            or "(404)" in error_lower
            or "authorization_pending" in error_lower
            or "slow_down" in error_lower
            or "deviceauth_authorization_unknown" in error_lower
        ):
            return {"status": "pending"}

        if "expired" in error_lower:
            with _auth_lock:
                _auth_state["status"] = "expired"
            return {"status": "expired", "error": "Device code expired. Start a new flow."}

        return {"status": "error", "error": error_str}

    authorization_code = str(resp.get("authorization_code") or "").strip()
    code_verifier = str(resp.get("code_verifier") or "").strip()

    if not authorization_code or not code_verifier:
        return {"status": "pending"}

    try:
        token_resp = _post_form(
            OAUTH_TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "code_verifier": code_verifier,
            },
        )
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    access_token = str(token_resp.get("access_token") or "").strip()
    if not access_token:
        return {"status": "error", "error": "OpenAI token exchange did not return an access token"}

    expires_in = max(60, _parse_int(token_resp.get("expires_in"), 3600))

    # Success — store tokens
    tokens = {
        "access_token": access_token,
        "refresh_token": str(token_resp.get("refresh_token") or "").strip(),
        "expires_in": expires_in,
        "expires": time.time() + expires_in,
        "token_type": str(token_resp.get("token_type") or "Bearer").strip() or "Bearer",
    }

    save_tokens(tokens)

    with _auth_lock:
        _auth_state["status"] = "complete"

    return {"status": "complete"}


def get_auth_status() -> Dict[str, Any]:
    """Return current auth status."""
    tokens = load_tokens()
    if tokens:
        expires = tokens.get("expires", 0)
        return {
            "authenticated": True,
            "expires_in": max(0, int(expires - time.time())) if expires else None,
        }

    with _auth_lock:
        if _auth_state.get("status") == "pending":
            return {
                "authenticated": False,
                "flow_active": True,
                "user_code": _auth_state.get("user_code", ""),
                "verification_uri": _auth_state.get("verification_uri", ""),
            }

    return {"authenticated": False, "flow_active": False}
