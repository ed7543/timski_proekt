"""HTTP-level tests for the Blog admin endpoints (/api/blog POST/DELETE):
who can reach them, the SSRF guard on pasted URLs, and the duplicate-URL
guard. Runs against your real database - see README.md "Run the tests".

fetch_article_metadata is mocked for the "happy path"/dedup tests (same
pattern as test_finki_announcements.py) so they don't depend on real
network access or a specific external page's markup; the SSRF tests
deliberately do NOT mock it, since the whole point is to exercise
blog_fetcher.py's own address-validation guard before any HTTP request
would be made.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.database.models import BlogPost
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)
pytestmark = pytest.mark.bulk_register

# Unique prefix so cleanup never touches real data (same convention as
# test_finki_announcements.py's _TEST_URL_PREFIX).
_TEST_URL_PREFIX = "https://test.example/__blog_route_test__/"


def _cleanup_test_blog_posts(db):
    db.query(BlogPost).filter(BlogPost.source_url.like(f"{_TEST_URL_PREFIX}%")).delete(synchronize_session=False)
    db.commit()


_FAKE_META = {
    "title": "Тест статија",
    "excerpt": "Краток опис",
    "image_url": "https://example.com/img.jpg",
    "source_name": "test.example",
}


# --------------------------------------------------------------- gating ----

def test_create_and_delete_require_auth():
    assert client.post("/api/blog", json={"url": f"{_TEST_URL_PREFIX}x"}).status_code == 401
    assert client.delete("/api/blog/1").status_code == 401


def test_create_and_delete_reject_non_admin():
    db = SessionLocal()
    email = unique_email("blog-gate-student")
    try:
        token = register_and_login(client, db, email)
        headers = auth_headers(token)
        assert client.post("/api/blog", headers=headers, json={"url": f"{_TEST_URL_PREFIX}x"}).status_code == 403
        assert client.delete("/api/blog/1", headers=headers).status_code == 403
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_list_is_public_and_requires_no_auth():
    # No Authorization header at all - matches the docstring in
    # routes/blogRoute.py ("Public ... No auth required").
    resp = client.get("/api/blog")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# -------------------------------------------------------------- SSRF ------

@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",  # AWS/GCP metadata IP
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "ftp://example.com/file",  # non-http(s) scheme
    ],
)
def test_create_rejects_unsafe_urls(unsafe_url):
    db = SessionLocal()
    email = unique_email("blog-ssrf-admin")
    try:
        token = register_and_login(client, db, email, role="admin")
        resp = client.post("/api/blog", headers=auth_headers(token), json={"url": unsafe_url})
        assert resp.status_code == 422, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


# ------------------------------------------------------------- create -----

def test_admin_can_create_post():
    db = SessionLocal()
    email = unique_email("blog-create-admin")
    url = f"{_TEST_URL_PREFIX}create-1"
    try:
        _cleanup_test_blog_posts(db)
        token = register_and_login(client, db, email, role="admin")
        with patch("backend.routes.blogRoute.fetch_article_metadata", return_value=_FAKE_META):
            resp = client.post("/api/blog", headers=auth_headers(token), json={"url": url, "category": "Препораки"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["title"] == _FAKE_META["title"]
        assert body["source_url"] == url
        assert body["category"] == "Препораки"
    finally:
        _cleanup_test_blog_posts(db)
        cleanup_test_data(db, [email])
        db.close()


def test_admin_cannot_create_duplicate_post():
    db = SessionLocal()
    email = unique_email("blog-dup-admin")
    url = f"{_TEST_URL_PREFIX}dup-1"
    try:
        _cleanup_test_blog_posts(db)
        token = register_and_login(client, db, email, role="admin")
        with patch("backend.routes.blogRoute.fetch_article_metadata", return_value=_FAKE_META):
            first = client.post("/api/blog", headers=auth_headers(token), json={"url": url})
            assert first.status_code == 201, first.text
            second = client.post("/api/blog", headers=auth_headers(token), json={"url": url})
        assert second.status_code == 409, second.text
        posts = db.query(BlogPost).filter(BlogPost.source_url == url).all()
        assert len(posts) == 1
    finally:
        _cleanup_test_blog_posts(db)
        cleanup_test_data(db, [email])
        db.close()


def test_create_returns_422_on_fetch_failure():
    db = SessionLocal()
    email = unique_email("blog-fetchfail-admin")
    url = f"{_TEST_URL_PREFIX}unreachable"
    try:
        from backend.services.blog_fetcher import BlogFetchError

        token = register_and_login(client, db, email, role="admin")
        with patch("backend.routes.blogRoute.fetch_article_metadata", side_effect=BlogFetchError("Не успеав да ја отворам страницата")):
            resp = client.post("/api/blog", headers=auth_headers(token), json={"url": url})
        assert resp.status_code == 422, resp.text
    finally:
        cleanup_test_data(db, [email])
        db.close()


# -------------------------------------------------------------- delete ----

def test_admin_can_delete_post():
    db = SessionLocal()
    email = unique_email("blog-delete-admin")
    url = f"{_TEST_URL_PREFIX}delete-1"
    try:
        _cleanup_test_blog_posts(db)
        token = register_and_login(client, db, email, role="admin")
        with patch("backend.routes.blogRoute.fetch_article_metadata", return_value=_FAKE_META):
            created = client.post("/api/blog", headers=auth_headers(token), json={"url": url})
        post_id = created.json()["id"]
        resp = client.delete(f"/api/blog/{post_id}", headers=auth_headers(token))
        assert resp.status_code == 204
        assert db.query(BlogPost).filter(BlogPost.id == post_id).first() is None
    finally:
        _cleanup_test_blog_posts(db)
        cleanup_test_data(db, [email])
        db.close()
