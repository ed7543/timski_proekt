import type { ReactNode } from 'react';

interface AppShellProps {
  sidebar: ReactNode;
  children: ReactNode;
  rightSidebar?: ReactNode;
}

export function AppShell({ sidebar, children, rightSidebar }: AppShellProps) {
  return (
    <div className="app paper-grain">
      <aside className="sidebar-left">{sidebar}</aside>
      <main>{children}</main>
      {rightSidebar && <aside className="sidebar-right">{rightSidebar}</aside>}
    </div>
  );
}
