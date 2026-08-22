import { BookIcon, GlobeIcon } from '../icons';
import type { CourseOut } from '../../types/course';

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
  courses: CourseOut[];
  courseId: number | null;
  onCourseChange: (courseId: number | null) => void;
}

export function ChatMasthead({
  title,
  subject,
  onSubjectChange,
  live,
  onToggleLive,
  courses,
  courseId,
  onCourseChange,
}: Props) {
  return (
    <header className="masthead">
      <div className="masthead-l">
        <span className="vol">Vol. I · No. 01</span>
        <span className="vbar" />
        <h1 className="conv-title">{title}</h1>
      </div>
      <div className="masthead-r">
        {courses.length > 0 && (
          <>
            <div
              className="select-wrap select-wrap-course"
              title="Tie this conversation to a FINKI course for course-aware answers"
            >
              <span className="select-wrap-icon">
                <BookIcon />
              </span>
              <select
                value={courseId ?? ''}
                onChange={(e) => onCourseChange(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">No course</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <span className="masthead-divider" />
          </>
        )}
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
