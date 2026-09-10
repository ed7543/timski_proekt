import { useCallback, useState } from 'react';

/** Persisted collapse/expand toggle for a sidebar panel - same localStorage
 * persistence shape as ThemeContext, just a plain boolean per key rather
 * than a shared context, since each sidebar's toggle is local to whichever
 * component owns it. */
export function useCollapsed(key: string, defaultValue = false): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored === 'true') return true;
      if (stored === 'false') return false;
    } catch {
      /* localStorage unavailable - fall through to default */
    }
    return defaultValue;
  });

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(key, String(next));
      } catch {
        /* ignore - collapse state just won't persist */
      }
      return next;
    });
  }, [key]);

  return [collapsed, toggle];
}
