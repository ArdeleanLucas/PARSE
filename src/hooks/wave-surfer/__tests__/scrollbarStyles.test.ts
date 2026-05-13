// @vitest-environment jsdom

import { describe, it, expect } from 'vitest';

import {
  injectWavesurferScrollbarStyles,
  WAVESURFER_SCROLLBAR_CSS,
} from '../scrollbarStyles';

describe('injectWavesurferScrollbarStyles', () => {
  it('returns null when wrapper has no shadowRoot', () => {
    const div = document.createElement('div');

    expect(injectWavesurferScrollbarStyles(div)).toBeNull();
  });

  it('returns null when wrapper is null or undefined', () => {
    expect(injectWavesurferScrollbarStyles(null)).toBeNull();
    expect(injectWavesurferScrollbarStyles(undefined)).toBeNull();
  });

  it('injects a <style> with the scrollbar CSS on first call', () => {
    const div = document.createElement('div');
    const shadow = div.attachShadow({ mode: 'open' });

    const result = injectWavesurferScrollbarStyles(div);

    expect(result).not.toBeNull();
    expect(result?.tagName).toBe('STYLE');
    expect(shadow.children).toHaveLength(1);
    expect(result?.textContent).toContain('::-webkit-scrollbar');
    expect(result?.textContent).toContain('var(--accent');
  });

  it('is idempotent: second call is a no-op', () => {
    const div = document.createElement('div');
    div.attachShadow({ mode: 'open' });

    injectWavesurferScrollbarStyles(div);
    const second = injectWavesurferScrollbarStyles(div);

    expect(second).toBeNull();
    expect(div.shadowRoot?.children).toHaveLength(1);
  });

  it('exports a CSS constant containing the expected rules', () => {
    expect(WAVESURFER_SCROLLBAR_CSS).toContain('::-webkit-scrollbar-thumb');
    expect(WAVESURFER_SCROLLBAR_CSS).toContain('var(--border-strong');
    expect(WAVESURFER_SCROLLBAR_CSS).toContain('var(--accent');
  });
});
