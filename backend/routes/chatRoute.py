import json
from datetime import datetime

from fastapi import HTTPException, APIRouter, Depends
from sqlalchemy.orm import Session

from backend.ai.chat import stream_groq_response, generate_quiz, generate_explore_queries, \
    generate_summary, generate_followups  # Changed import
from backend.database.models import Conversation, ChatMessage, User
from backend.database.session import get_db, SessionLocal
from backend.middleware.auth import get_current_user
from backend.models.QuizRequest import QuizRequest
from backend.models.askMoreRequest import AskMoreRequest
from backend.models.chatRequest import ChatRequest
from backend.models.exploreRequest import ExploreRequest
from backend.models.summaryRequest import SummaryRequest
from backend.routes.conversationRoute import _get_owned_conversation
from backend.web_search.search import build_search_query, web_search, format_search_context, explore_search
from config import GROQ_API_KEY, TAVILY_API_KEY
from fastapi.responses import StreamingResponse

router = APIRouter()

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
    if request.conversation_id:
        conversation = _get_owned_conversation(db, request.conversation_id, current_user)
    else:
        conversation = Conversation(
            user_id=current_user.id,
            title=(latest_user_msg[:48] or "New conversation"),
            subject=request.subject,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    if latest_user_msg:
        db.add(ChatMessage(conversation_id=conversation.id, role="user", content=latest_user_msg))
        conversation.updated_at = datetime.utcnow()
        db.commit()

    # Capture plain values before the request-scoped DB session closes.
    # (The `db` session from Depends(get_db) is closed as soon as this function
    # returns the StreamingResponse - it does NOT stay open for the duration of
    # the stream. Touching `conversation.*` or `db` inside event_stream() below
    # would raise a DetachedInstanceError, so we only use plain vars there and
    # open a brand new session for the final save.)
    conv_id = conversation.id
    conv_title = conversation.title

    # Live web search for context
    search_results = []
    if request.search and TAVILY_API_KEY and latest_user_msg:
        query = build_search_query(latest_user_msg, request.subject)
        search_results = await web_search(query)

    context = format_search_context(search_results)

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
            # The original `db` session is closed by now - use a fresh one.
            save_db = SessionLocal()
            try:
                save_db.add(ChatMessage(conversation_id=conv_id, role="assistant", content=full_response))
                conv = save_db.query(Conversation).filter(Conversation.id == conv_id).first()
                if conv:
                    conv.updated_at = datetime.utcnow()
                save_db.commit()
            finally:
                save_db.close()

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/api/quiz")
async def quiz(request: QuizRequest):
    """Generate a quiz from the current conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to base quiz on")
    result = await generate_quiz(request.messages, request.subject)
    return result

@router.post("/api/summary")
async def summary(request: SummaryRequest):
    """Generate a study summary from the conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to summarize")
    result = await generate_summary(request.messages, request.subject)
    return result


@router.post("/api/explore")
async def explore(request: ExploreRequest):
    """Find related links based on the conversation topic."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to explore from")
    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not set")

    queries = await generate_explore_queries(request.messages, request.subject)
    if not queries:
        raise HTTPException(status_code=500, detail="Could not generate explore queries")

    results = await explore_search(queries, num_results=3)
    return {
        "queries": queries,
        "links": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results[:9]]
    }

@router.post("/api/ask-more")
async def ask_more(request: AskMoreRequest):
    """Suggest follow-up questions based on the conversation."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages to base follow-ups on")
    questions = await generate_followups(request.messages, request.subject)
    if not questions:
        raise HTTPException(status_code=500, detail="Could not generate follow-up questions")
    return {"questions": questions}