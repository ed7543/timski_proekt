"""Tests for backend/services/course_context.py::format_course_context and
backend/routes/chatRoute.py::_get_course_context.

format_course_context() only reads attributes/relationships off a Course
instance, so most cases here build unpersisted, in-memory Course/Recording/
CourseMaterial objects (SQLAlchemy relationship lists work fine as plain
Python attributes without hitting the DB). _get_course_context() actually
queries by id, so those cases need a real, persisted row - same DB-fixture
pattern as test_search_cache.py.
"""
import pytest

from backend.database.models import Course, CourseMaterial, Recording
from backend.database.session import SessionLocal
from backend.routes.chatRoute import _get_course_context
from backend.services.course_context import format_course_context


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def test_format_course_context_returns_empty_for_none():
    assert format_course_context(None) == ""


def test_format_course_context_includes_metadata():
    course = Course(name="Структурно програмирање", code="F23L1W020", semester="semester-1",
                     description="Код на предмет: F23L1W020", source_url="https://example.com/course")
    context = format_course_context(course)
    assert "Структурно програмирање" in context
    assert "F23L1W020" in context
    assert "semester-1" in context
    assert "Код на предмет: F23L1W020" in context
    assert "https://example.com/course" in context


def test_format_course_context_topics_prefer_predavanja_category():
    course = Course(name="Test Course")
    course.recordings = [
        Recording(topic="Циклуси", category="Предавања", video_url="https://v/1"),
        Recording(topic="Функции", category="Предавања", video_url="https://v/2"),
        Recording(topic="Пример задача", category="Аудиториски вежби", video_url="https://v/3"),
    ]
    context = format_course_context(course)
    assert "Циклуси" in context
    assert "Функции" in context
    # Non-lecture category should be excluded once at least one lecture-category topic exists
    assert "Пример задача" not in context


def test_format_course_context_falls_back_to_all_recordings_when_no_lectures():
    course = Course(name="Test Course")
    course.recordings = [
        Recording(topic="Пример задача", category="Аудиториски вежби", video_url="https://v/1"),
    ]
    context = format_course_context(course)
    assert "Пример задача" in context


def test_format_course_context_dedupes_and_sorts_topics():
    course = Course(name="Test Course")
    course.recordings = [
        Recording(topic="Б тема", category="Предавања", video_url="https://v/1"),
        Recording(topic="А тема", category="Предавања", video_url="https://v/2"),
        Recording(topic="А тема", category="Предавања", video_url="https://v/3"),  # duplicate topic
    ]
    context = format_course_context(course)
    lines = [l for l in context.splitlines() if l.startswith("- ")]
    assert lines == ["- А тема", "- Б тема"]


def test_format_course_context_caps_topics_at_40():
    course = Course(name="Test Course")
    course.recordings = [
        Recording(topic=f"Topic {i:03d}", category="Предавања", video_url=f"https://v/{i}")
        for i in range(50)
    ]
    context = format_course_context(course)
    topic_lines = [l for l in context.splitlines() if l.startswith("- Topic")]
    assert len(topic_lines) == 40


def test_format_course_context_includes_materials_with_links():
    course = Course(name="Test Course")
    course.materials = [
        CourseMaterial(title="Solved exercises", category="Дополнителна содржина", url="https://github.com/x/y"),
    ]
    context = format_course_context(course)
    assert "Additional materials" in context
    assert "Solved exercises (Дополнителна содржина): https://github.com/x/y" in context


def test_format_course_context_caps_materials_at_20():
    course = Course(name="Test Course")
    course.materials = [
        CourseMaterial(title=f"Material {i}", url=f"https://example.com/{i}") for i in range(30)
    ]
    context = format_course_context(course)
    material_lines = [l for l in context.splitlines() if l.startswith("- Material")]
    assert len(material_lines) == 20


def test_format_course_context_materials_included_without_recordings():
    """A course with materials but no recordings should still surface them -
    the two sections are independent, not one gated on the other."""
    course = Course(name="Test Course")
    course.materials = [CourseMaterial(title="Notes", url="https://example.com/notes")]
    context = format_course_context(course)
    assert "Notes" in context
    assert "Topics covered" not in context


def test_get_course_context_returns_empty_for_missing_id(db):
    assert _get_course_context(db, None) == ""
    assert _get_course_context(db, 999999) == ""


def test_get_course_context_looks_up_real_course(db):
    course = Course(slug="test-course-context-lookup", name="Lookup Test Course")
    db.add(course)
    db.commit()
    db.refresh(course)
    try:
        context = _get_course_context(db, course.id)
        assert "Lookup Test Course" in context
    finally:
        db.delete(course)
        db.commit()
