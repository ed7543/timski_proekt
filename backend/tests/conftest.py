"""Shared test helpers for the Marketplace/billing/admin test suite
(test_course_submission.py, test_admin_approval.py, test_marketplace_pricing.py,
test_course_deletion.py, test_billing.py, test_upload_material.py,
test_course_notes.py).

These tests run against your REAL database, exactly like the existing
test_chat_route.py/test_search_cache.py suite (see README.md "Run the
tests") - there is no SQLite fallback. Every test creates its own
uniquely-emailed users/courses and cleans them up afterward via
cleanup_test_data(), so re-running the suite never collides with leftover
data from a previous run or with real accounts in your database.
"""
import uuid

import pytest
from sqlalchemy import or_

from backend.database.models import (
    ChatMessage,
    Conversation,
    ConversationInvite,
    ConversationMember,
    Course,
    CourseMaterial,
    CourseNote,
    CoursePurchase,
    Recording,
    User,
    VerificationToken,
)
from backend.middleware.rate_limit import limiter


@pytest.fixture(autouse=True)
def _disable_register_rate_limit(request):
    """Tests that register far more than 5 accounts/minute - every test uses
    its own uniquely-emailed users for isolation (see unique_email() below),
    which is the opposite of what the real 5/minute limiter on
    POST /api/auth/register (middleware/rate_limit.py) expects from one
    caller - mark their module with `pytestmark = pytest.mark.bulk_register`
    (see test_admin_approval.py etc. for an example). Without that marker,
    such tests fail with 429s that have nothing to do with the feature being
    tested. The rate limiter itself isn't what these tests are about, so
    it's turned off for their duration and restored after.

    Scoped to just marked modules (rather than session-wide) so it doesn't
    mask test_lesson_quiz_rate_limit.py, which specifically tests that the
    limiter is enforced. Uses a marker rather than a hardcoded module-name
    list so a new bulk-registering test file only needs one line added to
    itself, not a separate edit here."""
    if request.node.get_closest_marker("bulk_register"):
        limiter.enabled = False
        yield
        limiter.enabled = True
    else:
        yield


def unique_email(prefix: str) -> str:
    """A throwaway-but-readable test email, unique per call so parallel test
    runs (or a crashed previous run that skipped cleanup) never collide on
    the users.email unique constraint."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}@test.example"


def register_and_login(client, db, email, password="testpass123", role=None, is_premium=False, full_name="Test User"):
    """Registers + logs in a user via the real API (so password hashing/JWT
    issuance are exercised for real), then optionally pokes role/is_premium
    directly - those aren't settable through any endpoint, matching how an
    admin account actually gets created in this app (see README "Create an
    admin account"). Returns the bearer token."""
    resp = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": full_name})
    assert resp.status_code == 201, f"register failed for {email}: {resp.status_code} {resp.text}"
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"login failed for {email}: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]

    if role is not None or is_premium:
        user = db.query(User).filter(User.email == email).first()
        if role is not None:
            user.role = role
        if is_premium:
            user.is_premium = True
        db.commit()

    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def cleanup_test_data(db, emails: list[str]) -> None:
    """Deletes everything a test could plausibly have created for the given
    list of user emails: course purchases, materials/recordings (via their
    course_id), the courses themselves (whether submitted OR reviewed by any
    of these users), conversations/chat messages, verification tokens, and
    finally the user rows. Order matters - children before parents - since
    none of this goes through the ORM's cascade="all, delete-orphan" (that
    only fires on `db.delete(obj)` for a loaded instance, not bulk `.delete()`
    queries), and Course.submitted_by_id/reviewed_by_id + CoursePurchase.user_id
    are plain FKs with no ON DELETE action - deleting a referenced user first
    would just raise a ForeignKeyViolation. Safe/no-op for emails never used."""
    users = db.query(User).filter(User.email.in_(emails)).all()
    user_ids = [u.id for u in users]
    if not user_ids:
        return

    courses = (
        db.query(Course)
        .filter(or_(Course.submitted_by_id.in_(user_ids), Course.reviewed_by_id.in_(user_ids)))
        .all()
    )
    course_ids = [c.id for c in courses]

    # CourseNote can reference a course these users don't own at all (e.g. a
    # student notes on the official FINKI catalog, or on someone else's
    # Marketplace course), so it's cleaned up by uploader as well as by
    # course_ids - not just by course_ids like CoursePurchase/CourseMaterial/
    # Recording below, which only ever attach to a course these users
    # submitted or reviewed.
    db.query(CourseNote).filter(
        or_(CourseNote.course_id.in_(course_ids), CourseNote.uploaded_by_id.in_(user_ids))
    ).delete(synchronize_session=False)

    if course_ids:
        db.query(CoursePurchase).filter(CoursePurchase.course_id.in_(course_ids)).delete(synchronize_session=False)
        db.query(CourseMaterial).filter(CourseMaterial.course_id.in_(course_ids)).delete(synchronize_session=False)
        db.query(Recording).filter(Recording.course_id.in_(course_ids)).delete(synchronize_session=False)

    db.query(CoursePurchase).filter(CoursePurchase.user_id.in_(user_ids)).delete(synchronize_session=False)

    if course_ids:
        db.query(Course).filter(Course.id.in_(course_ids)).delete(synchronize_session=False)

    # Conversations these users own, plus group-chat rows tied to them either
    # way: ConversationMember/ConversationInvite must go before their parent
    # Conversation (bulk .delete() doesn't trigger the ORM-level cascade,
    # same reasoning as course_ids above). A user can also be a *member* of
    # someone else's conversation (not owned by any of these emails) - that
    # membership/invite-authorship is cleaned up by user_id regardless of
    # conv_ids, and a message they authored there is nulled out rather than
    # deleted, since that conversation isn't this cleanup's to remove.
    conv_ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id.in_(user_ids)).all()]
    if conv_ids:
        db.query(ConversationMember).filter(ConversationMember.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(ConversationInvite).filter(ConversationInvite.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)

    db.query(ConversationMember).filter(ConversationMember.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(ConversationInvite).filter(ConversationInvite.created_by_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(ChatMessage).filter(ChatMessage.author_user_id.in_(user_ids)).update(
        {"author_user_id": None}, synchronize_session=False
    )

    if conv_ids:
        db.query(Conversation).filter(Conversation.user_id.in_(user_ids)).delete(synchronize_session=False)

    db.query(VerificationToken).filter(VerificationToken.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
