"""Tests for the Medium/Hard quiz difficulty tiers - see courseRoute.py's
generate_lesson_quiz (now takes a `difficulty` query param), gemini_generator.py's
`difficulty` parameter on generate_quiz/build_quiz_prompt, and migration
f7a2c9d14e6b (adds the `quiz_hard` column alongside the original `quiz`).

Mirrors test_lesson_quiz_rate_limit.py's style: gemini_generator.generate_quiz
is monkeypatched so this makes no real (billed) Gemini calls and needs no
GEMINI_API_KEY to run.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database.models import Course, Lesson, User
from backend.database.session import SessionLocal
from backend.main import app
from backend.middleware.rate_limit import limiter

client = TestClient(app)

_FAKE_QUIZ = {
    "questions": [
        {
            "question": "Q?",
            "options": ["a", "b", "c", "d"],
            "correct_option_index": 0,
            "explanation": "E.",
        }
    ]
}


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    # Same reasoning as test_lesson_quiz_rate_limit.py - in-memory slowapi
    # storage persists across tests in the same process.
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def auth_headers_and_lesson():
    email = "quiz-difficulty-test@example.com"
    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()

    resp = client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    course = Course(slug="quiz-difficulty-test-course", name="Test Course")
    db.add(course)
    db.commit()
    db.refresh(course)

    lesson = Lesson(course_id=course.id, order_index=1, topic_title="Тема",
                     documentation="Веќе генерирана документација.")
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    yield headers, course.id, lesson.id

    db.query(Lesson).filter(Lesson.id == lesson.id).delete()
    db.query(Course).filter(Course.id == course.id).delete()
    user = db.query(User).filter(User.email == email).first()
    if user:
        db.delete(user)
    db.commit()
    db.close()


def test_medium_is_the_default_and_writes_only_the_quiz_column(auth_headers_and_lesson):
    headers, course_id, lesson_id = auth_headers_and_lesson

    with patch(
        "backend.routes.courseRoute.gemini_generator.generate_quiz",
        return_value=_FAKE_QUIZ,
    ) as mock_generate:
        resp = client.post(f"/api/courses/{course_id}/lessons/{lesson_id}/quiz", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["quiz"] == _FAKE_QUIZ
    assert body["quiz_hard"] is None
    assert body["has_quiz"] is True
    assert body["has_quiz_hard"] is False
    assert mock_generate.call_args.kwargs["difficulty"] == "medium"


def test_hard_writes_only_quiz_hard_and_leaves_medium_untouched(auth_headers_and_lesson):
    headers, course_id, lesson_id = auth_headers_and_lesson

    with patch(
        "backend.routes.courseRoute.gemini_generator.generate_quiz",
        return_value=_FAKE_QUIZ,
    ) as mock_generate:
        # Generate Medium first, exactly like a real student would ...
        first = client.post(
            f"/api/courses/{course_id}/lessons/{lesson_id}/quiz?difficulty=medium", headers=headers
        )
        # ... then Hard, separately - this must not overwrite Medium.
        resp = client.post(
            f"/api/courses/{course_id}/lessons/{lesson_id}/quiz?difficulty=hard", headers=headers
        )

    assert first.status_code == 200
    assert resp.status_code == 200
    body = resp.json()
    assert body["quiz"] == _FAKE_QUIZ  # from the first (Medium) call, untouched by the second
    assert body["quiz_hard"] == _FAKE_QUIZ
    assert body["has_quiz"] is True
    assert body["has_quiz_hard"] is True
    assert mock_generate.call_args.kwargs["difficulty"] == "hard"


def test_invalid_difficulty_is_rejected_with_400(auth_headers_and_lesson):
    headers, course_id, lesson_id = auth_headers_and_lesson

    resp = client.post(
        f"/api/courses/{course_id}/lessons/{lesson_id}/quiz?difficulty=easy", headers=headers
    )

    assert resp.status_code == 400
