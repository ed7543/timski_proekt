"""Admin course-moderation endpoints (/api/admin/courses/*): who can reach
them, the approve/reject state machine, and what happens to a course's
public visibility on each side of a decision. Runs against your real
database - see README.md "Run the tests"."""
from fastapi.testclient import TestClient

from backend.database.models import Course
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


def _submit_pending(token, name="Курс на чекање"):
    resp = client.post(
        "/api/courses/submit",
        headers=auth_headers(token),
        json={"name": name, "materials": [], "price": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------------------------------------------------------------- gating ----

def test_all_admin_endpoints_require_auth():
    assert client.get("/api/admin/courses/pending").status_code == 401
    assert client.get("/api/admin/courses").status_code == 401
    assert client.post("/api/admin/courses/1/approve").status_code == 401
    assert client.post("/api/admin/courses/1/reject", json={"reason": "x"}).status_code == 401


def test_all_admin_endpoints_reject_non_admin():
    db = SessionLocal()
    email = unique_email("admin-gate-student")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id = _submit_pending(token)
        headers = auth_headers(token)

        assert client.get("/api/admin/courses/pending", headers=headers).status_code == 403
        assert client.get("/api/admin/courses", headers=headers).status_code == 403
        assert client.post(f"/api/admin/courses/{course_id}/approve", headers=headers).status_code == 403
        assert client.post(f"/api/admin/courses/{course_id}/reject", headers=headers, json={"reason": "x"}).status_code == 403
    finally:
        cleanup_test_data(db, [email])
        db.close()


# -------------------------------------------------------------- approve ----

def test_approve_publishes_the_course_and_records_the_reviewer():
    db = SessionLocal()
    submitter_email = unique_email("approve-submitter")
    admin_email = unique_email("approve-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit_pending(sub_token, name="Курс за одобрување")

        resp = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "approved"

        listing = client.get("/api/courses", params={"source": "community"})
        assert course_id in [c["id"] for c in listing.json()]

        db2 = SessionLocal()
        course = db2.query(Course).filter(Course.id == course_id).first()
        admin_user_id = db2.query(Course).filter(Course.id == course_id).first().reviewed_by_id
        assert course.reviewed_at is not None
        assert admin_user_id is not None
        db2.close()
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


def test_approving_a_non_pending_course_is_rejected_with_400():
    db = SessionLocal()
    submitter_email = unique_email("approve-twice-sub")
    admin_email = unique_email("approve-twice-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit_pending(sub_token)

        first = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
        assert first.status_code == 200

        second = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
        assert second.status_code == 400
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


def test_approving_a_nonexistent_course_is_404():
    db = SessionLocal()
    admin_email = unique_email("approve-404-admin")
    try:
        admin_token = register_and_login(client, db, admin_email, role="admin")
        resp = client.post("/api/admin/courses/999999999/approve", headers=auth_headers(admin_token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [admin_email])
        db.close()


# --------------------------------------------------------------- reject ----

def test_reject_requires_a_reason():
    db = SessionLocal()
    submitter_email = unique_email("reject-noreason-sub")
    admin_email = unique_email("reject-noreason-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit_pending(sub_token)

        missing = client.post(f"/api/admin/courses/{course_id}/reject", headers=auth_headers(admin_token), json={})
        assert missing.status_code == 422

        empty = client.post(f"/api/admin/courses/{course_id}/reject", headers=auth_headers(admin_token), json={"reason": ""})
        assert empty.status_code == 422
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


def test_reject_hides_the_course_but_the_submitter_sees_the_reason_on_mine():
    db = SessionLocal()
    submitter_email = unique_email("reject-flow-sub")
    admin_email = unique_email("reject-flow-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit_pending(sub_token, name="Курс за одбивање")

        resp = client.post(
            f"/api/admin/courses/{course_id}/reject",
            headers=auth_headers(admin_token),
            json={"reason": "Нема доволно материјали"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"

        listing = client.get("/api/courses", params={"source": "community"})
        assert course_id not in [c["id"] for c in listing.json()]

        mine = client.get("/api/courses/mine", headers=auth_headers(sub_token))
        mine_course = next(c for c in mine.json() if c["id"] == course_id)
        assert mine_course["status"] == "rejected"
        assert mine_course["rejection_reason"] == "Нема доволно материјали"
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


def test_rejecting_a_non_pending_course_is_400():
    db = SessionLocal()
    submitter_email = unique_email("reject-twice-sub")
    admin_email = unique_email("reject-twice-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit_pending(sub_token)
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        resp = client.post(
            f"/api/admin/courses/{course_id}/reject",
            headers=auth_headers(admin_token),
            json={"reason": "too late"},
        )
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()


# --------------------------------------------------------- list/filter ----

def test_list_courses_for_admin_filters_by_status_and_excludes_official_catalog():
    db = SessionLocal()
    submitter_email = unique_email("list-admin-sub")
    admin_email = unique_email("list-admin-admin")
    try:
        sub_token = register_and_login(client, db, submitter_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")

        pending_id = _submit_pending(sub_token, name="Останува pending")
        approved_id = _submit_pending(sub_token, name="Ќе биде одобрен")
        client.post(f"/api/admin/courses/{approved_id}/approve", headers=auth_headers(admin_token))

        # An official (scraped) catalog course must never show up here,
        # regardless of status filter - it has no submitter to moderate.
        db2 = SessionLocal()
        official = Course(slug=unique_email("official")[:40], name="Официјален курс", status="approved", submitted_by_id=None, price_cents=0)
        db2.add(official)
        db2.commit()
        official_id = official.id
        db2.close()

        pending_list = client.get("/api/admin/courses", params={"status": "pending"}, headers=auth_headers(admin_token)).json()
        assert pending_id in [c["id"] for c in pending_list]
        assert approved_id not in [c["id"] for c in pending_list]
        assert official_id not in [c["id"] for c in pending_list]

        approved_list = client.get("/api/admin/courses", params={"status": "approved"}, headers=auth_headers(admin_token)).json()
        assert approved_id in [c["id"] for c in approved_list]
        assert official_id not in [c["id"] for c in approved_list]

        all_list = client.get("/api/admin/courses", params={"status": "all"}, headers=auth_headers(admin_token)).json()
        all_ids = [c["id"] for c in all_list]
        assert pending_id in all_ids and approved_id in all_ids
        assert official_id not in all_ids

        db3 = SessionLocal()
        db3.query(Course).filter(Course.id == official_id).delete()
        db3.commit()
        db3.close()

        bad = client.get("/api/admin/courses", params={"status": "bogus"}, headers=auth_headers(admin_token))
        assert bad.status_code == 400
    finally:
        cleanup_test_data(db, [submitter_email, admin_email])
        db.close()
