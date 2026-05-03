"""PARSE server route-domain module: jobs."""
from __future__ import annotations

import server as _server

def _resolve_compute_mode() -> str:
    """Return the active compute mode — 'thread' (default), 'subprocess',
    or 'persistent'.

    Precedence:
      1. ``--compute-mode`` CLI flag (most explicit, survives WSL interop).
      2. ``PARSE_USE_PERSISTENT_WORKER=true`` (shortcut for the 2026-04
         persistent-worker rollout flag).
      3. ``PARSE_COMPUTE_MODE`` env var.
      4. Default ``'thread'`` (legacy behaviour).
    """
    if _server._COMPUTE_MODE_OVERRIDE:
        return _server._COMPUTE_MODE_OVERRIDE.strip().lower() or 'thread'
    if str(_server.os.environ.get('PARSE_USE_PERSISTENT_WORKER', '')).strip().lower() in {'1', 'true', 'yes', 'on'}:
        return 'persistent'
    env = _server.os.environ.get('PARSE_COMPUTE_MODE', '').strip().lower()
    return env or 'thread'


def _job_snapshot_dir(*, create: bool=True) -> _server.pathlib.Path:
    raw_path = str(_server.os.environ.get('PARSE_JOB_SNAPSHOT_DIR') or '').strip()
    workspace_raw = str(_server.os.environ.get('PARSE_WORKSPACE_DIR') or '').strip()
    if raw_path:
        path = _server.pathlib.Path(raw_path).expanduser()
    elif workspace_raw:
        path = _server.pathlib.Path(workspace_raw).expanduser() / '.parse-jobs'
    else:
        path = _server._project_root() / '.parse' / 'jobs'
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print('[JOBS] WARNING: unable to create job snapshot dir {0}: {1}'.format(path, exc), file=_server.sys.stderr, flush=True)
    return path


def _job_snapshot_safe_name(job_id: str) -> str:
    value = str(job_id or '').strip()
    safe = _server.re.sub(r'[^A-Za-z0-9_.-]+', '_', value)
    return safe or 'job'


def _job_snapshot_path(job_id: str) -> _server.pathlib.Path:
    return _server._job_snapshot_dir(create=True) / '{0}.json'.format(_server._job_snapshot_safe_name(job_id))


def _persist_job_snapshot(job_snapshot: _server.Dict[str, _server.Any]) -> None:
    job_id = str(job_snapshot.get('jobId') or '').strip() if isinstance(job_snapshot, dict) else ''
    if not job_id:
        return
    try:
        path = _server._job_snapshot_path(job_id)
        payload = _server.copy.deepcopy(job_snapshot)
        payload['snapshot_version'] = 1
        tmp_path = path.with_name('.{0}.{1}.tmp'.format(path.name, _server.os.getpid()))
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            _server.json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write('\n')
        _server.os.replace(tmp_path, path)
    except Exception as exc:
        print('[JOBS] WARNING: unable to persist job snapshot {0}: {1}'.format(job_id, exc), file=_server.sys.stderr, flush=True)


def _delete_job_snapshot(job_id: str) -> None:
    try:
        _server._job_snapshot_path(job_id).unlink(missing_ok=True)
    except Exception:
        pass


def _coerce_loaded_job_snapshot(raw_job: _server.Any) -> _server.Optional[_server.Dict[str, _server.Any]]:
    if not isinstance(raw_job, dict):
        return None
    job = _server.copy.deepcopy(raw_job)
    job.pop('snapshot_version', None)
    job_id = str(job.get('jobId') or '').strip()
    if not job_id:
        return None
    now_ts = _server.time.time()
    now_iso = _server._utc_iso_from_ts(now_ts)
    job['jobId'] = job_id
    job['type'] = str(job.get('type') or 'unknown')
    job['status'] = str(job.get('status') or 'error').strip().lower() or 'error'
    try:
        job['progress'] = _server._clamp_progress(job.get('progress', 0.0))
    except Exception:
        job['progress'] = 0.0
    for key in ('segmentsProcessed', 'totalSegments'):
        try:
            job[key] = max(0, int(job.get(key, 0) or 0))
        except (TypeError, ValueError):
            job[key] = 0
    if not isinstance(job.get('meta'), dict):
        job['meta'] = {}
    if not isinstance(job.get('logs'), list):
        job['logs'] = []
    if not isinstance(job.get('locks'), dict):
        job['locks'] = _server._empty_job_locks_payload()
    job.setdefault('created_at', now_iso)
    job.setdefault('created_ts', now_ts)
    job.setdefault('updated_at', now_iso)
    job.setdefault('updated_ts', now_ts)
    job.setdefault('completed_at', None)
    job.setdefault('completed_ts', None)
    return job


def _empty_job_locks_payload() -> _server.Dict[str, _server.Any]:
    return {'active': False, 'resources': [], 'heartbeat_at': None, 'heartbeat_ts': None, 'expires_at': None, 'expires_ts': None, 'released_at': None, 'released_ts': None, 'released_reason': None, 'ttl_seconds': _server.JOB_LOCK_TTL_SECONDS}


def _mark_loaded_job_interrupted(job: _server.Dict[str, _server.Any]) -> None:
    now_ts = _server.time.time()
    now_iso = _server._utc_iso_from_ts(now_ts)
    previous_status = str(job.get('status') or 'running')
    job['status'] = 'error'
    job['error'] = 'Server restarted before this job reached a terminal state; the in-flight worker was interrupted. Re-run the job after checking logs and system memory.'
    job['error_code'] = 'server_restarted'
    job['recovered_from_disk'] = True
    job['updated_at'] = now_iso
    job['updated_ts'] = now_ts
    job['completed_at'] = now_iso
    job['completed_ts'] = now_ts
    locks = job.get('locks') if isinstance(job.get('locks'), dict) else _server._empty_job_locks_payload()
    locks['active'] = False
    locks['released_at'] = now_iso
    locks['released_ts'] = now_ts
    locks['released_reason'] = 'server_restarted'
    locks['expires_at'] = None
    locks['expires_ts'] = None
    job['locks'] = locks
    logs = job.get('logs') if isinstance(job.get('logs'), list) else []
    logs.append(_server._job_log_entry(level='error', event='job.recovered_after_restart', message='Recovered non-terminal job snapshot as interrupted after server restart', source='job_snapshot', progress=_server._clamp_progress(job.get('progress', 0.0)), data={'previous_status': previous_status}))
    log_limit = _server._job_log_limit()
    if len(logs) > log_limit:
        del logs[:-log_limit]
    job['logs'] = logs


