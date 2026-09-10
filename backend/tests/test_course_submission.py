"""Course submission (POST /api/courses/submit) and its visibility rules:
who can submit, who can see a pending/rejected course before an admin acts
on it, GET /api/courses/mine, and GET /api/auth/me's has_submitted_courses
flag. Runs against your real database - see README.md "Run the tests"."""
import pytest
from fastapi.testclient import TestClient

from backend.database.models import Course, User
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)
pytestmark = pytest.mark.bulk_register


def _submit(token, name="Тест курс", price=0, materials=None):
    return client.post(
        "/api/courses/submit",
        headers=auth_headers(token),
        json={"name": name, "materials": materials or [], "price": price},
    )


# ---------------------------------------------------------------- gating ----

def test_plain_student_cannot_submit():
    db = SessionLocal()
    email = unique_email("submit-student")
    try:
        token = register_and_login(client, db, email)  # role="student", is_premium=False (defaults)
        resp = _submit(token)
        assert resp.status_code == 403, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_premium_student_can_submit():
    db = SessionLocal()
    email = unique_email("submit-premium")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        resp = _submit(token, name="Премиум курс", price=0)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Премиум курс"
        assert body["locked"] is False  # free course, never locked
        assert body["material_count"] == 0
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_admin_can_submit_without_being_premium():
    """get_current_paying_user allows role="admin" as a bypass even with
    is_premium=False - admins shouldn't need to pay to test the pipeline."""
    db = SessionLocal()
    email = unique_email("submit-admin")
    try:
        token = register_and_login(client, db, email, role="admin", is_premium=False)
        resp = _submit(token, name="Admin курс")
        assert resp.status_code == 201, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_submit_requires_auth_at_all():
    resp = client.post("/api/courses/submit", json={"name": "X", "materials": [], "price": 0})
    assert resp.status_code == 401


def test_submitted_course_starts_pending_and_carries_materials_and_submitter_name():
    db = SessionLocal()
    email = unique_email("submit-materials")
    try:
        token = register_and_login(client, db, email, is_premium=True, full_name="Марија Тестова")
        resp = _submit(
            token,
            name="Курс со материјали",
            materials=[
                {"title": "Скрипта", "url": "https://example.com/skripta.pdf", "category": "Notes"},
                {"title": "Видео 1", "url": "https://example.com/v1.mp4", "category": "Video"},
            ],
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["material_count"] == 2
        assert body["submitted_by_name"] == "Марија Тестова"

        db2 = SessionLocal()
        course = db2.query(Course).filter(Course.id == body["id"]).first()
        assert course.status == "pending"
        assert len(course.materials) == 2
        db2.close()
    finally:
        cleanup_test_data(db, [email])
        db.close()


# ------------------------------------------------------------ visibility ----

def test_pending_course_hidden_from_public_catalog():
    db = SessionLocal()
    email = unique_email("submit-hidden")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        resp = _submit(token, name="Скриен курс")
        course_id = resp.json()["id"]

        listing = client.get("/api/courses", params={"source": "community"})
        assert course_id not in [c["id"] for c in listing.json()]
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_submitter_can_see_own_pending_course_but_a_stranger_cannot():
    db = SessionLocal()
    submitter_email = unique_email("submit-owner")
    stranger_email = unique_email("submit-stranger")
    try:
        owner_token = register_and_login(client, db, submitter_email, is_premium=True)
        stranger_token = register_and_login(client, db, stranger_email)
        resp = _submit(owner_token, name="Приватен курс")
        course_id = resp.json()["id"]

        own_view = client.get(f"/api/courses/{course_id}", headers=auth_headers(owner_token))
        assert own_view.status_code == 200

        stranger_view = client.get(f"/api/courses/{course_id}", headers=auth_headers(stranger_token))
        assert stranger_view.status_code == 404  # same as "doesn't exist" - no leak that it's pending

        anon_view = client.get(f"/api/courses/{course_id}")
        assert anon_view.status_code == 404
    finally:
        cleanup_test_data(db, [submitter_email, stranger_email])
        db.close()


def test_admin_can_see_any_pending_course():
    db = SessionLocal()
    submitter_email = unique_email("submit-forAdmin")
    admin_email = unique_email("submit-adminViewer")
    try:
        owner_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        resp = _submit(owner_token, name="Курс за admin преглед")
        course_id = resp.json()["id"]

        admin_view = client.get(f"/api/courses/{course_id}", headers=auth_headers(admin_token))
        assert admin_view.status_code == 200
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


# -------------------------------------------------------------- /mine ----

def test_mine_lists_every_status_for_the_current_user_only():
    db = SessionLocal()
    mine_email = unique_email("mine-user")
    other_email = unique_email("mine-other")
    try:
        mine_token = register_and_login(client, db, mine_email, is_premium=True)
        other_token = register_and_login(client, db, other_email, is_premium=True)

        _submit(mine_token, name="Мој курс 1")
        _submit(mine_token, name="Мој курс 2")
        _submit(other_token, name="Туѓ курс")

        resp = client.get("/api/courses/mine", headers=auth_headers(mine_token))
        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Мој курс 1", "Мој курс 2"}
    finally:
        cleanup_test_data(db, [mine_email, other_email])
        db.close()


def test_mine_requires_auth():
    resp = client.get("/api/courses/mine")
    assert resp.status_code == 401


def test_mine_is_empty_list_not_error_for_a_user_with_no_submissions():
    db = SessionLocal()
    email = unique_email("mine-empty")
    try:
        token = register_and_login(client, db, email)
        resp = client.get("/api/courses/mine", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        cleanup_test_data(db, [email])
        db.close()


# ---------------------------------------------------- has_submitted_courses ----

def test_has_submitted_courses_reflects_submission_history_independent_of_is_premium():
    """The whole point of this flag: it must survive is_premium being turned
    back off (e.g. after cancelling a subscription - see billingRoute.py's
    /cancel), so the frontend's "My courses" nav link doesn't disappear out
    from under someone who already has submissions - see NavTabs.tsx."""
    db = SessionLocal()
    email = unique_email("hsc")
    try:
        token = register_and_login(client, db, email)

        me = client.get("/api/auth/me", headers=auth_headers(token))
        assert me.json()["has_submitted_courses"] is False

        # Flip to premium, submit, then flip back off (mirrors what
        # POST /api/billing/cancel does to is_premium).
        user = db.query(User).filter(User.email == email).first()
        user.is_premium = True
        db.commit()

        _submit(token, name="Курс па откажување")

        me = client.get("/api/auth/me", headers=auth_headers(token))
        assert me.json()["has_submitted_courses"] is True
        assert me.json()["is_premium"] is True

        user = db.query(User).filter(User.email == email).first()
        user.is_premium = False
        db.commit()

        me = client.get("/api/auth/me", headers=auth_headers(token))
        assert me.json()["is_premium"] is False
        assert me.json()["has_submitted_courses"] is True  # still True - this is the whole point
    finally:
        cleanup_test_data(db, [email])
        db.close()
