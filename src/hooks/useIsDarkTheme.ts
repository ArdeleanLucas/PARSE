import { useEffect, useState } from 'react';

const DARK_THEME_CLASSES = ['theme-amber', 'theme-violet', 'theme-blue'] as const;

function detectDarkTheme(): boolean {
  if (typeof document === 'undefined') return false;
  const classList = document.documentElement.classList;
  return DARK_THEME_CLASSES.some((className) => classList.contains(className));
}

export function useIsDarkTheme(): boolean {
  const [isDark, setIsDark] = useState<boolean>(detectDarkTheme);

  useEffect(() => {
    const update = () => setIsDark(detectDarkTheme());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observer.disconnect();
  }, []);

  return isDark;
}
