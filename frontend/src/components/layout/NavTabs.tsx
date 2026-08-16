import { NavLink } from 'react-router-dom';
import { ChatIcon, BookIcon } from '../icons';

export function NavTabs() {
  return (
    <nav className="nav-tabs">
      <NavLink to="/chat" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
        <ChatIcon /> Chat
      </NavLink>
      <NavLink to="/courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
        <BookIcon /> Courses
      </NavLink>
    </nav>
  );
}
