import { apiFetchRaw } from './client';

export interface UploadResult {
  url: string;
  resource_type: string | null;
  original_filename: string | null;
}

/** Uploads a single file (PDF, image, or video) for a course material and
 * returns its public URL. Uses apiFetchRaw directly (not apiFetch) because
 * this needs a multipart/form-data body - the browser sets that Content-Type
 * header itself (with the right boundary) when given a FormData body, so we
 * must NOT set our own.
 *
 * `context` controls the backend's size cap (see uploadRoute.py's
 * MAX_UPLOAD_BYTES_BY_CONTEXT): 'material' (default) for premium course
 * submissions, 'note' for the free/unmoderated community-notes path, which
 * gets a much smaller cap since anyone logged in can reach it. */
export async function uploadMaterialFile(
  file: File,
  context: 'material' | 'note' = 'material',
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('context', context);
  const resp = await apiFetchRaw('/api/courses/upload-material', {
    method: 'POST',
    body: formData,
  });
  return resp.json() as Promise<UploadResult>;
}
