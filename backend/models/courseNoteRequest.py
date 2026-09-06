from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

# Only http(s) links are renderable safely as a plain <a href> in the
# frontend (CourseNotes.tsx) - without this, a value like
# "javascript:fetch(...)" or "data:text/html,<script>..." would pass through
# untouched and execute in another viewer's session the moment they clicked
# the note, since nothing else in this pipeline sanitizes it.
_ALLOWED_URL_SCHEMES = {"http", "https"}


class CourseNoteCreate(BaseModel):
    """Payload for POST /api/courses/{course_id}/notes. `url` can be either a
    pasted external link or the URL returned by POST /api/courses/upload-material
    (Supabase Storage) - same convention as MaterialLinkIn.url."""

    title: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=1000)
    description: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title can't be blank")
        return v

    @field_validator("url")
    @classmethod
    def _url_must_be_http_or_https(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url can't be blank")
        if urlparse(v).scheme.lower() not in _ALLOWED_URL_SCHEMES:
            raise ValueError("url must be an http:// or https:// link")
        return v

    @field_validator("description")
    @classmethod
    def _blank_description_is_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None
