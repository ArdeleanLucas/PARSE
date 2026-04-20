# Fix Plan — `POST /api/auth/key` 500 Error

## Bug

`POST /api/auth/key` returns 500:
```
{"error": "'RangeRequestHandler' object has no attribute '_read_body'"}
```
Test-connection icon is red when saving an xAI API key in the chat panel.

## Root Cause

PR #48 introduced `_api_auth_key()` (`python/server.py` line 2775) which calls
`self._read_body()` — a method that **does not exist** on `RangeRequestHandler`.
Every other POST handler in the server uses `self._read_json_body()`.

## Fix (`python/server.py`, `_api_auth_key`)

**Before** (broken, lines 2775-2776):
```python
body = self._read_body()
data = json.loads(body)
```

**After** (fixed):
```python
data = self._read_json_body()
```

`_read_json_body()` already reads the raw body, decodes UTF-8, and returns
parsed JSON — so the separate `json.loads()` call is redundant and gets dropped.

## Checklist
- [ ] Replace `self._read_body()` + `json.loads(body)` → `data = self._read_json_body()` in `_api_auth_key`
- [ ] Confirm no other `_read_body` references exist (grep — there are none)
- [ ] Run `npm run test -- --run` + `tsc --noEmit` (floor ≥132 passing)
- [ ] Delete this FIX_PLAN.md before merge

## Impact
Single 2-line → 1-line fix. No API contract changes, no frontend changes.
