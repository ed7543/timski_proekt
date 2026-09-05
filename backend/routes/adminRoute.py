from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database.models import Course, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_admin
from backend.models.courseResponse import AdminCourseOut
from backend.models.courseSubmitRequest import CourseRejectRequest
from backend.utils.time import utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_pending_course_or_404(db: Session, course_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.status != "pending":
        raise HTTPException(status_code=400, detail=f"Course is already '{course.status}', not pending")
    return course


@router.get("/courses/pending", response_model=list[AdminCourseOut])
async def list_pending_courses(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Admin review queue: every course submission still awaiting a decision.
    Kept as its own endpoint (rather than folded into list_courses_for_admin
    below) since it's the default view the Admin panel loads on open."""
    courses = (
        db.query(Course)
        .filter(Course.status == "pending")
        .order_by(Course.created_at)
        .all()
    )
    return [AdminCourseOut.model_validate(c) for c in courses]


@router.get("/courses", response_model=list[AdminCourseOut])
async def list_courses_for_admin(
    status: str = Query(
        "all",
        description="'pending' | 'approved' | 'rejected' | 'all' - filters user-submitted courses by moderation status",
    ),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Every user-submitted course (any status), for the Admin panel's
    "All courses" view - the scraped FINKI catalog (submitted_by_id is
    null) is deliberately excluded, since that's managed by the ingestion
    pipeline, not this moderation UI. This is what backs the Delete button:
    an approved/rejected course has nowhere else in the admin UI to be
    removed from, since approve/reject only ever act on pending ones."""
    q = db.query(Course).filter(Course.submitted_by_id.isnot(None))
    if status != "all":
        if status not in ("pending", "approved", "rejected"):
            raise HTTPException(status_code=400, detail="status must be one of: pending, approved, rejected, all")
        q = q.filter(Course.status == status)
    courses = q.order_by(Course.created_at.desc()).all()
    return [AdminCourseOut.model_validate(c) for c in courses]


@router.post("/courses/{course_id}/approve", response_model=AdminCourseOut)
async def approve_course(
    course_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Publish a pending course submission to the public catalog."""
    course = _get_pending_course_or_404(db, course_id)
    course.status = "approved"
    course.reviewed_by_id = admin.id
    course.reviewed_at = utcnow()
    course.rejection_reason = None
    db.commit()
    db.refresh(course)
    return AdminCourseOut.model_validate(course)


@router.post("/courses/{course_id}/reject", response_model=AdminCourseOut)
async def reject_course(
    course_id: int,
    payload: CourseRejectRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Reject a pending course submission, recording why so the submitting
    professor can see it and resubmit."""
    course = _get_pending_course_or_404(db, course_id)
    course.status = "rejected"
    course.reviewed_by_id = admin.id
    course.reviewed_at = utcnow()
    course.rejection_reason = payload.reason
    db.commit()
    db.refresh(course)
    return AdminCourseOut.model_validate(course)
