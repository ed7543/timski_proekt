from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class QuizQuestionOut(BaseModel):
    question: str
    options: list[str]
    answer: str
    explanation: str


class QuizAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    subject: Optional[str] = None
    total_questions: int
    answered_count: int
    correct_count: int
    completed: bool
    updated_at: datetime
    questions: Optional[list[QuizQuestionOut]] = None


class QuizRecommendationOut(BaseModel):
    subject: str
    average_score_percent: int
    attempts: int
    reason: str
