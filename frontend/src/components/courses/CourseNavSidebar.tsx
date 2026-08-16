import { NavTabs } from '../layout/NavTabs';
import { UserFooter } from '../sidebar/UserFooter';

/** Lightweight left sidebar for the Courses section - just branding + section
 * nav + the user footer, since a conversation history list doesn't apply here. */
export function CourseNavSidebar() {
  return (
    <>
      <div className="brand">
        <div className="brand-mark">
          <span>L</span>
        </div>
        <div className="brand-name">LearnWise</div>
      </div>
      <NavTabs />
      <div style={{ flex: 1 }} />
      <UserFooter />
    </>
  );
}
