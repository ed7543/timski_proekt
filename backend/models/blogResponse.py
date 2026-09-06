from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BlogPostOut(BaseModel):
    """A curated external article card for the public Blog page - see
    database/models.py::BlogPost. Every field describing the article's
    content (title/excerpt/image) was scraped from the source page itself,
    not written by us; source_url/source_name are what let the Blog page
    credit and link back to the original. `category` is the only field an
    admin actually types (a free-text label like "Препораки"/"Конкурси" -
    see routes/blogRoute.py), used purely to group cards on the page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    source_url: str
    source_name: str
    category: Optional[str] = None
    added_by_name: Optional[str] = None
    created_at: datetime
