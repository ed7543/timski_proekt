from typing import List, Optional
from pydantic import BaseModel
from backend.models.message import Message


class SummaryRequest(BaseModel):
    messages: List[Message]
    subject: Optional[str] = None