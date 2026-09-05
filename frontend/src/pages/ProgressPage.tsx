import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { listQuizAttempts, getQuizRecommendations } from '../api/quizProgress';
import type { QuizAttemptOut, QuizRecommendationOut } from '../types/quizProgress';

export function ProgressPage() {
  const [attempts, setAttempts] = useState<QuizAttemptOut[] | null>(null);
  const [recommendations, setRecommendations] = useState<QuizRecommendationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listQuizAttempts(), getQuizRecommendations()])
      .then(([a, r]) => {
        setAttempts(a);
        setRecommendations(r);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load progress'));
  }, []);

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <h1>Your progress</h1>
            <p className="page-subtitle">
              Track your quiz scores as you go, and see which topics are worth revisiting.
            </p>
          </div>

          {error && (
            <div className="msg-error" style={{ marginTop: 20 }}>
              {error}
            </div>
          )}

          <div className="section-label" style={{ padding: 0, marginTop: 24 }}>
            Quiz attempts
          </div>

          {attempts === null && !error && (
            <div className="empty" style={{ marginTop: 12 }}>
              Loading…
            </div>
          )}

          {attempts !== null && attempts.length === 0 && (
            <div className="empty" style={{ marginTop: 12 }}>
              No quizzes taken yet — click "Quiz me" in a chat to get started.
            </div>
          )}

          {attempts !== null && attempts.length > 0 && (
            <div className="progress-list">
              {attempts.map((a) => (
                <div className="progress-item" key={a.id}>
                  <div className="progress-item-row">
                    <span>
                      {a.topic}
                      {a.subject ? ` · ${a.subject}` : ''}
                    </span>
                    <span className="progress-percent">
                      {a.completed
                        ? `${Math.round((a.correct_count / a.total_questions) * 100)}% correct`
                        : `${Math.round((a.answered_count / a.total_questions) * 100)}% answered`}
                    </span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{ width: `${(a.answered_count / a.total_questions) * 100}%` }}
                      data-completed={a.completed}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="section-label" style={{ padding: 0, marginTop: 40 }}>
            Worth revisiting
          </div>

          {recommendations !== null && recommendations.length === 0 && (
            <div className="empty" style={{ marginTop: 12 }}>
              Complete a few quizzes to get personalized recommendations.
            </div>
          )}

          {recommendations !== null && recommendations.length > 0 && (
            <div className="progress-list">
              {recommendations.map((r) => (
                <div className="progress-item" key={r.subject}>
                  <div className="progress-item-row">
                    <span>{r.subject}</span>
                    <span className="progress-percent">{r.average_score_percent}% avg</span>
                  </div>
                  <div className="progress-reason">{r.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
