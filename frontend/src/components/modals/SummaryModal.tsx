import { marked } from 'marked';
import { useMemo } from 'react';
import { ModalShell } from './ModalShell';

export function SummaryModal({ summary, onClose }: { summary: string; onClose: () => void }) {
  const html = useMemo(() => marked.parse(summary || '', { async: false }) as string, [summary]);

  return (
    <ModalShell onClose={onClose}>
      <h2>Study recap</h2>
      <div className="modal-subtitle">Generated from your conversation</div>
      <div className="msg-ai-body" dangerouslySetInnerHTML={{ __html: html }} />
      <div className="modal-footer">
        <div />
        <button className="modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
