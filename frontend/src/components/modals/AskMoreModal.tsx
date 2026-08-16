import { ArrowIcon } from '../icons';
import { ModalShell } from './ModalShell';

interface Props {
  questions: string[];
  onPick: (question: string) => void;
  onClose: () => void;
}

export function AskMoreModal({ questions, onPick, onClose }: Props) {
  return (
    <ModalShell onClose={onClose}>
      <h2>Ask more</h2>
      <div className="modal-subtitle">Suggested follow-ups based on your conversation</div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {questions.map((q, i) => (
          <button
            key={q}
            className="sugg"
            style={{ marginBottom: 10, width: '100%' }}
            onClick={() => onPick(q)}
          >
            <span className="sugg-num">{String(i + 1).padStart(2, '0')}</span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="sugg-q">{q}</div>
            </div>
            <ArrowIcon />
          </button>
        ))}
      </div>
      <div className="modal-footer">
        <div />
        <button className="modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
