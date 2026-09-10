import { useEffect, useMemo, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { QuizModal } from '../components/modals/QuizModal';
import { listQuizAttempts, getQuizRecommendations, redoQuizAttempt } from '../api/quizProgress';
import type { QuizAttemptOut, QuizRecommendationOut } from '../types/quizProgress';
import { SparkleIcon } from '../components/icons';

interface AttemptGroup {
  key: string;
  topic: string;
  subject: string | null;
  count: number;
  best: QuizAttemptOut;
  latest: QuizAttemptOut;
}

function scoreOf(a: QuizAttemptOut): number {
  return a.completed ? a.correct_count / a.total_questions : -1;
}

function groupAttempts(attempts: QuizAttemptOut[]): AttemptGroup[] {
  const groups = new Map<string, AttemptGroup>();
  for (const a of attempts) {
    const key = `${a.topic} ${a.subject ?? ''}`;
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, { key, topic: a.topic, subject: a.subject, count: 1, best: a, latest: a });
    } else {
      existing.count += 1;
      if (scoreOf(a) > scoreOf(existing.best)) existing.best = a;
    }
  }
  return Array.from(groups.values());
}

export function ProgressPage() {
  const [attempts, setAttempts] = useState<QuizAttemptOut[] | null>(null);
  const [recommendations, setRecommendations] = useState<QuizRecommendationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [redoingId, setRedoingId] = useState<number | null>(null);
  const [redoAttempt, setRedoAttempt] = useState<QuizAttemptOut | null>(null);

  const loadAttempts = () => {
    listQuizAttempts()
      .then(setAttempts)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load progress'));
  };

  useEffect(() => {
    Promise.all([listQuizAttempts(), getQuizRecommendations()])
      .then(([a, r]) => {
        setAttempts(a);
        setRecommendations(r);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load progress'));
  }, []);

  const attemptGroups = useMemo(() => (attempts ? groupAttempts(attempts) : []), [attempts]);

  const handleRedo = async (attempt: QuizAttemptOut) => {
    setRedoingId(attempt.id);
    setError(null);
    try {
      const fresh = await redoQuizAttempt(attempt.id);
      setAttempts((prev) => (prev ? [fresh, ...prev] : [fresh]));
      setRedoAttempt(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to redo quiz');
    } finally {
      setRedoingId(null);
    }
  };

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container">
          <div className="page-header">
            <div className="page-header-title">
              <h1>Your progress</h1>
              <SparkleIcon style={{ color: 'var(--muted)' }} />
            </div>
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
              {attemptGroups.map((g) => (
                <div className="progress-item" key={g.key}>
                  <div className="progress-item-row">
                    <span>
                      {g.topic}
                      {g.subject ? ` · ${g.subject}` : ''}
                      {g.count > 1 && <span className="progress-attempt-badge">×{g.count}</span>}
                    </span>
                    <span className="progress-percent">
                      {g.best.completed
                        ? `${Math.round((g.best.correct_count / g.best.total_questions) * 100)}% best`
                        : `${Math.round((g.best.answered_count / g.best.total_questions) * 100)}% answered`}
                    </span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{ width: `${(g.best.answered_count / g.best.total_questions) * 100}%` }}
                      data-completed={g.best.completed}
                    />
                  </div>
                  <button
                    type="button"
                    className="progress-redo-btn"
                    disabled={redoingId === g.latest.id}
                    onClick={() => handleRedo(g.latest)}
                  >
                    {redoingId === g.latest.id ? 'Generating…' : 'Redo'}
                  </button>
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

      {redoAttempt && (
        <QuizModal
          data={{ topic: redoAttempt.topic, questions: redoAttempt.questions ?? [] }}
          subject={redoAttempt.subject}
          existingAttemptId={redoAttempt.id}
          onClose={() => {
            setRedoAttempt(null);
            loadAttempts();
          }}
        />
      )}
    </AppShell>
  );
}