def _load_job_snapshots() -> int:
    directory = _server._job_snapshot_dir(create=False)
    if not directory.exists():
        return 0
    loaded_jobs: _server.List[_server.Dict[str, _server.Any]] = []
    recovered_job_ids: _server.List[str] = []
    snapshot_entries: _server.List[_server.Tuple[float, _server.pathlib.Path]] = []
    for path in directory.glob('*.json'):
        try:
            snapshot_entries.append((float(path.stat().st_mtime), path))
        except OSError:
            snapshot_entries.append((0.0, path))
    snapshot_entries.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
    for _mtime, stale_path in snapshot_entries[200:]:
        try:
            stale_path.unlink()
        except OSError:
            pass
    for _mtime, path in snapshot_entries[:200]:
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                raw_job = _server.json.load(handle)
        except Exception as exc:
            print('[JOBS] WARNING: unable to read job snapshot {0}: {1}'.format(path, exc), file=_server.sys.stderr, flush=True)
            continue
        job = _server._coerce_loaded_job_snapshot(raw_job)
        if job is None:
            continue
        if str(job.get('status') or '').strip().lower() not in {'complete', 'error'}:
            _server._mark_loaded_job_interrupted(job)
            recovered_job_ids.append(str(job.get('jobId') or ''))
        loaded_jobs.append(job)
    if not loaded_jobs:
        return 0
    with _server._jobs_lock:
        for job in loaded_jobs:
            _server._jobs[str(job.get('jobId'))] = job
    for job in loaded_jobs:
        if str(job.get('jobId') or '') in recovered_job_ids:
            _server._persist_job_snapshot(job)
    return len(loaded_jobs)


def _subprocess_missing_result_message(exit_code: _server.Any, result_path: str) -> str:
    try:
        code_int = int(exit_code)
    except (TypeError, ValueError):
        code_int = 0
    if code_int in {-9, 137}:
        return (
            'Compute subprocess exited code={0} (SIGKILL) without writing result file {1}; '
            'this is OOM-suspect because the OS may have killed the worker under memory pressure.'
        ).format(exit_code, result_path)
    return 'Compute subprocess exited code={0} without writing result file {1}'.format(exit_code, result_path)


