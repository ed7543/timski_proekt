"""Regression test for the SSE mid-stream failure fix in chatRoute.py.

Before this fix, any exception raised while iterating stream_groq_response()
(a Groq timeout, a 429, etc.) propagated out of the async generator after
HTTP 200 + headers were already sent - Starlette/uvicorn had no way to turn
that into a clean response, so the connection just died with no explanation,
and the partial reply that had already streamed to the client was never
saved (save_assistant_reply only ran after the loop completed normally).

Reproduced live with a real mid-stream 429 during development; this test
locks that fix in place going forward.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.database.models import ChatMessage, Conversation, User, VerificationToken
from backend.database.session import SessionLocal
from backend.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    email = "sse-regression-test@example.com"
    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()
    db.close()

    resp = client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    yield headers

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        conv_ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == user.id).all()]
        db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
        db.query(VerificationToken).filter(VerificationToken.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
    db.close()


def test_mid_stream_failure_sends_error_frame_and_saves_partial_reply(auth_headers):
    async def fake_stream(*args, **kwargs):
        yield "Partial answer before "
        yield "it "
        raise HTTPException(status_code=429, detail="rate limited")

    with patch("backend.routes.chatRoute.stream_groq_response", fake_stream):
        with client.stream(
            "POST", "/api/chat", headers=auth_headers,
            json={"messages": [{"role": "user", "content": "test question"}], "search": False},
        ) as resp:
            body = b"".join(resp.iter_bytes()).decode()

    assert "event: error" in body
    assert "You're sending messages too fast" in body
    assert body.strip().endswith("data: [DONE]")

    db = SessionLocal()
    user = db.query(User).filter(User.email == "sse-regression-test@example.com").first()
    conv = db.query(Conversation).filter(Conversation.user_id == user.id).first()
    messages = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.id).all()
    db.close()

    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].content == "Partial answer before it "


def test_mid_stream_generic_failure_uses_generic_message(auth_headers):
    async def fake_stream(*args, **kwargs):
        yield "Some text "
        raise RuntimeError("boom")

    with patch("backend.routes.chatRoute.stream_groq_response", fake_stream):
        with client.stream(
            "POST", "/api/chat", headers=auth_headers,
            json={"messages": [{"role": "user", "content": "another question"}], "search": False},
        ) as resp:
            body = b"".join(resp.iter_bytes()).decode()

    assert "event: error" in body
    assert "trouble responding" in body
    assert body.strip().endswith("data: [DONE]")
