"""PARSE server route-domain module: chat."""
from __future__ import annotations

import server as _server

def _normalize_chat_session_id(raw_session_id: _server.Any) -> str:
    session_id = str(raw_session_id or '').strip()
    if not session_id:
        raise ValueError('sessionId is required')
    if not _server.CHAT_SESSION_ID_PATTERN.match(session_id):
        raise ValueError('sessionId must match [A-Za-z0-9_-]{1,128}')
    return session_id

def _cleanup_old_chat_sessions() -> None:
    now_ts = _server.time.time()
    stale_session_ids: _server.List[str] = []
    with _server._chat_sessions_lock:
        for session_id, session in _server._chat_sessions.items():
            updated_ts = session.get('updated_ts')
            if not isinstance(updated_ts, (int, float)):
                continue
            if now_ts - float(updated_ts) > _server.CHAT_SESSION_RETENTION_SECONDS:
                stale_session_ids.append(session_id)
        for session_id in stale_session_ids:
            _server._chat_sessions.pop(session_id, None)

def _chat_session_public_payload(session: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    policy_payload = _server._chat_public_policy_payload()
    messages_raw = session.get('messages')
    messages_out: _server.List[_server.Dict[str, _server.Any]] = []
    tokens_used: _server.Optional[int] = None
    if isinstance(messages_raw, list):
        for message in messages_raw:
            if not isinstance(message, dict):
                continue
            role = str(message.get('role') or '').strip().lower()
            if role not in {'user', 'assistant', 'system'}:
                continue
            content = str(message.get('content') or '')
            created_at = message.get('created_at')
            messages_out.append({'role': role, 'content': content, 'created_at': created_at})
            if role == 'assistant':
                meta = message.get('meta')
                if isinstance(meta, dict):
                    candidate = meta.get('tokensUsed')
                    if isinstance(candidate, int) and candidate >= 0:
                        tokens_used = candidate
    model_name = str(policy_payload.get('model') or '')
    tokens_limit = _server.resolve_context_window(model_name)
    return {'sessionId': str(session.get('sessionId') or ''), 'created_at': session.get('created_at'), 'updated_at': session.get('updated_at'), 'ephemeral': True, 'sharedAcrossPages': True, **policy_payload, 'messages': messages_out, 'tokensUsed': tokens_used, 'tokensLimit': tokens_limit}

def _chat_create_or_get_session(session_id: _server.Optional[str]=None) -> _server.Dict[str, _server.Any]:
    _server._cleanup_old_chat_sessions()
    resolved_session_id = str(session_id or '').strip()
    if resolved_session_id:
        resolved_session_id = _server._normalize_chat_session_id(resolved_session_id)
    else:
        resolved_session_id = 'chat_{0}'.format(_server.uuid.uuid4().hex)
    now_iso = _server._utc_now_iso()
    now_ts = _server.time.time()
    with _server._chat_sessions_lock:
        existing = _server._chat_sessions.get(resolved_session_id)
        if existing is not None:
            existing['updated_at'] = now_iso
            existing['updated_ts'] = now_ts
            return _server.copy.deepcopy(existing)
        created = {'sessionId': resolved_session_id, 'created_at': now_iso, 'updated_at': now_iso, 'created_ts': now_ts, 'updated_ts': now_ts, 'messages': []}
        _server._chat_sessions[resolved_session_id] = created
        return _server.copy.deepcopy(created)

def _chat_get_session_snapshot(session_id: str) -> _server.Optional[_server.Dict[str, _server.Any]]:
    with _server._chat_sessions_lock:
        session = _server._chat_sessions.get(session_id)
        if session is None:
            return None
        return _server.copy.deepcopy(session)

def _chat_append_message(session_id: str, role: str, content: str, metadata: _server.Optional[_server.Dict[str, _server.Any]]=None) -> _server.Dict[str, _server.Any]:
    normalized_role = str(role or '').strip().lower()
    if normalized_role not in {'user', 'assistant', 'system'}:
        raise ValueError('Unsupported chat role: {0}'.format(role))
    policy = _server._chat_runtime_policy()
    max_message_chars = int(policy.get('maxUserMessageChars') or _server.CHAT_DEFAULT_MAX_MESSAGE_CHARS)
    max_session_messages = int(policy.get('maxSessionMessages') or _server.CHAT_DEFAULT_MAX_MESSAGES_PER_SESSION)
    text = str(content or '')
    if len(text) > max_message_chars:
        text = text[:max_message_chars]
    with _server._chat_sessions_lock:
        session = _server._chat_sessions.get(session_id)
        if session is None:
            raise ValueError('Unknown chat session: {0}'.format(session_id))
        messages = session.get('messages')
        if not isinstance(messages, list):
            messages = []
            session['messages'] = messages
        message_payload: _server.Dict[str, _server.Any] = {'id': 'msg_{0}'.format(_server.uuid.uuid4().hex), 'role': normalized_role, 'content': text, 'created_at': _server._utc_now_iso()}
        if isinstance(metadata, dict) and metadata:
            message_payload['meta'] = _server.copy.deepcopy(metadata)
        messages.append(message_payload)
        if len(messages) > max_session_messages:
            session['messages'] = messages[-max_session_messages:]
        session['updated_at'] = _server._utc_now_iso()
        session['updated_ts'] = _server.time.time()
        return _server.copy.deepcopy(message_payload)

def _chat_start_stt_job(speaker: str, source_wav: str, language: _server.Optional[str]) -> str:
    job_id = _server._create_job('stt', {'speaker': speaker, 'sourceWav': source_wav, 'language': language, 'origin': 'chat_tool'})
    _server._launch_compute_runner(job_id, 'stt', {'speaker': speaker, 'sourceWav': source_wav, 'language': language})
    return job_id

def _chat_get_job_snapshot(job_id: str) -> _server.Optional[_server.Dict[str, _server.Any]]:
    return _server._get_job_snapshot(job_id)

def _chat_list_jobs(filters: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    filters_obj = dict(filters or {})
    rows = _server._list_jobs_snapshots(statuses=filters_obj.get('statuses') or [], job_types=filters_obj.get('types') or [], speaker=filters_obj.get('speaker'), limit=int(filters_obj.get('limit') or 100))
    return {'jobs': rows, 'count': len(rows)}

def _chat_get_job_logs(job_id: str, offset: int, limit: int) -> _server.Dict[str, _server.Any]:
    job = _server._get_job_snapshot(job_id)
    if job is None:
        return {'jobId': job_id, 'count': 0, 'offset': offset, 'limit': limit, 'logs': []}
    return _server._job_logs_payload(job, offset=offset, limit=limit)

def _job_callback_url_from_mapping(payload: _server.Dict[str, _server.Any]) -> _server.Optional[str]:
    body_obj = payload if isinstance(payload, dict) else {}
    raw = body_obj.get('callbackUrl', body_obj.get('callback_url'))
    try:
        return _server._normalize_job_callback_url(raw)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc)) from exc

