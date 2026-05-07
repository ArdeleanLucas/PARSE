import { describe, expect, it } from 'vitest';

import { extractRerunError } from './AnnotateView';

describe('extractRerunError', () => {
  it('normalizes apiFetch networkError wrapper strings to user-facing copy', () => {
    expect(extractRerunError(new Error(
      'Could not reach the PARSE API for POST /api/lexeme/run_ipa. Check that the Python server is running at http://127.0.0.1:8766 and that the Vite /api proxy is active.',
    ))).toBe('Network error. Try again.');
  });

  it('keeps defensive TypeError network fallback support', () => {
    expect(extractRerunError(new TypeError('Failed to fetch'))).toBe('Network error. Try again.');
  });

  it('extracts server error payload text from apiFetch 4xx wrappers', () => {
    expect(extractRerunError(new Error('API POST /api/lexeme/run_ipa failed 400: {"error":"interval too long"}'))).toBe('interval too long');
  });

  it('returns plain Error messages unchanged', () => {
    expect(extractRerunError(new Error('plain message'))).toBe('plain message');
  });

  it('falls back when the thrown value is empty', () => {
    expect(extractRerunError(null)).toBe('Re-run failed.');
  });
});
