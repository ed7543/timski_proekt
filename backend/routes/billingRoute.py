"""Stripe billing - two independent things happen here:

1. A recurring subscription that unlocks course submission (User.is_premium),
   via POST /checkout.
2. A one-time payment a student makes to unlock a single priced course
   (CoursePurchase), via POST /courses/{course_id}/checkout. The course's
   price is set by whoever submitted it (Course.price_cents, see
   CourseSubmitRequest.price) - we don't pre-create a Stripe Price for each
   course, we build the Checkout line item's price inline (`price_data`) at
   checkout time so any professor can set any amount without touching Stripe.

Both flows land on the same /webhook endpoint; the handler branches on
metadata["kind"] to know which one just got paid for.

Test-mode only for now - see .env.example for how to get test keys and a
local webhook secret via `stripe listen`.

NOTE (flagged for the team): Stripe does not currently support North
Macedonia as a merchant/payout country (confirmed against
https://stripe.com/global), so this only works end-to-end with a Stripe
account registered in a supported country - fine for local dev/testing with
test-mode keys, but going to production with real charges will need a
different processor (Paddle/Lemon Squeezy as Merchant-of-Record, or PayPal)
or a supported-country entity to hold the Stripe account.
"""
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database.models import Course, CoursePurchase, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_user
from config import FRONTEND_URL, STRIPE_PRICE_ID, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

stripe.api_key = STRIPE_SECRET_KEY


@router.get("/plans")
async def list_plans():
    """Available subscription plans - just the one (course submission) for
    now, but shaped as a list so more can be added later without the
    frontend's /subscribe page needing to change. Price/name/interval are
    read live from Stripe (via STRIPE_PRICE_ID) rather than hardcoded here,
    so this always matches whatever's actually configured - no risk of the
    page quoting a stale price after a change in the Stripe dashboard."""
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return []
    try:
        price = stripe.Price.retrieve(STRIPE_PRICE_ID, expand=["product"])
    except stripe.error.StripeError:
        logger.exception("Failed to fetch Stripe price for /billing/plans")
        return []

    product = price.get("product") or {}
    recurring = price.get("recurring") or {}
    return [{
        "id": "submission_subscription",
        "name": product.get("name") or "Course Submission",
        "description": product.get("description"),
        "price_cents": price.get("unit_amount") or 0,
        "currency": price.get("currency") or "eur",
        "interval": recurring.get("interval"),  # "year" | "month" | None
    }]


@router.post("/checkout")
async def create_checkout_session(current_user: User = Depends(get_current_user)):
    """Start a Stripe Checkout session for the course-submission subscription.
    Returns a URL the frontend redirects the browser to."""
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    if current_user.is_premium:
        raise HTTPException(status_code=400, detail="Already premium")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            customer_email=current_user.email,
            client_reference_id=str(current_user.id),
            metadata={"kind": "submission_subscription", "user_id": str(current_user.id)},
            success_url=f"{FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/billing/cancel",
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"checkout_url": session.url}


@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancels the current user's course-submission subscription immediately
    (not at period end) - Stripe is the source of truth so we cancel there
    first, then flip is_premium off locally once that's confirmed. An admin
    who never actually subscribed (is_premium False, submitting only via
    their role bypass) has nothing to cancel here."""
    if not current_user.is_premium:
        raise HTTPException(status_code=400, detail="You don't have an active subscription")
    if not current_user.stripe_subscription_id:
        # Shouldn't normally happen (is_premium is only ever set alongside
        # stripe_subscription_id in the webhook above) but don't leave the
        # user stuck if it does - just clear the flag locally.
        current_user.is_premium = False
        db.commit()
        return {"is_premium": False}

    try:
        stripe.Subscription.delete(current_user.stripe_subscription_id)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe subscription cancellation failed for user %s", current_user.id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    current_user.is_premium = False
    current_user.stripe_subscription_id = None
    db.commit()
    logger.info("User %s cancelled their submission subscription", current_user.id)
    return {"is_premium": False}


@router.post("/courses/{course_id}/checkout")
async def create_course_checkout_session(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a one-time Stripe Checkout session to unlock a single priced
    course's materials/recordings for the current user."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    course = db.query(Course).filter(Course.id == course_id, Course.status == "approved").first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.price_cents <= 0:
        raise HTTPException(status_code=400, detail="This course is free - nothing to buy")

    already_purchased = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == current_user.id, CoursePurchase.course_id == course.id)
        .first()
    )
    if already_purchased:
        raise HTTPException(status_code=400, detail="You already own this course")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": course.price_cents,
                    "product_data": {"name": course.name},
                },
                "quantity": 1,
            }],
            customer_email=current_user.email,
            metadata={
                "kind": "course_purchase",
                "user_id": str(current_user.id),
                "course_id": str(course.id),
            },
            success_url=f"{FRONTEND_URL}/marketplace/{course.id}?purchased=1",
            cancel_url=f"{FRONTEND_URL}/marketplace/{course.id}",
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe course checkout session creation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe calls this when a checkout/subscription event happens. Only
    checkout.session.completed is handled - that's the moment payment
    actually succeeded. metadata["kind"] tells us whether to flip
    is_premium (submission subscription) or record a CoursePurchase
    (one-time course unlock)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("Rejected Stripe webhook: invalid payload/signature")
        raise HTTPException(status_code=400, detail="Invalid webhook payload or signature") from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata") or {}
        kind = metadata.get("kind", "submission_subscription")  # older sessions had no "kind"

        if kind == "course_purchase":
            _handle_course_purchase(db, metadata, session)
        else:
            _handle_submission_subscription(db, metadata, session)

    return {"received": True}


def _handle_submission_subscription(db: Session, metadata: dict, session: dict) -> None:
    user_id = metadata.get("user_id") or session.get("client_reference_id")
    if not user_id:
        logger.warning("Stripe webhook: submission_subscription with no user_id metadata")
        return
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        logger.warning("Stripe webhook: no user found for id %s", user_id)
        return
    user.is_premium = True
    # Recorded so POST /api/billing/cancel knows which Stripe subscription to
    # actually cancel later - session["customer"]/["subscription"] are only
    # present on a mode="subscription" Checkout Session (always the case
    # here, since this handler is only reached for kind=submission_subscription).
    user.stripe_customer_id = session.get("customer")
    user.stripe_subscription_id = session.get("subscription")
    db.commit()
    logger.info("User %s upgraded to premium via Stripe checkout", user_id)


def _handle_course_purchase(db: Session, metadata: dict, session: dict) -> None:
    user_id = metadata.get("user_id")
    course_id = metadata.get("course_id")
    if not user_id or not course_id:
        logger.warning("Stripe webhook: course_purchase with missing user_id/course_id metadata")
        return

    # Idempotent: Stripe can redeliver the same event, and CoursePurchase has
    # a unique(user_id, course_id) constraint - just skip if it already exists.
    existing = (
        db.query(CoursePurchase)
        .filter(CoursePurchase.user_id == int(user_id), CoursePurchase.course_id == int(course_id))
        .first()
    )
    if existing:
        logger.info("Stripe webhook: course_purchase for user %s/course %s already recorded", user_id, course_id)
        return

    db.add(CoursePurchase(
        user_id=int(user_id),
        course_id=int(course_id),
        amount_cents=session.get("amount_total") or 0,
    ))
    db.commit()
    logger.info("User %s purchased course %s via Stripe checkout", user_id, course_id)
