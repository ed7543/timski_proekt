from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.models import QuizAttempt, User
from backend.database.session import get_db
from backend.middleware.auth import get_current_user
from backend.models.quizProgressRequest import QuizAttemptCreateRequest, QuizAttemptUpdateRequest
from backend.models.quizProgressResponse import QuizAttemptOut, QuizRecommendationOut

router = APIRouter(prefix="/api/quiz-progress", tags=["quiz-progress"])

LOW_SCORE_THRESHOLD_PERCENT = 70


@router.get("", response_model=list[QuizAttemptOut])
async def list_quiz_attempts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.user_id == current_user.id)
        .order_by(QuizAttempt.updated_at.desc())
        .all()
    )
    return [QuizAttemptOut.model_validate(a) for a in attempts]


@router.post("", response_model=QuizAttemptOut)
async def create_quiz_attempt(
    request: QuizAttemptCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = QuizAttempt(
        user_id=current_user.id,
        topic=request.topic,
        subject=request.subject,
        total_questions=request.total_questions,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return QuizAttemptOut.model_validate(attempt)


@router.patch("/{attempt_id}", response_model=QuizAttemptOut)
async def update_quiz_attempt(
    attempt_id: int,
    request: QuizAttemptUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.id == attempt_id, QuizAttempt.user_id == current_user.id)
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Quiz attempt not found")

    attempt.answered_count = min(request.answered_count, attempt.total_questions)
    attempt.correct_count = min(request.correct_count, attempt.answered_count)
    attempt.completed = attempt.answered_count >= attempt.total_questions
    db.commit()
    db.refresh(attempt)
    return QuizAttemptOut.model_validate(attempt)


@router.get("/recommendations", response_model=list[QuizRecommendationOut])
async def get_quiz_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    completed = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.user_id == current_user.id, QuizAttempt.completed == True)  # noqa: E712
        .all()
    )

    by_subject: dict[str, list[QuizAttempt]] = defaultdict(list)
    for a in completed:
        by_subject[a.subject or "General"].append(a)

    recommendations: list[QuizRecommendationOut] = []
    for subject, attempts in by_subject.items():
        total_questions = sum(a.total_questions for a in attempts)
        total_correct = sum(a.correct_count for a in attempts)
        if total_questions == 0:
            continue
        avg_percent = round(100 * total_correct / total_questions)
        if avg_percent < LOW_SCORE_THRESHOLD_PERCENT:
            recommendations.append(
                QuizRecommendationOut(
                    subject=subject,
                    average_score_percent=avg_percent,
                    attempts=len(attempts),
                    reason=f"You've averaged {avg_percent}% here — worth another look",
                )
            )

    recommendations.sort(key=lambda r: r.average_score_percent)
    return recommendations[:5]