def _copy_job_for_snapshot(job: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    return _server.copy.deepcopy(job)


def _launch_compute_runner(job_id: str, compute_type: str, payload: _server.Dict[str, _server.Any]) -> None:
    """Start the backing worker for a compute job.

    Two modes, selected by ``--compute-mode`` CLI flag or
    ``PARSE_COMPUTE_MODE`` env var (CLI wins — env vars don't cross the
    WSL↔Windows python.exe boundary):

    - ``"thread"`` (default) — legacy behaviour. Spawns a
      ``threading.Thread`` that runs ``_run_compute_job`` in the same
      Python process as the HTTP server. Simple, works on Linux
      native, but wedges on Windows python.exe + WSL interop when the
      compute thread touches CUDA (observed 2026-04-23, see
      fix/compute-subprocess-runner).

    - ``"subprocess"`` — spawns a fresh Python process via
      ``multiprocessing.get_context("spawn")``. The child imports
      ``server``, runs the same ``_run_compute_job`` function, and
      writes its result to a temp JSON file. A monitor thread reads
      that file and updates the in-memory ``_jobs`` dict so status
      polls work unchanged. CUDA initialisation happens in the child,
      isolated from the HTTP server's address space — whatever
      threading quirk is causing the wedge can't reach us here. The
      trade-off is startup overhead (~1-3s per job to import + reload
      torch) which is negligible for multi-minute compute jobs.

    Env vars:
        PARSE_COMPUTE_MODE=subprocess — opt in to subprocess mode.
        PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC — hard kill deadline
            (default 4 hours; covers a razhan+wav2vec2 run on a
            multi-hour recording on CPU).
    """
    mode = _server._resolve_compute_mode()
    if mode == 'persistent':
        _server._compute_checkpoint('LAUNCH.persistent', job_id=job_id, compute_type=compute_type)
        _server._launch_compute_persistent(job_id, compute_type, payload)
        return
    if mode == 'subprocess':
        _server._compute_checkpoint('LAUNCH.subprocess', job_id=job_id, compute_type=compute_type)
        _server._launch_compute_subprocess(job_id, compute_type, payload)
        return
    _server._compute_checkpoint('LAUNCH.thread', job_id=job_id, compute_type=compute_type, mode=mode)
    thread = _server.threading.Thread(target=_server._run_compute_job, args=(job_id, compute_type, payload), daemon=True)
    thread.start()

def _launch_compute_subprocess(job_id: str, compute_type: str, payload: _server.Dict[str, _server.Any]) -> None:
    """Spawn a child Python process to run the compute job.

    The child writes its outcome to ``/tmp/parse-compute-<job_id>.json``.
    A local monitor thread reads that file when the child exits and
    promotes the outcome to ``_set_job_complete`` / ``_set_job_error``
    so the existing HTTP status polling keeps working.

    Uses ``get_context("spawn")`` explicitly — on Windows python.exe
    this is the default but we name it so Linux native servers get
    the same isolation guarantees (fork would share torch state
    between parent and child, which is exactly the hazard we're
    trying to escape).
    """
    import multiprocessing
    import tempfile
    import json as _json
    result_path = _server.os.path.join(tempfile.gettempdir(), 'parse-compute-{0}.json'.format(job_id))
    try:
        if _server.os.path.exists(result_path):
            _server.os.remove(result_path)
    except OSError:
        pass
    checkpoint_path = _server._compute_checkpoint_path()
    ctx = multiprocessing.get_context('spawn')
    child = ctx.Process(target=_server._compute_subprocess_entry, name='parse-compute-{0}'.format(compute_type), args=(job_id, compute_type, payload, result_path, checkpoint_path), daemon=True)
    child.start()
    _server._compute_checkpoint('SUBPROCESS.started', job_id=job_id, child_pid=child.pid, result_path=result_path)
    try:
        timeout_raw = _server.os.environ.get('PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC', '14400')
        timeout_sec = max(60.0, float(timeout_raw))
    except ValueError:
        timeout_sec = 14400.0

    def _monitor() -> None:
        child.join(timeout=timeout_sec)
        if child.is_alive():
            _server._compute_checkpoint('SUBPROCESS.timeout', job_id=job_id, pid=child.pid, timeout=timeout_sec)
            try:
                child.terminate()
                child.join(timeout=10.0)
            except Exception:
                pass
            _server._set_job_error(job_id, 'Compute subprocess exceeded PARSE_COMPUTE_SUBPROCESS_TIMEOUT_SEC ({0}s) and was terminated.'.format(int(timeout_sec)))
            return
        exit_code = child.exitcode
        _server._compute_checkpoint('SUBPROCESS.exited', job_id=job_id, exit_code=exit_code)
        if not _server.os.path.exists(result_path):
            _server._set_job_error(job_id, _server._subprocess_missing_result_message(exit_code, result_path))
            return
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                payload_out = _json.load(f)
        except Exception as exc:
            _server._set_job_error(job_id, 'Compute subprocess result file unreadable: {0}'.format(exc))
            return
        finally:
            try:
                _server.os.remove(result_path)
            except OSError:
                pass
        ok = bool(payload_out.get('ok'))
        if ok:
            _server._set_job_complete(job_id, payload_out.get('result'), message='Compute subprocess complete')
        else:
            err = str(payload_out.get('error') or 'Compute subprocess reported failure')
            tb = str(payload_out.get('traceback') or '') or None
            _server._set_job_error(job_id, err, traceback_str=tb)
    monitor = _server.threading.Thread(target=_monitor, name='parse-compute-monitor-{0}'.format(job_id), daemon=True)
    monitor.start()

def _compute_subprocess_entry(job_id: str, compute_type: str, payload: _server.Dict[str, _server.Any], result_path: str, checkpoint_path: str) -> None:
    """Runs in a fresh Python process.

    Imports the server module to reuse every compute function and
    its dependency graph, then writes a JSON outcome to ``result_path``.
    Any import-time / compute-time failure is captured as
    ``{ok: False, error, traceback}``.

    The child writes to the shared ``checkpoint_path`` (same buffer-
    free file the parent uses) so we get a continuous per-stage log
    across process boundaries. Pipe buffering can't hide it — the
    file is append-only + fsync'd per write on both sides.
    """
    import json as _json
    import traceback as _tb
    try:
        child_stderr = open('/tmp/parse-compute-{0}.stderr.log'.format(job_id), 'w', encoding='utf-8')
        _server.sys.stderr = child_stderr
    except Exception:
        pass
    _server.os.environ['PARSE_COMPUTE_CHECKPOINT_LOG'] = checkpoint_path
    outcome: _server.Dict[str, _server.Any] = {'ok': False}
    try:
        _server._compute_checkpoint('CHILD.entry', job_id=job_id, compute_type=compute_type)
        normalized_type = str(compute_type or '').strip().lower()
        if normalized_type in {'cognates', 'similarity'}:
            result = _server._compute_cognates('child-{0}'.format(job_id), payload)
        elif normalized_type == 'contact-lexemes':
            result = _server._compute_contact_lexemes('child-{0}'.format(job_id), payload)
        elif normalized_type in {'ipa_only', 'ipa-only', 'ipa'}:
            result = _server._compute_speaker_ipa('child-{0}'.format(job_id), payload)
        elif normalized_type in {'ortho', 'ortho_only', 'ortho-only'}:
            result = _server._compute_speaker_ortho('child-{0}'.format(job_id), payload)
        elif normalized_type in {'forced_align', 'forced-align', 'align'}:
            result = _server._compute_speaker_forced_align('child-{0}'.format(job_id), payload)
        elif normalized_type in {'boundaries', 'bnd', 'ortho_words', 'ortho-words'}:
            result = _server._compute_speaker_boundaries('child-{0}'.format(job_id), payload)
        elif normalized_type in {'full_pipeline', 'full-pipeline', 'pipeline'}:
            result = _server._compute_full_pipeline('child-{0}'.format(job_id), payload)
        elif normalized_type in {'train_ipa_model', 'train-ipa-model', 'train_ipa'}:
            result = _server._compute_training_job('child-{0}'.format(job_id), payload)
        elif normalized_type == 'stt':
            result = _server._compute_stt('child-{0}'.format(job_id), payload)
        elif normalized_type in {
            'retranscribe_with_boundaries',
            'retranscribe-with-boundaries',
            'boundary_constrained_stt',
            'boundary-constrained-stt',
            'bnd_stt',
        }:
            result = _server._compute_speaker_retranscribe_with_boundaries('child-{0}'.format(job_id), payload)
        elif normalized_type in {'offset_detect', 'offset-detect'}:
            result = _server._compute_offset_detect('child-{0}'.format(job_id), payload)
        elif normalized_type in {'offset_detect_from_pair', 'offset-detect-from-pair'}:
            result = _server._compute_offset_detect_from_pair('child-{0}'.format(job_id), payload)
        else:
            raise RuntimeError('Unsupported compute type: {0}'.format(normalized_type))
        _server._compute_checkpoint('CHILD.ok', job_id=job_id)
        outcome = {'ok': True, 'result': result}
    except Exception as exc:
        _server._compute_checkpoint('CHILD.exc', job_id=job_id, exc_type=type(exc).__name__, exc=str(exc)[:200])
        outcome = {'ok': False, 'error': str(exc), 'traceback': _tb.format_exc()}
    try:
        with open(result_path, 'w', encoding='utf-8') as f:
            _json.dump(outcome, f, ensure_ascii=False, default=str)
    except Exception as exc:
        _server._compute_checkpoint('CHILD.result_write_failed', job_id=job_id, exc=str(exc)[:200])

def _launch_compute_persistent(job_id: str, compute_type: str, payload: _server.Dict[str, _server.Any]) -> None:
    handle = _server._PERSISTENT_WORKER_HANDLE
    if handle is None or not handle.is_alive():
        _server._set_job_error(job_id, 'Persistent compute worker is not running. Restart the server.')
        return
    handle.submit(job_id, compute_type, payload)

def _cleanup_old_jobs() -> None:
    now_ts = _server.time.time()
    stale_ids: _server.List[str] = []
    with _server._jobs_lock:
        for job_id, job in _server._jobs.items():
            if job.get('status') not in {'complete', 'error'}:
                continue
            completed_ts = job.get('completed_ts')
            if not isinstance(completed_ts, (int, float)):
                continue
            if now_ts - float(completed_ts) > _server.JOB_RETENTION_SECONDS:
                stale_ids.append(job_id)
        for job_id in stale_ids:
            _server._jobs.pop(job_id, None)
    for job_id in stale_ids:
        _server._delete_job_snapshot(job_id)

def _job_log_limit() -> int:
    raw = str(_server.os.environ.get('PARSE_JOB_LOG_MAX_ENTRIES') or '').strip()
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = _server.JOB_LOG_MAX_ENTRIES
        return max(10, min(parsed, 1000))
    return _server.JOB_LOG_MAX_ENTRIES

def _infer_job_error_code(error_message: _server.Any) -> str:
    text = str(error_message or '').strip().lower()
    if not text:
        return 'job_failed'
    if 'server restarted before this job reached a terminal state' in text:
        return 'server_restarted'
    if 'oom' in text or 'out of memory' in text or 'insufficient host memory' in text or 'sigkill' in text or 'exit code=-9' in text or 'exit code 137' in text or 'code=137' in text:
        return 'oom_suspect'
    if 'unknown jobid' in text or 'unknown job_id' in text:
        return 'job_not_found'
    if 'not a' in text and 'job' in text:
        return 'invalid_job_type'
    if 'timeout' in text:
        return 'timeout'
    if 'ffmpeg' in text:
        return 'ffmpeg_failed'
    if 'provider init failed' in text or 'loading model' in text:
        return 'model_init_failed'
    if 'cuda' in text or 'cublas' in text:
        return 'cuda_runtime_error'
    if 'validation' in text or 'required' in text:
        return 'validation_error'
    return 'job_failed'

def _job_log_entry(*, level: str, event: str, message: str, source: str='job_registry', progress: _server.Optional[float]=None, data: _server.Optional[_server.Dict[str, _server.Any]]=None) -> _server.Dict[str, _server.Any]:
    entry: _server.Dict[str, _server.Any] = {'ts': _server._utc_now_iso(), 'level': str(level or 'info'), 'event': str(event or 'job.event'), 'message': str(message or ''), 'source': str(source or 'job_registry')}
    if progress is not None:
        entry['progress'] = _server._clamp_progress(progress)
    if isinstance(data, dict) and data:
        entry['data'] = _server.copy.deepcopy(data)
    return entry

def _append_job_log_locked(job: _server.Dict[str, _server.Any], *, level: str, event: str, message: str, source: str='server', progress: _server.Optional[float]=None, data: _server.Optional[_server.Dict[str, _server.Any]]=None) -> None:
    logs = job.get('logs')
    if not isinstance(logs, list):
        logs = []
        job['logs'] = logs
    entry = _server._job_log_entry(level=level, event=event, message=message, source=source, progress=progress, data=data)
    logs.append(entry)
    log_limit = _server._job_log_limit()
    if len(logs) > log_limit:
        del logs[:-log_limit]
    job_id = str(job.get('jobId') or '').strip()
    job_type = str(job.get('type') or '').strip()
    if job_id and job_type:
        _server._publish_job_stream_event('job.log', job_id=job_id, job_type=job_type, payload=entry)

def _job_lock_resources(job_type: str, metadata: _server.Optional[_server.Dict[str, _server.Any]]) -> _server.List[_server.Dict[str, str]]:
    meta = metadata if isinstance(metadata, dict) else {}
    speaker = str(meta.get('speaker') or '').strip()
    if not speaker:
        return []
    normalized_job_type = str(job_type or '').strip().lower()
    if normalized_job_type in _server._MUTATING_SPEAKER_JOB_TYPES:
        return [{'kind': 'speaker', 'id': speaker}]
    if normalized_job_type.startswith('compute:'):
        compute_type = str(meta.get('computeType') or normalized_job_type.split(':', 1)[1] or '').strip().lower()
        if compute_type in _server._MUTATING_SPEAKER_COMPUTE_TYPES:
            return [{'kind': 'speaker', 'id': speaker}]
    return []

def _expire_job_locks_locked(job: _server.Dict[str, _server.Any], now_ts: float, *, reason: str='ttl_expired') -> None:
    locks = job.get('locks')
    if not isinstance(locks, dict) or not locks.get('active'):
        return
    locks['active'] = False
    locks['expires_at'] = None
    locks['expires_ts'] = None
    locks['released_at'] = _server._utc_iso_from_ts(now_ts)
    locks['released_ts'] = now_ts
    locks['released_reason'] = reason

def _find_job_resource_conflict_locked(resources: _server.Sequence[_server.Dict[str, str]], *, now_ts: float) -> _server.Optional[_server.Tuple[_server.Dict[str, _server.Any], _server.Dict[str, str]]]:
    wanted = {(str(resource.get('kind') or '').strip(), str(resource.get('id') or '').strip()) for resource in resources if str(resource.get('kind') or '').strip() and str(resource.get('id') or '').strip()}
    if not wanted:
        return None
    for job in _server._jobs.values():
        if str(job.get('status') or '').strip().lower() not in {'queued', 'running'}:
            continue
        locks = job.get('locks')
        if not isinstance(locks, dict) or not locks.get('active'):
            continue
        try:
            expires_ts = float(locks.get('expires_ts') or 0.0)
        except (TypeError, ValueError):
            expires_ts = 0.0
        if expires_ts and expires_ts <= now_ts:
            _server._expire_job_locks_locked(job, now_ts)
            continue
        for resource in locks.get('resources') or []:
            resource_kind = str(resource.get('kind') or '').strip()
            resource_id = str(resource.get('id') or '').strip()
            if (resource_kind, resource_id) in wanted:
                return (job, {'kind': resource_kind, 'id': resource_id})
    return None

def _refresh_job_locks_locked(job: _server.Dict[str, _server.Any], now_ts: float) -> None:
    locks = job.get('locks')
    if not isinstance(locks, dict) or not locks.get('active'):
        return
    ttl_seconds = max(1, int(locks.get('ttl_seconds') or _server.JOB_LOCK_TTL_SECONDS))
    locks['heartbeat_at'] = _server._utc_iso_from_ts(now_ts)
    locks['heartbeat_ts'] = now_ts
    locks['expires_at'] = _server._utc_iso_from_ts(now_ts + ttl_seconds)
    locks['expires_ts'] = now_ts + ttl_seconds

def _release_job_locks_locked(job: _server.Dict[str, _server.Any], now_ts: float) -> None:
    locks = job.get('locks')
    if not isinstance(locks, dict) or not locks.get('active'):
        return
    resources = _server.copy.deepcopy(locks.get('resources') or [])
    locks['active'] = False
    locks['expires_at'] = None
    locks['expires_ts'] = None
    locks['released_at'] = _server._utc_iso_from_ts(now_ts)
    locks['released_ts'] = now_ts
    locks['released_reason'] = 'job_finished'
    if resources:
        _server._append_job_log_locked(job, level='info', event='job.lock_released', message='Released job resource lock', progress=_server._clamp_progress(job.get('progress', 0.0)), data={'resources': resources})

def _job_locks_payload(locks: _server.Any) -> _server.Dict[str, _server.Any]:
    locks_dict = locks if isinstance(locks, dict) else {}
    resources = locks_dict.get('resources') if isinstance(locks_dict.get('resources'), list) else []
    return {'active': bool(locks_dict.get('active')), 'resources': _server.copy.deepcopy(resources), 'heartbeat_at': locks_dict.get('heartbeat_at'), 'expires_at': locks_dict.get('expires_at'), 'released_at': locks_dict.get('released_at'), 'released_reason': locks_dict.get('released_reason'), 'ttl_seconds': int(locks_dict.get('ttl_seconds') or _server.JOB_LOCK_TTL_SECONDS)}

def _normalize_job_callback_url(raw_value: _server.Any) -> _server.Optional[str]:
    value = str(raw_value or '').strip()
    if not value:
        return None
    parsed = _server.urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('callbackUrl must be an absolute http(s) URL')
    return value

def _job_callback_payload(job: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    payload = _server._job_detail_payload(job, include_logs=False)
    payload['event'] = 'job.{0}'.format(str(job.get('status') or 'unknown'))
    return payload

def _post_job_callback(callback_url: str, payload: _server.Dict[str, _server.Any]) -> None:
    body = _server.json.dumps(payload).encode('utf-8')
    request = _server.Request(callback_url, data=body, headers={'Content-Type': 'application/json', 'User-Agent': 'PARSE-Job-Callback/1.0'}, method='POST')
    with _server.urlopen(request, timeout=10.0) as response:
        response.read()

def _dispatch_job_callback(job_snapshot: _server.Dict[str, _server.Any]) -> None:
    meta = job_snapshot.get('meta') if isinstance(job_snapshot.get('meta'), dict) else {}
    callback_url = str(meta.get('callbackUrl') or '').strip()
    if not callback_url:
        return
    try:
        _server._post_job_callback(callback_url, _server._job_callback_payload(job_snapshot))
    except Exception as exc:
        job_id = str(job_snapshot.get('jobId') or '')
        with _server._jobs_lock:
            live_job = _server._jobs.get(job_id)
            if live_job is not None:
                _server._append_job_log_locked(live_job, level='error', event='job.callback_failed', message='Callback delivery failed: {0}'.format(exc), progress=_server._clamp_progress(live_job.get('progress', 0.0)), data={'callbackUrl': callback_url})

def _dispatch_job_callback_async(job_snapshot: _server.Dict[str, _server.Any]) -> None:
    meta = job_snapshot.get('meta') if isinstance(job_snapshot.get('meta'), dict) else {}
    callback_url = str(meta.get('callbackUrl') or '').strip()
    if not callback_url:
        return
    thread = _server.threading.Thread(target=_server._dispatch_job_callback, args=(_server.copy.deepcopy(job_snapshot),), daemon=True)
    thread.start()

def _create_job(job_type: str, metadata: _server.Optional[_server.Dict[str, _server.Any]]=None, *, initial_status: str='running') -> str:
    _server._cleanup_old_jobs()
    job_id = str(_server.uuid.uuid4())
    now_ts = _server.time.time()
    now_iso = _server._utc_now_iso()
    normalized_status = str(initial_status or 'running').strip().lower() or 'running'
    if normalized_status not in {'queued', 'running'}:
        normalized_status = 'running'
    resources = _server._job_lock_resources(job_type, metadata)
    with _server._jobs_lock:
        conflict = _server._find_job_resource_conflict_locked(resources, now_ts=now_ts)
        if conflict is not None:
            holder_job, resource = conflict
            raise _server.JobResourceConflictError(resource_kind=str(resource.get('kind') or 'resource'), resource_id=str(resource.get('id') or ''), holder_job_id=str(holder_job.get('jobId') or ''), holder_job_type=str(holder_job.get('type') or 'unknown'), holder_status=str(holder_job.get('status') or 'running'))
        locks_payload = {'active': bool(resources), 'resources': _server.copy.deepcopy(resources), 'heartbeat_at': None, 'heartbeat_ts': None, 'expires_at': None, 'expires_ts': None, 'released_at': None, 'released_ts': None, 'released_reason': None, 'ttl_seconds': _server.JOB_LOCK_TTL_SECONDS}
        if resources:
            locks_payload['heartbeat_at'] = now_iso
            locks_payload['heartbeat_ts'] = now_ts
            locks_payload['expires_at'] = _server._utc_iso_from_ts(now_ts + _server.JOB_LOCK_TTL_SECONDS)
            locks_payload['expires_ts'] = now_ts + _server.JOB_LOCK_TTL_SECONDS
        job: _server.Dict[str, _server.Any] = {'jobId': job_id, 'type': str(job_type), 'status': normalized_status, 'progress': 0.0, 'result': None, 'error': None, 'error_code': None, 'message': None, 'segmentsProcessed': 0, 'totalSegments': 0, 'created_at': now_iso, 'updated_at': now_iso, 'completed_at': None, 'created_ts': now_ts, 'updated_ts': now_ts, 'completed_ts': None, 'meta': _server.copy.deepcopy(metadata or {}), 'locks': locks_payload, 'logs': []}
        _server._append_job_log_locked(job, level='info', event='job.queued' if normalized_status == 'queued' else 'job.created', message='Job queued' if normalized_status == 'queued' else 'Job created', progress=0.0, data={'jobId': job_id, 'type': str(job_type), 'meta': _server.copy.deepcopy(metadata or {})})
        if resources:
            _server._append_job_log_locked(job, level='info', event='job.lock_acquired', message='Acquired job resource lock', progress=0.0, data={'resources': _server.copy.deepcopy(resources)})
        _server._jobs[job_id] = job
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    _server._persist_job_snapshot(snapshot_to_persist)
    return job_id

def _tail_log_file(path: str, max_lines: int=200, max_bytes: int=256 * 1024) -> _server.Optional[str]:
    """Return the last ``max_lines`` lines of ``path``, capped at ``max_bytes``.

    Best-effort: returns None if the file is missing, unreadable, or empty.
    Used by ``_api_get_job_logs`` to surface worker stderr tails without
    pulling the whole file. Bytes cap protects against a multi-MB log
    ending up in a JSON response body.
    """
    try:
        with open(path, 'rb') as fh:
            try:
                fh.seek(0, _server.os.SEEK_END)
                size = fh.tell()
            except OSError:
                size = 0
            if size <= 0:
                return None
            start = max(0, size - max_bytes)
            fh.seek(start)
            chunk = fh.read()
    except (OSError, FileNotFoundError):
        return None
    if not chunk:
        return None
    text = chunk.decode('utf-8', errors='replace')
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return '\n'.join(lines) if lines else None

def _set_job_running(job_id: str, message: _server.Optional[str]=None) -> None:
    stream_payload: _server.Optional[_server.Dict[str, _server.Any]] = None
    snapshot_to_persist: _server.Optional[_server.Dict[str, _server.Any]] = None
    job_type = ''
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if job is None:
            return
        if str(job.get('status') or '') == 'running':
            return
        now_ts = _server.time.time()
        job['status'] = 'running'
        if job.get('recovered_from_disk'):
            job['recovered_from_disk'] = False
        job['updated_at'] = _server._utc_iso_from_ts(now_ts)
        job['updated_ts'] = now_ts
        _server._refresh_job_locks_locked(job, now_ts)
        if message is not None:
            job['message'] = str(message)
        _server._append_job_log_locked(job, level='info', event='job.started', message=str(job.get('message') or message or 'Job started'), progress=_server._clamp_progress(job.get('progress', 0.0)))
        job_type = str(job.get('type') or '')
        stream_payload = _server._job_response_payload(job)
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    if snapshot_to_persist is not None:
        _server._persist_job_snapshot(snapshot_to_persist)
    if stream_payload is not None and job_type:
        _server._publish_job_stream_event('job.progress', job_id=job_id, job_type=job_type, payload=stream_payload)

def _set_job_progress(job_id: str, progress: float, message: _server.Optional[str]=None, segments_processed: _server.Optional[int]=None, total_segments: _server.Optional[int]=None) -> None:
    stream_payload: _server.Optional[_server.Dict[str, _server.Any]] = None
    snapshot_to_persist: _server.Optional[_server.Dict[str, _server.Any]] = None
    job_type = ''
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if job is None or job.get('status') != 'running':
            return
        now_ts = _server.time.time()
        previous_message = str(job.get('message') or '')
        previous_progress = _server._clamp_progress(job.get('progress', 0.0))
        current_progress = _server._clamp_progress(progress)
        job['progress'] = current_progress
        job['updated_at'] = _server._utc_iso_from_ts(now_ts)
        job['updated_ts'] = now_ts
        _server._refresh_job_locks_locked(job, now_ts)
        if message is not None:
            job['message'] = str(message)
        if segments_processed is not None:
            try:
                job['segmentsProcessed'] = max(0, int(segments_processed))
            except (TypeError, ValueError):
                job['segmentsProcessed'] = 0
        if total_segments is not None:
            try:
                job['totalSegments'] = max(0, int(total_segments))
            except (TypeError, ValueError):
                job['totalSegments'] = 0
        current_message = str(job.get('message') or '')
        if current_message and current_message != previous_message:
            _server._append_job_log_locked(job, level='info', event='job.progress', message=current_message, progress=current_progress, data={'segmentsProcessed': int(job.get('segmentsProcessed', 0) or 0), 'totalSegments': int(job.get('totalSegments', 0) or 0)})
        elif current_progress != previous_progress and abs(current_progress - previous_progress) >= 25.0:
            _server._append_job_log_locked(job, level='info', event='job.progress', message='Progress updated', progress=current_progress)
        job_type = str(job.get('type') or '')
        stream_payload = _server._job_response_payload(job)
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    if snapshot_to_persist is not None:
        _server._persist_job_snapshot(snapshot_to_persist)
    if stream_payload is not None and job_type:
        _server._publish_job_stream_event('job.progress', job_id=job_id, job_type=job_type, payload=stream_payload)

def _set_job_complete(job_id: str, result: _server.Any, message: _server.Optional[str]=None, segments_processed: _server.Optional[int]=None, total_segments: _server.Optional[int]=None) -> None:
    callback_snapshot: _server.Optional[_server.Dict[str, _server.Any]] = None
    stream_payload: _server.Optional[_server.Dict[str, _server.Any]] = None
    snapshot_to_persist: _server.Optional[_server.Dict[str, _server.Any]] = None
    job_type = ''
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if job is None:
            return
        now_ts = _server.time.time()
        now_iso = _server._utc_iso_from_ts(now_ts)
        job['status'] = 'complete'
        job['progress'] = 100.0
        job['result'] = _server.copy.deepcopy(result)
        job['error'] = None
        job['error_code'] = None
        job['updated_at'] = now_iso
        job['updated_ts'] = now_ts
        job['completed_at'] = now_iso
        job['completed_ts'] = now_ts
        if message is not None:
            job['message'] = str(message)
        if segments_processed is not None:
            try:
                job['segmentsProcessed'] = max(0, int(segments_processed))
            except (TypeError, ValueError):
                pass
        if total_segments is not None:
            try:
                job['totalSegments'] = max(0, int(total_segments))
            except (TypeError, ValueError):
                pass
        _server._release_job_locks_locked(job, now_ts)
        _server._append_job_log_locked(job, level='info', event='job.completed', message=str(job.get('message') or 'Job complete'), progress=100.0)
        callback_snapshot = _server.copy.deepcopy(job)
        job_type = str(job.get('type') or '')
        stream_payload = _server._job_response_payload(job)
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    if snapshot_to_persist is not None:
        _server._persist_job_snapshot(snapshot_to_persist)
    if stream_payload is not None and job_type:
        _server._publish_job_stream_event('job.complete', job_id=job_id, job_type=job_type, payload=stream_payload)
    if callback_snapshot is not None:
        _server._dispatch_job_callback_async(callback_snapshot)

def _set_job_error(job_id: str, error_message: str, traceback_str: _server.Optional[str]=None, *, error_code: _server.Optional[str]=None, details: _server.Optional[_server.Dict[str, _server.Any]]=None) -> None:
    """Mark a job as errored. ``traceback_str`` is stored separately from
    the short error message so the UI's crash-log modal can render the
    one-line reason on top and the full Python traceback below without
    having to split-on-newline."""
    callback_snapshot: _server.Optional[_server.Dict[str, _server.Any]] = None
    stream_payload: _server.Optional[_server.Dict[str, _server.Any]] = None
    snapshot_to_persist: _server.Optional[_server.Dict[str, _server.Any]] = None
    job_type = ''
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if job is None:
            return
        now_ts = _server.time.time()
        now_iso = _server._utc_iso_from_ts(now_ts)
        job['status'] = 'error'
        job['error'] = str(error_message)
        if traceback_str:
            job['traceback'] = str(traceback_str)
        job['error_code'] = str(error_code) if error_code else _server._infer_job_error_code(error_message)
        if isinstance(details, dict):
            for key in ('mem_available_gb', 'required_gb', 'swap_total_gb'):
                if key not in details or details.get(key) is None:
                    continue
                try:
                    job[key] = float(details.get(key))
                except (TypeError, ValueError):
                    continue
        job['updated_at'] = now_iso
        job['updated_ts'] = now_ts
        job['completed_at'] = now_iso
        job['completed_ts'] = now_ts
        _server._release_job_locks_locked(job, now_ts)
        _server._append_job_log_locked(job, level='error', event='job.failed', message=str(error_message), progress=_server._clamp_progress(job.get('progress', 0.0)))
        callback_snapshot = _server.copy.deepcopy(job)
        job_type = str(job.get('type') or '')
        stream_payload = _server._job_response_payload(job)
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    if snapshot_to_persist is not None:
        _server._persist_job_snapshot(snapshot_to_persist)
    if stream_payload is not None and job_type:
        _server._publish_job_stream_event('job.error', job_id=job_id, job_type=job_type, payload=stream_payload)
    if callback_snapshot is not None:
        _server._dispatch_job_callback_async(callback_snapshot)

def _get_job_snapshot(job_id: str) -> _server.Optional[_server.Dict[str, _server.Any]]:
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if job is None:
            return None
        return _server.copy.deepcopy(job)

def _job_logs_payload(job: _server.Dict[str, _server.Any], *, offset: int=0, limit: int=_server.JOB_LOG_MAX_ENTRIES) -> _server.Dict[str, _server.Any]:
    logs = job.get('logs') if isinstance(job.get('logs'), list) else []
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(int(limit or _server._job_log_limit()), _server._job_log_limit()))
    sliced = _server.copy.deepcopy(logs[safe_offset:safe_offset + safe_limit])
    return {'jobId': str(job.get('jobId') or ''), 'count': len(logs), 'offset': safe_offset, 'limit': safe_limit, 'logs': sliced}

def _job_detail_payload(job: _server.Dict[str, _server.Any], *, include_logs: bool=False) -> _server.Dict[str, _server.Any]:
    payload = _server._job_response_payload(job)
    payload['createdAt'] = job.get('created_at')
    payload['updatedAt'] = job.get('updated_at')
    payload['completedAt'] = job.get('completed_at')
    payload['meta'] = _server.copy.deepcopy(job.get('meta') if isinstance(job.get('meta'), dict) else {})
    payload['locks'] = _server._job_locks_payload(job.get('locks'))
    logs = job.get('logs') if isinstance(job.get('logs'), list) else []
    payload['logCount'] = len(logs)
    if include_logs:
        payload['logs'] = _server.copy.deepcopy(logs)
    return payload

def _list_jobs_snapshots(*, statuses: _server.Optional[_server.Sequence[str]]=None, job_types: _server.Optional[_server.Sequence[str]]=None, speaker: _server.Optional[str]=None, limit: int=100) -> _server.List[_server.Dict[str, _server.Any]]:
    normalized_statuses = {str(value or '').strip().lower() for value in statuses or [] if str(value or '').strip()}
    normalized_types = {str(value or '').strip() for value in job_types or [] if str(value or '').strip()}
    speaker_filter = str(speaker or '').strip()
    safe_limit = max(1, min(int(limit or 100), 500))
    rows: _server.List[_server.Dict[str, _server.Any]] = []
    with _server._jobs_lock:
        jobs_sorted = sorted(_server._jobs.values(), key=lambda item: float(item.get('created_ts') or 0.0), reverse=True)
        for job in jobs_sorted:
            job_status = str(job.get('status') or '').strip().lower()
            if normalized_statuses and job_status not in normalized_statuses:
                continue
            job_type = str(job.get('type') or '').strip()
            if normalized_types and job_type not in normalized_types:
                continue
            meta = job.get('meta') if isinstance(job.get('meta'), dict) else {}
            if speaker_filter and str(meta.get('speaker') or '').strip() != speaker_filter:
                continue
            rows.append(_server._job_detail_payload(job))
            if len(rows) >= safe_limit:
                break
    return rows

def _job_response_payload(job: _server.Dict[str, _server.Any]) -> _server.Dict[str, _server.Any]:
    status = str(job.get('status') or 'error')
    job_id = str(job.get('jobId') or '')
    payload: _server.Dict[str, _server.Any] = {'jobId': job_id, 'status': status, 'progress': _server._clamp_progress(job.get('progress', 0.0)), 'result': job.get('result')}
    job_type = str(job.get('type') or '')
    if job_type:
        payload['type'] = job_type
    meta = job.get('meta') if isinstance(job.get('meta'), dict) else {}
    if isinstance(meta, dict):
        session_id = str(meta.get('sessionId') or '').strip()
        if session_id:
            payload['sessionId'] = session_id
    if job.get('message'):
        payload['message'] = job.get('message')
    if job.get('error'):
        payload['error'] = str(job.get('error'))
    if job.get('traceback'):
        payload['traceback'] = str(job.get('traceback'))
    payload['segmentsProcessed'] = int(job.get('segmentsProcessed', 0) or 0)
    payload['totalSegments'] = int(job.get('totalSegments', 0) or 0)
    payload['locks'] = _server._job_locks_payload(job.get('locks'))
    if job.get('error_code'):
        payload['errorCode'] = str(job.get('error_code'))
    for detail_key in ('mem_available_gb', 'required_gb', 'swap_total_gb'):
        if detail_key in job:
            payload[detail_key] = job.get(detail_key)
    if job.get('recovered_from_disk') is True:
        payload['recovered_from_disk'] = True
    if job_type == 'chat:run':
        payload['runId'] = job_id
        payload.update(_server._chat_public_policy_payload())
    done = status in {'complete', 'error'}
    payload['done'] = done
    payload['success'] = status == 'complete'
    return payload

def _list_active_jobs_snapshots() -> _server.List[_server.Dict[str, _server.Any]]:
    """Return public snapshots for all currently-running jobs.

    Used by the frontend on page load to rehydrate in-flight progress bars
    (STT, normalize, IPA, etc.) after a reload — backend threads outlive the
    browser, so the job is still running; the UI just lost its ``job_id``.
    """
    results: _server.List[_server.Dict[str, _server.Any]] = []
    with _server._jobs_lock:
        for job in _server._jobs.values():
            if job.get('status') != 'running':
                continue
            payload = _server._job_response_payload(job)
            meta = job.get('meta') if isinstance(job.get('meta'), dict) else {}
            if isinstance(meta, dict) and meta:
                speaker = meta.get('speaker')
                if isinstance(speaker, str) and speaker.strip():
                    payload['speaker'] = speaker.strip()
                language = meta.get('language')
                if isinstance(language, str) and language.strip():
                    payload['language'] = language.strip()
            results.append(payload)
    return results

def _reset_job_to_running(job_id: str) -> None:
    """Clear terminal-state flags on a job so later pipeline steps can report progress.

    ``_run_normalize_job`` and ``_run_stt_job`` are designed as one-shot background
    workers that call ``_set_job_complete`` on success. When we call them inline
    from the full-pipeline sequencer we need to undo that so the outer job stays
    in a ``running`` state for the next step.
    """
    snapshot_to_persist: _server.Optional[_server.Dict[str, _server.Any]] = None
    with _server._jobs_lock:
        job = _server._jobs.get(job_id)
        if not isinstance(job, dict):
            return
        job['status'] = 'running'
        job['result'] = None
        job['error'] = None
        job['error_code'] = None
        job.pop('traceback', None)
        job['completed_at'] = None
        job['completed_ts'] = None
        job['updated_at'] = _server._utc_now_iso()
        job['updated_ts'] = _server.time.time()
        snapshot_to_persist = _server._copy_job_for_snapshot(job)
    if snapshot_to_persist is not None:
        _server._persist_job_snapshot(snapshot_to_persist)

def _run_compute_job(job_id: str, compute_type: str, payload: _server.Dict[str, _server.Any]) -> None:
    _server._compute_checkpoint('COMPUTE.entry', job_id=job_id, compute_type=compute_type)
    print('[COMPUTE] _run_compute_job entry job_id={0} compute_type={1} payload={2}'.format(job_id, compute_type, payload), file=_server.sys.stderr, flush=True)
    try:
        normalized_type = str(compute_type or '').strip().lower()
        _server._set_job_progress(job_id, 5.0, message='Starting compute job')
        _server._compute_checkpoint('COMPUTE.dispatch', job_id=job_id, normalized=normalized_type)
        print('[COMPUTE] dispatching normalized_type={0}'.format(normalized_type), file=_server.sys.stderr, flush=True)
        if normalized_type in {'cognates', 'similarity'}:
            result = _server._compute_cognates(job_id, payload)
        elif normalized_type == 'contact-lexemes':
            result = _server._compute_contact_lexemes(job_id, payload)
        elif normalized_type in {'ipa_only', 'ipa-only', 'ipa'}:
            result = _server._compute_speaker_ipa(job_id, payload)
        elif normalized_type in {'ortho', 'ortho_only', 'ortho-only'}:
            result = _server._compute_speaker_ortho(job_id, payload)
        elif normalized_type in {'forced_align', 'forced-align', 'align'}:
            result = _server._compute_speaker_forced_align(job_id, payload)
        elif normalized_type in {'boundaries', 'bnd', 'ortho_words', 'ortho-words'}:
            result = _server._compute_speaker_boundaries(job_id, payload)
        elif normalized_type in {'full_pipeline', 'full-pipeline', 'pipeline'}:
            result = _server._compute_full_pipeline(job_id, payload)
        elif normalized_type in {'train_ipa_model', 'train-ipa-model', 'train_ipa'}:
            result = _server._compute_training_job(job_id, payload)
        elif normalized_type == 'stt':
            result = _server._compute_stt(job_id, payload)
        elif normalized_type in {
            'retranscribe_with_boundaries',
            'retranscribe-with-boundaries',
            'boundary_constrained_stt',
            'boundary-constrained-stt',
            'bnd_stt',
        }:
            result = _server._compute_speaker_retranscribe_with_boundaries(job_id, payload)
        elif normalized_type in {'offset_detect', 'offset-detect'}:
            result = _server._compute_offset_detect(job_id, payload)
        elif normalized_type in {'offset_detect_from_pair', 'offset-detect-from-pair'}:
            result = _server._compute_offset_detect_from_pair(job_id, payload)
        else:
            raise RuntimeError('Unsupported compute type: {0}'.format(normalized_type))
        _server._set_job_complete(job_id, result, message='Compute complete')
    except Exception as exc:
        _server._set_job_error(
            job_id,
            str(exc),
            error_code=getattr(exc, 'error_code', None),
            details=getattr(exc, 'details', None),
        )

def _api_get_jobs(self) -> None:
    try:
        response = _server._app_build_jobs_response(self.path, list_jobs_snapshots=_server._list_jobs_snapshots)
    except _server._app_JobObservabilityHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message)
    self._send_json(response.status, response.payload)

