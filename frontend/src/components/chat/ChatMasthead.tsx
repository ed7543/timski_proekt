import { GlobeIcon } from '../icons';

const SUBJECTS = [
  'Any subject',
  'Python',
  'FastAPI',
  'React',
  'JavaScript',
  'TypeScript',
  'SQL',
  'Docker',
  'Machine Learning',
  'Git',
  'Linux',
];

interface Props {
  title: string;
  subject: string;
  onSubjectChange: (subject: string) => void;
  live: boolean;
  onToggleLive: () => void;
}

export function ChatMasthead({ title, subject, onSubjectChange, live, onToggleLive }: Props) {
  return (
    <header className="masthead">
      <div className="masthead-l">
        <span className="vol">Vol. I · No. 01</span>
        <span className="vbar" />
        <h1 className="conv-title">{title}</h1>
      </div>
      <div className="masthead-r">
        <div className="select-wrap">
          <select value={subject} onChange={(e) => onSubjectChange(e.target.value)}>
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <button className="toggle-btn" onClick={onToggleLive} title="Toggle live web search">
          <GlobeIcon />
          <span>Live search</span>
          <span className={`toggle ${live ? 'on' : ''}`}>
            <span className="toggle-dot" />
          </span>
        </button>
      </div>
    </header>
  );
}

export { SUBJECTS };
