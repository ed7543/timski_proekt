from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.models import Course, CourseMaterial, Recording
from backend.database.session import get_db
from backend.models.courseResponse import CourseDetailOut, CourseMaterialOut, CourseOut, RecordingOut

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("", response_model=list[CourseOut])
async def list_courses(
    semester: Optional[str] = Query(None, description="Filter by semester, e.g. 'semester-1'"),
    search: Optional[str] = Query(None, description="Filter by course name substring"),
    db: Session = Depends(get_db),
):
    """List courses in the public catalog. Read-only, no auth needed."""
    q = db.query(Course)
    if semester:
        q = q.filter(Course.semester == semester)
    if search:
        q = q.filter(Course.name.ilike(f"%{search}%"))
    courses = q.order_by(Course.semester, Course.name).all()
    return [CourseOut.model_validate(c) for c in courses]


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(course_id: int, db: Session = Depends(get_db)):
    course = _get_course_or_404(db, course_id)
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
        material_count=material_count or 0,
        recording_count=recording_count or 0,
    )


@router.get("/{course_id}/materials", response_model=list[CourseMaterialOut])
async def list_course_materials(course_id: int, db: Session = Depends(get_db)):
    _get_course_or_404(db, course_id)
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
):
    _get_course_or_404(db, course_id)
    q = db.query(Recording).filter(Recording.course_id == course_id)
    if category:
        q = q.filter(Recording.category == category)
    recordings = q.order_by(Recording.year, Recording.category, Recording.topic).all()
    return [RecordingOut.model_validate(r) for r in recordings]
