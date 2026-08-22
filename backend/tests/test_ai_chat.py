"""Tests for backend/ai/chat.py - prompt construction, course-context
threading through generate_quiz/generate_summary/generate_explore_queries/
generate_followups/stream_groq_response, and two regression guards:

1. GROQ_MODEL must never silently revert to a retired model - this project
   already broke in production once (llama-3.3-70b-versatile was pulled from
   Groq's catalog, see the comment above GROQ_MODEL in chat.py).
2. SYSTEM_PROMPT must keep the anti-fabrication rule - found via manual
   testing that the AI padded a real 3-item materials list with 2 invented
   ones; the fix was purely a prompt change, easy to silently lose in a
   future edit without a test catching it.

No real network calls are made - httpx.AsyncClient.post/.stream are
monkeypatched at the class level for each test.
"""
import json

import httpx
import pytest
from fastapi import HTTPException

from backend.ai import chat as ai_chat
from backend.models.message import Message


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", lines=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._lines = lines or []

    def json(self):
        return self._json_data

    async def aread(self):
        return self.text.encode()

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCM:
    """Mimics the async context manager httpx.AsyncClient.stream() returns."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


def _groq_completion_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture(autouse=True)
def fake_groq_key(monkeypatch):
    # Every function under test bails early with a 500 if this is falsy.
    monkeypatch.setattr(ai_chat, "GROQ_API_KEY", "test-key")


def test_system_prompt_forbids_fabricated_resources():
    assert "NEVER invent" in ai_chat.SYSTEM_PROMPT
    assert "fabricate" in ai_chat.SYSTEM_PROMPT.lower()


def test_groq_model_is_not_the_retired_model():
    assert ai_chat.GROQ_MODEL != "llama-3.3-70b-versatile"
    assert ai_chat.GROQ_MODEL


@pytest.mark.asyncio
async def test_generate_quiz_sends_configured_model_and_course_context(monkeypatch):
    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        return _FakeResponse(200, _groq_completion_payload(
            '{"topic": "T", "questions": []}'
        ))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ai_chat.generate_quiz(
        [Message(role="user", content="teach me recursion")],
        subject="DSA",
        course_context="## Course Context: Test Course\n- Recursion",
    )

    assert result == {"topic": "T", "questions": []}
    assert captured["json"]["model"] == ai_chat.GROQ_MODEL
    prompt = captured["json"]["messages"][0]["content"]
    assert "## Course Context: Test Course" in prompt
    assert "DSA" in prompt


@pytest.mark.asyncio
async def test_generate_quiz_strips_markdown_fences(monkeypatch):
    async def fake_post(self, url, headers=None, json=None):
        return _FakeResponse(200, _groq_completion_payload(
            '```json\n{"topic": "T", "questions": []}\n```'
        ))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ai_chat.generate_quiz([Message(role="user", content="hi")], subject=None)
    assert result == {"topic": "T", "questions": []}


@pytest.mark.asyncio
async def test_generate_quiz_raises_on_groq_error(monkeypatch):
    async def fake_post(self, url, headers=None, json=None):
        return _FakeResponse(429, text="rate limited")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(HTTPException) as exc_info:
        await ai_chat.generate_quiz([Message(role="user", content="hi")], subject=None)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_generate_summary_includes_course_context(monkeypatch):
    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["json"] = json
        return _FakeResponse(200, _groq_completion_payload("A summary"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await ai_chat.generate_summary(
        [Message(role="user", content="hi")], subject=None, course_context="COURSE-MARKER"
    )
    assert result == {"summary": "A summary"}
    assert "COURSE-MARKER" in captured["json"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_generate_explore_queries_includes_course_context_and_caps_at_3(monkeypatch):
    async def fake_post(self, url, headers=None, json=None):
        assert "COURSE-MARKER" in json["messages"][0]["content"]
        return _FakeResponse(200, _groq_completion_payload('["q1", "q2", "q3", "q4"]'))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    queries = await ai_chat.generate_explore_queries(
        [Message(role="user", content="hi")], subject=None, course_context="COURSE-MARKER"
    )
    assert queries == ["q1", "q2", "q3"]


@pytest.mark.asyncio
async def test_generate_followups_returns_empty_list_on_malformed_json(monkeypatch):
    async def fake_post(self, url, headers=None, json=None):
        return _FakeResponse(200, _groq_completion_payload("not valid json"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    questions = await ai_chat.generate_followups([Message(role="user", content="hi")], subject=None)
    assert questions == []


@pytest.mark.asyncio
async def test_stream_groq_response_injects_course_context_and_uses_configured_model(monkeypatch):
    captured = {}
    sse_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello "}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": "world"}}]}),
        "data: [DONE]",
    ]

    def fake_stream(self, method, url, headers=None, json=None):
        captured["json"] = json
        return _FakeStreamCM(_FakeResponse(200, lines=sse_lines))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    chunks = []
    async for chunk in ai_chat.stream_groq_response(
        [Message(role="user", content="hi")], context="COURSE-MARKER", subject="DSA"
    ):
        chunks.append(chunk)

    assert "".join(chunks) == "Hello world"
    assert captured["json"]["model"] == ai_chat.GROQ_MODEL
    system_message = captured["json"]["messages"][0]["content"]
    assert "COURSE-MARKER" in system_message
    assert "DSA" in system_message


@pytest.mark.asyncio
async def test_stream_groq_response_raises_on_non_200(monkeypatch):
    def fake_stream(self, method, url, headers=None, json=None):
        return _FakeStreamCM(_FakeResponse(429, text="rate limited"))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    with pytest.raises(HTTPException) as exc_info:
        async for _ in ai_chat.stream_groq_response(
            [Message(role="user", content="hi")], context="", subject=None
        ):
            pass
    assert exc_info.value.status_code == 429
