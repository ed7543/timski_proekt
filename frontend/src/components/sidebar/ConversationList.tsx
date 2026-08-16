import type { ConversationOut } from '../../types/conversation';
import { ConversationListItem } from './ConversationListItem';

interface Props {
  threads: ConversationOut[];
  activeId: number | null;
  loggedIn: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onRename: (id: number, title: string) => void;
}

export function ConversationList({ threads, activeId, loggedIn, onSelect, onDelete, onRename }: Props) {
  if (!loggedIn) {
    return (
      <div className="empty" style={{ margin: '0 8px' }}>
        Sign in to save and revisit your conversations.
      </div>
    );
  }
  if (threads.length === 0) {
    return (
      <div className="empty" style={{ margin: '0 8px' }}>
        No conversations yet - ask something to get started.
      </div>
    );
  }

  const sorted = [...threads].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

  return (
    <>
      {sorted.map((t) => (
        <ConversationListItem
          key={t.id}
          thread={t}
          active={t.id === activeId}
          onSelect={() => onSelect(t.id)}
          onDelete={() => onDelete(t.id)}
          onRename={(title) => onRename(t.id, title)}
        />
      ))}
    </>
  );
}
