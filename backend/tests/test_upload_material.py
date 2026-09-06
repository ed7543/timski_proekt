"""POST /api/courses/upload-material. The real Supabase client
(supabase.create_client) is mocked out - these tests never hit a real
Supabase project and don't need SUPABASE_* configured in .env. Runs
against your real database for the User rows it touches - see README.md
"Run the tests"."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database.session import SessionLocal
from backend.main import app
from backend.middleware.rate_limit import limiter
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)
pytestmark = pytest.mark.bulk_register

_REAL_PDF_BYTES = b"%PDF-1.4 fake content"


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    # Same reasoning as test_lesson_quiz_rate_limit.py - the 10/minute limit
    # on this endpoint would otherwise leak state between tests/modules.
    limiter.reset()
    yield
    limiter.reset()


class _FakeBucket:
    def __init__(self):
        self.uploaded = []

    def upload(self, path, contents, options):
        self.uploaded.append((path, contents, options))
        return {"path": path}

    def get_public_url(self, path):
        return f"https://fake.supabase.co/storage/v1/object/public/course-materials/{path}"


class _FakeStorage:
    def __init__(self, bucket):
        self._bucket = bucket

    def from_(self, bucket_name):
        return self._bucket


class _FakeSupabaseClient:
    def __init__(self):
        self.bucket = _FakeBucket()
        self.storage = _FakeStorage(self.bucket)


def _configure_supabase(monkeypatch, url="https://fake.supabase.co", key="sb_secret_fake"):
    """SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY are module-level constants read
    once from config at uploadRoute import time - patch those directly."""
    monkeypatch.setattr("backend.routes.uploadRoute.SUPABASE_URL", url)
    monkeypatch.setattr("backend.routes.uploadRoute.SUPABASE_SERVICE_ROLE_KEY", key)


def _upload(token, filename="notes.pdf", content=_REAL_PDF_BYTES, content_type="application/pdf", context=None):
    data = {"context": context} if context is not None else {}
    return client.post(
        "/api/courses/upload-material",
        headers=auth_headers(token),
        files={"file": (filename, content, content_type)},
        data=data,
    )


def test_upload_requires_auth():
    resp = client.post("/api/courses/upload-material", files={"file": ("x.pdf", b"data", "application/pdf")})
    assert resp.status_code == 401


def test_upload_allowed_for_a_plain_non_premium_student(monkeypatch):
    """Uploading a file is a free action for any logged-in user - the
    premium gate lives downstream, at POST /api/courses/submit, not here.
    See CourseNote (routes/courseRoute.py) for the other, non-premium path
    that actually attaches an uploaded file's URL somewhere."""
    _configure_supabase(monkeypatch)
    db = SessionLocal()
    email = unique_email("upload-notpremium")
    try:
        token = register_and_login(client, db, email)  # plain student, is_premium=False
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token)
        assert resp.status_code == 200, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_500_when_supabase_not_configured():
    db = SessionLocal()
    email = unique_email("upload-notconfigured")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        with patch("backend.routes.uploadRoute.SUPABASE_URL", ""), patch("backend.routes.uploadRoute.SUPABASE_SERVICE_ROLE_KEY", ""):
            resp = _upload(token)
        assert resp.status_code == 500
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_success_returns_public_url(monkeypatch):
    _configure_supabase(monkeypatch)
    db = SessionLocal()
    email = unique_email("upload-success")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token, filename="скрипта.pdf", content=b"%PDF-1.4 fake content", content_type="application/pdf")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["original_filename"] == "скрипта.pdf"
        assert body["resource_type"] == "application/pdf"
        assert body["url"].startswith("https://fake.supabase.co/storage/v1/object/public/course-materials/")
        assert body["url"].endswith(".pdf")

        # Uploaded with a random-uuid path, not the original filename - so
        # two people uploading "notes.pdf" never collide (see uploadRoute.py).
        uploaded_path, uploaded_bytes, _ = fake_client.bucket.uploaded[0]
        assert uploaded_path != "скрипта.pdf"
        assert uploaded_bytes == b"%PDF-1.4 fake content"
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_admin_can_upload_without_being_premium(monkeypatch):
    _configure_supabase(monkeypatch)
    db = SessionLocal()
    email = unique_email("upload-admin")
    try:
        token = register_and_login(client, db, email, role="admin", is_premium=False)
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token)
        assert resp.status_code == 200, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_rejects_an_unsupported_content_type():
    """Content with no recognizable magic bytes at all (not just a bad
    declared header) - genuinely not one of the allowed types, regardless
    of what Content-Type the client claims. Checked before Supabase is even
    consulted, so this doesn't need _configure_supabase."""
    db = SessionLocal()
    email = unique_email("upload-badtype")
    try:
        token = register_and_login(client, db, email)
        resp = _upload(
            token, filename="virus.exe",
            content=b"MZ\x90\x00\x03\x00\x00\x00 definitely not a pdf",
            content_type="application/x-msdownload",
        )
        assert resp.status_code == 415
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_rejects_a_mislabeled_file_despite_a_valid_declared_content_type():
    """The declared Content-Type header is fully attacker-controlled and is
    no longer trusted at all - only the actual leading bytes matter. A file
    that's really plain text, dressed up with Content-Type: application/pdf,
    must still be rejected."""
    db = SessionLocal()
    email = unique_email("upload-mislabeled")
    try:
        token = register_and_login(client, db, email)
        resp = _upload(
            token, filename="notes.pdf",
            content=b"just plain text, not a real pdf at all",
            content_type="application/pdf",  # lying about what this is
        )
        assert resp.status_code == 415
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_rejects_file_over_size_limit(monkeypatch):
    _configure_supabase(monkeypatch)
    monkeypatch.setattr("backend.routes.uploadRoute.MAX_UPLOAD_BYTES_BY_CONTEXT", {"material": 10, "note": 10})
    db = SessionLocal()
    email = unique_email("upload-toolarge")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token, content=_REAL_PDF_BYTES + b" - definitely more than ten bytes")
        assert resp.status_code == 413
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_note_context_gets_a_smaller_size_cap_than_material(monkeypatch):
    """context='note' (the community-notes path, no premium gate at all) is
    capped much lower than context='material' (default, premium course
    submissions) - see MAX_UPLOAD_BYTES_BY_CONTEXT."""
    _configure_supabase(monkeypatch)
    monkeypatch.setattr("backend.routes.uploadRoute.MAX_UPLOAD_BYTES_BY_CONTEXT", {"material": 1000, "note": 10})
    db = SessionLocal()
    email = unique_email("upload-notecap")
    try:
        token = register_and_login(client, db, email)
        content = _REAL_PDF_BYTES + b" - more than ten bytes but under a thousand"
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            note_resp = _upload(token, content=content, context="note")
            material_resp = _upload(token, content=content, context="material")
        assert note_resp.status_code == 413, note_resp.text
        assert material_resp.status_code == 200, material_resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_rejects_an_invalid_context_value():
    db = SessionLocal()
    email = unique_email("upload-badcontext")
    try:
        token = register_and_login(client, db, email)
        resp = _upload(token, context="bogus")
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_upload_returns_502_when_supabase_raises(monkeypatch):
    _configure_supabase(monkeypatch)
    db = SessionLocal()
    email = unique_email("upload-supabasefails")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        fake_client = _FakeSupabaseClient()
        fake_client.bucket.upload = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("storage is down"))
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token)
        assert resp.status_code == 502
    finally:
        cleanup_test_data(db, [email])
        db.close()
