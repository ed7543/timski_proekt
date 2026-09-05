"""POST /api/courses/upload-material. The real Supabase client
(supabase.create_client) is mocked out - these tests never hit a real
Supabase project and don't need SUPABASE_* configured in .env. Runs
against your real database for the User rows it touches - see README.md
"Run the tests"."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


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


def _upload(token, filename="notes.pdf", content=b"hello world", content_type="application/pdf"):
    return client.post(
        "/api/courses/upload-material",
        headers=auth_headers(token),
        files={"file": (filename, content, content_type)},
    )


def test_upload_requires_auth():
    resp = client.post("/api/courses/upload-material", files={"file": ("x.pdf", b"data", "application/pdf")})
    assert resp.status_code == 401


def test_upload_requires_premium_subscription(monkeypatch):
    _configure_supabase(monkeypatch)
    db = SessionLocal()
    email = unique_email("upload-notpremium")
    try:
        token = register_and_login(client, db, email)  # plain student
        resp = _upload(token)
        assert resp.status_code == 403
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


def test_upload_rejects_file_over_size_limit(monkeypatch):
    _configure_supabase(monkeypatch)
    monkeypatch.setattr("backend.routes.uploadRoute.MAX_UPLOAD_BYTES", 10)  # tiny, so the test file doesn't need to be 50MB
    db = SessionLocal()
    email = unique_email("upload-toolarge")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        fake_client = _FakeSupabaseClient()
        with patch("backend.routes.uploadRoute.create_client", return_value=fake_client):
            resp = _upload(token, content=b"this is definitely more than ten bytes")
        assert resp.status_code == 413
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