def _chat_pipeline_state(speaker: str) -> _server.Dict[str, _server.Any]:
    """Thin wrapper so ParseChatTools can reach the preflight probe."""
    return _server._pipeline_state_for_speaker(speaker)

def _chat_start_compute_job(compute_type: str, payload: _server.Dict[str, _server.Any]) -> str:
    """Start a compute job and return its jobId.

    Backs both the Tier 2/3 acoustic-alignment tools
    (``forced_align`` / ``ipa_only``) and the pipeline-run tool
    (``full_pipeline``). Mirrors ``_api_post_compute_start`` without the
    HTTP layer so chat-tool / MCP callers get the same behaviour as the
    REST client: ``full_pipeline`` runs step-resilient, records per-step
    tracebacks, and the returned jobId is pollable via
    ``_get_job_snapshot``. The job type is recorded as
    ``compute:<type>`` so ``compute_status`` and
    ``_generic_compute_status`` can filter by compute-type suffix.
    """
    normalized_type = str(compute_type or '').strip().lower()
    if not normalized_type:
        raise ValueError('compute_type is required')
    body_obj = dict(payload or {})
    speaker = str(body_obj.get('speaker') or '').strip() or None
    job_metadata = {'computeType': normalized_type, 'payload': body_obj, 'origin': 'chat_tool'}
    if speaker:
        job_metadata['speaker'] = speaker
    job_id = _server._create_job('compute:{0}'.format(normalized_type), job_metadata)
    _server._launch_compute_runner(job_id, normalized_type, body_obj)
    return job_id

