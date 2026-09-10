import { apiFetch } from './client';
import type { QuizAttemptOut, QuizQuestionOut, QuizRecommendationOut } from '../types/quizProgress';

export function createQuizAttempt(
  topic: string,
  subject: string | null,
  totalQuestions: number,
  questions?: QuizQuestionOut[] | null,
): Promise<QuizAttemptOut> {
  return apiFetch<QuizAttemptOut>('/api/quiz-progress', {
    method: 'POST',
    body: JSON.stringify({
      topic,
      subject,
      total_questions: totalQuestions,
      questions: questions ?? null,
    }),
  });
}

export function redoQuizAttempt(attemptId: number): Promise<QuizAttemptOut> {
  return apiFetch<QuizAttemptOut>(`/api/quiz-progress/${attemptId}/redo`, {
    method: 'POST',
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
