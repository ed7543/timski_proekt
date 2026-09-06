from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.database.models import BlogPost, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_admin
from backend.models.blogRequest import BlogPostCreateRequest
from backend.models.blogResponse import BlogPostOut
from backend.services.blog_fetcher import BlogFetchError, fetch_article_metadata

router = APIRouter(prefix="/api/blog", tags=["blog"])


@router.get("", response_model=list[BlogPostOut])
async def list_blog_posts(db: Session = Depends(get_db)):
    """Public - every curated article, newest first. No auth required: same
    read-only, no-personal-data resource page as the course catalog."""
    posts = (
        db.query(BlogPost)
        .options(joinedload(BlogPost.added_by_user))
        .order_by(BlogPost.created_at.desc())
        .all()
    )
    return [BlogPostOut.model_validate(p) for p in posts]


@router.post("", response_model=BlogPostOut, status_code=201)
async def create_blog_post(
    payload: BlogPostCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin-only: paste a link (and optionally pick/type a category), we
    scrape the title/excerpt/image straight from the page's own metadata and
    save it as a new card. Nothing from the article's body is stored beyond
    that short excerpt - the full piece stays on its original site, and the
    card always links back to it."""
    try:
        meta = fetch_article_metadata(str(payload.url))
    except BlogFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    post = BlogPost(
        title=meta["title"],
        excerpt=meta["excerpt"],
        image_url=meta["image_url"],
        source_url=str(payload.url),
        source_name=meta["source_name"],
        category=(payload.category or "").strip() or None,
        added_by_id=admin.id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return BlogPostOut.model_validate(post)


@router.delete("/{post_id}", status_code=204)
async def delete_blog_post(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Admin-only: remove a bad or mis-scraped card."""
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    db.delete(post)
    db.commit()
