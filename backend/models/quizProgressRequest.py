from typing import Optional

from pydantic import BaseModel, Field


class QuizQuestionIn(BaseModel):
    question: str
    options: list[str]
    answer: str
    explanation: str


class QuizAttemptCreateRequest(BaseModel):
    topic: str
    subject: Optional[str] = None
    total_questions: int = Field(ge=1)
    # The generated quiz questions, cached alongside the attempt so it can be
    # reopened later without asking the AI again.
    questions: Optional[list[QuizQuestionIn]] = None


class QuizAttemptUpdateRequest(BaseModel):
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
