import type { ReactNode } from 'react';

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell paper-grain">
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
