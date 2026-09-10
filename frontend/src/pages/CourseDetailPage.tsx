import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { CourseNotes } from '../components/courses/CourseNotes';
import { LessonDetail } from '../components/courses/LessonDetail';
import { MaterialStudyGuide } from '../components/courses/MaterialStudyGuide';
import { getCourse, getCourseLessons, getCourseMaterials, getCourseRecordings } from '../api/courses';
import { createCourseCheckoutSession } from '../api/billing';
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

function formatPrice(cents: number): string {
  return `€${(cents / 100).toFixed(2)}`;
}

function BuyCourseCard({ courseId, priceCents, justPurchased }: { courseId: number; priceCents: number; justPurchased: boolean }) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleBuy = async () => {
    setError(null);
    setStarting(true);
    try {
      const { checkout_url } = await createCourseCheckoutSession(courseId);
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setStarting(false);
    }
  };

  return (
    <div className="empty" style={{ marginTop: 8, textAlign: 'left' }}>
      <p style={{ margin: 0 }}>
        {justPurchased
          ? 'Confirming your purchase with Stripe… this can take a few seconds, refresh if it stays locked.'
          : `Materials and recordings are locked until you buy this course for ${formatPrice(priceCents)}.`}
      </p>
      {error && <div className="auth-error" style={{ marginTop: 12 }}>{error}</div>}
      {!justPurchased && (
        <button type="button" className="btn btn-primary" style={{ marginTop: 12 }} disabled={starting} onClick={handleBuy}>
          {starting ? 'Redirecting…' : `Buy for ${formatPrice(priceCents)}`}
        </button>
      )}
    </div>
  );
}

