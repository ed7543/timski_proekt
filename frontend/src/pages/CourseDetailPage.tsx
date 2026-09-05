import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { getCourse, getCourseMaterials, getCourseRecordings } from '../api/courses';
import { createCourseCheckoutSession } from '../api/billing';
import type { CourseDetailOut, CourseMaterialOut, RecordingOut } from '../types/course';
import { ExternalLinkIcon, FileIcon, PlayIcon } from '../components/icons';

function siteFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
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
        <button type="button" className="login-btn" style={{ marginTop: 12 }} disabled={starting} onClick={handleBuy}>
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
    load();

    return () => {
      cancelled = true;
    };
  }, [id, justPurchased]);

  const recordingGroups = new Map<string, RecordingOut[]>();
  recordings.forEach((r) => {
    if (!recordingGroups.has(r.category)) recordingGroups.set(r.category, []);
    recordingGroups.get(r.category)!.push(r);
  });

  // Everything below is Marketplace-only (isCommunity) behavior - grouping
  // materials by the type the submitter picked, and moving "Video"-tagged
  // materials under Recordings. The official FINKI catalog (isCommunity
  // false) must render exactly as it did before: a flat Materials list and
  // its own pre-existing Recordings grouping, untouched.

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
          <Link to={isCommunity ? '/marketplace' : '/courses'} className="course-back">
            ← Back to {isCommunity ? 'the marketplace' : 'catalog'}
          </Link>

          {loading && <div className="empty">Loading course…</div>}
          {error && <div className="msg-error">{error}</div>}

          {course && !loading && !error && (
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

              {course.locked ? (
                <BuyCourseCard courseId={course.id} priceCents={course.price_cents} justPurchased={justPurchased} />
              ) : (
                <>
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
                                <a className="src" href={m.url} target="_blank" rel="noreferrer">
                                  <div className="src-row">
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
                                  </div>
                                </a>
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
                                        <span>{[r.presenter, r.year].filter(Boolean).join(', ') || siteFromUrl(r.video_url)}</span>
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
        </div>
      </div>
    </AppShell>
  );
}
