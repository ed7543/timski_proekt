import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useHelpTour } from '../../context/HelpTourContext';
import { GuestIcon } from '../icons';

interface Props {
  /** Injected by AppShell (cloneElement) via the parent sidebar, or passed
   * directly by CourseNavSidebar - shrinks to avatar-only, and the user
   * menu becomes a flyout instead of an upward panel bound to the sidebar's
   * (now much narrower) width. */
  collapsed?: boolean;
}

export function UserFooter({ collapsed }: Props) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { openTour } = useHelpTour();
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
          <div className={`user-foot-dropdown${collapsed ? ' flyout' : ''}`}>
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
            <div className="user-foot-menu-item user-foot-menu-toggle" onClick={toggleTheme}>
              <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
              <span className={`toggle ${theme === 'dark' ? 'on' : ''}`}>
                <span className="toggle-dot" />
              </span>
            </div>
            <span
              className="user-foot-menu-item"
              onClick={() => {
                setMenuOpen(false);
                openTour();
              }}
            >
              Help &amp; quick tour
            </span>
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
            {!collapsed && (
              <div className="user-info">
                <div className="user-name">{user.full_name || user.email}</div>
                <div className="user-plan">{user.is_premium ? 'Subscribed' : 'Not subscribed'}</div>
              </div>
            )}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="user-foot">
      <div className="avatar">
        <GuestIcon />
      </div>
      {!collapsed && (
        <>
          <div className="user-info">
            <div className="user-name">Guest</div>
            <div className="user-plan">Not signed in</div>
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/login')}>
            Sign in
          </button>
        </>
      )}
    </div>
  );
}
