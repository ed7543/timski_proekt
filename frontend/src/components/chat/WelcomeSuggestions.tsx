import { ArrowIcon } from '../icons';

const SUGGESTIONS = [
  { q: 'How does async/await work?', tag: 'Concurrency' },
  { q: 'FastAPI dependency injection', tag: 'FastAPI' },
  { q: 'useEffect vs useLayoutEffect', tag: 'React' },
  { q: 'SQL JOIN queries explained', tag: 'SQL' },
];

export function WelcomeSuggestions({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="welcome">
      <div className="rule-row">
        <span className="rule" />
        <span className="label">The morning edition</span>
        <span className="rule" />
      </div>
      <h2>
        Ask anything,
        <br />
        <span className="it">learn anything.</span>
      </h2>
      <p>
        LearnWise is an editorial AI tutor that consults live documentation and returns well-sourced, footnoted
        answers. Start with a question, or pick a prompt below.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((s, i) => (
          <button key={s.q} className="sugg" onClick={() => onPick(s.q)}>
            <span className="sugg-num">{String(i + 1).padStart(2, '0')}</span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="sugg-tag">{s.tag}</div>
              <div className="sugg-q">{s.q}</div>
            </div>
            <ArrowIcon />
          </button>
        ))}
      </div>
    </div>
  );
}
