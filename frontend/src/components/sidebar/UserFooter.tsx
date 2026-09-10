import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { GuestIcon, MoonIcon, SunIcon } from '../icons';

function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      className="icon-btn theme-toggle"
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

export function UserFooter() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onClickOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [menuOpen]);

  if (user) {
    const initial = (user.full_name || user.email || '?')[0].toUpperCase();
    const showBecomeContributor = !user.is_premium && user.role !== 'admin';

    return (
      <div className="user-foot-wrap" ref={wrapRef}>
        {menuOpen && (
          <div className="user-foot-dropdown">
            {showBecomeContributor && (
              <Link to="/subscribe" className="user-foot-menu-item" onClick={() => setMenuOpen(false)}>
                Become a contributor
              </Link>
            )}
            {user.is_premium && (
              <Link to="/subscribe" className="user-foot-menu-item" onClick={() => setMenuOpen(false)}>
                Cancel subscription
              </Link>
            )}
            <span
              className="user-foot-menu-item"
              onClick={async () => {
                setMenuOpen(false);
                await logout();
                navigate('/login');
              }}
            >
              Log out
            </span>
          </div>
        )}
        <div className="user-foot">
          <button type="button" className="user-foot-trigger" onClick={() => setMenuOpen((v) => !v)}>
            <div className="avatar">
              <span style={{ fontFamily: "'Instrument Serif', serif", fontStyle: 'italic' }}>{initial}</span>
            </div>
            <div className="user-info">
              <div className="user-name">{user.full_name || user.email}</div>
              <div className="user-plan">{user.is_premium ? 'Subscribed' : 'Not subscribed'}</div>
            </div>
          </button>
          <ThemeToggleButton />
        </div>
      </div>
    );
  }

  return (
    <div className="user-foot">
      <div className="avatar">
        <GuestIcon />
      </div>
      <div className="user-info">
        <div className="user-name">Guest</div>
        <div className="user-plan">Not signed in</div>
      </div>
      <ThemeToggleButton />
      <button className="btn btn-primary" onClick={() => navigate('/login')}>
        Sign in
      </button>
    </div>
  );
}
