from typing import Optional

from pydantic import BaseModel, Field


class QuizAttemptCreateRequest(BaseModel):
    topic: str
    subject: Optional[str] = None
    total_questions: int = Field(ge=1)


class QuizAttemptUpdateRequest(BaseModel):
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
