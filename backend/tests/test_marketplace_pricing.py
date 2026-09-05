"""Marketplace listing filters (source/price_filter) and the priced-course
access rules (locked metadata vs. locked materials/recordings, and who
bypasses the lock: submitter, admin, or a CoursePurchase owner). Runs
against your real database - see README.md "Run the tests"."""
from fastapi.testclient import TestClient

from backend.database.models import Course, CoursePurchase, User
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


def _submit_and_approve(admin_token, sub_token, name, price=0):
    resp = client.post(
        "/api/courses/submit",
        headers=auth_headers(sub_token),
        json={"name": name, "materials": [{"title": "M", "url": "https://example.com/m.pdf"}], "price": price},
    )
    assert resp.status_code == 201, resp.text
    course_id = resp.json()["id"]
    approved = client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))
    assert approved.status_code == 200
    return course_id


# --------------------------------------------------------------- source ----

def test_source_official_excludes_community_and_vice_versa():
    db = SessionLocal()
    sub_email = unique_email("source-sub")
    admin_email = unique_email("source-admin")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        community_id = _submit_and_approve(admin_token, sub_token, "Community курс за source тест")

        official = client.get("/api/courses", params={"source": "official"}).json()
        assert community_id not in [c["id"] for c in official]

        community = client.get("/api/courses", params={"source": "community"}).json()
        assert community_id in [c["id"] for c in community]

        both = client.get("/api/courses", params={"source": "all"}).json()
        assert community_id in [c["id"] for c in both]

        bad = client.get("/api/courses", params={"source": "bogus"})
        assert bad.status_code == 400
    finally:
        cleanup_test_data(db, [sub_email, admin_email])
        db.close()


# ---------------------------------------------------------- price_filter ----

def test_price_filter_free_only_returns_zero_priced():
    db = SessionLocal()
    sub_email = unique_email("pf-free-sub")
    admin_email = unique_email("pf-free-admin")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        free_id = _submit_and_approve(admin_token, sub_token, "Бесплатен курс", price=0)
        priced_id = _submit_and_approve(admin_token, sub_token, "Платен курс", price=9.99)

        free_only = client.get("/api/courses", params={"source": "community", "price_filter": "free"}).json()
        ids = [c["id"] for c in free_only]
        assert free_id in ids
        assert priced_id not in ids
    finally:
        cleanup_test_data(db, [sub_email, admin_email])
        db.close()


def test_price_filter_purchased_requires_auth():
    resp = client.get("/api/courses", params={"source": "community", "price_filter": "purchased"})
    assert resp.status_code == 401


