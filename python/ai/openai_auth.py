"""OpenAI device authorization flow for PARSE.

Implements the same device auth flow used by Codex CLI / OpenCode:
1. Request a user code from auth.openai.com
2. User visits the verification URL and enters the code
3. Poll for token completion
4. Store tokens locally for API use

Tokens are stored in config/auth_tokens.json (gitignored).
"""

import json
import pathlib
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Dict, Optional

# Same client ID used by Codex CLI
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
CHATGPT_API = "https://chatgpt.com/backend-api"

USERCODE_URL = "{issuer}/api/accounts/deviceauth/usercode".format(issuer=ISSUER)
TOKEN_URL = "{issuer}/api/accounts/deviceauth/token".format(issuer=ISSUER)
REDIRECT_URI = "{issuer}/deviceauth/callback".format(issuer=ISSUER)

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


def _post_json(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST JSON and return parsed response."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
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
    resp = _post_json(USERCODE_URL, {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    })

    user_code = resp.get("user_code", "")
    verification_uri = resp.get("verification_uri", "")
    device_code = resp.get("device_code", "")
    interval = resp.get("interval", 5)
    expires_in = resp.get("expires_in", 600)

    if not user_code or not device_code:
        raise RuntimeError("Failed to get device code from OpenAI auth server")

    with _auth_lock:
        _auth_state.clear()
        _auth_state["device_code"] = device_code
        _auth_state["user_code"] = user_code
        _auth_state["verification_uri"] = verification_uri
        _auth_state["interval"] = interval
        _auth_state["expires_at"] = time.time() + expires_in
        _auth_state["status"] = "pending"
        _auth_state["error"] = None

    return {
        "user_code": user_code,
        "verification_uri": verification_uri or "https://auth.openai.com/deviceauth",
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
        if not _auth_state.get("device_code"):
            return {"status": "error", "error": "No active auth flow. Call start first."}

        if _auth_state.get("status") == "complete":
            return {"status": "complete"}

        if time.time() > _auth_state.get("expires_at", 0):
            _auth_state["status"] = "expired"
            return {"status": "expired", "error": "Device code expired. Start a new flow."}

        device_code = _auth_state["device_code"]

    try:
        resp = _post_json(TOKEN_URL, {
            "client_id": CLIENT_ID,
            "device_code": device_code,
        })
    except RuntimeError as e:
        error_str = str(e)
        if "authorization_pending" in error_str.lower() or "slow_down" in error_str.lower():
            return {"status": "pending"}
        return {"status": "error", "error": error_str}

    access_token = resp.get("access_token", "")
    if not access_token:
        return {"status": "pending"}

    # Success — store tokens
    tokens = {
        "access_token": access_token,
        "refresh_token": resp.get("refresh_token", ""),
        "expires_in": resp.get("expires_in", 3600),
        "expires": time.time() + resp.get("expires_in", 3600),
        "token_type": resp.get("token_type", "Bearer"),
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
