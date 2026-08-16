from typing import List, Optional

from pydantic import BaseModel

from backend.models.message import Message


class ChatRequest(BaseModel):
    messages: List[Message]
    subject: Optional[str] = None   # e.g. "Python", "FastAPI", "React"
    search: bool = True             # toggle live search on/off
    conversation_id: Optional[int] = None  # existing conversation to append to; omit to start a new one
    course_id: Optional[int] = None  # optional FINKI course to pull syllabus/topic context from