def _chat_docs_root() -> _server.Optional[_server.pathlib.Path]:
    raw = str(_server.os.environ.get('PARSE_CHAT_DOCS_ROOT') or '').strip()
    if not raw:
        return None
    root = _server.pathlib.Path(raw).expanduser()
    if not root.is_absolute():
        root = _server._project_root() / root
    try:
        return root.resolve()
    except Exception:
        return root

def _chat_external_read_roots() -> _server.List[_server.pathlib.Path]:
    """Parse PARSE_EXTERNAL_READ_ROOTS as an OS-path-separated list.

    Use ``:`` on POSIX and ``;`` on Windows. Non-existent or unreadable entries
    are dropped silently so an over-eager config doesn't break chat startup.
    """
    raw = str(_server.os.environ.get('PARSE_EXTERNAL_READ_ROOTS') or '').strip()
    if not raw:
        return []
    sep = ';' if _server.os.name == 'nt' or ';' in raw else _server.os.pathsep
    roots: _server.List[_server.pathlib.Path] = []
    for piece in raw.split(sep):
        piece = piece.strip()
        if not piece:
            continue
        if piece in {'*', '**', '/'}:
            roots.append(_server.pathlib.Path(piece))
            continue
        candidate = _server.pathlib.Path(piece).expanduser()
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots

def _chat_memory_path() -> _server.pathlib.Path:
    raw = str(_server.os.environ.get('PARSE_CHAT_MEMORY_PATH') or '').strip()
    if raw:
        candidate = _server.pathlib.Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = _server._project_root() / candidate
        try:
            return candidate.resolve()
        except Exception:
            return candidate
    return (_server._project_root() / 'parse-memory.md').resolve()

def _chat_onboard_speaker(speaker: str, source_wav_path: _server.pathlib.Path, source_csv_path: _server.Optional[_server.pathlib.Path], is_primary: bool) -> _server.Dict[str, _server.Any]:
    """Synchronous onboarding callback used by the chat tool.

    Copies the source WAV (and optional CSV) into the project's audio/original/
    tree, then runs the existing onboard-speaker worker in-thread so the
    annotation scaffold and source_index registration follow the same path the
    HTTP /api/onboard/speaker endpoint uses.
    """
    project_root_path = _server._project_root()
    target_dir = project_root_path / 'audio' / 'original' / speaker
    target_dir.mkdir(parents=True, exist_ok=True)
    wav_dest = target_dir / source_wav_path.name
    wav_dest.write_bytes(source_wav_path.read_bytes())
    csv_dest: _server.Optional[_server.pathlib.Path] = None
    if source_csv_path is not None:
        csv_dest = target_dir / source_csv_path.name
        csv_dest.write_bytes(source_csv_path.read_bytes())
    job_id = _server._create_job('onboard:speaker', {'speaker': speaker, 'wavPath': str(wav_dest.relative_to(project_root_path)), 'csvPath': str(csv_dest.relative_to(project_root_path)) if csv_dest else None, 'initiatedBy': 'chat'})
    _server._run_onboard_speaker_job(job_id, speaker, wav_dest, csv_dest)
    snapshot = _server._get_job_snapshot(job_id) or {}
    result = snapshot.get('result') if isinstance(snapshot, dict) else None
    if snapshot.get('status') != 'complete':
        raise RuntimeError('Onboarding job {0} failed: {1}'.format(job_id, snapshot.get('error') or 'unknown error'))
    if is_primary is False and isinstance(result, dict):
        source_index_path = _server._source_index_path()
        source_index = _server._read_json_file(source_index_path, {})
        speakers_block = source_index.get('speakers') if isinstance(source_index, dict) else None
        if isinstance(speakers_block, dict):
            entry = speakers_block.get(speaker)
            if isinstance(entry, dict):
                for source_entry in entry.get('source_wavs', []) or []:
                    if isinstance(source_entry, dict) and source_entry.get('filename') == wav_dest.name:
                        source_entry['is_primary'] = False
                _server._write_json_file(source_index_path, source_index)
    return {'jobId': job_id, 'annotationPath': (result or {}).get('annotationPath') if isinstance(result, dict) else None, 'wavPath': (result or {}).get('wavPath') if isinstance(result, dict) else None, 'csvPath': (result or {}).get('csvPath') if isinstance(result, dict) else None}

