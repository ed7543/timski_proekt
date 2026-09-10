import { cloneElement, isValidElement } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { useCollapsed } from '../../hooks/useCollapsed';
import { ChevronIcon } from '../icons';

interface AppShellProps {
  sidebar: ReactNode;
  children: ReactNode;
  rightSidebar?: ReactNode;
  /** Only meaningful when rightSidebar is passed - controlled by the caller
   * since its toggle button lives wherever makes sense for that page (e.g.
   * ChatPage's own masthead), not inside this generic shell. */
  rightSidebarCollapsed?: boolean;
}

export function AppShell({ sidebar, children, rightSidebar, rightSidebarCollapsed }: AppShellProps) {
  const [leftCollapsed, toggleLeft] = useCollapsed('lw_sidebar_left');

  const sidebarContent = isValidElement(sidebar)
    ? cloneElement(sidebar as ReactElement<{ collapsed?: boolean }>, { collapsed: leftCollapsed })
    : sidebar;

  return (
    <div className="app paper-grain">
      <aside className={`sidebar-left${leftCollapsed ? ' collapsed' : ''}`}>
        {sidebarContent}
        <button
          type="button"
          className="sidebar-collapse-btn"
          onClick={toggleLeft}
          aria-label={leftCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={leftCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ChevronIcon flip={leftCollapsed} />
        </button>
      </aside>
      <main>{children}</main>
      {rightSidebar && (
        <aside className={`sidebar-right${rightSidebarCollapsed ? ' collapsed' : ''}`}>
          {!rightSidebarCollapsed && rightSidebar}
        </aside>
      )}
    </div>
  );
}
