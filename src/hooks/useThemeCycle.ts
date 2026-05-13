import { useCallback, useEffect, useMemo, useState } from 'react';

export type Theme = 'light' | 'amber' | 'violet' | 'blue';

export const THEME_ORDER: readonly Theme[] = ['light', 'amber', 'violet', 'blue'] as const;
export const THEME_STORAGE_KEY = 'parse.theme';
export const THEME_LABELS: Record<Theme, string> = {
  light: 'Light',
  amber: 'Dark · Warm Amber',
  violet: 'Dark · Cool Violet',
  blue: 'Dark · Bright Blue',
};

export function readStoredTheme(): Theme {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (raw && (THEME_ORDER as readonly string[]).includes(raw)) {
      return raw as Theme;
    }
  } catch {
    // localStorage unavailable.
  }
  return 'light';
}

export function useThemeCycle(): { theme: Theme; cycleTheme: () => void; nextTheme: Theme } {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    const root = document.documentElement;
    for (const t of THEME_ORDER) {
      root.classList.toggle(`theme-${t}`, theme === t);
    }
    root.classList.toggle('dark', theme !== 'light');
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Ignore persistence failures.
    }
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setTheme((prev) => {
      const idx = THEME_ORDER.indexOf(prev);
      return THEME_ORDER[(idx + 1) % THEME_ORDER.length];
    });
  }, []);

  const nextTheme = useMemo(() => {
    const idx = THEME_ORDER.indexOf(theme);
    return THEME_ORDER[(idx + 1) % THEME_ORDER.length];
  }, [theme]);

  return { theme, cycleTheme, nextTheme };
}
