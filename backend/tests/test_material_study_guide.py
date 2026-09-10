"""Marketplace material study-guide generation (GET/POST
/api/courses/{course_id}/materials/{material_id}/study-guide) - see
services/material_study_guide.py and courseRoute.py. Same Medium/Hard quiz
split as test_lesson_quiz_difficulty.py (this is the Marketplace equivalent -
both reuse gemini_generator.generate_quiz(difficulty=...) directly, no
separate function). Gemini and the text-extraction fetch are mocked; no real
API calls or network requests. Runs against your real database - see
README.md "Run the tests"."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database.session import SessionLocal
from backend.main import app
from backend.services import material_study_guide
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

pytestmark = pytest.mark.bulk_register

client = TestClient(app)

_FAKE_QUIZ = {
    "questions": [
        {"question": "Q1?", "options": ["a", "b", "c", "d"], "correct_option_index": 0, "explanation": "because"},
    ]
}


def _submit_course_with_material(token, price=0, category=None):
    resp = client.post(
        "/api/courses/submit",
        headers=auth_headers(token),
        json={
            "name": "Курс со материјал",
            "price": price,
            "materials": [
                {
                    "title": "Белешки",
                    "url": "https://example.test/notes.pdf",
                    "category": category,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    course_id = resp.json()["id"]
    materials = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(token))
    assert materials.status_code == 200, materials.text
    material_id = materials.json()[0]["id"]
    return course_id, material_id


def _study_guide_url(course_id, material_id, difficulty=None):
    url = f"/api/courses/{course_id}/materials/{material_id}/study-guide"
    return f"{url}?difficulty={difficulty}" if difficulty else url


def test_get_before_generation_shows_empty_guide():
    db = SessionLocal()
    email = unique_email("study-guide-get-empty")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)
        resp = client.get(_study_guide_url(course_id, material_id), headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["has_documentation"] is False
        assert body["has_quiz"] is False
        assert body["has_quiz_hard"] is False
        assert body["documentation"] is None
        assert body["quiz"] is None
        assert body["quiz_hard"] is None
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_generate_requires_auth():
    db = SessionLocal()
    email = unique_email("study-guide-noauth")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)
        resp = client.post(_study_guide_url(course_id, material_id))
        assert resp.status_code == 401
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_medium_is_the_default_and_generates_documentation_plus_quiz():
    """Confirms Medium is generated (and documentation extracted/generated
    along with it) on first call, and that a second Medium call reuses both -
    no new extraction, no new documentation call, no new quiz call."""
    db = SessionLocal()
    email = unique_email("study-guide-medium")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)

        with patch.object(material_study_guide, "extract_material_text", return_value="some extracted text") as m_extract, \
             patch("backend.routes.courseRoute.gemini_generator.generate_documentation", return_value="Generated docs") as m_doc, \
             patch("backend.routes.courseRoute.gemini_generator.generate_quiz", return_value=_FAKE_QUIZ) as m_quiz:
            resp = client.post(_study_guide_url(course_id, material_id), headers=auth_headers(token))
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["has_documentation"] is True
            assert body["has_quiz"] is True
            assert body["has_quiz_hard"] is False
            assert body["documentation"] == "Generated docs"
            assert body["quiz"] == _FAKE_QUIZ
            assert body["quiz_hard"] is None
            assert m_extract.call_count == 1
            assert m_doc.call_count == 1
            assert m_quiz.call_count == 1
            assert m_quiz.call_args.kwargs["difficulty"] == "medium"

            # Second Medium call: already cached, must NOT call Gemini/extraction again.
            resp2 = client.post(_study_guide_url(course_id, material_id, "medium"), headers=auth_headers(token))
            assert resp2.status_code == 200, resp2.text
            assert resp2.json()["documentation"] == "Generated docs"
            assert m_extract.call_count == 1
            assert m_doc.call_count == 1
            assert m_quiz.call_count == 1

        get_resp = client.get(_study_guide_url(course_id, material_id), headers=auth_headers(token))
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["has_documentation"] is True
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_hard_reuses_existing_documentation_and_leaves_medium_untouched():
    """Generating Hard after Medium must not re-extract/re-generate the
    (shared) documentation, and must not touch the Medium quiz already
    stored - mirrors test_lesson_quiz_difficulty.py's equivalent test."""
    db = SessionLocal()
    email = unique_email("study-guide-hard")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)

        with patch.object(material_study_guide, "extract_material_text", return_value="some extracted text") as m_extract, \
             patch("backend.routes.courseRoute.gemini_generator.generate_documentation", return_value="Generated docs") as m_doc, \
             patch("backend.routes.courseRoute.gemini_generator.generate_quiz", return_value=_FAKE_QUIZ) as m_quiz:
            first = client.post(_study_guide_url(course_id, material_id, "medium"), headers=auth_headers(token))
            resp = client.post(_study_guide_url(course_id, material_id, "hard"), headers=auth_headers(token))

            assert first.status_code == 200, first.text
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["quiz"] == _FAKE_QUIZ  # from the first (Medium) call, untouched by the second
            assert body["quiz_hard"] == _FAKE_QUIZ
            assert body["has_quiz"] is True
            assert body["has_quiz_hard"] is True
            # documentation extraction/generation only happened once, shared by both tiers
            assert m_extract.call_count == 1
            assert m_doc.call_count == 1
            assert m_quiz.call_count == 2
            assert m_quiz.call_args.kwargs["difficulty"] == "hard"
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_invalid_difficulty_is_rejected_with_400():
    db = SessionLocal()
    email = unique_email("study-guide-baddiff")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)
        resp = client.post(_study_guide_url(course_id, material_id, "easy"), headers=auth_headers(token))
        assert resp.status_code == 400, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_video_category_rejected():
    db = SessionLocal()
    email = unique_email("study-guide-video")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token, category="Video")
        resp = client.post(_study_guide_url(course_id, material_id), headers=auth_headers(token))
        assert resp.status_code == 400, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_unextractable_material_returns_502():
    db = SessionLocal()
    email = unique_email("study-guide-unextractable")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, material_id = _submit_course_with_material(token)
        with patch.object(
            material_study_guide,
            "extract_material_text",
            side_effect=material_study_guide.UnsupportedMaterialError("no text"),
        ):
            resp = client.post(_study_guide_url(course_id, material_id), headers=auth_headers(token))
        assert resp.status_code == 502, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_locked_priced_course_blocks_both_get_and_post():
    """A priced course must be approved (visible to non-submitters at all)
    AND not-yet-purchased by the viewer to hit the 402 path specifically -
    otherwise a stranger just gets 404 (pending courses are invisible to
    everyone but the submitter/admin), which is a different, already-covered
    rule (test_course_submission.py)."""
    db = SessionLocal()
    submitter_email = unique_email("study-guide-owner")
    stranger_email = unique_email("study-guide-stranger")
    admin_email = unique_email("study-guide-admin")
    try:
        owner_token = register_and_login(client, db, submitter_email, is_premium=True)
        course_id, material_id = _submit_course_with_material(owner_token, price=4.99)

        admin_token = register_and_login(client, db, admin_email, role="admin")
        approve_resp = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
        assert approve_resp.status_code == 200, approve_resp.text

        stranger_token = register_and_login(client, db, stranger_email)

        get_resp = client.get(_study_guide_url(course_id, material_id), headers=auth_headers(stranger_token))
        assert get_resp.status_code == 402, get_resp.text

        post_resp = client.post(_study_guide_url(course_id, material_id), headers=auth_headers(stranger_token))
        assert post_resp.status_code == 402, post_resp.text
    finally:
        cleanup_test_data(db, [submitter_email, stranger_email, admin_email])
        db.close()


def test_material_not_found_404():
    db = SessionLocal()
    email = unique_email("study-guide-404")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id, _ = _submit_course_with_material(token)
        resp = client.get(_study_guide_url(course_id, 9_999_999), headers=auth_headers(token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()
