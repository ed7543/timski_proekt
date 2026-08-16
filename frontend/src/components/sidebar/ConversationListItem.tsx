import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { ConversationOut } from '../../types/conversation';
import { EditIcon, TrashIcon } from '../icons';

interface Props {
  thread: ConversationOut;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}

export function ConversationListItem({ thread, active, onSelect, onDelete, onRename }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(thread.title);

  const commitRename = () => {
    const trimmed = draft.trim();
    setEditing(false);
    if (trimmed && trimmed !== thread.title) {
      onRename(trimmed);
    } else {
      setDraft(thread.title);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitRename();
    } else if (e.key === 'Escape') {
      setDraft(thread.title);
      setEditing(false);
    }
  };

  return (
    <div className={`thread ${active ? 'active' : ''}`} onClick={editing ? undefined : onSelect}>
      <div className="thread-row">
        <span className="thread-dot" />
        <span style={{ minWidth: 0, flex: 1 }}>
          {editing ? (
            <input
              className="thread-title-input"
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onBlur={commitRename}
              onKeyDown={handleKeyDown}
            />
          ) : (
            <span className="thread-title">{thread.title || 'Untitled'}</span>
          )}
          <span className="thread-meta">
            {thread.message_count} {thread.message_count === 1 ? 'message' : 'messages'}
          </span>
        </span>
      </div>
      {!editing && (
        <div className="thread-actions">
          <button
            className="thread-action-btn"
            aria-label="Rename"
            onClick={(e) => {
              e.stopPropagation();
              setEditing(true);
            }}
          >
            <EditIcon />
          </button>
          <button
            className="thread-action-btn danger"
            aria-label="Delete"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <TrashIcon />
          </button>
        </div>
      )}
    </div>
  );
}