def _api_get_job(self, job_id_part: str) -> None:
    try:
        response = _server._app_build_job_detail_response(job_id_part, get_job_snapshot=_server._get_job_snapshot, job_detail_payload=_server._job_detail_payload)
    except _server._app_JobObservabilityHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message)
    self._send_json(response.status, response.payload)

def _api_get_job_logs(self, job_id_part: str) -> None:
    try:
        response = _server._app_build_job_logs_response(job_id_part, self.path, get_job_snapshot=_server._get_job_snapshot, job_logs_payload=_server._job_logs_payload, job_log_limit=_server._job_log_limit, job_log_max_entries=_server.JOB_LOG_MAX_ENTRIES)
    except _server._app_JobObservabilityHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message)
    self._send_json(response.status, response.payload)

def _api_get_jobs_active(self) -> None:
    """Return a list of currently-running jobs so the UI can rehydrate
    progress after a page reload. See ``_list_active_jobs_snapshots``."""
    response = _server._app_build_jobs_active_response(list_active_jobs_snapshots=_server._list_active_jobs_snapshots)
    self._send_json(response.status, response.payload)

def _api_get_job_error_logs(self, job_id: str) -> None:
    """Return the error, traceback, and tail of any stderr log files
    associated with a job. Powers the UI's "View crash log" modal.

    Reads from two places:
      1. The in-memory job record — ``error`` (short reason) and
         ``traceback`` (full Python traceback), when the job failed.
      2. The per-job stderr log written by ``_compute_subprocess_entry``
         at ``/tmp/parse-compute-<job_id>.stderr.log`` and the shared
         persistent-worker log at ``/tmp/parse-compute-worker.stderr.log``.
         Only the last ~200 lines of each are returned so a runaway
         log doesn't bloat the response.

    Response shape: ``{jobId, status, type, error?, traceback?,
    message?, stderrLog?, workerStderrLog?}``. All log fields are
    omitted when unavailable — the UI renders whatever is present.
    """
    try:
        response = _server._app_build_job_error_logs_response(job_id, get_job_snapshot=_server._get_job_snapshot, tail_log_file=_server._tail_log_file)
    except _server._app_JobObservabilityHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message)
    self._send_json(response.status, response.payload)

