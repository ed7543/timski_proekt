import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { useAuth } from '../context/AuthContext';
import { submitCourse } from '../api/courses';
import { uploadMaterialFile } from '../api/uploads';
import type { MaterialLinkIn } from '../types/course';

let nextRowId = 1;

const MATERIAL_TYPES = ['Video', 'Book', 'Presentation', 'Notes', 'Other'];

interface MaterialRow extends MaterialLinkIn {
  _rowId: number;
  _uploading: boolean;
  _uploadError: string | null;
  _uploadedFilename: string | null;
}

function emptyMaterialRow(): MaterialRow {
  return {
    _rowId: nextRowId++,
    title: '',
    url: '',
    category: '',
    description: '',
    _uploading: false,
    _uploadError: null,
    _uploadedFilename: null,
  };
}

function GoPremiumCard() {
  return (
    <div className="empty" style={{ marginTop: 24, textAlign: 'left' }}>
      <p style={{ margin: 0 }}>Submitting a course requires an active subscription.</p>
      <Link to="/subscribe" className="login-btn" style={{ marginTop: 12, display: 'inline-block' }}>
        Choose a plan
      </Link>
    </div>
  );
}

function MaterialRowInput({
  row,
  onChange,
  onRemove,
  removable,
}: {
  row: MaterialRow;
  onChange: (patch: Partial<MaterialRow>) => void;
  onRemove: () => void;
  removable: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onChange({ _uploading: true, _uploadError: null });
    try {
      const result = await uploadMaterialFile(file);
      onChange({
        url: result.url,
        title: row.title || file.name,
        _uploading: false,
        _uploadedFilename: result.original_filename || file.name,
      });
    } catch (err) {
      onChange({ _uploading: false, _uploadError: err instanceof Error ? err.message : 'Upload failed' });
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="material-row">
      <div className="material-row-fields">
        <input
          className="auth-input"
          type="text"
          placeholder="Title"
          value={row.title}
          onChange={(e) => onChange({ title: e.target.value })}
        />
        <select
          className="auth-input"
          value={row.category || ''}
          onChange={(e) => onChange({ category: e.target.value })}
        >
          <option value="">Type…</option>
          {MATERIAL_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="material-row-fields">
        <input
          className="auth-input"
          type="url"
          placeholder="Paste a link, or upload a file →"
          style={{ flex: 1 }}
          value={row.url}
          onChange={(e) => onChange({ url: e.target.value, _uploadedFilename: null })}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,image/*,video/*"
          style={{ display: 'none' }}
          onChange={handleFilePick}
        />
        <button
          type="button"
          className="modal-close ghost"
          style={{ flexShrink: 0 }}
          disabled={row._uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {row._uploading ? 'Uploading…' : 'Upload file'}
        </button>
        <button type="button" className="modal-close ghost" style={{ flexShrink: 0 }} onClick={onRemove} disabled={!removable}>
          Remove
        </button>
      </div>

      <textarea
        className="auth-input"
        rows={2}
        placeholder="Description (optional)"
        value={row.description || ''}
        onChange={(e) => onChange({ description: e.target.value })}
      />

      {row._uploadedFilename && !row._uploading && (
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>Uploaded: {row._uploadedFilename}</div>
      )}
      {row._uploadError && <div className="auth-error" style={{ marginTop: 4 }}>{row._uploadError}</div>}
    </div>
  );
}

export function SubmitCoursePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [semester, setSemester] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('0');
  const [materials, setMaterials] = useState<MaterialRow[]>([emptyMaterialRow()]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = user?.is_premium || user?.role === 'admin';

  if (user && !canSubmit) {
    return (
      <AppShell sidebar={<CourseNavSidebar />}>
        <div className="body">
          <div className="page-container" style={{ maxWidth: 480 }}>
            <div className="page-header">
              <h1>Submit a course</h1>
              <p className="page-subtitle">
                Anyone can submit a course for review once they've subscribed - it's not tied to being a
                professor.
              </p>
            </div>
            <GoPremiumCard />
          </div>
        </div>
      </AppShell>
    );
  }

  const updateMaterial = (rowId: number, patch: Partial<MaterialRow>) => {
    setMaterials((prev) => prev.map((m) => (m._rowId === rowId ? { ...m, ...patch } : m)));
  };

  const addMaterialRow = () => setMaterials((prev) => [...prev, emptyMaterialRow()]);
  const removeMaterialRow = (rowId: number) =>
    setMaterials((prev) => (prev.length > 1 ? prev.filter((m) => m._rowId !== rowId) : prev));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (materials.some((m) => m._uploading)) {
      setError('Wait for uploads to finish before submitting.');
      return;
    }

    setSubmitting(true);
    try {
      const cleanMaterials = materials
        .filter((m) => m.title.trim() && m.url.trim())
        .map((m) => ({
          title: m.title.trim(),
          url: m.url.trim(),
          category: m.category?.trim() || null,
          description: m.description?.trim() || null,
        }));

      await submitCourse({
        name: name.trim(),
        code: code.trim() || null,
        semester: semester.trim() || null,
        description: description.trim() || null,
        materials: cleanMaterials,
        price: Number(price) || 0,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit course');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container" style={{ maxWidth: 620 }}>
          <div className="page-header">
            <h1>Submit a course</h1>
            <p className="page-subtitle">
              Your submission (course details + materials) is reviewed by an admin before it appears in the
              Marketplace. You'll be able to see whether it was approved or rejected once reviewed.
            </p>
          </div>

          {success ? (
            <div className="empty" style={{ marginTop: 24 }}>
              Submitted — it's now pending admin review.
              <div style={{ marginTop: 12 }}>
                <button type="button" className="login-btn" onClick={() => navigate('/marketplace')}>
                  Back to Marketplace
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="submit-course-form">
              {error && <div className="auth-error">{error}</div>}

              <div className="auth-field">
                <label>Course name</label>
                <input className="auth-input" type="text" required value={name} onChange={(e) => setName(e.target.value)} />
              </div>

              <div className="submit-course-row">
                <div className="auth-field" style={{ flex: 1 }}>
                  <label>Course code (optional)</label>
                  <input className="auth-input" type="text" value={code} onChange={(e) => setCode(e.target.value)} />
                </div>
                <div className="auth-field" style={{ flex: 1 }}>
                  <label>Semester (optional)</label>
                  <input
                    className="auth-input"
                    type="text"
                    placeholder="e.g. semester-1"
                    value={semester}
                    onChange={(e) => setSemester(e.target.value)}
                  />
                </div>
                <div className="auth-field" style={{ flex: 1 }}>
                  <label>Price (EUR, 0 = free)</label>
                  <input
                    className="auth-input"
                    type="number"
                    min="0"
                    step="0.01"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                  />
                </div>
              </div>

              <div className="auth-field">
                <label>Description (optional)</label>
                <textarea className="auth-input" rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>

              <div className="auth-field">
                <label>Materials (books, PDFs, videos)</label>
                {materials.map((m) => (
                  <MaterialRowInput
                    key={m._rowId}
                    row={m}
                    onChange={(patch) => updateMaterial(m._rowId, patch)}
                    onRemove={() => removeMaterialRow(m._rowId)}
                    removable={materials.length > 1}
                  />
                ))}
                <button type="button" className="modal-close ghost" onClick={addMaterialRow}>
                  + Add another material
                </button>
              </div>

              <button className="auth-submit" type="submit" disabled={submitting} style={{ marginTop: 12 }}>
                {submitting ? 'Submitting…' : 'Submit for review'}
              </button>
            </form>
          )}
        </div>
      </div>
    </AppShell>
  );
}
