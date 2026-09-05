"""DELETE /api/courses/{id}: the submitter-or-admin permission matrix, the
official-catalog guard (submitted_by_id is null - never deletable here, by
anyone), and that the old admin-only DELETE /api/admin/courses/{id} route
(moved to courseRoute.py this feature) is genuinely gone, not just aliased.
Runs against your real database - see README.md "Run the tests"."""
from fastapi.testclient import TestClient

from backend.database.models import Course, CourseMaterial
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


def _submit(token, name="Курс за бришење", price=0):
    resp = client.post(
        "/api/courses/submit",
        headers=auth_headers(token),
        json={"name": name, "materials": [{"title": "M", "url": "https://example.com/m.pdf"}], "price": price},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_old_admin_namespaced_delete_route_no_longer_exists():
    resp = client.delete("/api/admin/courses/1")
    assert resp.status_code in (404, 405)


def test_delete_requires_auth():
    db = SessionLocal()
    email = unique_email("delete-noauth-sub")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id = _submit(token)
        resp = client.delete(f"/api/courses/{course_id}")
        assert resp.status_code == 401
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_a_different_professor_and_a_random_student_cannot_delete_someone_elses_course():
    db = SessionLocal()
    owner_email = unique_email("delete-owner")
    other_email = unique_email("delete-other-sub")
    student_email = unique_email("delete-student")
    try:
        owner_token = register_and_login(client, db, owner_email, is_premium=True)
        other_token = register_and_login(client, db, other_email, is_premium=True)
        student_token = register_and_login(client, db, student_email)
        course_id = _submit(owner_token)

        assert client.delete(f"/api/courses/{course_id}", headers=auth_headers(other_token)).status_code == 403
        assert client.delete(f"/api/courses/{course_id}", headers=auth_headers(student_token)).status_code == 403

        # Still there - neither forbidden attempt actually deleted it.
        assert client.get(f"/api/courses/{course_id}", headers=auth_headers(owner_token)).status_code == 200
    finally:
        cleanup_test_data(db, [owner_email, other_email, student_email])
        db.close()


def test_owner_can_delete_their_own_pending_course():
    db = SessionLocal()
    email = unique_email("delete-owner-pending")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        course_id = _submit(token)

        resp = client.delete(f"/api/courses/{course_id}", headers=auth_headers(token))
        assert resp.status_code == 204

        assert client.get(f"/api/courses/{course_id}", headers=auth_headers(token)).status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_owner_can_delete_their_own_approved_course_and_it_leaves_the_marketplace():
    db = SessionLocal()
    sub_email = unique_email("delete-owner-approved-sub")
    admin_email = unique_email("delete-owner-approved-admin")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit(sub_token, name="Одобрен па избришан")
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        before = client.get("/api/courses", params={"source": "community"}).json()
        assert course_id in [c["id"] for c in before]

        resp = client.delete(f"/api/courses/{course_id}", headers=auth_headers(sub_token))
        assert resp.status_code == 204

        after = client.get("/api/courses", params={"source": "community"}).json()
        assert course_id not in [c["id"] for c in after]
    finally:
        cleanup_test_data(db, [sub_email, admin_email])
        db.close()


def test_admin_can_delete_anyones_course():
    db = SessionLocal()
    sub_email = unique_email("delete-admin-sub")
    admin_email = unique_email("delete-admin-admin")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        course_id = _submit(sub_token)

        resp = client.delete(f"/api/courses/{course_id}", headers=auth_headers(admin_token))
        assert resp.status_code == 204
    finally:
        cleanup_test_data(db, [sub_email, admin_email])
        db.close()


def test_deleting_a_course_cascades_its_materials():
    db = SessionLocal()
    email = unique_email("delete-cascade")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        resp = client.post(
            "/api/courses/submit",
            headers=auth_headers(token),
            json={
                "name": "Курс со материјали за каскада",
                "materials": [
                    {"title": "M1", "url": "https://example.com/1.pdf"},
                    {"title": "M2", "url": "https://example.com/2.pdf"},
                ],
                "price": 0,
            },
        )
        course_id = resp.json()["id"]

        client.delete(f"/api/courses/{course_id}", headers=auth_headers(token))

        db2 = SessionLocal()
        leftover = db2.query(CourseMaterial).filter(CourseMaterial.course_id == course_id).count()
        db2.close()
        assert leftover == 0
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_even_admin_cannot_delete_an_official_catalog_course_through_this_endpoint():
    db = SessionLocal()
    admin_email = unique_email("delete-official-admin")
    official_id = None
    try:
        admin_token = register_and_login(client, db, admin_email, role="admin")

        official = Course(slug=unique_email("official-del")[:40], name="Официјален курс", status="approved", submitted_by_id=None, price_cents=0)
        db.add(official)
        db.commit()
        official_id = official.id

        resp = client.delete(f"/api/courses/{official_id}", headers=auth_headers(admin_token))
        assert resp.status_code == 400

        # Still there.
        assert client.get(f"/api/courses/{official_id}").status_code == 200
    finally:
        if official_id is not None:
            db.query(Course).filter(Course.id == official_id).delete()
            db.commit()
        cleanup_test_data(db, [admin_email])
        db.close()


def test_deleting_a_nonexistent_course_is_404():
    db = SessionLocal()
    email = unique_email("delete-404")
    try:
        token = register_and_login(client, db, email)
        resp = client.delete("/api/courses/999999999", headers=auth_headers(token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()
