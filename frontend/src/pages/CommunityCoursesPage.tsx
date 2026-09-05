import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { useAuth } from '../context/AuthContext';
import { listCourses } from '../api/courses';
import type { CourseOut } from '../types/course';
import { ArrowIcon } from '../components/icons';

function formatPrice(cents: number): string {
  return cents > 0 ? `€${(cents / 100).toFixed(2)}` : 'Free';
}

/** Courses submitted by paying users and approved by an admin - kept in its
 * own tab (own list_courses(source="community") query), separate from the
 * scraped FINKI catalog in CoursesPage. */
export function CommunityCoursesPage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<CourseOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = (query: string) => {
    listCourses({ source: 'community', ...(query ? { search: query } : {}) })
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

  const canSubmit = user?.is_premium || user?.role === 'admin';

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <h1>Community courses</h1>
            <p className="page-subtitle">
              Courses submitted by users and approved by an admin - separate from the scraped FINKI catalog
              under Courses. Anyone with an active subscription can submit one, with materials attached.
            </p>
          </div>

          <div className="page-toolbar">
            <div className="search-wrap">
              <input
                className="search-input"
                type="text"
                placeholder="Search community courses…"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
              />
            </div>
            <Link to="/marketplace/submit" className="login-btn" style={{ flexShrink: 0 }}>
              {canSubmit ? 'Submit a course' : 'Subscribe to submit a course'}
            </Link>
          </div>

          {error && <div className="msg-error" style={{ marginTop: 20 }}>{error}</div>}

          {courses === null && !error && <div className="empty" style={{ marginTop: 24 }}>Loading courses…</div>}

          {courses !== null && courses.length === 0 && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              {search ? `No community courses matching "${search}".` : 'No community courses yet - be the first to submit one.'}
            </div>
          )}

          {courses !== null && courses.length > 0 && (
            <div className="course-grid" style={{ marginTop: 16 }}>
              {courses.map((course) => (
                <Link key={course.id} className="sugg" to={`/community/${course.id}`}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="sugg-tag">
                      {course.code || course.slug} · {formatPrice(course.price_cents)}
                    </div>
                    <div className="sugg-q">{course.name}</div>
                  </div>
                  <ArrowIcon />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
