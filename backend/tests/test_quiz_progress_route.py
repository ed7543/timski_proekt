from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database.models import QuizAttempt, User, VerificationToken
from backend.database.session import SessionLocal
from backend.main import app

client = TestClient(app)


def _register_once(email: str) -> dict:
    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()
    db.close()

    resp = client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _clear_attempts(email: str):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id).delete()
        db.commit()
    db.close()


def _delete_user(email: str):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        db.query(QuizAttempt).filter(QuizAttempt.user_id == user.id).delete()
        db.query(VerificationToken).filter(VerificationToken.user_id == user.id).delete()
        db.delete(user)
        db.commit()
    db.close()


# Registered once per test run (not per test) since /api/auth/register is
# rate-limited to 5/minute - each test only needs a clean QuizAttempt slate,
# not a fresh account.
_MAIN_EMAIL = "quiz-progress-test@example.com"
_OTHER_EMAIL = "quiz-progress-test-other@example.com"


@pytest.fixture(scope="module")
def _main_headers():
    headers = _register_once(_MAIN_EMAIL)
    yield headers
    _delete_user(_MAIN_EMAIL)


@pytest.fixture(scope="module")
def _other_headers():
    headers = _register_once(_OTHER_EMAIL)
    yield headers
    _delete_user(_OTHER_EMAIL)


@pytest.fixture
def auth_headers(_main_headers):
    yield _main_headers
    _clear_attempts(_MAIN_EMAIL)


@pytest.fixture
def other_auth_headers(_other_headers):
    yield _other_headers
    _clear_attempts(_OTHER_EMAIL)


def test_create_attempt_starts_at_zero(auth_headers):
    resp = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answered_count"] == 0
    assert body["correct_count"] == 0
    assert body["completed"] is False
    assert body["total_questions"] == 5


def test_update_attempt_tracks_progress_without_completing(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    attempt_id = create.json()["id"]

    resp = client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 2, "correct_count": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answered_count"] == 2
    assert body["correct_count"] == 1
    assert body["completed"] is False


def test_update_attempt_marks_completed_when_all_answered(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 3},
    )
    attempt_id = create.json()["id"]

    resp = client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 3, "correct_count": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


def test_update_clamps_counts_beyond_total(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 3},
    )
    attempt_id = create.json()["id"]

    resp = client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 99, "correct_count": 99},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answered_count"] == 3
    assert body["correct_count"] == 3
    assert body["completed"] is True


def test_update_rejects_other_users_attempt(auth_headers, other_auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    attempt_id = create.json()["id"]

    resp = client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=other_auth_headers,
        json={"answered_count": 5, "correct_count": 5},
    )
    assert resp.status_code == 404

    unchanged = client.get("/api/quiz-progress", headers=auth_headers).json()
    assert unchanged[0]["answered_count"] == 0


def test_list_only_returns_own_attempts(auth_headers, other_auth_headers):
    client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Mine", "subject": "Python", "total_questions": 5},
    )
    client.post(
        "/api/quiz-progress",
        headers=other_auth_headers,
        json={"topic": "Theirs", "subject": "Python", "total_questions": 5},
    )

    mine = client.get("/api/quiz-progress", headers=auth_headers).json()
    assert [a["topic"] for a in mine] == ["Mine"]


def test_recommendations_flags_low_scoring_subject(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Pointers", "subject": "C", "total_questions": 10},
    )
    attempt_id = create.json()["id"]
    client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 10, "correct_count": 4},
    )

    recs = client.get("/api/quiz-progress/recommendations", headers=auth_headers).json()
    assert any(r["subject"] == "C" and r["average_score_percent"] == 40 for r in recs)


def test_recommendations_excludes_high_scoring_subject(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Loops", "subject": "Java", "total_questions": 10},
    )
    attempt_id = create.json()["id"]
    client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 10, "correct_count": 9},
    )

    recs = client.get("/api/quiz-progress/recommendations", headers=auth_headers).json()
    assert all(r["subject"] != "Java" for r in recs)


def test_create_attempt_caches_questions(auth_headers):
    questions = [
        {"question": "What is a decorator?", "options": ["A) x", "B) y"], "answer": "A", "explanation": "because"},
    ]
    resp = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 1, "questions": questions},
    )
    assert resp.status_code == 200
    assert resp.json()["questions"] == questions


def test_create_attempt_without_questions_returns_none(auth_headers):
    resp = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["questions"] is None


def test_redo_generates_new_attempt_without_touching_original(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    original = create.json()
    client.patch(
        f"/api/quiz-progress/{original['id']}",
        headers=auth_headers,
        json={"answered_count": 5, "correct_count": 5},
    )

    fresh_questions = [
        {"question": "New question?", "options": ["A) x", "B) y"], "answer": "B", "explanation": "because"},
    ]
    with patch(
        "backend.routes.quizProgressRoute.generate_quiz_from_topic",
        return_value={"topic": "Decorators", "questions": fresh_questions},
    ):
        resp = client.post(f"/api/quiz-progress/{original['id']}/redo", headers=auth_headers)

    assert resp.status_code == 200
    redone = resp.json()
    assert redone["id"] != original["id"]
    assert redone["topic"] == "Decorators"
    assert redone["subject"] == "Python"
    assert redone["questions"] == fresh_questions
    assert redone["total_questions"] == len(fresh_questions)
    assert redone["answered_count"] == 0
    assert redone["completed"] is False

    original_unchanged = client.get("/api/quiz-progress", headers=auth_headers).json()
    original_row = next(a for a in original_unchanged if a["id"] == original["id"])
    assert original_row["completed"] is True


def test_redo_rejects_other_users_attempt(auth_headers, other_auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Decorators", "subject": "Python", "total_questions": 5},
    )
    attempt_id = create.json()["id"]

    with patch("backend.routes.quizProgressRoute.generate_quiz_from_topic") as fake_generate:
        resp = client.post(f"/api/quiz-progress/{attempt_id}/redo", headers=other_auth_headers)

    assert resp.status_code == 404
    fake_generate.assert_not_called()


def test_redo_404_for_missing_attempt(auth_headers):
    resp = client.post("/api/quiz-progress/999999/redo", headers=auth_headers)
    assert resp.status_code == 404


def test_recommendations_excludes_incomplete_attempts(auth_headers):
    create = client.post(
        "/api/quiz-progress",
        headers=auth_headers,
        json={"topic": "Generics", "subject": "TypeScript", "total_questions": 10},
    )
    attempt_id = create.json()["id"]
    client.patch(
        f"/api/quiz-progress/{attempt_id}",
        headers=auth_headers,
        json={"answered_count": 3, "correct_count": 0},
    )

    recs = client.get("/api/quiz-progress/recommendations", headers=auth_headers).json()
    assert all(r["subject"] != "TypeScript" for r in recs)
