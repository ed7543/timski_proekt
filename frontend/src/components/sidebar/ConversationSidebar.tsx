import type { ConversationOut } from '../../types/conversation';
import { NewConversationButton } from './NewConversationButton';
import { ConversationSearchInput } from './ConversationSearchInput';
import { ConversationList } from './ConversationList';
import { UserFooter } from './UserFooter';
import { NavTabs } from '../layout/NavTabs';

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
}: Props) {
  return (
    <>
      <div className="brand">
        <div className="brand-mark">
          <span>L</span>
        </div>
        <div className="brand-name">LearnWise</div>
      </div>
      <NavTabs />
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
      <UserFooter />
    </>
  );
}
