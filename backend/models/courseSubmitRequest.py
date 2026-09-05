from typing import Optional

from pydantic import BaseModel, Field


class MaterialLinkIn(BaseModel):
    """One material (book/PDF/video/notes/etc.) attached to a course
    submission. `url` can be either a pasted external link or the URL
    returned by POST /api/courses/upload-material (Supabase Storage) - both look
    identical from here on out."""

    title: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class CourseSubmitRequest(BaseModel):
    """Payload a paying user sends to propose a new course, materials
    included. Starts life as status="pending" and only becomes visible
    (course + materials together) once an admin approves it (see
    routes/adminRoute.py)."""

    # Optional - auto-generated from `name` if omitted (see
    # routes/courseRoute.py::submit_course). Exposed mainly so a resubmission
    # can pin a specific slug if it ever needs to; the form doesn't ask for it.
    slug: Optional[str] = Field(None, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    semester: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    source_url: Optional[str] = Field(None, max_length=500)
    materials: list[MaterialLinkIn] = Field(default_factory=list)
    # In euros, e.g. 4.99. 0 (default) = free. Converted to price_cents when
    # the Course row is created - see routes/courseRoute.py::submit_course.
    price: float = Field(0, ge=0, le=1000)


class CourseRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Shown back to the submitting professor")
