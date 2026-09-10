import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ModalShell } from '../modals/ModalShell';
import { useAuth } from '../../context/AuthContext';
import {
  SparkleIcon,
  PlusIcon,
  ChevronIcon,
  GlobeIcon,
  CopyIcon,
  SummaryIcon,
  BookIcon,
  ChartIcon,
  StoreIcon,
  FileIcon,
  ShieldIcon,
  MoonIcon,
} from '../icons';

interface Slide {
  icon: ReactNode;
  title: string;
  body: ReactNode;
}

const BASE_SLIDES: Slide[] = [
  {
    icon: <SparkleIcon />,
    title: 'Welcome to LearnWise',
    body: 'Your AI tutor for FINKI — ask anything and get sourced, footnoted answers. Here\'s a quick look at what everything does.',
  },
  {
    icon: <PlusIcon />,
    title: 'Start a conversation',
    body: (
      <>
        Click <strong>+ New conversation</strong> in the sidebar, or just press <kbd>N</kbd> anywhere outside a
        text field. Past conversations are listed below it, numbered in the order you started them.
      </>
    ),
  },
  {
    icon: <ChevronIcon />,
    title: 'Chat, Courses, Progress',
    body: 'Switch between pages from the sidebar. Click the arrow at its edge to collapse it down to icons when you want more room to read.',
  },
  {
    icon: <GlobeIcon />,
    title: 'Course, subject & live search',
    body: 'Pick a course or subject at the top of the chat to scope answers to it, and toggle Live search to let LearnWise pull in fresh documentation while it answers.',
  },
  {
    icon: <CopyIcon />,
    title: 'Read-along code',
    body: 'Code the tutor writes is syntax-highlighted like an IDE, with a one-click Copy button right in the header of every block.',
  },
  {
    icon: <SummaryIcon />,
    title: 'The dossier: sources & study tools',
    body: (
      <>
        The right-hand panel lists every cited source behind an answer, numbered as footnotes. Below that,{' '}
        <strong>Study tools</strong> turns the conversation into a Quiz, a Summary, follow-up questions
        (Ask more), related searches (Explore), or a Markdown export.
      </>
    ),
  },
  {
    icon: <BookIcon />,
    title: 'Courses',
    body: 'The FINKI course catalog — subjects, materials, and lecture recordings, sourced from the community-run finki-hub.com project.',
  },
  {
    icon: <ChartIcon />,
    title: 'Progress',
    body: 'Track your quiz scores over time, and see which topics are worth a second look.',
  },
  {
    icon: <StoreIcon />,
    title: 'Marketplace',
    body: 'Courses submitted by other users and approved by an admin — separate from the scraped FINKI catalog. Subscribers can submit their own, with materials attached.',
  },
];

const MY_COURSES_SLIDE: Slide = {
  icon: <FileIcon />,
  title: 'My courses',
  body: 'Everything you\'ve submitted to the Marketplace, whatever its review status — approved, pending, or rejected with a reason. Delete your own submissions from here.',
};

const ADMIN_SLIDE: Slide = {
  icon: <ShieldIcon />,
  title: 'Admin panel',
  body: 'Approve or reject course submissions to the Marketplace. Approved courses go live immediately; rejected ones stay hidden with your reason shown to the submitter.',
};

const CLOSING_SLIDE: Slide = {
  icon: <MoonIcon />,
  title: 'Light or dark, your call',
  body: 'Switch between light and dark mode any time from your avatar menu — right where you found this tour. That\'s the whole tour — happy studying.',
};

export function HelpTourModal({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const [rawIndex, setIndex] = useState(0);

  const slides = useMemo(() => {
    const list = [...BASE_SLIDES];
    if (user?.is_premium || user?.has_submitted_courses) list.push(MY_COURSES_SLIDE);
    if (user?.role === 'admin') list.push(ADMIN_SLIDE);
    list.push(CLOSING_SLIDE);
    return list;
  }, [user]);

  // slides can shrink mid-session (e.g. user cancels premium while the tour
  // is open, dropping the "My courses" slide) - clamp once and use this
  // everywhere below, so the counter/dots/button can't end up referencing
  // an index that no longer exists.
  const index = Math.min(rawIndex, slides.length - 1);
  const slide = slides[index];
  const isFirst = index === 0;
  const isLast = index === slides.length - 1;

  return (
    <ModalShell onClose={onClose} className="tour-modal" maxWidth={440}>
      <div className="rule-row tour-kicker">
        <span className="label">Quick tour</span>
        <span className="rule" />
        <span className="label">
          {index + 1} / {slides.length}
        </span>
      </div>

      <div className="tour-icon">{slide.icon}</div>
      <h2 className="tour-title">{slide.title}</h2>
      <p className="tour-body">{slide.body}</p>

      <div className="tour-dots">
        {slides.map((_, i) => (
          <button
            key={i}
            type="button"
            className={`tour-dot${i === index ? ' active' : ''}`}
            aria-label={`Go to slide ${i + 1}`}
            onClick={() => setIndex(i)}
          />
        ))}
      </div>

      <div className="tour-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Skip
        </button>
        <div className="tour-actions-nav">
          {!isFirst && (
            <button type="button" className="btn btn-secondary" onClick={() => setIndex((i) => i - 1)}>
              Back
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => (isLast ? onClose() : setIndex((i) => i + 1))}
          >
            {isLast ? 'Get started' : 'Next'}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
