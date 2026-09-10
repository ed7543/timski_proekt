import { useState } from 'react';
import { ModalShell } from './ModalShell';
import { addBlogPost } from '../../api/blog';
import type { BlogPostOut } from '../../types/blog';
import { BLOG_CATEGORIES } from '../../types/blog';

interface Props {
  onClose: () => void;
  onCreated: (post: BlogPostOut) => void;
  /** Pre-selects the category dropdown to whichever tab was open on the
   * Blog page when "+ Додади нова статија" was clicked - "Сите" (no tab
   * selected) falls back to the first real category. */
  defaultCategory?: string;
}

/** Admin-only "+ Додади нова статија" flow: paste a link and pick a
 * category, the backend scrapes the title/excerpt/image itself - nothing
 * about the article's own content is typed by hand here on purpose, so
 * there's no chance of the card's text drifting from what the source page
 * actually says. */
export function AddBlogPostModal({ onClose, onCreated, defaultCategory }: Props) {
  const [url, setUrl] = useState('');
  const [category, setCategory] = useState(defaultCategory || BLOG_CATEGORIES[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!url.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const post = await addBlogPost(url.trim(), category);
      onCreated(post);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add article');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell onClose={onClose} maxWidth={480}>
      <h2>Додади нова статија</h2>
      <p className="modal-subtitle">Вметни линк — насловот и краткиот опис се преземаат автоматски</p>
      <input
        className="search-input"
        style={{ width: '100%', marginTop: 4 }}
        type="url"
        placeholder="https://..."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submit();
        }}
        autoFocus
      />
      <select
        className="search-input"
        style={{ width: '100%', marginTop: 10 }}
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      >
        {BLOG_CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      {error && (
        <div className="msg-error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 20, justifyContent: 'flex-end' }}>
        <button type="button" className="modal-close ghost" onClick={onClose}>
          Откажи
        </button>
        <button type="button" className="login-btn" onClick={submit} disabled={loading || !url.trim()}>
          {loading ? 'Се вчитува…' : 'Додади'}
        </button>
      </div>
    </ModalShell>
  );
}
