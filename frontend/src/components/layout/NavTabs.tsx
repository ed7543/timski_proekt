import { NavLink } from 'react-router-dom';
import { ChatIcon, BookIcon, ChartIcon } from '../icons';

export function NavTabs() {
  return (
    <nav className="nav-tabs">
      <NavLink to="/chat" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
        <ChatIcon /> Chat
      </NavLink>
      <NavLink to="/courses" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
        <BookIcon /> Courses
      </NavLink>
      <NavLink to="/progress" className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>
        <ChartIcon /> Progress
      </NavLink>
    </nav>
  );
}
