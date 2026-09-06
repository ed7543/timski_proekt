"""Group chat: invites (create/revoke/accept), membership (list/leave/kick),
and the visibility/permission rules layered on top of the existing
single-owner conversation endpoints. Runs against your real database - see
README.md "Run the tests"."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.database.models import ConversationInvite, ConversationMember
from backend.database.session import SessionLocal
from backend.main import app
from backend.tests.conftest import auth_headers, cleanup_test_data, register_and_login, unique_email
from backend.utils.time import utcnow

client = TestClient(app)
pytestmark = pytest.mark.bulk_register


def _create_conversation(token):
    resp = client.post("/api/conversations", headers=auth_headers(token), json={"title": "Group chat test"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_invite(token, conv_id):
    resp = client.post(f"/api/conversations/{conv_id}/invites", headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _accept(token, invite_token):
    return client.post(f"/api/conversations/invites/{invite_token}/accept", headers=auth_headers(token))


# ------------------------------------------------------------ non-members ----

def test_a_stranger_gets_404_on_a_conversation_they_dont_own_or_belong_to():
    db = SessionLocal()
    owner_email = unique_email("conv-strangers-owner")
    stranger_email = unique_email("conv-strangers-stranger")
    try:
        owner_token = register_and_login(client, db, owner_email)
        stranger_token = register_and_login(client, db, stranger_email)
        conv_id = _create_conversation(owner_token)

        resp = client.get(f"/api/conversations/{conv_id}", headers=auth_headers(stranger_token))
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [owner_email, stranger_email])
        db.close()


# ---------------------------------------------------------------- invites ----

def test_accepting_a_valid_invite_makes_you_a_member():
    db = SessionLocal()
    owner_email = unique_email("conv-accept-owner")
    member_email = unique_email("conv-accept-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)

        resp = _accept(member_token, invite["token"])
        assert resp.status_code == 200, resp.text

        detail = client.get(f"/api/conversations/{conv_id}", headers=auth_headers(member_token))
        assert detail.status_code == 200
        assert detail.json()["is_owner"] is False

        members = client.get(f"/api/conversations/{conv_id}/members", headers=auth_headers(owner_token)).json()
        assert len(members) == 2
        assert any(m["is_owner"] for m in members)
        assert any(not m["is_owner"] for m in members)
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_accepting_the_same_invite_twice_is_a_noop():
    db = SessionLocal()
    owner_email = unique_email("conv-accepttwice-owner")
    member_email = unique_email("conv-accepttwice-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)

        first = _accept(member_token, invite["token"])
        second = _accept(member_token, invite["token"])
        assert first.status_code == 200
        assert second.status_code == 200

        members = client.get(f"/api/conversations/{conv_id}/members", headers=auth_headers(owner_token)).json()
        assert len(members) == 2  # not duplicated
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_a_revoked_invite_is_rejected():
    db = SessionLocal()
    owner_email = unique_email("conv-revoked-owner")
    member_email = unique_email("conv-revoked-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)

        revoke = client.delete(
            f"/api/conversations/{conv_id}/invites/{invite['id']}", headers=auth_headers(owner_token)
        )
        assert revoke.status_code == 204

        resp = _accept(member_token, invite["token"])
        assert resp.status_code == 410
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_an_expired_invite_is_rejected():
    db = SessionLocal()
    owner_email = unique_email("conv-expired-owner")
    member_email = unique_email("conv-expired-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)

        db_invite = db.query(ConversationInvite).filter(ConversationInvite.id == invite["id"]).first()
        db_invite.expires_at = utcnow()
        db.commit()

        resp = _accept(member_token, invite["token"])
        assert resp.status_code == 410
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_a_nonexistent_invite_token_is_404():
    db = SessionLocal()
    email = unique_email("conv-badtoken")
    try:
        token = register_and_login(client, db, email)
        resp = _accept(token, "not-a-real-token")
        assert resp.status_code == 404
    finally:
        cleanup_test_data(db, [email])
        db.close()


def test_invite_accept_enforces_the_three_member_cap():
    db = SessionLocal()
    owner_email = unique_email("conv-cap-owner")
    member_a_email = unique_email("conv-cap-a")
    member_b_email = unique_email("conv-cap-b")
    member_c_email = unique_email("conv-cap-c")
    try:
        owner_token = register_and_login(client, db, owner_email)
        a_token = register_and_login(client, db, member_a_email)
        b_token = register_and_login(client, db, member_b_email)
        c_token = register_and_login(client, db, member_c_email)
        conv_id = _create_conversation(owner_token)

        invite = _create_invite(owner_token, conv_id)
        assert _accept(a_token, invite["token"]).status_code == 200  # owner + a = 2
        invite2 = _create_invite(owner_token, conv_id)
        assert _accept(b_token, invite2["token"]).status_code == 200  # owner + a + b = 3, at cap

        invite3 = _create_invite(owner_token, conv_id)
        resp = _accept(c_token, invite3["token"])
        assert resp.status_code == 409
    finally:
        cleanup_test_data(db, [owner_email, member_a_email, member_b_email, member_c_email])
        db.close()


def test_concurrent_accepts_of_the_same_invite_dont_produce_a_duplicate_member_or_a_500():
    """Regression test for a TOCTOU race in accept_invite: two accept
    requests for the same invite/user (e.g. the link open in two tabs)
    used to both read "not a member yet" before either committed, so the
    second could hit the uq_conversation_members_conv_user UniqueConstraint
    as a raw, unhandled IntegrityError instead of the documented no-op.
    Fixed with a with_for_update() row lock on the conversation - this test
    fires two real concurrent requests (not sequential calls) to prove it."""
    db = SessionLocal()
    owner_email = unique_email("conv-race-owner")
    member_email = unique_email("conv-race-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_accept, member_token, invite["token"]) for _ in range(2)]
            responses = [f.result() for f in futures]

        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]

        member_rows = (
            db.query(ConversationMember)
            .filter(ConversationMember.conversation_id == conv_id)
            .all()
        )
        assert len(member_rows) == 1
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_concurrent_accepts_from_different_users_dont_exceed_the_member_cap():
    """Same TOCTOU race, the other direction: two different users accepting
    two different invites at (nearly) the same instant, when only one slot
    is free, used to both be able to read "under the cap" before either
    committed - landing the conversation one member over MAX_CONVERSATION_MEMBERS.
    The with_for_update() row lock serializes them so only one succeeds."""
    db = SessionLocal()
    owner_email = unique_email("conv-race-cap-owner")
    member_a_email = unique_email("conv-race-cap-a")
    member_b_email = unique_email("conv-race-cap-b")
    member_c_email = unique_email("conv-race-cap-c")
    try:
        owner_token = register_and_login(client, db, owner_email)
        a_token = register_and_login(client, db, member_a_email)
        b_token = register_and_login(client, db, member_b_email)
        c_token = register_and_login(client, db, member_c_email)
        conv_id = _create_conversation(owner_token)

        invite_a = _create_invite(owner_token, conv_id)
        assert _accept(a_token, invite_a["token"]).status_code == 200  # owner + a = 2, one slot left

        invite_b = _create_invite(owner_token, conv_id)
        invite_c = _create_invite(owner_token, conv_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_b = pool.submit(_accept, b_token, invite_b["token"])
            future_c = pool.submit(_accept, c_token, invite_c["token"])
            resp_b, resp_c = future_b.result(), future_c.result()

        statuses = sorted([resp_b.status_code, resp_c.status_code])
        assert statuses == [200, 409], (resp_b.text, resp_c.text)

        member_rows = (
            db.query(ConversationMember)
            .filter(ConversationMember.conversation_id == conv_id)
            .all()
        )
        assert len(member_rows) == 2  # a, plus whichever of b/c won the race - never both
    finally:
        cleanup_test_data(db, [owner_email, member_a_email, member_b_email, member_c_email])
        db.close()


def test_only_the_owner_can_create_an_invite():
    db = SessionLocal()
    owner_email = unique_email("conv-inviteperm-owner")
    member_email = unique_email("conv-inviteperm-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])

        resp = client.post(f"/api/conversations/{conv_id}/invites", headers=auth_headers(member_token))
        assert resp.status_code == 404  # member can see the conversation, but invite-management is owner-only
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


# ---------------------------------------------------------------- members ----

def test_a_member_can_leave_but_not_kick_someone_else():
    db = SessionLocal()
    owner_email = unique_email("conv-leave-owner")
    member_a_email = unique_email("conv-leave-a")
    member_b_email = unique_email("conv-leave-b")
    try:
        owner_token = register_and_login(client, db, owner_email)
        a_token = register_and_login(client, db, member_a_email)
        b_token = register_and_login(client, db, member_b_email)
        conv_id = _create_conversation(owner_token)

        invite_a = _create_invite(owner_token, conv_id)
        _accept(a_token, invite_a["token"])
        invite_b = _create_invite(owner_token, conv_id)
        assert _accept(b_token, invite_b["token"]).status_code == 200
        me_b = client.get("/api/auth/me", headers=auth_headers(b_token)).json()
        me_a = client.get("/api/auth/me", headers=auth_headers(a_token)).json()

        # a tries to kick b - forbidden, a isn't the owner
        kick_resp = client.delete(
            f"/api/conversations/{conv_id}/members/{me_b['id']}", headers=auth_headers(a_token)
        )
        assert kick_resp.status_code == 403

        # a leaves on their own - allowed
        leave_resp = client.delete(
            f"/api/conversations/{conv_id}/members/{me_a['id']}", headers=auth_headers(a_token)
        )
        assert leave_resp.status_code == 204

        # a no longer has access
        assert client.get(f"/api/conversations/{conv_id}", headers=auth_headers(a_token)).status_code == 404
    finally:
        cleanup_test_data(db, [owner_email, member_a_email, member_b_email])
        db.close()


def test_owner_can_kick_a_member():
    db = SessionLocal()
    owner_email = unique_email("conv-kick-owner")
    member_email = unique_email("conv-kick-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])
        member_id = client.get("/api/auth/me", headers=auth_headers(member_token)).json()["id"]

        resp = client.delete(
            f"/api/conversations/{conv_id}/members/{member_id}", headers=auth_headers(owner_token)
        )
        assert resp.status_code == 204
        assert client.get(f"/api/conversations/{conv_id}", headers=auth_headers(member_token)).status_code == 404
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_the_owner_cannot_be_removed_by_anyone_including_themselves():
    db = SessionLocal()
    owner_email = unique_email("conv-ownerremove-owner")
    member_email = unique_email("conv-ownerremove-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])
        owner_id = client.get("/api/auth/me", headers=auth_headers(owner_token)).json()["id"]

        by_member = client.delete(
            f"/api/conversations/{conv_id}/members/{owner_id}", headers=auth_headers(member_token)
        )
        assert by_member.status_code == 400

        by_self = client.delete(
            f"/api/conversations/{conv_id}/members/{owner_id}", headers=auth_headers(owner_token)
        )
        assert by_self.status_code == 400
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_any_member_can_rename_the_conversation():
    db = SessionLocal()
    owner_email = unique_email("conv-rename-owner")
    member_email = unique_email("conv-rename-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])

        resp = client.patch(
            f"/api/conversations/{conv_id}", headers=auth_headers(member_token), json={"title": "Renamed by a member"}
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed by a member"
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_only_the_owner_can_delete_the_conversation():
    db = SessionLocal()
    owner_email = unique_email("conv-delete-owner")
    member_email = unique_email("conv-delete-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])

        resp = client.delete(f"/api/conversations/{conv_id}", headers=auth_headers(member_token))
        assert resp.status_code == 404  # member can see it, but delete is owner-only
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()


def test_list_conversations_includes_ones_you_are_a_member_of():
    db = SessionLocal()
    owner_email = unique_email("conv-list-owner")
    member_email = unique_email("conv-list-member")
    try:
        owner_token = register_and_login(client, db, owner_email)
        member_token = register_and_login(client, db, member_email)
        conv_id = _create_conversation(owner_token)
        invite = _create_invite(owner_token, conv_id)
        _accept(member_token, invite["token"])

        listing = client.get("/api/conversations", headers=auth_headers(member_token)).json()
        assert any(c["id"] == conv_id for c in listing)
    finally:
        cleanup_test_data(db, [owner_email, member_email])
        db.close()
