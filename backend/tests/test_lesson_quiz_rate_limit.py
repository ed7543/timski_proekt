"""Regression test for the missing rate limit on a billed endpoint.

POST /api/courses/{id}/lessons/{id}/quiz triggers a real, billed Gemini API
call per request and previously had no rate limit at all. Fixed by adding
@limiter.limit("5/minute") (courseRoute.py). This mirrors how evie verified
it manually - hit the endpoint 7 times with a real token, got 5 real
responses then 429 on attempts 6 and 7 - except gemini_generator.generate_quiz
is monkeypatched so the test doesn't make real (billed) API calls and doesn't
need a GEMINI_API_KEY.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database.models import Course, Lesson, User
from backend.database.session import SessionLocal
from backend.main import app
from backend.middleware.rate_limit import limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    # In-memory slowapi storage persists across tests in the same process -
    # reset it so this test's count doesn't depend on what ran before it.
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def auth_headers_and_lesson():
    email = "quiz-rate-limit-test@example.com"
    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()

    resp = client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    course = Course(slug="quiz-rate-limit-course", name="Test Course")
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


def test_sixth_request_within_a_minute_gets_429(auth_headers_and_lesson):
    headers, course_id, lesson_id = auth_headers_and_lesson

    with patch(
        "backend.routes.courseRoute.gemini_generator.generate_quiz",
        return_value={"questions": []},
    ):
        statuses = [
            client.post(f"/api/courses/{course_id}/lessons/{lesson_id}/quiz", headers=headers).status_code
            for _ in range(7)
        ]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
    assert statuses[6] == 429
