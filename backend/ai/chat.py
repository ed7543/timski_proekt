import json
from typing import List, Optional

import httpx
from fastapi import HTTPException

from backend.models.message import Message
from config import GROQ_API_KEY

SYSTEM_PROMPT = """You are LearnWise, an expert AI tutor. Your job is to help students understand technical topics clearly and accurately.

When answering:
1. Be concise but thorough — explain the WHY not just the WHAT
2. Use simple analogies for complex concepts
3. Include short, practical code examples when relevant
4. If search results are provided, use them as your primary source of truth and cite them
5. If a concept has a common mistake or gotcha, point it out
6. End responses with 1-2 follow-up questions the student might want to explore next
7. Respond in the language, you are being asked in

Format your responses with markdown (headers, code blocks, bullet points).
Always be encouraging and patient."""


async def stream_groq_response(messages: List[Message], context: str, subject: Optional[str]):
    """Stream a response from GROQ with optional search context injected."""

    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    # Build the system prompt with context
    system = SYSTEM_PROMPT
    if subject:
        system += f"\n\nThe student is currently learning about: **{subject}**"
    if context:
        system += f"\n\n{context}"

    # Convert our messages to GROQ format
    groq_messages = [{"role": m.role, "content": m.content} for m in messages]
    # Add system message at the beginning
    groq_messages.insert(0, {"role": "system", "content": system})

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": groq_messages,
                    "stream": True,
                    "max_tokens": 1500,
                    "temperature": 0.7,
                },
        ) as response:
            if response.status_code != 200:
                error = await response.aread()
                raise HTTPException(status_code=response.status_code, detail=error.decode())

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                        if event.get("choices"):
                            delta = event["choices"][0].get("delta", {})
                            if delta.get("content"):
                                yield delta.get("content", "")
                    except json.JSONDecodeError:
                        continue


async def generate_quiz(messages: List[Message], subject: Optional[str]):
    """Generate a multiple-choice quiz based on the conversation."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    # Summarise the conversation topic for the quiz prompt
    conversation = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in messages[-10:]  # last 10 msgs
    )

    quiz_prompt = f"""Based on this tutoring conversation, generate a quiz with 5 multiple-choice questions.

CONVERSATION:
{conversation}

{"The topic is: " + subject if subject else ""}

Respond ONLY with a valid JSON object in exactly this format, no markdown, no extra text:
{{
  "topic": "short topic title",
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["A) option", "B) option", "C) option", "D) option"],
      "answer": "A",
      "explanation": "Brief explanation of why this is correct."
    }}
  ]
}}"""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": quiz_prompt}],
                "max_tokens": 2000,
                "temperature": 0.5,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        # Strip any accidental markdown fences
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)

async def generate_summary(messages: List[Message], subject: Optional[str]):
    """Summarize the entire conversation into a concise study recap."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    conversation = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)

    summary_prompt = f"""Summarize this tutoring conversation into a concise study recap.

CONVERSATION:
{conversation}

{"The topic is: " + subject if subject else ""}

Write a clear, well-organized summary covering:
1. The main concepts discussed
2. Key takeaways the student should remember
3. Any important gotchas or common mistakes mentioned

Use markdown with short headers and bullet points. Keep it concise — aim for something a student could review in under a minute."""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": summary_prompt}],
                "max_tokens": 800,
                "temperature": 0.4,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        return {"summary": data["choices"][0]["message"]["content"]}


async def generate_explore_queries(messages: List[Message], subject: Optional[str]) -> List[str]:
    """Ask Groq for 3 focused search queries related to the conversation topic."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    conversation = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages[-10:])

    query_prompt = f"""Based on this tutoring conversation, suggest 3 short, specific web search queries
that would help the student explore related topics, deeper resources, or adjacent concepts.

CONVERSATION:
{conversation}

{"The topic is: " + subject if subject else ""}

Respond ONLY with a valid JSON array of exactly 3 strings, no markdown, no extra text.
Example: ["FastAPI background tasks vs Celery", "Python async context managers", "uvicorn worker tuning"]"""

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": query_prompt}],
                "max_tokens": 200,
                "temperature": 0.6,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            queries = json.loads(raw)
            if isinstance(queries, list):
                return [str(q) for q in queries[:3]]
        except json.JSONDecodeError:
            pass
        return []