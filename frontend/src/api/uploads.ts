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
 * must NOT set our own. */
export async function uploadMaterialFile(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await apiFetchRaw('/api/courses/upload-material', {
    method: 'POST',
    body: formData,
  });
  return resp.json() as Promise<UploadResult>;
}