export function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);
  const location = useLocation();
  const isCommunity = location.pathname.startsWith('/marketplace');
  const [searchParams] = useSearchParams();
  const justPurchased = searchParams.get('purchased') === '1';

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
    let attempts = 0;

    const load = async () => {
      try {
        const c = await getCourse(id);
        if (cancelled) return;
        setCourse(c);

        if (!c.locked) {
          const [m, r] = await Promise.all([getCourseMaterials(id), getCourseRecordings(id)]);
          if (cancelled) return;
          setMaterials(m);
          setRecordings(r);
          setError(null);
          setLoading(false);
          return;
        }

        // Locked right after a Stripe redirect might just mean the webhook
        // hasn't landed yet - poll a few times before settling on "locked".
        if (justPurchased && attempts < 5) {
          attempts += 1;
          setTimeout(load, 1500);
          return;
        }

        setError(null);
        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load course');
          setLoading(false);
        }
      }
    };

    setLoading(true);
    setError(null);
    setSelectedLesson(null);
    setPassedLessonIds(loadPassedLessons(id));
    load();

    return () => {
      cancelled = true;
    };
  }, [id, justPurchased]);

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

  // Everything below is Marketplace-only (isCommunity) behavior - grouping
  // materials by the type the submitter picked, and moving "Video"-tagged
  // materials under Recordings. The official FINKI catalog (isCommunity
  // false) must render exactly as it did before: a flat Materials list and
  // its own pre-existing Recordings grouping, untouched. Lessons (below) only
  // ever exist for ingested official-catalog courses, so that section is
  // gated to !isCommunity.

  // A material tagged "Video" in the submit form is a lecture-style video,
  // not a book/notes/slide deck - it reads better living under Recordings
  // than under Materials, so it's pulled out here and rendered as its own
  // group there (see below) instead of in the Materials list.
  const videoMaterials = isCommunity ? materials.filter((m) => m.category?.trim().toLowerCase() === 'video') : [];
  const nonVideoMaterials = isCommunity
    ? materials.filter((m) => m.category?.trim().toLowerCase() !== 'video')
    : materials;

  // Grouped by whatever type the submitter picked for each material
  // (Book/Presentation/Notes/Other - see SubmitCoursePage) so a course's
  // books and slides don't sit in one undifferentiated list. Materials with
  // no category fall into an "Other" bucket at the end. Only applied for
  // Marketplace courses - see note above.
  const materialGroups = new Map<string, CourseMaterialOut[]>();
  if (isCommunity) {
    nonVideoMaterials.forEach((m) => {
      const label = m.category?.trim() || 'Other';
      if (!materialGroups.has(label)) materialGroups.set(label, []);
      materialGroups.get(label)!.push(m);
    });
  }
  const materialGroupEntries = [...materialGroups.entries()].sort(([a], [b]) => {
    if (a === 'Other') return 1;
    if (b === 'Other') return -1;
    return a.localeCompare(b);
  });

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          {!selectedLesson && (
            <Link to={isCommunity ? '/marketplace' : '/courses'} className="course-back">
              ← Back to {isCommunity ? 'the marketplace' : 'catalog'}
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
                      <span className={`course-meta-pill${isCommunity ? ' course-price-pill' : ''}`}>
                        {course.price_cents > 0 ? formatPrice(course.price_cents) : 'Free'}
                      </span>
                    </div>
                  </div>

                  {course.description && <p className="course-desc">{course.description}</p>}

                  <CourseNotes courseId={id} />

                  {isCommunity ? (
                    <div className="course-caveat">
                      Submitted{course.submitted_by_name ? ` by ${course.submitted_by_name}` : ' by a user'} and approved
                      by an admin - not part of the scraped FINKI catalog.
                      {course.source_url && (
                        <>
                          {' '}
                          See{' '}
                          <a href={course.source_url} target="_blank" rel="noreferrer">
                            source
                          </a>
                          .
                        </>
                      )}
                    </div>
                  ) : (
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
                  )}
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
                  {course.locked ? (
                    <BuyCourseCard courseId={course.id} priceCents={course.price_cents} justPurchased={justPurchased} />
                  ) : (
                    <>
                      {!isCommunity && (
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
                      )}
    
                      <div className="course-section">
                        <div className="sec-head">
                          <h3 className="sec-title">Materials</h3>
                          <span className="sec-sub">{nonVideoMaterials.length} items</span>
                        </div>
                        {nonVideoMaterials.length === 0 ? (
                          <div className="empty">No standalone materials ingested for this course yet.</div>
                        ) : isCommunity ? (
                          materialGroupEntries.map(([category, items]) => (
                            <div className="recording-group" key={category}>
                              <div className="recording-group-label">{category.toUpperCase()}</div>
                              <ol className="src-list">
                                {items.map((m) => (
                                  <li key={m.id}>
                                    <div className="src">
                                      <div className="src-row">
                                        <a className="src-link" href={m.url} target="_blank" rel="noreferrer">
                                          <span className="src-num">
                                            <FileIcon />
                                          </span>
                                          <div className="src-body">
                                            <div className="src-title">{m.title}</div>
                                            <div className="src-meta">
                                              <span>{siteFromUrl(m.url)}</span>
                                            </div>
                                            {m.description && <div className="src-desc">{m.description}</div>}
                                          </div>
                                          <ExternalLinkIcon />
                                        </a>
                                        <MaterialStudyGuide courseId={id} material={m} />
                                      </div>
                                    </div>
                                  </li>
                                ))}
                              </ol>
                            </div>
                          ))
                        ) : (
                          // Official FINKI catalog - original flat list, unchanged.
                          <ol className="src-list">
                            {nonVideoMaterials.map((m) => (
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
                          <span className="sec-sub">{recordings.length + videoMaterials.length} total</span>
                        </div>
                        {recordings.length === 0 && videoMaterials.length === 0 ? (
                          <div className="empty">No lecture recordings ingested for this course yet.</div>
                        ) : (
                          <>
                            {videoMaterials.length > 0 && (
                              <div className="recording-group">
                                <div className="recording-group-label">VIDEO</div>
                                <ol className="src-list">
                                  {videoMaterials.map((m) => (
                                    <li key={m.id}>
                                      <a className="src" href={m.url} target="_blank" rel="noreferrer">
                                        <div className="src-row">
                                          <span className="src-num">
                                            <PlayIcon />
                                          </span>
                                          <div className="src-body">
                                            <div className="src-title">{m.title}</div>
                                            <div className="src-meta">
                                              <span>{siteFromUrl(m.url)}</span>
                                            </div>
                                            {m.description && <div className="src-desc">{m.description}</div>}
                                          </div>
                                          <ExternalLinkIcon />
                                        </div>
                                      </a>
                                    </li>
                                  ))}
                                </ol>
                              </div>
                            )}
                            {[...recordingGroups.entries()].map(([category, items]) => (
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
                            ))}
                          </>
                        )}
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
