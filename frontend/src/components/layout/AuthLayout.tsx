import type { ReactNode } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { MoonIcon, SunIcon } from '../icons';

export function AuthLayout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="auth-shell paper-grain">
      <button
        type="button"
        className="icon-btn theme-toggle auth-theme-toggle"
        onClick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
      </button>
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">
            <span>L</span>
          </div>
          <div className="brand-name">LearnWise</div>
        </div>
        {children}
      </div>
    </div>
  );
}
