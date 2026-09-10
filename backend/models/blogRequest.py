from typing import Optional

from pydantic import BaseModel, HttpUrl


class BlogPostCreateRequest(BaseModel):
    """Body for POST /api/blog. The admin only ever supplies a link and an
    optional category label - the title, excerpt and image are scraped from
    that page's own metadata (see services/blog_fetcher.py), never typed in
    by hand and never AI-written."""

    url: HttpUrl
    category: Optional[str] = None
