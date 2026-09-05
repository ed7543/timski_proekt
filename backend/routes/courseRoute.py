from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.database.models import Course, CourseMaterial, CoursePurchase, Recording, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_paying_user, get_current_user, get_current_user_optional
from backend.models.courseResponse import AdminCourseOut, CourseDetailOut, CourseMaterialOut, CourseOut, RecordingOut
from backend.models.courseSubmitRequest import CourseSubmitRequest
from backend.utils.slugify import slugify

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _unique_slug(db: Session, name: str, requested: Optional[str]) -> str:
    """Slugs are generated from the course name so submitters never have to
    think about URLs - if `requested` is given (currently unused by the
    frontend form) it's respected as-is instead. Falls back to "-2", "-3"...
    on collision, and to the literal string "course" if the name has no
    sluggable characters at all (e.g. a name that's pure punctuation)."""
    if requested:
        return requested
    base = slugify(name) or "course"
    candidate = base
    suffix = 2
    while db.query(Course).filter(Course.slug == candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _can_view_unapproved(course: Course, viewer: Optional[User]) -> bool:
    """A pending/rejected course is only visible to the person who submitted
    it (so they can see its status/rejection reason) or an admin - everyone
    else gets a 404, same as if it didn't exist."""
    if viewer is None:
        return False
    return viewer.role == "admin" or viewer.id == course.submitted_by_id


def _get_visible_course_or_404(db: Session, course_id: int, viewer: Optional[User]) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.status != "approved" and not _can_view_unapproved(course, viewer):
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _has_course_access(db: Session, course: Course, viewer: Optional[User]) -> bool:
    """Whether `viewer` can see this course's materials/recordings. Free
    courses (price_cents == 0) are open to anyone. Priced courses require
    being the submitter, an admin, or having a CoursePurchase row (see
    routes/billingRoute.py, which creates one on a successful Stripe
    checkout)."""
    if course.price_cents <= 0:
        return True
    if viewer is None:
        return False
    if viewer.role == "admin" or viewer.id == course.submitted_by_id:
        return True
    return (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == viewer.id, CoursePurchase.course_id == course.id)
        .first()
        is not None
    )


