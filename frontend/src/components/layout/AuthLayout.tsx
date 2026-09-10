import type { ReactNode } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { SparkleIcon, ChatIcon, BookIcon, ChartIcon } from '../icons';

export function AuthLayout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="auth-shell paper-grain">
      <div className="auth-decor">
        <div className="rule-row">
          <span className="label">Vol. I &middot; The Student Edition</span>
          <span className="rule" />
        </div>
        <h1 className="auth-decor-h">
          Learn <span className="it">anything.</span>
          <br />
          Ask <span className="it">everything.</span>
        </h1>
        <p className="auth-decor-p">
          <SparkleIcon /> Your AI tutor for FINKI &mdash; always on, always patient.
        </p>
        <ul className="auth-decor-list">
          <li>
            <ChatIcon /> Ask questions in plain language, get real answers
          </li>
          <li>
            <BookIcon /> Study guides and quizzes from your own course materials
          </li>
          <li>
            <ChartIcon /> Track your progress as you go
          </li>
        </ul>
      </div>
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-name">LearnWise</div>
        </div>
        {children}
        <div className="auth-theme-link">
          <button type="button" onClick={toggleTheme}>
            Switch to {theme === 'dark' ? 'light' : 'dark'} mode
          </button>
        </div>
      </div>
    </div>
  );
}
