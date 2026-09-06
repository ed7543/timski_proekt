"""Community study notes (POST/GET/DELETE /api/courses/{id}/notes) - the
free, any-logged-in-user alternative to the premium submit-a-course flow.
Key behaviours under test: no premium subscription required to add one,
never gated by a priced course's lock (unlike materials/recordings), hidden
for a pending/rejected course the viewer can't see, and deletable only by
the uploader or an admin. Runs against your real database - see README.md
"Run the tests"."""
import pytest
from fastapi.testclient import TestClient

from backend.database.models import Course, CourseNote
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)
pytestmark = pytest.mark.bulk_register


def _make_official_course(db, slug):
    """An official-catalog-style course (submitted_by_id=None, auto-approved)
    - NOT tied to any test user's submitted_by_id/reviewed_by_id, so
    cleanup_test_data() won't find it. Callers must delete it (and any
    CourseNote rows on it) themselves in their own finally block."""
    course = Course(slug=slug, name="Test Course")
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _delete_course_and_its_notes(db, course_id):
    db.query(CourseNote).filter(CourseNote.course_id == course_id).delete(synchronize_session=False)
    db.query(Course).filter(Course.id == course_id).delete(synchronize_session=False)
    db.commit()


def _submit_and_approve(admin_token, sub_token, name, price=0):
    resp = client.post(
        "/api/courses/submit",
        headers=auth_headers(sub_token),
        json={"name": name, "materials": [], "price": price},
    )
    assert resp.status_code == 201, resp.text
    course_id = resp.json()["id"]
    approved = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
    assert approved.status_code == 200
    return course_id


def _add_note(token, course_id, title="Скрипта", url="https://example.com/notes.pdf"):
    return client.post(
        f"/api/courses/{course_id}/notes",
        headers=auth_headers(token),
        json={"title": title, "url": url},
    )


# ------------------------------------------------------------------ auth ----

def test_add_note_requires_auth():
    resp = client.post("/api/courses/1/notes", json={"title": "X", "url": "https://example.com/x"})
    assert resp.status_code == 401


def test_delete_note_requires_auth():
    resp = client.delete("/api/courses/1/notes/1")
    assert resp.status_code == 401


def test_deleting_a_missing_note_is_404():
    db = SessionLocal()
    email = unique_email("notes-delete-missing")
    try:
        token = register_and_login(client, db, email)
        resp = client.delete("/api/courses/999999/notes/999999999", headers=auth_headers(token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()


# ------------------------------------------------------- no premium needed ----

def test_a_plain_non_premium_student_can_add_a_note_to_the_official_catalog():
    """No premium/subscription gate here, unlike POST /api/courses/submit -
    any logged-in user can contribute a note to any course they can see."""
    db = SessionLocal()
    email = unique_email("notes-student")
    course = _make_official_course(db, f"notes-official-{email}")
    try:
        token = register_and_login(client, db, email)  # role="student", is_premium=False
        resp = _add_note(token, course.id, title="Мои белешки", url="https://example.com/moi-beleshki.pdf")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["title"] == "Мои белешки"
        assert body["uploaded_by_id"] is not None
        assert body["uploaded_by_name"] == "Test User"
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [email])
        db.close()


# --------------------------------------------------------- free even when locked ----

def test_notes_are_visible_and_addable_on_a_priced_course_a_viewer_hasnt_bought():
    """The whole point of this feature: unlike materials/recordings, notes
    are never behind _has_course_access - so a random, non-purchasing
    viewer can still add one and see it, even on a priced course."""
    db = SessionLocal()
    sub_email = unique_email("notes-sub")
    admin_email = unique_email("notes-admin")
    stranger_email = unique_email("notes-stranger")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        stranger_token = register_and_login(client, db, stranger_email)  # no purchase, no premium
        course_id = _submit_and_approve(admin_token, sub_token, "Платен курс за белешки", price=5)

        # Confirm the course really is locked for this stranger (materials 402).
        locked_check = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(stranger_token))
        assert locked_check.status_code == 402

        add_resp = _add_note(stranger_token, course_id)
        assert add_resp.status_code == 201, add_resp.text

        list_resp = client.get(f"/api/courses/{course_id}/notes", headers=auth_headers(stranger_token))
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        anon_list_resp = client.get(f"/api/courses/{course_id}/notes")
        assert anon_list_resp.status_code == 200
        assert len(anon_list_resp.json()) == 1
    finally:
        cleanup_test_data(db, [sub_email, admin_email, stranger_email])
        db.close()


# --------------------------------------------------------- pending visibility ----

def test_notes_hidden_for_a_pending_course_a_stranger_cant_see():
    db = SessionLocal()
    sub_email = unique_email("notes-pending-sub")
    stranger_email = unique_email("notes-pending-stranger")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        stranger_token = register_and_login(client, db, stranger_email)
        resp = client.post(
            "/api/courses/submit",
            headers=auth_headers(sub_token),
            json={"name": "Курс на чекање за белешки", "materials": [], "price": 0},
        )
        course_id = resp.json()["id"]  # still "pending" - never approved

        list_resp = client.get(f"/api/courses/{course_id}/notes", headers=auth_headers(stranger_token))
        assert list_resp.status_code == 404

        add_resp = _add_note(stranger_token, course_id)
        assert add_resp.status_code == 404
    finally:
        cleanup_test_data(db, [sub_email, stranger_email])
        db.close()


