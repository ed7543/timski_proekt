import json

from fastapi import HTTPException, APIRouter

from backend.ai.chat import stream_groq_response, generate_quiz, generate_explore_queries, \
    generate_summary, generate_followups  # Changed import
from backend.models.QuizRequest import QuizRequest
from backend.models.askMoreRequest import AskMoreRequest
from backend.models.chatRequest import ChatRequest
from backend.models.exploreRequest import ExploreRequest
from backend.models.summaryRequest import SummaryRequest
from backend.web_search.search import build_search_query, web_search, format_search_context, explore_search
from config import GROQ_API_KEY, TAVILY_API_KEY
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Optionally searches the web for context before answering.
    Streams the response back as Server-Sent Events (SSE).
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")

    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    # Get the latest user message for search
    latest_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    # Live web search for context
    search_results = []
    if request.search and TAVILY_API_KEY and latest_user_msg:
        query = build_search_query(latest_user_msg, request.subject)
        search_results = await web_search(query)

    context = format_search_context(search_results)

    async def event_stream():
        # First emit the search sources so the UI can show them
        if search_results:
            sources_payload = json.dumps([
                {"title": r.title, "url": r.url} for r in search_results
            ])
            yield f"event: sources\ndata: {sources_payload}\n\n"

        # Then stream the AI response
        async for chunk in stream_groq_response(request.messages, context, request.subject):
            yield f"data: {json.dumps(chunk)}\n\n"

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