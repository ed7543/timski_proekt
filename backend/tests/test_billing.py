"""Billing endpoints (/api/billing/*). Every real Stripe SDK call
(Price.retrieve, checkout.Session.create, Subscription.delete,
Webhook.construct_event) is mocked - these tests never hit Stripe's actual
API and don't need real STRIPE_* keys configured in .env. Runs against your
real database for the User/Course/CoursePurchase rows it touches - see
README.md "Run the tests"."""
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from fastapi.testclient import TestClient

from backend.database.models import CoursePurchase, User
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email

client = TestClient(app)


def _configure_stripe(monkeypatch, secret="sk_test_fake", price_id="price_fake", webhook_secret="whsec_fake"):
    """STRIPE_SECRET_KEY/STRIPE_PRICE_ID/STRIPE_WEBHOOK_SECRET are read once
    from config at billingRoute import time (module-level constants, not
    re-read per request) - patch those names directly rather than the
    environment, which wouldn't be re-read after import."""
    monkeypatch.setattr("backend.routes.billingRoute.STRIPE_SECRET_KEY", secret)
    monkeypatch.setattr("backend.routes.billingRoute.STRIPE_PRICE_ID", price_id)
    monkeypatch.setattr("backend.routes.billingRoute.STRIPE_WEBHOOK_SECRET", webhook_secret)


# ---------------------------------------------------------------- plans ----

def test_plans_is_empty_when_stripe_not_configured(monkeypatch):
    _configure_stripe(monkeypatch, secret="", price_id="")
    resp = client.get("/api/billing/plans")
    assert resp.status_code == 200
    assert resp.json() == []


