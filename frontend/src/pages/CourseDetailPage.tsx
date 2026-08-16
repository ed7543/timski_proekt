import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { getCourse, getCourseMaterials, getCourseRecordings } from '../api/courses';
import type { CourseDetailOut, CourseMaterialOut, RecordingOut } from '../types/course';
import { ExternalLinkIcon, FileIcon, PlayIcon } from '../components/icons';

function siteFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);

  const [course, setCourse] = useState<CourseDetailOut | null>(null);
  const [materials, setMaterials] = useState<CourseMaterialOut[]>([]);
  const [recordings, setRecordings] = useState<RecordingOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
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

  const recordingGroups = new Map<string, RecordingOut[]>();
  recordings.forEach((r) => {
    if (!recordingGroups.has(r.category)) recordingGroups.set(r.category, []);
    recordingGroups.get(r.category)!.push(r);
  });

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <Link to="/courses" className="course-back">
            ← Back to catalog
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
                  ))
                )}
              </div>

            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