def _build_workflow_runtime() -> _server.WorkflowTools:
    return _server.WorkflowTools(project_root=_server._project_root(), config_path=_server._config_path(), docs_root=_server._chat_docs_root(), start_stt_job=_server._chat_start_stt_job, get_job_snapshot=_server._chat_get_job_snapshot, external_read_roots=_server._chat_external_read_roots(), memory_path=_server._chat_memory_path(), onboard_speaker=_server._chat_onboard_speaker, start_compute_job=_server._chat_start_compute_job, pipeline_state=_server._chat_pipeline_state)

def _execute_mcp_http_tool(tool_name: str, raw_args: _server.Dict[str, _server.Any], mode: str='active') -> _server.Dict[str, _server.Any]:
    parse_tools, _ = _server._get_chat_runtime()
    workflow_tools = _server._build_workflow_runtime()
    try:
        return _server._app_execute_mcp_http_tool(tool_name, raw_args, mode=mode, project_root=_server._project_root(), parse_tools=parse_tools, workflow_tools=workflow_tools)
    except _server._app_ExternalApiHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc

def _run_chat_job(job_id: str, session_id: str) -> None:
    try:
        _server._set_job_progress(job_id, 5.0, message='Preparing chat context')
        session_snapshot = _server._chat_get_session_snapshot(session_id)
        if session_snapshot is None:
            raise RuntimeError('Unknown chat session: {0}'.format(session_id))
        _server._set_job_progress(job_id, 20.0, message='Running chat orchestration')
        _, orchestrator = _server._get_chat_runtime()

        def _tool_progress(tool_name: str) -> None:
            _server._set_job_progress(job_id, 20.0, message='Running: {0}'.format(tool_name))
        result = orchestrator.run(session_id=session_id, session_messages=session_snapshot.get('messages', []), on_tool_call=_tool_progress)
        assistant_payload = result.get('assistant') if isinstance(result, dict) else {}
        if not isinstance(assistant_payload, dict):
            assistant_payload = {}
        assistant_content = str(assistant_payload.get('content') or '').strip()
        if not assistant_content:
            assistant_content = 'I could not produce a response for this request.'
        reasoning_meta = result.get('reasoning') if isinstance(result, dict) else None
        total_tokens = None
        if isinstance(reasoning_meta, dict):
            total_tokens_raw = reasoning_meta.get('totalTokens')
            if isinstance(total_tokens_raw, int) and total_tokens_raw >= 0:
                total_tokens = total_tokens_raw
        _server._chat_append_message(session_id, role='assistant', content=assistant_content, metadata={'model': result.get('model') if isinstance(result, dict) else None, 'toolTraceCount': len(result.get('toolTrace', [])) if isinstance(result, dict) else 0, 'tokensUsed': total_tokens})
        _server._set_job_complete(job_id, assistant_content, message='Chat run complete')
    except _server.ChatOrchestratorError as exc:
        _server._set_job_error(job_id, str(exc))
    except Exception as exc:
        _server._set_job_error(job_id, str(exc))

def _api_get_chat_session(self, session_part: str) -> None:
    try:
        session_id = _server._normalize_chat_session_id(session_part)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    session = _server._chat_get_session_snapshot(session_id)
    if session is None:
        raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, 'Unknown sessionId')
    self._send_json(_server.HTTPStatus.OK, _server._chat_session_public_payload(session))

def _api_get_mcp_exposure(self) -> None:
    try:
        parse_tools, _ = _server._get_chat_runtime()
        self._send_json(_server.HTTPStatus.OK, _server._app_build_mcp_exposure_response(query_params=self._request_query_params(), project_root=_server._project_root(), parse_tools=parse_tools, workflow_tools=_server._build_workflow_runtime()))
    except _server._app_ExternalApiHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc

def _api_get_mcp_tools(self) -> None:
    try:
        parse_tools, _ = _server._get_chat_runtime()
        self._send_json(_server.HTTPStatus.OK, _server._app_build_mcp_tools_response(query_params=self._request_query_params(), project_root=_server._project_root(), parse_tools=parse_tools, workflow_tools=_server._build_workflow_runtime()))
    except _server._app_ExternalApiHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc

