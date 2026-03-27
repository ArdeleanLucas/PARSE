(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;

  const MUTATING_TOOL_PATTERN = /(save|write|update|edit|patch|delete|remove|create|insert|import|commit|push|overwrite|rename)/i;
  const PREVIEW_MAX_CHARS = 320;

  function toObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function toArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function toString(value) {
    return String(value == null ? '' : value).trim();
  }

  function clampProgress(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return null;
    }

    if (num <= 1 && num >= 0) {
      return Math.max(0, Math.min(100, num * 100));
    }

    return Math.max(0, Math.min(100, num));
  }

  function normalizeStatus(rawStatus, fallback) {
    const status = toString(rawStatus).toLowerCase();

    if (!status) {
      return toString(fallback).toLowerCase() || 'queued';
    }

    if (status === 'queued' || status === 'pending' || status === 'submitted' || status === 'created') {
      return 'queued';
    }

    if (
      status === 'running' ||
      status === 'in_progress' ||
      status === 'in-progress' ||
      status === 'processing' ||
      status === 'streaming'
    ) {
      return 'running';
    }

    if (
      status === 'complete' ||
      status === 'completed' ||
      status === 'done' ||
      status === 'success' ||
      status === 'succeeded' ||
      status === 'ok'
    ) {
      return 'completed';
    }

    if (status === 'cancelled' || status === 'canceled' || status === 'aborted' || status === 'stopped') {
      return 'cancelled';
    }

    if (status === 'error' || status === 'failed' || status === 'failure') {
      return 'error';
    }

    return status;
  }

  function isDoneStatus(status) {
    const normalized = normalizeStatus(status, '');
    return normalized === 'completed' || normalized === 'error' || normalized === 'cancelled';
  }

  function isActiveStatus(status) {
    const normalized = normalizeStatus(status, '');
    return normalized === 'queued' || normalized === 'running';
  }

  function isErrorStatus(status) {
    const normalized = normalizeStatus(status, '');
    return normalized === 'error' || normalized === 'cancelled';
  }

  function statusMeta(status) {
    const normalized = normalizeStatus(status, 'queued');

    if (normalized === 'completed') {
      return { status: normalized, label: 'Completed', tone: 'ok' };
    }

    if (normalized === 'running') {
      return { status: normalized, label: 'Running', tone: 'running' };
    }

    if (normalized === 'cancelled') {
      return { status: normalized, label: 'Cancelled', tone: 'warn' };
    }

    if (normalized === 'error') {
      return { status: normalized, label: 'Failed', tone: 'danger' };
    }

    return { status: normalized, label: 'Queued', tone: 'pending' };
  }

  function normalizeTimestamp(value) {
    const text = toString(value);
    if (!text) {
      return null;
    }

    const parsed = Date.parse(text);
    if (!Number.isFinite(parsed)) {
      return null;
    }

    return new Date(parsed).toISOString();
  }

  function preview(value) {
    if (value == null) {
      return '';
    }

    if (typeof value === 'string') {
      const clean = value.replace(/\s+/g, ' ').trim();
      if (clean.length <= PREVIEW_MAX_CHARS) {
        return clean;
      }
      return clean.slice(0, PREVIEW_MAX_CHARS - 1) + '…';
    }

    try {
      const asJson = JSON.stringify(value);
      if (!asJson) {
        return '';
      }
      if (asJson.length <= PREVIEW_MAX_CHARS) {
        return asJson;
      }
      return asJson.slice(0, PREVIEW_MAX_CHARS - 1) + '…';
    } catch (_) {
      return toString(value);
    }
  }

  function extractRunId(payload) {
    const body = toObject(payload);

    const candidate =
      body.runId != null ? body.runId :
      body.run_id != null ? body.run_id :
      body.jobId != null ? body.jobId :
      body.job_id != null ? body.job_id :
      body.id;

    const text = toString(candidate);
    return text || null;
  }

  function extractAssistantTextFromObject(obj) {
    const body = toObject(obj);

    const direct = [
      body.assistantText,
      body.assistant_text,
      body.assistant,
      body.output_text,
      body.outputText,
      body.answer,
      body.text,
      body.content,
    ];

    for (let i = 0; i < direct.length; i += 1) {
      const text = toString(direct[i]);
      if (text) {
        return text;
      }
    }

    const message = body.message;
    if (message && typeof message === 'object') {
      const nestedText = extractAssistantTextFromObject(message);
      if (nestedText) {
        return nestedText;
      }
    }

    return '';
  }

  function extractAssistantText(payload) {
    const body = toObject(payload);

    const directText = extractAssistantTextFromObject(body);
    if (directText) {
      return directText;
    }

    const resultText = extractAssistantTextFromObject(body.result);
    if (resultText) {
      return resultText;
    }

    const responseText = extractAssistantTextFromObject(body.response);
    if (responseText) {
      return responseText;
    }

    const dataText = extractAssistantTextFromObject(body.data);
    if (dataText) {
      return dataText;
    }

    return '';
  }

  function extractError(payload, status) {
    const body = toObject(payload);

    if (typeof body.error === 'string' && body.error.trim()) {
      return body.error.trim();
    }

    const errorObj = toObject(body.error);
    const nestedError = toString(errorObj.message || errorObj.detail || errorObj.error);
    if (nestedError) {
      return nestedError;
    }

    if (typeof body.message === 'string' && body.message.trim() && isErrorStatus(status)) {
      return body.message.trim();
    }

    if (typeof body.detail === 'string' && body.detail.trim() && isErrorStatus(status)) {
      return body.detail.trim();
    }

    return '';
  }

  function inferToolName(entry) {
    const item = toObject(entry);

    const candidate =
      item.toolName != null ? item.toolName :
      item.tool_name != null ? item.tool_name :
      item.tool != null ? item.tool :
      item.name != null ? item.name :
      item.command != null ? item.command :
      item.type;

    const text = toString(candidate);
    return text || 'tool';
  }

  function inferToolTitle(toolName) {
    const raw = toString(toolName);
    if (!raw) {
      return 'Tool';
    }

    return raw
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, function (char) {
        return char.toUpperCase();
      });
  }

  function inferStatusFromEventType(eventType, fallbackStatus) {
    const type = toString(eventType).toLowerCase();
    if (!type) {
      return normalizeStatus(fallbackStatus, 'running');
    }

    if (type.indexOf('error') !== -1 || type.indexOf('fail') !== -1) {
      return 'error';
    }

    if (type.indexOf('cancel') !== -1 || type.indexOf('abort') !== -1) {
      return 'cancelled';
    }

    if (
      type.indexOf('done') !== -1 ||
      type.indexOf('end') !== -1 ||
      type.indexOf('complete') !== -1 ||
      type.indexOf('success') !== -1
    ) {
      return 'completed';
    }

    if (type.indexOf('start') !== -1 || type.indexOf('run') !== -1) {
      return 'running';
    }

    return normalizeStatus(fallbackStatus, 'running');
  }

  function extractToolDetail(entry) {
    const item = toObject(entry);

    const direct = [
      item.detail,
      item.summary,
      item.message,
      item.note,
      item.output_text,
      item.outputText,
      item.output,
      item.result,
      item.response,
    ];

    for (let i = 0; i < direct.length; i += 1) {
      const text = preview(direct[i]);
      if (text) {
        return text;
      }
    }

    const inputPreview = preview(item.input != null ? item.input : item.args);
    if (inputPreview) {
      return 'Input: ' + inputPreview;
    }

    return '';
  }

  function buildToolEntryId(source, index, entry, toolName) {
    const item = toObject(entry);
    const candidate =
      item.id != null ? item.id :
      item.eventId != null ? item.eventId :
      item.event_id != null ? item.event_id :
      item.toolCallId != null ? item.toolCallId :
      item.tool_call_id != null ? item.tool_call_id :
      item.callId != null ? item.callId :
      item.call_id != null ? item.call_id :
      item.stepId != null ? item.stepId :
      item.step_id;

    const explicit = toString(candidate);
    if (explicit) {
      return explicit;
    }

    const cleanSource = toString(source || 'tool').replace(/[^a-zA-Z0-9_.-]+/g, '-');
    const cleanName = toString(toolName || 'tool').replace(/[^a-zA-Z0-9_.-]+/g, '-');
    return cleanSource + ':' + cleanName + ':' + String(index);
  }

  function normalizeToolEntry(entry, index, source) {
    const item = toObject(entry);
    const toolName = inferToolName(item);

    const status = normalizeStatus(
      item.status || item.state || item.phase || inferStatusFromEventType(item.type, item.status),
      'running'
    );

    const startedAt = normalizeTimestamp(
      item.startedAt != null ? item.startedAt :
      item.started_at != null ? item.started_at :
      item.startTime != null ? item.startTime :
      item.start_time
    );

    const endedAt = normalizeTimestamp(
      item.endedAt != null ? item.endedAt :
      item.ended_at != null ? item.ended_at :
      item.endTime != null ? item.endTime :
      item.end_time != null ? item.end_time :
      item.completedAt != null ? item.completedAt :
      item.completed_at
    );

    return {
      id: buildToolEntryId(source, index, item, toolName),
      type: 'tool',
      source: toString(source) || 'tool',
      toolName: toolName,
      title: toString(item.title) || inferToolTitle(toolName),
      status: status,
      detail: extractToolDetail(item),
      mutating: MUTATING_TOOL_PATTERN.test(toolName),
      inputPreview: preview(item.input != null ? item.input : item.args),
      outputPreview: preview(item.output != null ? item.output : item.result),
      startedAt: startedAt,
      endedAt: endedAt,
      order: Number.isFinite(Number(item.order)) ? Number(item.order) : index,
    };
  }

  function shouldTreatStepAsTool(step) {
    const item = toObject(step);
    if (item.tool || item.toolName || item.tool_name) {
      return true;
    }

    const type = toString(item.type || item.kind).toLowerCase();
    if (!type) {
      return false;
    }

    return type.indexOf('tool') !== -1 || type === 'call';
  }

  function collectTranscriptEntriesFromContainer(container, sourcePrefix, out) {
    const body = toObject(container);
    const prefix = toString(sourcePrefix) || 'payload';

    const arrays = [
      { source: prefix + '.tool_transcript', items: toArray(body.tool_transcript) },
      { source: prefix + '.transcript', items: toArray(body.transcript) },
      { source: prefix + '.tools', items: toArray(body.tools) },
      { source: prefix + '.tool_calls', items: toArray(body.tool_calls) },
    ];

    for (let a = 0; a < arrays.length; a += 1) {
      const list = arrays[a];
      for (let i = 0; i < list.items.length; i += 1) {
        out.push(normalizeToolEntry(list.items[i], i, list.source));
      }
    }

    const steps = toArray(body.steps);
    for (let i = 0; i < steps.length; i += 1) {
      if (!shouldTreatStepAsTool(steps[i])) {
        continue;
      }
      out.push(normalizeToolEntry(steps[i], i, prefix + '.steps'));
    }

    const events = toArray(body.events);
    for (let i = 0; i < events.length; i += 1) {
      const event = toObject(events[i]);
      const eventType = toString(event.type || event.name).toLowerCase();
      if (eventType.indexOf('tool') === -1) {
        continue;
      }
      out.push(normalizeToolEntry(event, i, prefix + '.events'));
    }
  }

  function collectTranscriptEntries(payload) {
    const out = [];
    const body = toObject(payload);

    collectTranscriptEntriesFromContainer(body, 'payload', out);
    collectTranscriptEntriesFromContainer(body.result, 'payload.result', out);
    collectTranscriptEntriesFromContainer(body.response, 'payload.response', out);
    collectTranscriptEntriesFromContainer(body.data, 'payload.data', out);

    return out;
  }

  function timestampSortValue(entry) {
    const item = toObject(entry);
    const candidates = [item.startedAt, item.endedAt, item.updatedAt, item.createdAt];

    for (let i = 0; i < candidates.length; i += 1) {
      const parsed = Date.parse(toString(candidates[i]));
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }

    return Number.MAX_SAFE_INTEGER;
  }

  function mergeTranscriptEntries(existing, incoming) {
    const current = toArray(existing);
    const next = toArray(incoming);

    const mergedById = Object.create(null);
    const orderedIds = [];

    function upsert(entry) {
      const item = toObject(entry);
      const id = toString(item.id);
      if (!id) {
        return;
      }

      if (!mergedById[id]) {
        mergedById[id] = Object.assign({}, item);
        orderedIds.push(id);
        return;
      }

      mergedById[id] = Object.assign({}, mergedById[id], item);
    }

    for (let i = 0; i < current.length; i += 1) {
      upsert(current[i]);
    }

    for (let i = 0; i < next.length; i += 1) {
      upsert(next[i]);
    }

    orderedIds.sort(function (leftId, rightId) {
      const left = mergedById[leftId];
      const right = mergedById[rightId];

      const leftTs = timestampSortValue(left);
      const rightTs = timestampSortValue(right);
      if (leftTs !== rightTs) {
        return leftTs - rightTs;
      }

      const leftOrder = Number.isFinite(Number(left.order)) ? Number(left.order) : Number.MAX_SAFE_INTEGER;
      const rightOrder = Number.isFinite(Number(right.order)) ? Number(right.order) : Number.MAX_SAFE_INTEGER;
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }

      return leftId.localeCompare(rightId);
    });

    const out = [];
    for (let i = 0; i < orderedIds.length; i += 1) {
      out.push(mergedById[orderedIds[i]]);
    }

    return out;
  }

  function normalizeRunPayload(payload, previousRun, hint) {
    const body = toObject(payload);
    const prev = toObject(previousRun);
    const context = toObject(hint);

    const status = normalizeStatus(
      body.status || body.state || body.phase || body.runStatus || body.run_status,
      prev.status || 'queued'
    );

    const runId = extractRunId(body) || toString(prev.serverRunId || prev.id || context.runId) || null;

    const message = toString(body.message || body.detail);
    const assistantText = extractAssistantText(body);
    const error = extractError(body, status);

    const progress =
      clampProgress(body.progress) != null ? clampProgress(body.progress) :
      clampProgress(body.percent) != null ? clampProgress(body.percent) :
      clampProgress(body.completion);

    const transcript = collectTranscriptEntries(body);

    const canCancel =
      body.canCancel != null ? !!body.canCancel :
      body.can_cancel != null ? !!body.can_cancel :
      isActiveStatus(status);

    const canRetry =
      body.canRetry != null ? !!body.canRetry :
      body.can_retry != null ? !!body.can_retry :
      isDoneStatus(status) && (isErrorStatus(status) || !!error);

    return {
      runId: runId,
      status: status,
      message: message,
      assistantText: assistantText,
      error: error,
      progress: progress,
      transcript: transcript,
      canCancel: canCancel,
      canRetry: canRetry,
      model: toString(body.model) || toString(toObject(body.meta).model) || '',
      reasoning: toString(body.reasoning) || toString(toObject(body.meta).reasoning) || '',
      intent: toString(body.intent) || toString(toObject(body.meta).intent) || '',
      done: isDoneStatus(status),
      success: status === 'completed' && !error,
    };
  }

  function formatToolEntry(entry) {
    const item = toObject(entry);
    const status = normalizeStatus(item.status, 'queued');
    const meta = statusMeta(status);

    return {
      id: toString(item.id) || null,
      title: toString(item.title) || inferToolTitle(item.toolName),
      status: status,
      statusLabel: meta.label,
      tone: meta.tone,
      detail: toString(item.detail) || '',
      mutating: !!item.mutating,
      startedAt: normalizeTimestamp(item.startedAt),
      endedAt: normalizeTimestamp(item.endedAt),
      inputPreview: toString(item.inputPreview),
      outputPreview: toString(item.outputPreview),
    };
  }

  P.modules.chatToolAdapters = {
    normalizeStatus: normalizeStatus,
    isDoneStatus: isDoneStatus,
    isActiveStatus: isActiveStatus,
    isErrorStatus: isErrorStatus,
    statusMeta: statusMeta,
    extractRunId: extractRunId,
    normalizeRunPayload: normalizeRunPayload,
    mergeTranscriptEntries: mergeTranscriptEntries,
    collectTranscriptEntries: collectTranscriptEntries,
    formatToolEntry: formatToolEntry,
  };
}());
