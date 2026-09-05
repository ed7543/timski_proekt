import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { LessonDetail } from '../components/courses/LessonDetail';
import { getCourse, getCourseLessons, getCourseMaterials, getCourseRecordings } from '../api/courses';
import type { CourseDetailOut, CourseMaterialOut, LessonOut, RecordingOut } from '../types/course';
import { BookIcon, ExternalLinkIcon, FileIcon, PlayIcon } from '../components/icons';

function siteFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

// Passed-quiz state is a per-browser convenience (no backend field for it yet) -
// stored per course so it survives reloads without needing a DB migration.
function passedLessonsStorageKey(courseId: number): string {
  return `learnwise:passed-lessons:${courseId}`;
}

function loadPassedLessons(courseId: number): Set<number> {
  try {
    const raw = localStorage.getItem(passedLessonsStorageKey(courseId));
    const ids = raw ? (JSON.parse(raw) as number[]) : [];
    return new Set(ids);
  } catch {
    return new Set();
  }
}

function savePassedLessons(courseId: number, ids: Set<number>): void {
  try {
    localStorage.setItem(passedLessonsStorageKey(courseId), JSON.stringify([...ids]));
  } catch {
    // ignore (private browsing / storage disabled) - passed-state just won't persist
  }
}

export function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);

  const [course, setCourse] = useState<CourseDetailOut | null>(null);
  const [materials, setMaterials] = useState<CourseMaterialOut[]>([]);
  const [recordings, setRecordings] = useState<RecordingOut[]>([]);
  const [lessons, setLessons] = useState<LessonOut[]>([]);
  const [lessonsLoading, setLessonsLoading] = useState(true);
  const [lessonsError, setLessonsError] = useState<string | null>(null);
  const [selectedLesson, setSelectedLesson] = useState<LessonOut | null>(null);
  const [openQuizDirectly, setOpenQuizDirectly] = useState(false);
  const [passedLessonIds, setPassedLessonIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedLesson(null);
    setPassedLessonIds(loadPassedLessons(id));
    Promise.all([getCourse(id), getCourseMaterials(id), getCourseRecordings(id)])
      .then(([c, m, r]) => {
        if (cancelled) return;
        setCourse(c);
        setMaterials(m);
        setRecordings(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load course');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Fetched independently from the core course/materials/recordings above -
  // lessons is the newest, least battle-tested endpoint, and a failure or
  // slowness here should never take down a course page that otherwise works
  // fine (materials/recordings existed and worked before lessons did).
  useEffect(() => {
    let cancelled = false;
    setLessonsLoading(true);
    setLessonsError(null);
    getCourseLessons(id)
      .then((l) => {
        if (!cancelled) setLessons(l);
      })
      .catch((err) => {
        if (!cancelled) setLessonsError(err instanceof Error ? err.message : 'Failed to load lessons');
      })
      .finally(() => {
        if (!cancelled) setLessonsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const recordingGroups = new Map<string, RecordingOut[]>();
  recordings.forEach((r) => {
    if (!recordingGroups.has(r.category)) recordingGroups.set(r.category, []);
    recordingGroups.get(r.category)!.push(r);
  });

  const openLesson = (lesson: LessonOut, quizDirectly: boolean) => {
    setSelectedLesson(lesson);
    setOpenQuizDirectly(quizDirectly);
  };

  const handleQuizPassed = (lessonId: number) => {
    setPassedLessonIds((prev) => {
      if (prev.has(lessonId)) return prev;
      const next = new Set(prev);
      next.add(lessonId);
      savePassedLessons(id, next);
      return next;
    });
  };

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          {!selectedLesson && (
            <Link to="/courses" className="course-back">
              ← Back to catalog
            </Link>
          )}

          {loading && <div className="empty">Loading course…</div>}
          {error && <div className="msg-error">{error}</div>}

          {course && !loading && !error && (
            <>
              {!selectedLesson && (
                <>
                  <div className="page-header">
                    <h1>{course.name}</h1>
                    <div className="course-meta-row">
                      {course.code && <span className="course-meta-pill">{course.code}</span>}
                      {course.semester && <span className="course-meta-pill">{course.semester}</span>}
                      <span className="course-meta-pill">{course.recording_count} recordings</span>
                      <span className="course-meta-pill">{course.material_count} materials</span>
                    </div>
                  </div>

                  {course.description && <p className="course-desc">{course.description}</p>}

                  <div className="course-caveat">
                    This overview is built from course metadata and real lecture-recording topics, not an official
                    syllabus — no public FINKI source publishes full curricula. Sourced from{' '}
                    {course.source_url ? (
                      <a href={course.source_url} target="_blank" rel="noreferrer">
                        finki-hub.com
                      </a>
                    ) : (
                      'finki-hub.com'
                    )}
                    .
                  </div>
                </>
              )}

              {selectedLesson ? (
                <LessonDetail
                  courseId={id}
                  lesson={selectedLesson}
                  onBack={() => setSelectedLesson(null)}
                  autoOpenQuiz={openQuizDirectly}
                  onQuizPassed={handleQuizPassed}
                />
              ) : (
                <>
                  <div className="course-section">
                    <div className="sec-head">
                      <h3 className="sec-title">Lessons</h3>
                      <span className="sec-sub">{lessons.length} items</span>
                    </div>
                    <div className="lessons-ai-note">
                      All lesson content below is generated by an AI model, based on the source materials available
                      for this course.
                    </div>
                    {lessonsLoading ? (
                      <div className="empty">Loading lessons…</div>
                    ) : lessonsError ? (
                      <div className="msg-error">{lessonsError}</div>
                    ) : lessons.length === 0 ? (
                      <div className="empty">No lessons generated for this course yet.</div>
                    ) : (
                      <ol className="src-list">
                        {lessons.map((l) => {
                          const passed = passedLessonIds.has(l.id);
                          return (
                            <li key={l.id}>
                              <div
                                className={`src src-clickable src-lesson${passed ? ' src-passed' : ''}`}
                                role="button"
                                tabIndex={0}
                                onClick={() => openLesson(l, false)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' || e.key === ' ') openLesson(l, false);
                                }}
                              >
                                <div className="src-row">
                                  <span className="src-num">
                                    <BookIcon />
                                  </span>
                                  <div className="src-body">
                                    <div className="src-title">{l.topic_title}</div>
                                    <div className="src-meta">
                                      <span>{l.has_documentation ? 'documentation available' : 'no documentation yet'}</span>
                                      {l.has_quiz && <span> · quiz available</span>}
                                      {passed && <span> · quiz passed</span>}
                                    </div>
                                  </div>
                                  <button
                                    type="button"
                                    className="try-quiz-btn"
                                    disabled={!l.has_documentation}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openLesson(l, true);
                                    }}
                                  >
                                    Try Quiz
                                  </button>
                                </div>
                              </div>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                  </div>

                  <div className="course-section">
                    <div className="sec-head">
                      <h3 className="sec-title">Materials</h3>
                      <span className="sec-sub">{materials.length} items</span>
                    </div>
                    {materials.length === 0 ? (
                      <div className="empty">No standalone materials ingested for this course yet.</div>
                    ) : (
                      <ol className="src-list">
                        {materials.map((m) => (
                          <li key={m.id}>
                            <a className="src" href={m.url} target="_blank" rel="noreferrer">
                              <div className="src-row">
                                <span className="src-num">
                                  <FileIcon />
                                </span>
                                <div className="src-body">
                                  <div className="src-title">{m.title}</div>
                                  <div className="src-meta">
                                    {m.category && <span>{m.category} · </span>}
                                    <span>{siteFromUrl(m.url)}</span>
                                  </div>
                                </div>
                                <ExternalLinkIcon />
                              </div>
                            </a>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>

                  <div className="course-section">
                    <div className="sec-head">
                      <h3 className="sec-title">Recordings</h3>
                      <span className="sec-sub">{recordings.length} total</span>
                    </div>
                    {recordings.length === 0 ? (
                      <div className="empty">No lecture recordings ingested for this course yet.</div>
                    ) : (
                      [...recordingGroups.entries()].map(([category, items]) => (
                        <div className="recording-group" key={category}>
                          <div className="recording-group-label">{category.toUpperCase()}</div>
                          <ol className="src-list">
                            {items.map((r) => (
                              <li key={r.id}>
                                <a className="src" href={r.video_url} target="_blank" rel="noreferrer">
                                  <div className="src-row">
                                    <span className="src-num">
                                      <PlayIcon />
                                    </span>
                                    <div className="src-body">
                                      <div className="src-title">{r.topic}</div>
                                      <div className="src-meta">
                                        <span>
                                          {[r.presenter, r.year].filter(Boolean).join(', ') || siteFromUrl(r.video_url)}
                                        </span>
                                      </div>
                                    </div>
                                    <ExternalLinkIcon />
                                  </div>
                                </a>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
