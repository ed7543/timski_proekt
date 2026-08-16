import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { listCourses } from '../api/courses';
import type { CourseOut } from '../types/course';
import { ArrowIcon } from '../components/icons';

function formatSemester(semester: string | null): string {
  if (!semester) return 'Other';
  const match = semester.match(/(\d+)/);
  return match ? `Semester ${match[1]}` : semester;
}

export function CoursesPage() {
  const [courses, setCourses] = useState<CourseOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = (query: string) => {
    listCourses(query ? { search: query } : undefined)
      .then((data) => {
        setCourses(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load courses'));
  };

  useEffect(() => {
    load('');
  }, []);

  const onSearchChange = (value: string) => {
    setSearch(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => load(value.trim()), 250);
  };

  const groups = new Map<string, CourseOut[]>();
  (courses || []).forEach((c) => {
    const label = formatSemester(c.semester);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(c);
  });
  const sortedLabels = [...groups.keys()].sort((a, b) => {
    if (a === 'Other') return 1;
    if (b === 'Other') return -1;
    return a.localeCompare(b, undefined, { numeric: true });
  });

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <h1>Course catalog</h1>
            <p className="page-subtitle">
              FINKI subjects, materials, and lecture recordings, sourced from the public{' '}
              <a href="https://finki-hub.com" target="_blank" rel="noreferrer">
                finki-hub.com
              </a>{' '}
              community project — not the official university site. Course descriptions here are metadata
              (code, semester, professors), not full syllabi, since no public source publishes those.
            </p>
          </div>

          <div className="page-toolbar">
            <div className="search-wrap">
              <input
                className="search-input"
                type="text"
                placeholder="Search courses…"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
              />
            </div>
          </div>

          {error && <div className="msg-error" style={{ marginTop: 20 }}>{error}</div>}

          {courses === null && !error && <div className="empty" style={{ marginTop: 24 }}>Loading courses…</div>}

          {courses !== null && courses.length === 0 && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              {search ? `No courses matching "${search}".` : 'No courses have been ingested yet.'}
            </div>
          )}

          {sortedLabels.map((label) => (
            <div className="semester-group" key={label}>
              <div className="section-label" style={{ padding: 0 }}>
                {label}
              </div>
              <div className="course-grid">
                {groups.get(label)!.map((course) => (
                  <Link key={course.id} className="sugg" to={`/courses/${course.id}`}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="sugg-tag">{course.code || course.slug}</div>
                      <div className="sugg-q">{course.name}</div>
                    </div>
                    <ArrowIcon />
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
