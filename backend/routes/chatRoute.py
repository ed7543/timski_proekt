import json
from typing import Optional

from fastapi import HTTPException, APIRouter, Depends
from sqlalchemy.orm import Session

from backend.ai.chat import stream_groq_response, generate_quiz, generate_explore_queries, \
    generate_summary, generate_followups  # Changed import
from backend.database.models import Course, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_user
from backend.models.QuizRequest import QuizRequest
from backend.models.askMoreRequest import AskMoreRequest
from backend.models.chatRequest import ChatRequest
from backend.models.exploreRequest import ExploreRequest
from backend.models.summaryRequest import SummaryRequest
from backend.services.chat_service import resolve_conversation, save_assistant_reply, save_user_message
from backend.services.course_context import format_course_context
from backend.services.search_cache import get_or_search, get_or_search_many
from backend.web_search.search import format_search_context
from config import GROQ_API_KEY, TAVILY_API_KEY
from fastapi.responses import StreamingResponse

router = APIRouter()


def _get_course_context(db: Session, course_id: Optional[int]) -> str:
    """Look up a course by id (if given) and format it into a context block.
    Silently returns "" for a missing/invalid course_id - course context is
    optional enrichment, not something that should ever 400/404 the request."""
    if not course_id:
        return ""
    course = db.query(Course).filter(Course.id == course_id).first()
    return format_course_context(course)

@router.post("/api/chat")
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Main chat endpoint. Optionally searches the web for context before answering.
    Streams the response back as Server-Sent Events (SSE), and persists both the
    user message and the AI reply to the owning conversation.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    # Get the latest user message for search + persistence
    latest_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    # Resolve (or create) the conversation this exchange belongs to
    conversation = resolve_conversation(db, request, current_user, latest_user_msg)

    if latest_user_msg:
        save_user_message(db, conversation, latest_user_msg)

    # Capture plain values before the request-scoped DB session closes.
    # (The `db` session from Depends(get_db) is closed as soon as this function
    # returns the StreamingResponse - it does NOT stay open for the duration of
    # the stream. Touching `conversation.*` or `db` inside event_stream() below
    # would raise a DetachedInstanceError, so we only use plain vars there and
    # open a brand new session for the final save.)
    conv_id = conversation.id
    conv_title = conversation.title

    # Web search for context - served from the cache when a similar question was
    # already searched before, otherwise a live Tavily call (see services/search_cache.py)
    search_results = []
    if request.search and TAVILY_API_KEY and latest_user_msg:
        search_results, _ = await get_or_search(db, latest_user_msg, request.subject)

    # Compose the search-cache context with the optional course-syllabus context
    # (see backend/services/course_context.py) - both are plain context blocks,
    # concatenated the same way format_search_context's own sections are.
    course_context = _get_course_context(db, request.course_id)
    context = "\n\n".join(c for c in (format_search_context(search_results), course_context) if c)

    async def event_stream():
        # First let the UI know which conversation this belongs to (important
        # when a new one was just created, so the frontend can select it)
        conv_payload = json.dumps({"id": conv_id, "title": conv_title})
        yield f"event: conversation\ndata: {conv_payload}\n\n"

        # Then emit the search sources so the UI can show them
        if search_results:
            sources_payload = json.dumps([
                {"title": r.title, "url": r.url} for r in search_results
            ])
            yield f"event: sources\ndata: {sources_payload}\n\n"

        # Then stream the AI response, accumulating the full text so we can save it
        full_response = ""
        async for chunk in stream_groq_response(request.messages, context, request.subject):
            full_response += chunk
            yield f"data: {json.dumps(chunk)}\n\n"

        if full_response:
            save_assistant_reply(conv_id, full_response)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/api/quiz")
async def quiz(
    request: QuizRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a quiz from the current conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to base quiz on")
    course_context = _get_course_context(db, request.course_id)
    result = await generate_quiz(request.messages, request.subject, course_context)
    return result

@router.post("/api/summary")
async def summary(
    request: SummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a study summary from the conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to summarize")
    course_context = _get_course_context(db, request.course_id)
    result = await generate_summary(request.messages, request.subject, course_context)
    return result


@router.post("/api/explore")
async def explore(
    request: ExploreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find related links based on the conversation topic."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to explore from")
    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not set")

    course_context = _get_course_context(db, request.course_id)
    queries = await generate_explore_queries(request.messages, request.subject, course_context)
    if not queries:
        raise HTTPException(status_code=500, detail="Could not generate explore queries")

    results = await get_or_search_many(db, queries, request.subject, num_results=3)
    return {
        "queries": queries,
        "links": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results[:9]]
    }

@router.post("/api/ask-more")
async def ask_more(
    request: AskMoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest follow-up questions based on the conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to base follow-ups on")
    course_context = _get_course_context(db, request.course_id)
    questions = await generate_followups(request.messages, request.subject, course_context)
    if not questions:
        raise HTTPException(status_code=500, detail="Could not generate follow-up questions")
    return {"questions": questions}