import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { useAuth } from '../context/AuthContext';
import { listCourses } from '../api/courses';
import type { CourseOut } from '../types/course';
import { ArrowIcon, SparkleIcon } from '../components/icons';

function formatPrice(cents: number): string {
  return cents > 0 ? `€${(cents / 100).toFixed(2)}` : 'Free';
}

/** Courses submitted by paying users and approved by an admin - kept in its
 * own tab (own list_courses(source="community") query - "community" is the
 * internal/API value, "Marketplace" is just the user-facing label),
 * separate from the scraped FINKI catalog in CoursesPage. */
type PriceFilter = 'all' | 'free' | 'purchased';

const FILTERS: { value: PriceFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'free', label: 'Free' },
  { value: 'purchased', label: 'My purchases' },
];

export function MarketplacePage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<CourseOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<PriceFilter>('all');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = (query: string, priceFilter: PriceFilter) => {
    listCourses({
      source: 'community',
      ...(query ? { search: query } : {}),
      ...(priceFilter !== 'all' ? { price_filter: priceFilter } : {}),
    })
      .then((data) => {
        setCourses(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load courses'));
  };

  useEffect(() => {
    load(search, filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const onSearchChange = (value: string) => {
    setSearch(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => load(value.trim(), filter), 250);
  };

  const canSubmit = user?.is_premium || user?.role === 'admin';

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <div className="page-header-title">
              <h1>Marketplace</h1>
              <SparkleIcon style={{ color: 'var(--muted)' }} />
            </div>
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
                placeholder="Search the marketplace…"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
              />
            </div>
            <Link to={canSubmit ? '/marketplace/submit' : '/subscribe'} className="btn btn-primary" style={{ flexShrink: 0 }}>
              {canSubmit ? 'Submit a course' : 'Subscribe to submit a course'}
            </Link>
          </div>

          <div className="filter-row">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                className={`filter-btn${filter === f.value ? ' active' : ''}`}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {error && <div className="msg-error" style={{ marginTop: 20 }}>{error}</div>}

          {courses === null && !error && <div className="empty" style={{ marginTop: 24 }}>Loading courses…</div>}

          {courses !== null && courses.length === 0 && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              {search ? `No courses matching "${search}".` : 'No marketplace courses yet - be the first to submit one.'}
            </div>
          )}

          {courses !== null && courses.length > 0 && (
            <div className="course-grid" style={{ marginTop: 16 }}>
              {courses.map((course) => (
                <Link key={course.id} className="sugg" to={`/marketplace/${course.id}`}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="sugg-tag">
                      {course.code || course.slug} · {formatPrice(course.price_cents)}
                    </div>
                    <div className="sugg-q">{course.name}</div>
                    {course.submitted_by_name && (
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                        by {course.submitted_by_name}
                      </div>
                    )}
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
