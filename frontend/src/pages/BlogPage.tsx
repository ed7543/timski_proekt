import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { useAuth } from '../context/AuthContext';
import { listBlogPosts, deleteBlogPost } from '../api/blog';
import { AddBlogPostModal } from '../components/modals/AddBlogPostModal';
import { BLOG_CATEGORIES } from '../types/blog';
import type { BlogPostOut } from '../types/blog';

const ALL_TAB = 'Сите';
const TABS = [ALL_TAB, ...BLOG_CATEGORIES];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('mk-MK', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** Public resource page - heading matches the nav tab's label ("News &
 * Recommendations" - Marina's call, replacing the earlier "Блог" heading
 * that didn't match it): a grid of curated links pulled in from external
 * sites, split into tabs (Препораки / Конкурси / Пракси и работа / Уписи /
 * Настани - see types/blog.ts::BLOG_CATEGORIES). Nothing here is written by
 * us or by AI - every card's title/excerpt was scraped from the source
 * page, and always links back to it. The disclaimer banner covers every
 * card at once rather than repeating per-card. */
export function BlogPage() {
  const { user } = useAuth();
  const [posts, setPosts] = useState<BlogPostOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [activeTab, setActiveTab] = useState<string>(ALL_TAB);

  const load = () => {
    listBlogPosts()
      .then((data) => {
        setPosts(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load articles'));
  };

  useEffect(() => {
    load();
  }, []);

  const onDelete = async (id: number) => {
    if (!confirm('Да ја отстранам оваа статија?')) return;
    try {
      await deleteBlogPost(id);
      setPosts((prev) => (prev ? prev.filter((p) => p.id !== id) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete article');
    }
  };

  const visiblePosts = posts?.filter((p) => activeTab === ALL_TAB || p.category === activeTab) ?? null;

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <h1>News & Recommendations</h1>
            <p className="page-subtitle">
              Избрани линкови од интернет — статии, конкурси, пракси, уписи и настани. Секоја картичка
              линкува до оригиналниот извор на изворниот сајт.
            </p>
          </div>

          <div className="blog-disclaimer">
            ⚠️ Содржината овде не е наша — секоја статија (наслов и краток опис) е преземена од
            надворешен извор. Кликнете на насловот за целосната, оригинална статија.
          </div>

          <div className="filter-row" style={{ marginTop: 20 }}>
            {TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`filter-btn${activeTab === tab ? ' active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {user?.role === 'admin' && (
            <div className="page-toolbar" style={{ marginTop: 16 }}>
              <button type="button" className="login-btn" onClick={() => setShowAdd(true)}>
                + Додади нова статија
              </button>
            </div>
          )}

          {error && (
            <div className="msg-error" style={{ marginTop: 20 }}>
              {error}
            </div>
          )}

          {visiblePosts === null && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              Се вчитува...
            </div>
          )}

          {visiblePosts !== null && visiblePosts.length === 0 && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              {activeTab === ALL_TAB ? 'Сè уште нема додадени статии.' : `Нема статии во „${activeTab}" сè уште.`}
            </div>
          )}

          {visiblePosts !== null && visiblePosts.length > 0 && (
            <div className="blog-grid">
              {visiblePosts.map((post) => (
                <div className="blog-card" key={post.id}>
                  <a href={post.source_url} target="_blank" rel="noreferrer" className="blog-card-image-wrap">
                    {post.image_url ? (
                      <img src={post.image_url} alt="" className="blog-card-image" />
                    ) : (
                      <div className="blog-card-image blog-card-image-placeholder" />
                    )}
                  </a>
                  <div className="blog-card-body">
                    <div className="blog-card-meta">
                      {post.category && <span className="sugg-tag">{post.category}</span>}
                      <span
                        className={`blog-source-badge ${
                          post.source_name === 'МОН' ? 'blog-source-badge--mon' : 'blog-source-badge--finki'
                        }`}
                      >
                        {post.source_name}
                      </span>
                    </div>
                    <a href={post.source_url} target="_blank" rel="noreferrer" className="blog-card-title">
                      {post.title}
                    </a>
                    {post.excerpt && <p className="blog-card-excerpt">{post.excerpt}</p>}
                    <div className="blog-card-footer">
                      <span>{formatDate(post.created_at)}</span>
                      {user?.role === 'admin' && (
                        <button type="button" className="logout-link" onClick={() => onDelete(post.id)}>
                          Избриши
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showAdd && (
        <AddBlogPostModal
          onClose={() => setShowAdd(false)}
          onCreated={(post) => setPosts((prev) => (prev ? [post, ...prev] : [post]))}
          defaultCategory={activeTab !== ALL_TAB ? activeTab : undefined}
        />
      )}
    </AppShell>
  );
}
