from fastapi import HTTPException, APIRouter
from config import GROQ_API_KEY, TAVILY_API_KEY


router = APIRouter()

@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "groq_key": bool(GROQ_API_KEY),
        "tavily_key": bool(TAVILY_API_KEY),
    }