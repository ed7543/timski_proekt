import { useMemo } from 'react';
import { ModalShell } from './ModalShell';
import { renderMarkdown, handleMarkdownClick } from '../../utils/markdown';

export function SummaryModal({ summary, onClose }: { summary: string; onClose: () => void }) {
  const html = useMemo(() => renderMarkdown(summary), [summary]);

  return (
    <ModalShell onClose={onClose}>
      <h2>Study recap</h2>
      <div className="modal-subtitle">Generated from your conversation</div>
      <div className="msg-ai-body" onClick={handleMarkdownClick} dangerouslySetInnerHTML={{ __html: html }} />
      <div className="modal-footer">
        <div />
        <button className="btn btn-primary" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