def _api_get_worker_status(self) -> None:
    """Health check for the persistent compute worker.

    Returns 200 with ``{mode, alive, pid, jobs_in_flight}`` when the
    worker is healthy (persistent mode + process alive) or when
    persistent mode is not active (thread/subprocess modes always
    report ``alive: null`` since there is no long-lived worker to
    probe). Returns 503 when persistent mode is active but the
    worker has exited — suitable for an external monitor (PM2,
    uptime-robot, Grafana) to trigger a restart.
    """
    response = _server._app_build_worker_status_response(resolve_compute_mode=_server._resolve_compute_mode, persistent_worker_handle=_server._PERSISTENT_WORKER_HANDLE)
    self._send_json(response.status, response.payload)


def _api_post_compute_cancel(self, job_id_part: str) -> None:
    job_id = str(job_id_part or '').strip()
    if not job_id or _server._get_job_snapshot(job_id) is None:
        self._send_json(
            _server.HTTPStatus.NOT_FOUND,
            {'cancelled': False, 'job_id': job_id, 'reason': 'not found'},
        )
        return
    from ai.job_cancel import request_cancel

    request_cancel(job_id)
    self._send_json(_server.HTTPStatus.OK, {'cancelled': True, 'job_id': job_id})


def _api_post_compute_start(self, compute_type: str) -> None:
    normalized_type = str(compute_type or '').strip().lower()
    if not normalized_type or normalized_type == 'status':
        raise _server.ApiError(_server.HTTPStatus.BAD_REQUEST, 'Compute type is required')
    body = self._read_json_body(required=False)
    body_obj = self._expect_object(body or {}, 'Request body')
    noop_payload = _server._compute_concept_scoped_noop_payload(normalized_type, body_obj)
    if noop_payload is not None:
        self._send_json(_server.HTTPStatus.OK, noop_payload)
        return
    callback_url = _server._job_callback_url_from_mapping(body_obj)
    try:
        response = _server._app_build_post_compute_start_response(compute_type, body_obj, callback_url=callback_url, create_job=_server._create_job, launch_compute_runner=_server._launch_compute_runner, job_conflict_error_cls=_server.JobResourceConflictError)
    except _server._app_ComputeOffsetHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

