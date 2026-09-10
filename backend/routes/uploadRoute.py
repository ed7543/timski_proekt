"""Real file uploads for course materials (books/PDFs/videos), backed by
Supabase Storage's free tier (no card required to sign up). Open to any
logged-in user (get_current_user) - uploading a file is a free action, the
same as attaching a pasted link; the meaningful gating happens downstream at
whichever endpoint actually attaches the returned URL somewhere
(POST /api/courses/submit requires a premium subscription, but
POST /api/courses/{id}/notes deliberately doesn't).

The frontend calls this once per file, gets back a URL, and then sends that
URL as either a MaterialLinkIn.url in the /api/courses/submit payload or a
CourseNoteCreate.url in the /api/courses/{id}/notes payload - same shape as
a pasted external link either way, so neither pipeline needs to know or care
whether a URL points at Supabase Storage or somewhere else."""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from supabase import create_client

from backend.database.models import User
from backend.middleware.auth import get_current_user
from backend.middleware.rate_limit import limiter
from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, SUPABASE_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/courses", tags=["courses"])

# 50 MB - Supabase's free-tier default max file size per upload. Applies to
# context="material" (premium course-submission uploads, which legitimately
# includes lecture-style video). context="note" gets a much smaller cap -
# see MAX_UPLOAD_BYTES_BY_CONTEXT - since that path has no premium gate at
# all (any logged-in user can call it) and shouldn't get to spend the same
# storage budget as a vetted submitter.
MAX_UPLOAD_BYTES_BY_CONTEXT = {
    "material": 50 * 1024 * 1024,
    "note": 10 * 1024 * 1024,
}

# Checked against sniffed file bytes (see _sniff_content_type below), not the
# client-supplied Content-Type header, which is trivially spoofable and was
# the whole reason this allowlist was added in the first place - it's meant
# to matter now that this endpoint is reachable by any logged-in user, not
# just a vetted premium submitter.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
}


def _sniff_content_type(head: bytes) -> str | None:
    """Identifies a file by its actual leading bytes (magic numbers),
    independent of whatever Content-Type the client claimed - that header is
    just a multipart form field the uploader fully controls, so trusting it
    for an allowlist meant to keep out disguised/malicious files defeats the
    point. Returns None for anything unrecognized (rejected by the caller).

    .docx/.pptx (both ZIP containers) are only distinguished from a plain PDF
    old-style .doc, or any other ZIP by their own leading bytes, not by
    inspecting the ZIP's internal parts - that's a deliberate scope limit
    (full validation would mean unzipping and reading [Content_Types].xml),
    not a security-critical gap: a mislabeled ZIP still can't execute in a
    browser, which is the actual threat this check exists to block."""
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        return "video/mp4"  # covers .mp4 and .mov (both ISO base media container)
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/msword"  # old binary .doc
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        # ZIP-based Office format - .docx/.pptx are indistinguishable from
        # each other (or a generic .zip) by magic bytes alone; either
        # allowed type is accepted here, actual extension-vs-content
        # mismatches are cosmetic, not a security concern (see docstring).
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None


def _get_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="File uploads are not configured on this server")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@router.post("/upload-material")
@limiter.limit("10/minute")
async def upload_material_file(
    request: Request,
    file: UploadFile,
    context: str = Form("material", description="'material' (default, premium course submissions) or 'note' (community study notes) - controls the size cap"),
    current_user: User = Depends(get_current_user),
):
    """Uploads a single file (PDF, image, or video) to Supabase Storage and
    returns its public URL. The bucket (SUPABASE_STORAGE_BUCKET) must be
    marked Public in the Supabase dashboard for get_public_url() to return a
    directly-usable link. Rate-limited (10/minute per IP) since storage has a
    real cost per call, same reasoning as the billed Gemini quiz endpoint."""
    if context not in MAX_UPLOAD_BYTES_BY_CONTEXT:
        raise HTTPException(status_code=400, detail="context must be 'material' or 'note'")
    max_bytes = MAX_UPLOAD_BYTES_BY_CONTEXT[context]

    contents = await file.read()
    sniffed_type = _sniff_content_type(contents[:64])
    if sniffed_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported or unrecognized file type. "
                   "Allowed: PDF, images (jpg/png/gif/webp), video (mp4/webm/mov), Word docs, PowerPoint slides.",
        )

    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (max {max_bytes // (1024 * 1024)} MB)",
        )

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix
    # Unique path so two people uploading "notes.pdf" never collide. No need
    # to nest a folder here - the bucket itself (SUPABASE_STORAGE_BUCKET) is
    # already dedicated to course materials.
    storage_path = f"{uuid.uuid4().hex}{ext}"

    supabase = _get_client()
    try:
        supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
            storage_path,
            contents,
            {"content-type": sniffed_type},
        )
        public_url = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)
    except Exception as exc:
        logger.exception("Supabase upload failed for %s", original_name)
        raise HTTPException(status_code=502, detail=f"Upload failed: {exc}") from exc

    return {
        "url": public_url,
        "resource_type": sniffed_type,
        "original_filename": original_name,
    }
