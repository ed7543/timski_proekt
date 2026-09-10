import { Dropdown } from '../Dropdown';
import { BookIcon, ChevronIcon, GlobeIcon, GuestIcon } from '../icons';
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
  /** 1-indexed position of the open conversation in the sidebar's list - not
   * a hardcoded "01", so it actually changes as you switch between chats. */
  issueNo: number;
  subject: string;
  onSubjectChange: (subject: string) => void;
  live: boolean;
  onToggleLive: () => void;
  courses: CourseOut[];
  courseId: number | null;
  onCourseChange: (courseId: number | null) => void;
  /** Only shown once a conversation exists (can't invite to one that hasn't been saved yet). */
  memberCount?: number;
  onOpenMembers?: () => void;
  /** Right "Dossier" sidebar's collapse state/toggle - lives here since this
   * is the one always-visible control strip regardless of that panel's width. */
  sourcesCollapsed?: boolean;
  onToggleSources?: () => void;
}

export function ChatMasthead({
  title,
  issueNo,
  subject,
  onSubjectChange,
  live,
  onToggleLive,
  courses,
  courseId,
  onCourseChange,
  memberCount,
  onOpenMembers,
  sourcesCollapsed,
  onToggleSources,
}: Props) {
  const courseOptions = [
    { value: '', label: 'No course' },
    ...courses.map((c) => ({ value: String(c.id), label: c.name })),
  ];

  return (
    <header className="masthead">
      <div className="masthead-l">
        <span className="vol">Vol. I · No. {String(issueNo).padStart(2, '0')}</span>
        <span className="vbar" />
        <h1 className="conv-title">{title}</h1>
      </div>
      <div className="masthead-r">
        {onOpenMembers && (
          <>
            <button className="toggle-btn" onClick={onOpenMembers} title="Invite others to this chat">
              <GuestIcon />
              <span>{memberCount && memberCount > 1 ? `${memberCount} people` : 'Invite'}</span>
            </button>
            <span className="masthead-divider" />
          </>
        )}
        {courses.length > 0 && (
          <>
            <Dropdown
              className="select-wrap-course"
              title="Tie this conversation to a FINKI course for course-aware answers"
              icon={<BookIcon />}
              value={courseId != null ? String(courseId) : ''}
              options={courseOptions}
              onChange={(v) => onCourseChange(v ? Number(v) : null)}
            />
            <span className="masthead-divider" />
          </>
        )}
        <Dropdown value={subject} options={SUBJECTS.map((s) => ({ value: s, label: s }))} onChange={onSubjectChange} />
        <button className="toggle-btn" onClick={onToggleLive} title="Toggle live web search">
          <GlobeIcon />
          <span>Live search</span>
          <span className={`toggle ${live ? 'on' : ''}`}>
            <span className="toggle-dot" />
          </span>
        </button>
        {onToggleSources && (
          <button
            type="button"
            className="icon-btn"
            onClick={onToggleSources}
            aria-label={sourcesCollapsed ? 'Show sources panel' : 'Hide sources panel'}
            title={sourcesCollapsed ? 'Show sources panel' : 'Hide sources panel'}
          >
            <ChevronIcon flip={!sourcesCollapsed} />
          </button>
        )}
      </div>
    </header>
  );
}

export { SUBJECTS };
