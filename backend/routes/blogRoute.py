from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from backend.database.models import BlogPost, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_admin
from backend.middleware.rate_limit import limiter
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
@limiter.limit("10/minute")
async def create_blog_post(
    request: Request,
    payload: BlogPostCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin-only: paste a link (and optionally pick/type a category), we
    scrape the title/excerpt/image straight from the page's own metadata and
    save it as a new card. Nothing from the article's body is stored beyond
    that short excerpt - the full piece stays on its original site, and the
    card always links back to it.

    Rate-limited (10/minute per IP, same as upload-material) since it makes
    a real outbound HTTP call per request - not just an abuse-prevention
    measure, this route can otherwise be used to probe/hammer arbitrary
    hosts (see blog_fetcher.py's SSRF guard) or hosts on the public internet.

    fetch_article_metadata() is a blocking (sync) call - it's shared as-is
    with the scheduled sync script (scripts/fetch_finki_announcements.py),
    which is plain sync CLI code - so it's offloaded to a worker thread via
    run_in_threadpool rather than run directly on this async def route,
    which would otherwise stall the whole event loop for up to
    FETCH_TIMEOUT_SECONDS on every call."""
    source_url = str(payload.url)
    if db.query(BlogPost.id).filter(BlogPost.source_url == source_url).first():
        raise HTTPException(status_code=409, detail="Оваа статија веќе е додадена.")

    try:
        meta = await run_in_threadpool(fetch_article_metadata, source_url)
    except BlogFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    post = BlogPost(
        title=meta["title"],
        excerpt=meta["excerpt"],
        image_url=meta["image_url"],
        source_url=source_url,
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
