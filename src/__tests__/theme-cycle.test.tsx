// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { THEME_LABELS, useThemeCycle } from '../hooks/useThemeCycle';

const themeClasses = ['theme-light', 'theme-amber', 'theme-violet', 'theme-blue', 'dark'];

function resetThemeState() {
  window.localStorage.clear();
  document.documentElement.classList.remove(...themeClasses);
}

function expectOnlyThemeClass(expected: 'light' | 'amber' | 'violet' | 'blue') {
  const root = document.documentElement;
  expect(root.classList.contains('theme-amber')).toBe(expected === 'amber');
  expect(root.classList.contains('theme-violet')).toBe(expected === 'violet');
  expect(root.classList.contains('theme-blue')).toBe(expected === 'blue');
  expect(root.classList.contains('dark')).toBe(expected !== 'light');
}

describe('useThemeCycle', () => {
  afterEach(() => {
    resetThemeState();
  });

  it('defaults to light without dark theme classes', () => {
    resetThemeState();

    const { result } = renderHook(() => useThemeCycle());

    expect(result.current.theme).toBe('light');
    expect(result.current.nextTheme).toBe('amber');
    expect(THEME_LABELS[result.current.theme]).toBe('Light');
    expectOnlyThemeClass('light');
  });

  it('cycles light to amber to violet to blue and back to light', () => {
    resetThemeState();
    const { result } = renderHook(() => useThemeCycle());

    for (const expected of ['amber', 'violet', 'blue', 'light'] as const) {
      act(() => result.current.cycleTheme());
      expect(result.current.theme).toBe(expected);
      expectOnlyThemeClass(expected);
    }
  });

  it('persists the active theme to localStorage', () => {
    resetThemeState();
    const { result } = renderHook(() => useThemeCycle());

    act(() => result.current.cycleTheme());

    expect(result.current.theme).toBe('amber');
    expect(window.localStorage.getItem('parse.theme')).toBe('amber');
  });

  it('hydrates a stored violet theme', () => {
    resetThemeState();
    window.localStorage.setItem('parse.theme', 'violet');

    const { result } = renderHook(() => useThemeCycle());

    expect(result.current.theme).toBe('violet');
    expect(result.current.nextTheme).toBe('blue');
    expectOnlyThemeClass('violet');
  });

  it('falls back to light for invalid stored theme values', () => {
    resetThemeState();
    window.localStorage.setItem('parse.theme', 'rainbow');

    const { result } = renderHook(() => useThemeCycle());

    expect(result.current.theme).toBe('light');
    expectOnlyThemeClass('light');
  });
});
