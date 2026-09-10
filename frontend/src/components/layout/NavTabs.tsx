import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ChatIcon, BookIcon, ChartIcon, StoreIcon, FileIcon, ShieldIcon, GlobeIcon } from '../icons';

interface Props {
  collapsed?: boolean;
}

export function NavTabs({ collapsed }: Props) {
  const { user } = useAuth();

  return (
    <div className={`nav-tabs-wrap${collapsed ? ' collapsed' : ''}`}>
      <nav className="nav-tabs">
        <NavLink to="/chat" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="Chat">
          <ChatIcon />
          {!collapsed && ' Chat'}
        </NavLink>
        <NavLink to="/courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="Courses">
          <BookIcon />
          {!collapsed && ' Courses'}
        </NavLink>
        <NavLink to="/progress" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="Progress">
          <ChartIcon />
          {!collapsed && ' Progress'}
        </NavLink>
      </nav>
      <nav className="nav-tabs nav-tabs-secondary">
        <NavLink to="/marketplace" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="Marketplace">
          <StoreIcon />
          {!collapsed && ' Marketplace'}
        </NavLink>
        <NavLink to="/blog" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="News & Recommendations">
          <GlobeIcon />
          {!collapsed && ' News & Recommendations'}
        </NavLink>
        {(user?.is_premium || user?.has_submitted_courses) && (
          <NavLink to="/my-courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="My courses">
            <FileIcon />
            {!collapsed && ' My courses'}
          </NavLink>
        )}
        {user?.role === 'admin' && (
          <NavLink to="/admin" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`} title="Admin panel">
            <ShieldIcon />
            {!collapsed && ' Admin panel'}
          </NavLink>
        )}
      </nav>
    </div>
  );
}
