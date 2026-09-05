import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ChatIcon, BookIcon, GuestIcon } from '../icons';

export function NavTabs() {
  const { user } = useAuth();

  return (
    <div className="nav-tabs-wrap">
      <nav className="nav-tabs">
        <NavLink to="/chat" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
          <ChatIcon /> Chat
        </NavLink>
        <NavLink to="/courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
          <BookIcon /> Courses
        </NavLink>
      </nav>
      <nav className="nav-tabs nav-tabs-secondary">
        <NavLink to="/marketplace" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
          <GuestIcon /> Marketplace
        </NavLink>
        {(user?.is_premium || user?.has_submitted_courses) && (
          <NavLink to="/my-courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
            My courses
          </NavLink>
        )}
        {user?.role === 'admin' && (
          <NavLink to="/admin" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
            Admin panel
          </NavLink>
        )}
      </nav>
    </div>
  );
}
