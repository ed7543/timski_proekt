from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    code: Optional[str] = None
    semester: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_scraped_at: Optional[datetime] = None
    price_cents: int = 0
    # None for the scraped FINKI catalog; the submitter's display name for a
    # Marketplace course. Read from Course.submitted_by_name (a computed
    # property, not a real column - see database/models.py).
    submitted_by_name: Optional[str] = None


class CourseDetailOut(CourseOut):
    description: Optional[str] = None
    material_count: int = 0
    recording_count: int = 0
    # Whether the current viewer can see materials/recordings right now -
    # always True for a free course; for a priced one, only the submitter,
    # an admin, or someone with a CoursePurchase gets True. Computed
    # per-request in routes/courseRoute.py, not stored.
    locked: bool = False


class CourseMaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    category: Optional[str] = None
    url: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AdminCourseOut(BaseModel):
    """Course view used by the admin approval queue - includes the
    moderation fields that the public CourseOut/CourseDetailOut deliberately
    omit (status, who submitted/reviewed it, and why it was rejected), plus
    the attached materials so an admin can actually look at what was
    submitted before approving/rejecting - not just the course metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    code: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None
    price_cents: int = 0
    status: str
    submitted_by_id: Optional[int] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    materials: list[CourseMaterialOut] = []
    submitted_by_name: Optional[str] = None


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    topic: str
    presenter: Optional[str] = None
    year: Optional[int] = None
    category: str
    video_url: str
    source_page_url: str
    created_at: datetime
    updated_at: datetime


class LessonOut(BaseModel):
    """Lightweight lesson listing (no documentation/quiz body) - used for the
    course-page lesson list, same spirit as CourseMaterialOut/RecordingOut."""

    id: int
    course_id: int
    order_index: int
    topic_title: str
    has_documentation: bool
    has_quiz: bool


class LessonDetailOut(LessonOut):
    """Full lesson content - fetched only when a single lesson is opened, or
    right after quiz generation, not for the list view."""

    documentation: Optional[str] = None
    quiz: Optional[dict] = None
