import { NavTabs } from '../layout/NavTabs';
import { UserFooter } from '../sidebar/UserFooter';

interface Props {
  /** Injected by AppShell (cloneElement) based on the shared left-sidebar
   * collapse toggle - not something this component's own callers set. */
  collapsed?: boolean;
}

/** Lightweight left sidebar for the Courses section - just branding + section
 * nav + the user footer, since a conversation history list doesn't apply here. */
export function CourseNavSidebar({ collapsed }: Props) {
  return (
    <>
      {!collapsed && (
        <div className="brand">
          <div className="brand-name">LearnWise</div>
        </div>
      )}
      <NavTabs collapsed={collapsed} />
      <div style={{ flex: 1 }} />
      <UserFooter collapsed={collapsed} />
    </>
  );
}