def test_plans_returns_live_stripe_price_data(monkeypatch):
    _configure_stripe(monkeypatch)
    fake_price = {
        "unit_amount": 999,
        "currency": "eur",
        "recurring": {"interval": "month"},
        "product": {"name": "Course Submission", "description": "Unlock submitting courses"},
    }
    with patch("stripe.Price.retrieve", return_value=fake_price) as mock_retrieve:
        resp = client.get("/api/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) == 1
    assert plans[0]["price_cents"] == 999
    assert plans[0]["currency"] == "eur"
    assert plans[0]["interval"] == "month"
    assert plans[0]["name"] == "Course Submission"
    mock_retrieve.assert_called_once()


def test_plans_returns_empty_list_on_stripe_error_instead_of_500(monkeypatch):
    _configure_stripe(monkeypatch)
    with patch("stripe.Price.retrieve", side_effect=stripe.error.StripeError("boom")):
        resp = client.get("/api/billing/plans")
    assert resp.status_code == 200
    assert resp.json() == []


# -------------------------------------------------------------- checkout ----

def test_checkout_requires_auth(monkeypatch):
    _configure_stripe(monkeypatch)
    resp = client.post("/api/billing/checkout")
    assert resp.status_code == 401


def test_checkout_500s_when_stripe_not_configured():
    db = SessionLocal()
    email = unique_email("checkout-notconfigured")
    try:
        token = register_and_login(client, db, email)
        with patch("backend.routes.billingRoute.STRIPE_SECRET_KEY", ""):
            resp = client.post("/api/billing/checkout", headers=auth_headers(token))
        assert resp.status_code == 500
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_checkout_rejects_already_premium_user(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    email = unique_email("checkout-alreadypremium")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        resp = client.post("/api/billing/checkout", headers=auth_headers(token))
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_checkout_success_returns_url_and_sets_correct_metadata(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    email = unique_email("checkout-success")
    try:
        token = register_and_login(client, db, email)
        fake_session = SimpleNamespace(url="https://checkout.stripe.com/fake-session")
        with patch("stripe.checkout.Session.create", return_value=fake_session) as mock_create:
            resp = client.post("/api/billing/checkout", headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"checkout_url": "https://checkout.stripe.com/fake-session"}

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["metadata"]["kind"] == "submission_subscription"
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_checkout_stripe_error_is_502(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    email = unique_email("checkout-stripeerror")
    try:
        token = register_and_login(client, db, email)
        with patch("stripe.checkout.Session.create", side_effect=stripe.error.StripeError("card issue")):
            resp = client.post("/api/billing/checkout", headers=auth_headers(token))
        assert resp.status_code == 502
    finally:
        cleanup_test_data(db, [email])
        db.close()


# ---------------------------------------------------------------- cancel ----

def test_cancel_requires_auth():
    resp = client.post("/api/billing/cancel")
    assert resp.status_code == 401


def test_cancel_without_active_subscription_is_400():
    db = SessionLocal()
    email = unique_email("cancel-notpremium")
    try:
        token = register_and_login(client, db, email, is_premium=False)
        resp = client.post("/api/billing/cancel", headers=auth_headers(token))
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_cancel_with_no_stripe_subscription_id_just_flips_the_flag_locally():
    """Shouldn't normally happen (is_premium is only ever set alongside
    stripe_subscription_id by the webhook) but must degrade gracefully - and
    critically, must NOT call the Stripe API with a None subscription id."""
    db = SessionLocal()
    email = unique_email("cancel-noStripeId")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        with patch("stripe.Subscription.delete") as mock_delete:
            resp = client.post("/api/billing/cancel", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json() == {"is_premium": False}
        mock_delete.assert_not_called()

        user = db.query(User).filter(User.email == email).first()
        assert user.is_premium is False
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_cancel_calls_stripe_and_clears_local_state_on_success():
    db = SessionLocal()
    email = unique_email("cancel-success")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        user = db.query(User).filter(User.email == email).first()
        user.stripe_subscription_id = "sub_fake123"
        db.commit()

        with patch("stripe.Subscription.delete") as mock_delete:
            resp = client.post("/api/billing/cancel", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json() == {"is_premium": False}
        mock_delete.assert_called_once_with("sub_fake123")

        db.refresh(user)
        assert user.is_premium is False
        assert user.stripe_subscription_id is None
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_cancel_stripe_failure_does_not_flip_is_premium():
    """Data-integrity invariant: if Stripe itself fails to cancel, our DB
    must NOT silently claim the subscription is gone - is_premium and
    stripe_subscription_id must be left untouched so the app's state never
    drifts from Stripe's actual state."""
    db = SessionLocal()
    email = unique_email("cancel-stripefails")
    try:
        token = register_and_login(client, db, email, is_premium=True)
        user = db.query(User).filter(User.email == email).first()
        user.stripe_subscription_id = "sub_fake456"
        db.commit()

        with patch("stripe.Subscription.delete", side_effect=stripe.error.StripeError("network blip")):
            resp = client.post("/api/billing/cancel", headers=auth_headers(token))
        assert resp.status_code == 502

        db.refresh(user)
        assert user.is_premium is True
        assert user.stripe_subscription_id == "sub_fake456"
    finally:
        cleanup_test_data(db, [email])
        db.close()


# --------------------------------------------------------- course checkout ----

def test_course_checkout_404_for_nonexistent_course(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    email = unique_email("coursecheckout-404")
    try:
        token = register_and_login(client, db, email)
        resp = client.post("/api/billing/courses/999999999/checkout", headers=auth_headers(token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_course_checkout_400_for_a_free_course(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    sub_email = unique_email("coursecheckout-free-sub")
    admin_email = unique_email("coursecheckout-free-admin")
    buyer_email = unique_email("coursecheckout-free-buyer")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        buyer_token = register_and_login(client, db, buyer_email)
        resp = client.post(
            "/api/courses/submit", headers=auth_headers(sub_token),
            json={"name": "Бесплатен курс за checkout тест", "materials": [], "price": 0},
        )
        course_id = resp.json()["id"]
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        resp = client.post(f"/api/billing/courses/{course_id}/checkout", headers=auth_headers(buyer_token))
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [sub_email, admin_email, buyer_email])
        db.close()


def test_course_checkout_400_when_already_purchased(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    sub_email = unique_email("coursecheckout-owned-sub")
    admin_email = unique_email("coursecheckout-owned-admin")
    buyer_email = unique_email("coursecheckout-owned-buyer")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        buyer_token = register_and_login(client, db, buyer_email)
        resp = client.post(
            "/api/courses/submit", headers=auth_headers(sub_token),
            json={"name": "Платен курс за double-buy тест", "materials": [], "price": 5},
        )
        course_id = resp.json()["id"]
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        buyer = db.query(User).filter(User.email == buyer_email).first()
        db.add(CoursePurchase(user_id=buyer.id, course_id=course_id, amount_cents=500))
        db.commit()

        resp = client.post(f"/api/billing/courses/{course_id}/checkout", headers=auth_headers(buyer_token))
        assert resp.status_code == 400
    finally:
        cleanup_test_data(db, [sub_email, admin_email, buyer_email])
        db.close()


def test_course_checkout_success_returns_url(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    sub_email = unique_email("coursecheckout-ok-sub")
    admin_email = unique_email("coursecheckout-ok-admin")
    buyer_email = unique_email("coursecheckout-ok-buyer")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        buyer_token = register_and_login(client, db, buyer_email)
        resp = client.post(
            "/api/courses/submit", headers=auth_headers(sub_token),
            json={"name": "Платен курс за успешен checkout", "materials": [], "price": 12.5},
        )
        course_id = resp.json()["id"]
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        fake_session = SimpleNamespace(url="https://checkout.stripe.com/fake-course-session")
        with patch("stripe.checkout.Session.create", return_value=fake_session) as mock_create:
            resp = client.post(f"/api/billing/courses/{course_id}/checkout", headers=auth_headers(buyer_token))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"checkout_url": "https://checkout.stripe.com/fake-course-session"}

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["mode"] == "payment"
        assert call_kwargs["metadata"]["kind"] == "course_purchase"
        assert call_kwargs["line_items"][0]["price_data"]["unit_amount"] == 1250
    finally:
        cleanup_test_data(db, [sub_email, admin_email, buyer_email])
        db.close()


# -------------------------------------------------------------- webhook ----

def test_webhook_rejects_invalid_signature(monkeypatch):
    _configure_stripe(monkeypatch)
    with patch("stripe.Webhook.construct_event", side_effect=stripe.error.SignatureVerificationError("bad sig", "sig_header")):
        resp = client.post("/api/billing/webhook", data=b"{}", headers={"stripe-signature": "bogus"})
    assert resp.status_code == 400


def test_webhook_submission_subscription_sets_is_premium_and_stripe_ids(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    email = unique_email("webhook-sub")
    try:
        register_and_login(client, db, email)
        user = db.query(User).filter(User.email == email).first()

        fake_event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "metadata": {"kind": "submission_subscription", "user_id": str(user.id)},
                "customer": "cus_fake",
                "subscription": "sub_fakeXYZ",
            }},
        }
        with patch("stripe.Webhook.construct_event", return_value=fake_event):
            resp = client.post("/api/billing/webhook", data=b"{}", headers={"stripe-signature": "sig"})
        assert resp.status_code == 200

        db.refresh(user)
        assert user.is_premium is True
        assert user.stripe_customer_id == "cus_fake"
        assert user.stripe_subscription_id == "sub_fakeXYZ"
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_webhook_course_purchase_creates_purchase_and_is_idempotent_on_redelivery(monkeypatch):
    _configure_stripe(monkeypatch)
    db = SessionLocal()
    sub_email = unique_email("webhook-purchase-sub")
    admin_email = unique_email("webhook-purchase-admin")
    buyer_email = unique_email("webhook-purchase-buyer")
    try:
        sub_token = register_and_login(client, db, sub_email, is_premium=True)
        admin_token = register_and_login(client, db, admin_email, role="admin")
        register_and_login(client, db, buyer_email)
        buyer = db.query(User).filter(User.email == buyer_email).first()

        resp = client.post(
            "/api/courses/submit", headers=auth_headers(sub_token),
            json={"name": "Курс за webhook купување", "materials": [], "price": 6},
        )
        course_id = resp.json()["id"]
        client.post(f"/api/admin/courses/{course_id}/approve", headers=auth_headers(admin_token))

        fake_event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "metadata": {"kind": "course_purchase", "user_id": str(buyer.id), "course_id": str(course_id)},
                "amount_total": 600,
            }},
        }
        with patch("stripe.Webhook.construct_event", return_value=fake_event):
            first = client.post("/api/billing/webhook", data=b"{}", headers={"stripe-signature": "sig"})
            second = client.post("/api/billing/webhook", data=b"{}", headers={"stripe-signature": "sig"})
        assert first.status_code == 200
        assert second.status_code == 200  # Stripe can redeliver - must not error

        purchases = db.query(CoursePurchase).filter(
            CoursePurchase.user_id == buyer.id, CoursePurchase.course_id == course_id
        ).all()
        assert len(purchases) == 1
        assert purchases[0].amount_cents == 600
    finally:
        cleanup_test_data(db, [sub_email, admin_email, buyer_email])
        db.close()