def _api_get_mcp_tool(self, tool_name: str) -> None:
    try:
        parse_tools, _ = _server._get_chat_runtime()
        self._send_json(_server.HTTPStatus.OK, _server._app_build_mcp_tool_response(tool_name, query_params=self._request_query_params(), project_root=_server._project_root(), parse_tools=parse_tools, workflow_tools=_server._build_workflow_runtime()))
    except _server._app_ExternalApiHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc

def _api_post_mcp_tool(self, tool_name: str) -> None:
    try:
        mode = _server._app_resolve_requested_catalog_mode(self._request_query_params())
    except _server._app_ExternalApiHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    body = self._expect_object(self._read_json_body(required=False) or {}, 'Request body')
    self._send_json(_server.HTTPStatus.OK, _server._execute_mcp_http_tool(tool_name, body, mode=mode))

def _api_post_chat_session(self) -> None:
    body = self._read_json_body(required=False)
    body_obj = self._expect_object(body or {}, 'Request body')
    raw_session_id = body_obj.get('sessionId', body_obj.get('session_id'))
    session_id = str(raw_session_id).strip() if raw_session_id is not None else ''
    try:
        session = _server._chat_create_or_get_session(session_id if session_id else None)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    self._send_json(_server.HTTPStatus.OK, _server._chat_session_public_payload(session))

def _api_post_chat_run_start(self) -> None:
    body = self._expect_object(self._read_json_body(required=True), 'Request body')
    policy = None
    try:
        policy, message_text = _server._chat_validate_run_request(body)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    raw_session_id = body.get('sessionId', body.get('session_id'))
    session_id = str(raw_session_id).strip() if raw_session_id is not None else ''
    callback_url = _server._job_callback_url_from_mapping(body)
    try:
        session = _server._chat_create_or_get_session(session_id if session_id else None)
        resolved_session_id = str(session.get('sessionId') or '')
        _server._chat_append_message(resolved_session_id, role='user', content=message_text)
    except ValueError as exc:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, str(exc))
    job_id = _server._create_job('chat:run', {'sessionId': resolved_session_id, 'callbackUrl': callback_url})
    thread = _server.threading.Thread(target=_server._run_chat_job, args=(job_id, resolved_session_id), daemon=True)
    thread.start()
    response_payload = {'jobId': job_id, 'runId': job_id, 'sessionId': resolved_session_id, 'status': 'running'}
    response_payload.update(_server._chat_public_policy_payload())
    if policy is not None:
        response_payload['provider'] = str(policy.get('provider') or response_payload.get('provider') or '')
        response_payload['model'] = str(policy.get('model') or response_payload.get('model') or '')
    self._send_json(_server.HTTPStatus.OK, response_payload)

def _api_post_chat_run_status(self) -> None:
    body = self._expect_object(self._read_json_body(required=True), 'Request body')
    job_id = str(body.get('jobId') or body.get('job_id') or body.get('runId') or body.get('run_id') or '').strip()
    if not job_id:
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'jobId or runId is required')
    job = _server._get_job_snapshot(job_id)
    if job is None:
        raise _server.ApiError(_server.HTTPStatus.NOT_FOUND, 'Unknown jobId')
    if str(job.get('type') or '') != 'chat:run':
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'jobId is not a chat run')
    self._send_json(_server.HTTPStatus.OK, _server._job_response_payload(job))

__all__ = ['_normalize_chat_session_id', '_cleanup_old_chat_sessions', '_chat_session_public_payload', '_chat_create_or_get_session', '_chat_get_session_snapshot', '_chat_append_message', '_chat_start_stt_job', '_chat_get_job_snapshot', '_chat_list_jobs', '_chat_get_job_logs', '_job_callback_url_from_mapping', '_chat_pipeline_state', '_chat_start_compute_job', '_chat_docs_root', '_chat_external_read_roots', '_chat_memory_path', '_chat_onboard_speaker', '_build_workflow_runtime', '_execute_mcp_http_tool', '_run_chat_job', '_api_get_chat_session', '_api_get_mcp_exposure', '_api_get_mcp_tools', '_api_get_mcp_tool', '_api_post_mcp_tool', '_api_post_chat_session', '_api_post_chat_run_start', '_api_post_chat_run_status']

