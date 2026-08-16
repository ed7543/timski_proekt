import { PlusIcon } from '../icons';

export function NewConversationButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-btn" onClick={onClick}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <PlusIcon />
        New conversation
      </span>
      <span className="kbd">⌘N</span>
    </button>
  );
}
