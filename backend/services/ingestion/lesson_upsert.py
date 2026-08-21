"""Idempotent-by-hand DB writes for the lesson-content seeding pipeline
(Lesson, CourseSource).

Unlike upsert.py's Course/Recording/CourseMaterial upserts, `lessons` and
`course_sources` have no unique constraint to key a Postgres
`ON CONFLICT DO UPDATE` off (see alembic revision bc6e93a07557 - both are
plain FK+PK tables), so this does a manual find-then-update-or-insert
instead. That's fine here: seed_lessons.py runs single-process, sequentially,
never concurrently against the same course.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.models import Course, CourseSource, Lesson


def find_course_id(db: Session, course_code: str, course_name_mk: str) -> Optional[int]:
    """Matches a courses_db.json entry to an existing Course row. Tries
    `code` first (matches courses_db.json's course_code), falls back to an
    exact name match - covers the one known edge case (id=38 "Микропроцесорски
    системи" has code=None in the DB, found while checking course counts
    earlier in this project)."""
    course = db.query(Course).filter(Course.code == course_code).first()
    if course:
        return course.id
    course = db.query(Course).filter(Course.name == course_name_mk).first()
    return course.id if course else None


def get_existing_documentation(db: Session, course_id: int, order_index: int) -> Optional[str]:
    """Used by seed_lessons.py to decide whether to skip regenerating a lesson
    that already has documentation (resume support)."""
    lesson = (
        db.query(Lesson)
        .filter(Lesson.course_id == course_id, Lesson.order_index == order_index)
        .first()
    )
    return lesson.documentation if lesson else None


def upsert_lesson(
    db: Session,
    course_id: int,
    order_index: int,
    topic_title: str,
    documentation: Optional[str] = None,
    quiz: Optional[dict] = None,
) -> None:
    """Creates the Lesson row if missing, or updates it in place. Passing
    documentation/quiz=None leaves those columns untouched if the row already
    exists (so a "topic-only" pass - see seed_lessons.py's no-source-course
    handling - never wipes previously generated content)."""
    now = datetime.utcnow()
    lesson = (
        db.query(Lesson)
        .filter(Lesson.course_id == course_id, Lesson.order_index == order_index)
        .first()
    )
    if lesson is None:
        lesson = Lesson(
            course_id=course_id,
            order_index=order_index,
            topic_title=topic_title,
            created_at=now,
            updated_at=now,
        )
        db.add(lesson)
    else:
        lesson.topic_title = topic_title
        lesson.updated_at = now

    if documentation is not None:
        lesson.documentation = documentation
        lesson.documentation_generated_at = now
    if quiz is not None:
        lesson.quiz = quiz
        lesson.quiz_generated_at = now

    db.commit()


def replace_course_sources(
    db: Session,
    course_id: int,
    primary_source: Optional[dict],
    additional_sources: Optional[list],
) -> None:
    """Deletes and re-inserts all CourseSource rows for this course from the
    current courses_db.json source/additional_sources - simplest way to stay
    idempotent without a unique constraint to key an upsert off."""
    db.query(CourseSource).filter(CourseSource.course_id == course_id).delete()
    now = datetime.utcnow()

    def _row(src: dict, is_primary: bool) -> CourseSource:
        return CourseSource(
            course_id=course_id,
            title=src.get("title") or "(без наслов)",
            author=src.get("author"),
            publisher=src.get("publisher"),
            license=src.get("license"),
            url=src.get("url"),
            note=src.get("note"),
            is_primary=is_primary,
            created_at=now,
        )

    if primary_source:
        db.add(_row(primary_source, True))
    for src in additional_sources or []:
        db.add(_row(src, False))
    db.commit()
