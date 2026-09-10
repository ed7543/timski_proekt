import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { addCourseNote, deleteCourseNote, getCourseNotes } from '../../api/courses';
import { uploadMaterialFile } from '../../api/uploads';
import type { CourseNoteOut } from '../../types/course';
import { ExternalLinkIcon, FileIcon, TrashIcon } from '../icons';

function siteFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Community-contributed study notes for a course - always free to view and
 * add to, regardless of whether the course itself is priced/locked (see
 * routes/courseRoute.py::list_course_notes - deliberately never gated by
 * _has_course_access). Fetched and rendered independently of
 * materials/recordings so it still shows even on a locked course page. */
export function CourseNotes({ courseId }: { courseId: number }) {
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [notes, setNotes] = useState<CourseNoteOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    getCourseNotes(courseId)
      .then((n) => {
        if (!cancelled) setNotes(n);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load notes');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const handleFilePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setFormError(null);
    try {
      const result = await uploadMaterialFile(file, 'note');
      setUrl(result.url);
      setUploadedFilename(result.original_filename || file.name);
      if (!title) setTitle(file.name);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !url.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const note = await addCourseNote(courseId, { title: title.trim(), url: url.trim() });
      setNotes((prev) => [note, ...prev]);
      setTitle('');
      setUrl('');
      setUploadedFilename(null);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to add note');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (noteId: number) => {
    const previous = notes;
    setDeleteError(null);
    setNotes((prev) => prev.filter((n) => n.id !== noteId));
    try {
      await deleteCourseNote(courseId, noteId);
    } catch (err) {
      setNotes(previous); // put it back - the delete didn't actually happen
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete note - please try again.');
    }
  };

  return (
    <div className="course-section">
      <div className="sec-head">
        <h3 className="sec-title">Study Notes</h3>
        <span className="sec-sub">{notes.length} items · always free</span>
      </div>
      <div className="lessons-ai-note">
        Contributed by students, for everyone - free to view here even on a priced course.
      </div>
      {deleteError && <div className="msg-error">{deleteError}</div>}

      {loading ? (
        <div className="empty">Loading notes…</div>
      ) : loadError ? (
        <div className="msg-error">{loadError}</div>
      ) : notes.length === 0 ? (
        <div className="empty">No study notes yet - be the first to add one.</div>
      ) : (
        <ol className="src-list">
          {notes.map((n) => (
            <li key={n.id}>
              <div className="src">
                <div className="src-row">
                  <span className="src-num">
                    <FileIcon />
                  </span>
                  <div className="src-body">
                    <a
                      className="src-title"
                      href={n.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ display: 'block' }}
                    >
                      {n.title}
                    </a>
                    <div className="src-meta">
                      <span>{siteFromUrl(n.url)}</span>
                      {n.uploaded_by_name && <span> · {n.uploaded_by_name}</span>}
                    </div>
                    {n.description && <div className="src-desc">{n.description}</div>}
                  </div>
                  <a href={n.url} target="_blank" rel="noreferrer" aria-label="Open note">
                    <ExternalLinkIcon />
                  </a>
                  {user && (user.id === n.uploaded_by_id || user.role === 'admin') && (
                    <button
                      type="button"
                      className="thread-action-btn danger"
                      aria-label="Delete note"
                      onClick={() => handleDelete(n.id)}
                    >
                      <TrashIcon />
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      {user ? (
        <form className="material-row" style={{ marginTop: 12 }} onSubmit={handleAdd}>
          <div className="material-row-fields">
            <input
              className="auth-input"
              type="text"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <input
              className="auth-input"
              type="url"
              placeholder="Paste a link, or upload a file →"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setUploadedFilename(null);
              }}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.webp,.mp4,.webm,.mov"
              style={{ display: 'none' }}
              onChange={handleFilePick}
            />
            <button
              type="button"
              className="btn btn-secondary"
              style={{ flexShrink: 0 }}
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? 'Uploading…' : 'Upload file'}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ flexShrink: 0 }}
              disabled={submitting || uploading || !title.trim() || !url.trim()}
            >
              {submitting ? 'Adding…' : 'Add note'}
            </button>
          </div>
          {uploadedFilename && !uploading && (
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>Uploaded: {uploadedFilename}</div>
          )}
          {formError && <div className="auth-error">{formError}</div>}
        </form>
      ) : (
        <div className="empty" style={{ marginTop: 12 }}>
          <Link to="/login">Log in</Link> to add a study note.
        </div>
      )}
    </div>
  );
}
