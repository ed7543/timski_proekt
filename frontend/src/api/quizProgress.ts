import { apiFetch } from './client';
import type { QuizAttemptOut, QuizRecommendationOut } from '../types/quizProgress';

export function createQuizAttempt(
  topic: string,
  subject: string | null,
  totalQuestions: number,
): Promise<QuizAttemptOut> {
  return apiFetch<QuizAttemptOut>('/api/quiz-progress', {
    method: 'POST',
    body: JSON.stringify({ topic, subject, total_questions: totalQuestions }),
  });
}

export function updateQuizAttempt(
  attemptId: number,
  answeredCount: number,
  correctCount: number,
): Promise<QuizAttemptOut> {
  return apiFetch<QuizAttemptOut>(`/api/quiz-progress/${attemptId}`, {
    method: 'PATCH',
    body: JSON.stringify({ answered_count: answeredCount, correct_count: correctCount }),
  });
}

export function listQuizAttempts(): Promise<QuizAttemptOut[]> {
  return apiFetch<QuizAttemptOut[]>('/api/quiz-progress');
}

export function getQuizRecommendations(): Promise<QuizRecommendationOut[]> {
  return apiFetch<QuizRecommendationOut[]>('/api/quiz-progress/recommendations');
}
