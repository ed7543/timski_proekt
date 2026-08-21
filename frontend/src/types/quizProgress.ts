export interface QuizAttemptOut {
  id: number;
  topic: string;
  subject: string | null;
  total_questions: number;
  answered_count: number;
  correct_count: number;
  completed: boolean;
  updated_at: string;
}

export interface QuizRecommendationOut {
  subject: string;
  average_score_percent: number;
  attempts: number;
  reason: string;
}
