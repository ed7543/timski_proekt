"""Real file uploads for course materials (books/PDFs/videos), backed by
Supabase Storage's free tier (no card required to sign up). Gated the same
way course submission itself is (get_current_paying_user) - only someone
who could submit a course can upload a file to attach to one.

The frontend calls this once per file, gets back a URL, and then sends that
URL as a normal MaterialLinkIn.url in the /api/courses/submit payload - same
shape as a pasted external link, so the rest of the approval/visibility
pipeline doesn't need to know or care whether a material's URL points at
Supabase Storage or somewhere else."""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from supabase import create_client

from backend.database.models import User
from backend.middleware.auth import get_current_paying_user
from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, SUPABASE_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/courses", tags=["courses"])

# 50 MB - Supabase's free-tier default max file size per upload. Set to
# match reality (unlike our earlier, too-generous 100MB constant) so users
# hit a clear error from *our* validation rather than a confusing one from
# Supabase's API.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _get_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="File uploads are not configured on this server")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@router.post("/upload-material")
async def upload_material_file(
    file: UploadFile,
    current_user: User = Depends(get_current_paying_user),
):
    """Uploads a single file (PDF, image, or video) to Supabase Storage and
    returns its public URL. The bucket (SUPABASE_STORAGE_BUCKET) must be
    marked Public in the Supabase dashboard for get_public_url() to return a
    directly-usable link."""
    supabase = _get_client()

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 50 MB)")

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix
    # Unique path so two people uploading "notes.pdf" never collide. No need
    # to nest a folder here - the bucket itself (SUPABASE_STORAGE_BUCKET) is
    # already dedicated to course materials.
    storage_path = f"{uuid.uuid4().hex}{ext}"

    try:
        supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
            storage_path,
            contents,
            {"content-type": file.content_type or "application/octet-stream"},
        )
        public_url = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
    except Exception as exc:
        logger.exception("Supabase upload failed for %s", original_name)
        raise HTTPException(status_code=502, detail=f"Upload failed: {exc}") from exc

    return {
        "url": public_url,
        "resource_type": file.content_type,
        "original_filename": original_name,
    }
