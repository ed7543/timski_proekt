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


class CourseDetailOut(CourseOut):
    description: Optional[str] = None
    material_count: int = 0
    recording_count: int = 0


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