# --------------------------------------------------------------- delete ----

def test_uploader_can_delete_their_own_note():
    db = SessionLocal()
    email = unique_email("notes-delete-owner")
    course = _make_official_course(db, f"notes-delowner-{email}")
    try:
        token = register_and_login(client, db, email)
        note_id = _add_note(token, course.id).json()["id"]
        resp = client.delete(f"/api/courses/{course.id}/notes/{note_id}", headers=auth_headers(token))
        assert resp.status_code == 204
        remaining = client.get(f"/api/courses/{course.id}/notes").json()
        assert all(n["id"] != note_id for n in remaining)
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [email])
        db.close()


def test_admin_can_delete_someone_elses_note():
    db = SessionLocal()
    uploader_email = unique_email("notes-delete-uploader")
    admin_email = unique_email("notes-delete-admin")
    course = _make_official_course(db, f"notes-deladmin-{uploader_email}")
    try:
        uploader_token = register_and_login(client, db, uploader_email)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        note_id = _add_note(uploader_token, course.id).json()["id"]
        resp = client.delete(f"/api/courses/{course.id}/notes/{note_id}", headers=auth_headers(admin_token))
        assert resp.status_code == 204
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [uploader_email, admin_email])
        db.close()


def test_a_random_user_cannot_delete_someone_elses_note():
    db = SessionLocal()
    uploader_email = unique_email("notes-delete-forbidden-uploader")
    stranger_email = unique_email("notes-delete-forbidden-stranger")
    course = _make_official_course(db, f"notes-delforbid-{uploader_email}")
    try:
        uploader_token = register_and_login(client, db, uploader_email)
        stranger_token = register_and_login(client, db, stranger_email)
        note_id = _add_note(uploader_token, course.id).json()["id"]
        resp = client.delete(f"/api/courses/{course.id}/notes/{note_id}", headers=auth_headers(stranger_token))
        assert resp.status_code == 403
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [uploader_email, stranger_email])
        db.close()


def test_delete_checks_course_visibility_same_as_list_and_add():
    """A stranger (neither the note's uploader, the course's submitter, nor
    an admin) trying to delete a note on a still-pending course they can't
    even see should get 404 (course not found, same as list/add), not 403
    (which would leak that a pending course exists at that id) -
    _get_visible_course_or_404 must run before the ownership check."""
    db = SessionLocal()
    sub_email = unique_email("notes-delvis-sub")
    stranger_email = unique_email("notes-delvis-stranger")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        stranger_token = register_and_login(client, db, stranger_email)
        resp = client.post(
            "/api/courses/submit",
            headers=auth_headers(sub_token),
            json={"name": "Курс за бришење видливост", "materials": [], "price": 0},
        )
        course_id = resp.json()["id"]  # still "pending" - only sub_token can see it

        note_id = _add_note(sub_token, course_id).json()["id"]

        resp = client.delete(f"/api/courses/{course_id}/notes/{note_id}", headers=auth_headers(stranger_token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [sub_email, stranger_email])
        db.close()


# -------------------------------------------------------------- validation ----

def test_javascript_scheme_url_is_rejected():
    """A javascript:/data: URL would otherwise sit in the DB and get
    rendered as a plain <a href> to every future viewer of the course page -
    only http(s) links are accepted."""
    db = SessionLocal()
    email = unique_email("notes-xss")
    course = _make_official_course(db, f"notes-xss-{email}")
    try:
        token = register_and_login(client, db, email)
        resp = _add_note(token, course.id, title="Click me", url="javascript:alert(document.cookie)")
        assert resp.status_code == 422
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [email])
        db.close()


def test_whitespace_only_title_is_rejected():
    db = SessionLocal()
    email = unique_email("notes-blanktitle")
    course = _make_official_course(db, f"notes-blanktitle-{email}")
    try:
        token = register_and_login(client, db, email)
        resp = _add_note(token, course.id, title="   ", url="https://example.com/x")
        assert resp.status_code == 422
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [email])
        db.close()


# --------------------------------------------------------- admin oversight ----

def test_admin_can_list_notes_across_every_course():
    db = SessionLocal()
    email = unique_email("notes-adminlist-uploader")
    admin_email = unique_email("notes-adminlist-admin")
    course = _make_official_course(db, f"notes-adminlist-{email}")
    try:
        token = register_and_login(client, db, email)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        note_id = _add_note(token, course.id, title="За модерирање").json()["id"]

        resp = client.get("/api/admin/notes", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        found = next((n for n in resp.json() if n["id"] == note_id), None)
        assert found is not None
        assert found["course_id"] == course.id
        assert found["course_name"] == "Test Course"
    finally:
        _delete_course_and_its_notes(db, course.id)
        cleanup_test_data(db, [email, admin_email])
        db.close()


def test_non_admin_cannot_list_notes_for_admin():
    db = SessionLocal()
    email = unique_email("notes-adminlist-forbidden")
    try:
        token = register_and_login(client, db, email)
        resp = client.get("/api/admin/notes", headers=auth_headers(token))
        assert resp.status_code == 403
    finally:
        cleanup_test_data(db, [email])
        db.close()