def test_price_filter_purchased_shows_submitters_own_and_bought_courses_only():
    """Two different submitters, so "purchased" for one of them can't be
    satisfied by the submitted_by_id == viewer.id branch alone for courses
    they didn't actually submit - isolates the CoursePurchase-based branch
    of the filter from the submitted-by-me branch."""
    db = SessionLocal()
    sub_email = unique_email("pf-pur-sub")
    other_sub_email = unique_email("pf-pur-othersub")
    admin_email = unique_email("pf-pur-admin")
    buyer_email = unique_email("pf-pur-buyer")
    stranger_email = unique_email("pf-pur-stranger")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        other_sub_token = register_and_login(client, db, other_sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        buyer_token = register_and_login(client, db, buyer_email)
        stranger_token = register_and_login(client, db, stranger_email)

        owned_priced_id = _submit_and_approve(admin_token, sub_token, "Мој платен курс", price=5)
        bought_priced_id = _submit_and_approve(admin_token, other_sub_token, "Купен курс", price=3)
        untouched_priced_id = _submit_and_approve(admin_token, other_sub_token, "Недопрен платен курс", price=3)

        buyer = db.query(User).filter(User.email == buyer_email).first()
        db.add(CoursePurchase(user_id=buyer.id, course_id=bought_priced_id, amount_cents=300))
        db.commit()

        submitter_view = client.get(
            "/api/courses", params={"source": "community", "price_filter": "purchased"}, headers=auth_headers(sub_token)
        ).json()
        submitter_ids = [c["id"] for c in submitter_view]
        assert owned_priced_id in submitter_ids
        assert bought_priced_id not in submitter_ids  # sub neither submitted nor bought it
        assert untouched_priced_id not in submitter_ids

        buyer_view = client.get(
            "/api/courses", params={"source": "community", "price_filter": "purchased"}, headers=auth_headers(buyer_token)
        ).json()
        buyer_ids = [c["id"] for c in buyer_view]
        assert bought_priced_id in buyer_ids
        assert owned_priced_id not in buyer_ids
        assert untouched_priced_id not in buyer_ids

        stranger_view = client.get(
            "/api/courses", params={"source": "community", "price_filter": "purchased"}, headers=auth_headers(stranger_token)
        ).json()
        assert stranger_view == []

        admin_view = client.get(
            "/api/courses", params={"source": "community", "price_filter": "purchased"}, headers=auth_headers(admin_token)
        ).json()
        admin_ids = [c["id"] for c in admin_view]
        # Admin sees every priced course via the purchased filter, not just their own/bought.
        assert owned_priced_id in admin_ids
        assert bought_priced_id in admin_ids
        assert untouched_priced_id in admin_ids
    finally:
        cleanup_test_data(db, [sub_email, other_sub_email, admin_email, buyer_email, stranger_email])
        db.close()


def test_invalid_price_filter_is_400():
    resp = client.get("/api/courses", params={"price_filter": "bogus"})
    assert resp.status_code == 400


# -------------------------------------------------------------- locking ----

def test_free_course_materials_are_open_to_anyone():
    db = SessionLocal()
    sub_email = unique_email("lock-free-sub")
    admin_email = unique_email("lock-free-admin")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        free_id = _submit_and_approve(admin_token, sub_token, "Отклучен курс", price=0)

        detail = client.get(f"/api/courses/{free_id}").json()
        assert detail["locked"] is False

        materials = client.get(f"/api/courses/{free_id}/materials")
        assert materials.status_code == 200
    finally:
        cleanup_test_data(db, [sub_email, admin_email])
        db.close()


def test_priced_course_is_locked_for_a_random_viewer_but_metadata_still_shows():
    db = SessionLocal()
    sub_email = unique_email("lock-priced-sub")
    admin_email = unique_email("lock-priced-admin")
    stranger_email = unique_email("lock-priced-stranger")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        stranger_token = register_and_login(client, db, stranger_email)
        priced_id = _submit_and_approve(admin_token, sub_token, "Заклучен курс", price=7.5)

        detail = client.get(f"/api/courses/{priced_id}", headers=auth_headers(stranger_token)).json()
        assert detail["locked"] is True
        assert detail["price_cents"] == 750  # metadata (incl. price) still visible

        materials = client.get(f"/api/courses/{priced_id}/materials", headers=auth_headers(stranger_token))
        assert materials.status_code == 402
        recordings = client.get(f"/api/courses/{priced_id}/recordings", headers=auth_headers(stranger_token))
        assert recordings.status_code == 402

        anon_detail = client.get(f"/api/courses/{priced_id}")
        assert anon_detail.json()["locked"] is True
    finally:
        cleanup_test_data(db, [sub_email, admin_email, stranger_email])
        db.close()


def test_priced_course_unlocked_for_submitter_admin_and_purchaser():
    db = SessionLocal()
    sub_email = unique_email("lock-unlock-sub")
    admin_email = unique_email("lock-unlock-admin")
    buyer_email = unique_email("lock-unlock-buyer")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        buyer_token = register_and_login(client, db, buyer_email)
        priced_id = _submit_and_approve(admin_token, sub_token, "Курс за отклучување", price=4.5)

        buyer = db.query(User).filter(User.email == buyer_email).first()
        db.add(CoursePurchase(user_id=buyer.id, course_id=priced_id, amount_cents=450))
        db.commit()

        for token in (sub_token, admin_token, buyer_token):
            detail = client.get(f"/api/courses/{priced_id}", headers=auth_headers(token)).json()
            assert detail["locked"] is False
            materials = client.get(f"/api/courses/{priced_id}/materials", headers=auth_headers(token))
            assert materials.status_code == 200
    finally:
        cleanup_test_data(db, [sub_email, admin_email, buyer_email])
        db.close()
