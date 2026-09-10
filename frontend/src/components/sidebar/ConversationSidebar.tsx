import type { ConversationOut } from '../../types/conversation';
import { NewConversationButton } from './NewConversationButton';
import { ConversationSearchInput } from './ConversationSearchInput';
import { ConversationList } from './ConversationList';
import { UserFooter } from './UserFooter';
import { NavTabs } from '../layout/NavTabs';
import { PlusIcon } from '../icons';

interface Props {
  threads: ConversationOut[];
  activeId: number | null;
  loggedIn: boolean;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onNewConversation: () => void;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onRename: (id: number, title: string) => void;
  /** Injected by AppShell (cloneElement) based on the shared left-sidebar
   * collapse toggle - not something this component's own callers set. */
  collapsed?: boolean;
}

export function ConversationSidebar({
  threads,
  activeId,
  loggedIn,
  searchQuery,
  onSearchChange,
  onNewConversation,
  onSelect,
  onDelete,
  onRename,
  collapsed,
}: Props) {
  return (
    <>
      {!collapsed && (
        <div className="brand">
          <div className="brand-name">LearnWise</div>
        </div>
      )}
      <NavTabs collapsed={collapsed} />
      {collapsed ? (
        <div className="sidebar-collapsed-body">
          <button
            type="button"
            className="sidebar-collapsed-new-btn"
            onClick={onNewConversation}
            title="New conversation"
            aria-label="New conversation"
          >
            <PlusIcon />
          </button>
        </div>
      ) : (
        <>
          <NewConversationButton onClick={onNewConversation} />
          <ConversationSearchInput value={searchQuery} onChange={onSearchChange} />
          <div className="section-label">History</div>
          <nav className="history">
            <ConversationList
              threads={threads}
              activeId={activeId}
              loggedIn={loggedIn}
              onSelect={onSelect}
              onDelete={onDelete}
              onRename={onRename}
            />
          </nav>
        </>
      )}
      <UserFooter collapsed={collapsed} />
    </>
  );
}