@router.get("", response_model=list[CourseOut])
async def list_courses(
    semester: Optional[str] = Query(None, description="Filter by semester, e.g. 'semester-1'"),
    search: Optional[str] = Query(None, description="Filter by course name substring"),
    source: str = Query(
        "official",
        description=(
            "'official' (default) = scraped FINKI catalog (submitted_by_id is null); "
            "'community' = approved user-submitted courses; 'all' = both"
        ),
    ),
    price_filter: Optional[str] = Query(
        None,
        description=(
            "'free' = only price_cents == 0 courses; 'purchased' = only priced "
            "courses the current viewer already has access to (submitted by "
            "them, or bought - see CoursePurchase). 'purchased' requires being "
            "logged in. Omit for no price filtering."
        ),
    ),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """List courses. Read-only (though price_filter="purchased" needs a
    logged-in viewer). Only status="approved" courses are shown here -
    pending/rejected submissions stay invisible until an admin approves them
    (see routes/adminRoute.py). `source` keeps the scraped FINKI catalog and
    user-submitted "community" courses in separate tabs on the frontend
    rather than mixed into one list. Priced community courses still show up
    here (with their price_cents) - only the materials/recordings underneath
    are locked, see _has_course_access. `price_filter` powers the Marketplace
    page's "Free" / "My purchases" filter buttons."""
    q = db.query(Course).filter(Course.status == "approved")
    if source == "official":
        q = q.filter(Course.submitted_by_id.is_(None))
    elif source == "community":
        q = q.filter(Course.submitted_by_id.isnot(None))
    elif source != "all":
        raise HTTPException(status_code=400, detail="source must be one of: official, community, all")
    if semester:
        q = q.filter(Course.semester == semester)
    if search:
        q = q.filter(Course.name.ilike(f"%{search}%"))
    if price_filter == "free":
        q = q.filter(Course.price_cents == 0)
    elif price_filter == "purchased":
        if viewer is None:
            raise HTTPException(status_code=401, detail="Log in to filter by your purchased courses")
        if viewer.role == "admin":
            q = q.filter(Course.price_cents > 0)
        else:
            owned_course_ids = db.query(CoursePurchase.course_id).filter(CoursePurchase.user_id == viewer.id)
            q = q.filter(Course.price_cents > 0).filter(
                or_(Course.submitted_by_id == viewer.id, Course.id.in_(owned_course_ids))
            )
    elif price_filter is not None:
        raise HTTPException(status_code=400, detail="price_filter must be one of: free, purchased")
    courses = q.order_by(Course.semester, Course.name).all()
    return [CourseOut.model_validate(c) for c in courses]


@router.get("/mine", response_model=list[AdminCourseOut])
async def list_my_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every course the current user has ever submitted, regardless of
    status - so they can track pending/approved/rejected and see the
    admin's reason if rejected (there's nowhere else in the app that
    surfaces rejection_reason - this "My courses" page is it). Reuses
    AdminCourseOut since the shape (status/rejection_reason/materials) is
    identical to what the admin queue already returns."""
    courses = (
        db.query(Course)
        .filter(Course.submitted_by_id == current_user.id)
        .order_by(Course.created_at.desc())
        .all()
    )
    return [AdminCourseOut.model_validate(c) for c in courses]


@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently deletes a user-submitted course (any status), along with
    its materials and purchase records (cascade="all, delete-orphan" on
    Course.materials/Course.purchases - see database/models.py). No undo.
    Allowed for the course's own submitter (a professor cleaning up their
    own Marketplace listing) or an admin (moderation) - anyone else gets
    403. Refuses to touch the scraped FINKI catalog (submitted_by_id is
    null) regardless of who's asking - that's not this endpoint's job."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.submitted_by_id is None:
        raise HTTPException(status_code=400, detail="Cannot delete official catalog courses here")
    is_owner = course.submitted_by_id == current_user.id
    if not is_owner and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the course's submitter or an admin can delete it")
    db.delete(course)
    db.commit()


@router.post("/submit", response_model=CourseDetailOut, status_code=201)
async def submit_course(
    payload: CourseSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_paying_user),
):
    """A paying user (is_premium, any role) proposes a new course, with its
    materials attached in the same request, and can optionally set a price
    for students (payload.price in euros, 0 = free). Course + materials are
    created together with status="pending" and are invisible to everyone
    except the submitter/an admin (see _can_view_unapproved) until an admin
    approves it via POST /api/admin/courses/{id}/approve. Note that the
    is_premium subscription (gating this endpoint) and the course's own
    price are deliberately separate: subscribing lets you submit courses at
    all; the price is what students pay to unlock this specific course's
    materials once it's approved.

    NOTE: materials can be either a pasted link or a file uploaded via
    POST /api/courses/upload-material (Supabase Storage-backed - see that route)."""
    slug = _unique_slug(db, payload.name, payload.slug)

    course = Course(
        slug=slug,
        name=payload.name,
        code=payload.code,
        semester=payload.semester,
        description=payload.description,
        source_url=payload.source_url,
        status="pending",
        submitted_by_id=current_user.id,
        price_cents=round(payload.price * 100),
    )
    db.add(course)
    db.flush()  # assigns course.id without ending the transaction, so materials below can reference it

    for m in payload.materials:
        db.add(CourseMaterial(
            course_id=course.id,
            title=m.title,
            url=m.url,
            category=m.category,
            description=m.description,
        ))

    db.commit()
    db.refresh(course)
    return CourseDetailOut(
        id=course.id,
        slug=course.slug,
        name=course.name,
        code=course.code,
        semester=course.semester,
        source_url=course.source_url,
        created_at=course.created_at,
        updated_at=course.updated_at,
        last_scraped_at=course.last_scraped_at,
        description=course.description,
        price_cents=course.price_cents,
        material_count=len(payload.materials),
        recording_count=0,
        locked=False,
        submitted_by_name=current_user.full_name or current_user.email,
    )


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """Course metadata is always visible once approved, regardless of price -
    it's the "product page" (name/description/price/counts). The `locked`
    field tells the frontend whether GET .../materials and .../recordings
    will actually return content or a 402, so it can show a Buy button
    instead of an empty list."""
    course = _get_visible_course_or_404(db, course_id, viewer)
    material_count = db.query(func.count(CourseMaterial.id)).filter(
        CourseMaterial.course_id == course.id
    ).scalar()
    recording_count = db.query(func.count(Recording.id)).filter(
        Recording.course_id == course.id
    ).scalar()
    return CourseDetailOut(
        id=course.id,
        slug=course.slug,
        name=course.name,
        code=course.code,
        semester=course.semester,
        source_url=course.source_url,
        created_at=course.created_at,
        updated_at=course.updated_at,
        last_scraped_at=course.last_scraped_at,
        description=course.description,
        price_cents=course.price_cents,
        material_count=material_count or 0,
        recording_count=recording_count or 0,
        locked=not _has_course_access(db, course, viewer),
        submitted_by_name=course.submitted_by_name,
    )


@router.get("/{course_id}/materials", response_model=list[CourseMaterialOut])
async def list_course_materials(
    course_id: int,
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    course = _get_visible_course_or_404(db, course_id, viewer)
    if not _has_course_access(db, course, viewer):
        raise HTTPException(status_code=402, detail="This course's materials are locked - purchase required")
    materials = (
        db.query(CourseMaterial)
        .filter(CourseMaterial.course_id == course_id)
        .order_by(CourseMaterial.category, CourseMaterial.title)
        .all()
    )
    return [CourseMaterialOut.model_validate(m) for m in materials]


@router.get("/{course_id}/recordings", response_model=list[RecordingOut])
async def list_course_recordings(
    course_id: int,
    category: Optional[str] = Query(None, description="Filter by category, e.g. 'Предавања'"),
    db: Session = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    course = _get_visible_course_or_404(db, course_id, viewer)
    if not _has_course_access(db, course, viewer):
        raise HTTPException(status_code=402, detail="This course's recordings are locked - purchase required")
    q = db.query(Recording).filter(Recording.course_id == course_id)
    if category:
        q = q.filter(Recording.category == category)
    recordings = q.order_by(Recording.year, Recording.category, Recording.topic).all()
    return [RecordingOut.model_validate(r) for r in recordings]
