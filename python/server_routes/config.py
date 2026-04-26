"""PARSE server route-domain module: config."""
from __future__ import annotations

import server as _server

def _workspace_frontend_config(base_config: _server.Optional[_server.Dict[str, _server.Any]]=None) -> _server.Dict[str, _server.Any]:
    return _server._app_build_workspace_frontend_config(_server._project_root(), base_config, schema_version=_server.CONFIG_SCHEMA_VERSION)

def _api_get_config(self) -> None:
    response = _server._app_build_get_config_response(load_config=lambda: _server.load_ai_config(_server._config_path()), workspace_frontend_config=_server._workspace_frontend_config)
    self._send_json(response.status, response.payload)

def _api_update_config(self) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_update_config_response(body, load_config=lambda: _server.load_ai_config(_server._config_path()), deep_merge_dicts=_server._deep_merge_dicts, write_config=lambda merged: _server._write_json_file(_server._config_path(), merged))
    except _server._app_ProjectConfigHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_auth_key(self) -> None:
    """POST /api/auth/key — store a direct API key."""
    from ai import openai_auth
    try:
        response = _server._app_build_auth_key_response(self._read_json_body(), save_api_key=openai_auth.save_api_key, reset_chat_runtime=_server._reset_chat_runtime_after_auth_key_save, get_auth_status=openai_auth.get_auth_status)
    except _server._app_AuthHandlerError as exc:
        self._send_json(exc.status, {'error': exc.message})
        return
    except Exception as exc:
        self._send_json(_server.HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(exc)})
        return
    self._send_json(response.status, response.payload)

def _api_auth_status(self) -> None:
    from ai import openai_auth
    response = _server._app_build_auth_status_response(get_auth_status=openai_auth.get_auth_status)
    self._send_json(response.status, response.payload)

def _api_auth_start(self) -> None:
    from ai import openai_auth
    try:
        response = _server._app_build_auth_start_response(start_device_auth=openai_auth.start_device_auth)
    except _server._app_AuthHandlerError as exc:
        self._send_json(exc.status, {'error': exc.message})
        return
    self._send_json(response.status, response.payload)

def _api_auth_poll(self) -> None:
    from ai import openai_auth
    response = _server._app_build_auth_poll_response(poll_device_auth=openai_auth.poll_device_auth)
    self._send_json(response.status, response.payload)

def _api_auth_logout(self) -> None:
    from ai import openai_auth
    response = _server._app_build_auth_logout_response(clear_tokens=openai_auth.clear_tokens)
    self._send_json(response.status, response.payload)

__all__ = ['_workspace_frontend_config', '_api_get_config', '_api_update_config', '_api_auth_key', '_api_auth_status', '_api_auth_start', '_api_auth_poll', '_api_auth_logout']