def _api_post_compute_status(self, compute_type: _server.Optional[str]) -> None:
    body = self._expect_object(self._read_json_body(), 'Request body')
    try:
        response = _server._app_build_post_compute_status_response(compute_type, body, get_job_snapshot=_server._get_job_snapshot, job_response_payload=_server._job_response_payload)
    except _server._app_ComputeOffsetHandlerError as exc:
        raise _server.ApiError(exc.status, exc.message) from exc
    self._send_json(response.status, response.payload)

__all__ = ['_resolve_compute_mode', '_job_snapshot_dir', '_job_snapshot_safe_name', '_job_snapshot_path', '_persist_job_snapshot', '_delete_job_snapshot', '_coerce_loaded_job_snapshot', '_empty_job_locks_payload', '_mark_loaded_job_interrupted', '_load_job_snapshots', '_subprocess_missing_result_message', '_copy_job_for_snapshot', '_launch_compute_runner', '_launch_compute_subprocess', '_compute_subprocess_entry', '_launch_compute_persistent', '_cleanup_old_jobs', '_job_log_limit', '_infer_job_error_code', '_job_log_entry', '_append_job_log_locked', '_job_lock_resources', '_expire_job_locks_locked', '_find_job_resource_conflict_locked', '_refresh_job_locks_locked', '_release_job_locks_locked', '_job_locks_payload', '_normalize_job_callback_url', '_job_callback_payload', '_post_job_callback', '_dispatch_job_callback', '_dispatch_job_callback_async', '_create_job', '_tail_log_file', '_set_job_running', '_set_job_progress', '_set_job_complete', '_set_job_error', '_get_job_snapshot', '_job_logs_payload', '_job_detail_payload', '_list_jobs_snapshots', '_job_response_payload', '_list_active_jobs_snapshots', '_reset_job_to_running', '_run_compute_job', '_api_get_jobs', '_api_get_job', '_api_get_job_logs', '_api_get_jobs_active', '_api_get_job_error_logs', '_api_get_worker_status', '_api_post_compute_cancel', '_api_post_compute_start', '_api_post_compute_status']
