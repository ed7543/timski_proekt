import type { ReactNode } from 'react';

interface Props {
  onClose: () => void;
  children: ReactNode;
  maxWidth?: number;
}

export function ModalShell({ onClose, children, maxWidth }: Props) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={maxWidth ? { maxWidth } : undefined} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}
