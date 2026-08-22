from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.genai import errors as genai_errors
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.models import Course, CourseMaterial, Lesson, Recording, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_user
from backend.models.courseResponse import (
    CourseDetailOut,
    CourseMaterialOut,
    CourseOut,
    LessonDetailOut,
    LessonOut,
    RecordingOut,
)
from backend.services.ingestion import gemini_generator

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _get_lesson_or_404(db: Session, course_id: int, lesson_id: int) -> Lesson:
    lesson = (
        db.query(Lesson)
        .filter(Lesson.id == lesson_id, Lesson.course_id == course_id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def _lesson_detail_out(lesson: Lesson) -> LessonDetailOut:
    return LessonDetailOut(
        id=lesson.id,
        course_id=lesson.course_id,
        order_index=lesson.order_index,
        topic_title=lesson.topic_title,
        has_documentation=bool(lesson.documentation),
        has_quiz=bool(lesson.quiz),
        documentation=lesson.documentation,
        quiz=lesson.quiz,
    )


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


@router.get("/{course_id}/lessons", response_model=list[LessonOut])
async def list_course_lessons(course_id: int, db: Session = Depends(get_db)):
    """Lightweight lesson list for the course page (topic titles + whether each
    already has documentation/a quiz) - read-only, no auth needed, same as
    materials/recordings above."""
    _get_course_or_404(db, course_id)
    lessons = (
        db.query(Lesson)
        .filter(Lesson.course_id == course_id)
        .order_by(Lesson.order_index)
        .all()
    )
    return [
        LessonOut(
            id=l.id,
            course_id=l.course_id,
            order_index=l.order_index,
            topic_title=l.topic_title,
            has_documentation=bool(l.documentation),
            has_quiz=bool(l.quiz),
        )
        for l in lessons
    ]


@router.get("/{course_id}/lessons/{lesson_id}", response_model=LessonDetailOut)
async def get_course_lesson(course_id: int, lesson_id: int, db: Session = Depends(get_db)):
    """Full lesson content (documentation + quiz, if generated) - fetched when
    a student opens one specific lesson."""
    _get_course_or_404(db, course_id)
    lesson = _get_lesson_or_404(db, course_id, lesson_id)
    return _lesson_detail_out(lesson)


@router.post("/{course_id}/lessons/{lesson_id}/quiz", response_model=LessonDetailOut)
async def generate_lesson_quiz(
    course_id: int,
    lesson_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates (or regenerates) the quiz for one lesson on demand, via the
    same Gemini call used by the offline ingestion pipeline
    (gemini_generator.generate_quiz), based on the lesson's already-generated
    documentation. Unlike the read-only GETs above, this requires auth - it
    triggers a real, billed Gemini API call, so it shouldn't be reachable
    anonymously. 400s if the lesson has no documentation yet (nothing to base
    a quiz on)."""
    _get_course_or_404(db, course_id)
    lesson = _get_lesson_or_404(db, course_id, lesson_id)
    if not lesson.documentation:
        raise HTTPException(
            status_code=400,
            detail="This lesson doesn't have generated documentation yet - a quiz can't be generated.",
        )
    try:
        quiz = gemini_generator.generate_quiz(lesson.topic_title, lesson.documentation)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except genai_errors.APIError:
        raise HTTPException(
            status_code=502,
            detail="Quiz generation failed (Gemini API error) - please try again.",
        )
    lesson.quiz = quiz
    lesson.quiz_generated_at = datetime.utcnow()
    db.commit()
    db.refresh(lesson)
    return _lesson_detail_out(lesson)
