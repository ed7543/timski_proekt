"""Tests for lesson_upsert.py - the manual find-then-update-or-insert writes
for Lesson rows (see module docstring: no unique constraint to key an
ON CONFLICT upsert off).
"""
import pytest

from backend.database.models import Course, Lesson
from backend.database.session import SessionLocal
from backend.services.ingestion.lesson_upsert import find_course_id, get_existing_documentation, upsert_lesson


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def course(db):
    c = Course(slug="upsert-test-course", name="Тест предмет", code="TEST999")
    db.add(c)
    db.commit()
    db.refresh(c)
    yield c
    db.query(Lesson).filter(Lesson.course_id == c.id).delete()
    db.query(Course).filter(Course.id == c.id).delete()
    db.commit()


def test_find_course_id_matches_by_code(db, course):
    assert find_course_id(db, "TEST999", "погрешно име") == course.id


def test_find_course_id_falls_back_to_name_when_code_is_none(db):
    # NOTE: don't reuse "Микропроцесорски системи" here (the real course the
    # module docstring's edge case refers to, id=38 in the seeded DB) - a
    # second row with that same name creates an ambiguous match and
    # find_course_id() can return either row, since Course.name has no
    # uniqueness constraint. A clearly-fake name avoids that collision.
    c = Course(slug="upsert-test-no-code", name="Тест-без-код предмет XYZ", code=None)
    db.add(c)
    db.commit()
    db.refresh(c)
    try:
        assert find_course_id(db, "NEPOSTOI", "Тест-без-код предмет XYZ") == c.id
    finally:
        db.delete(c)
        db.commit()


def test_upsert_lesson_creates_new_row(db, course):
    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1", documentation="докс", quiz={"questions": []})
    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson is not None
    assert lesson.documentation == "докс"
    assert lesson.quiz == {"questions": []}


def test_upsert_lesson_with_documentation_none_does_not_wipe_existing_documentation(db, course):
    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1", documentation="постоечка докс")
    # Second call passes documentation=None (e.g. a topic-only pass) - must
    # NOT erase what's already there.
    upsert_lesson(db, course.id, order_index=1, topic_title="Тема 1 (ажурирана)")

    lesson = db.query(Lesson).filter(Lesson.course_id == course.id, Lesson.order_index == 1).first()
    assert lesson.documentation == "постоечка докс"
    assert lesson.topic_title == "Тема 1 (ажурирана)"


def test_get_existing_documentation_returns_none_when_no_lesson(db, course):
    assert get_existing_documentation(db, course.id, order_index=1) is None
