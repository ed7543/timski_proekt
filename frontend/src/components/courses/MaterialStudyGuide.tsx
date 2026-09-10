import { useState } from 'react';
import { getMaterialStudyGuide, generateMaterialStudyGuide } from '../../api/courses';
import type { CourseMaterialOut, MaterialStudyGuideOut, QuizDifficulty } from '../../types/course';
import { ApiError } from '../../api/client';
import { renderMarkdown } from '../../utils/markdown';
import { LessonQuizModal } from './LessonDetail';

interface Props {
  courseId: number;
  material: CourseMaterialOut;
}

/** Marketplace equivalent of LessonDetail's documentation+quiz view, but
 * per-material instead of per curated lesson topic, and collapsed under a
 * toggle inside the material's own row rather than a full-page view - a
 * course can have many materials, and most visitors will never open this.
 * Same Medium/Hard quiz-difficulty split as LessonDetail (see
 * gemini_generator.generate_quiz(difficulty=...)), reusing the exact same
 * LessonQuizModal and .quiz-difficulty-pill styling. */
export function MaterialStudyGuide({ courseId, material }: Props) {
  const [open, setOpen] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [guide, setGuide] = useState<MaterialStudyGuideOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [showQuiz, setShowQuiz] = useState(false);
  const [difficulty, setDifficulty] = useState<QuizDifficulty>('medium');

  const isVideo = (material.category || '').trim().toLowerCase() === 'video';
  if (isVideo) return null;

  const currentQuiz = difficulty === 'hard' ? guide?.quiz_hard : guide?.quiz;

  const handleToggle = () => {
    const opening = !open;
    setOpen(opening);
    if (opening && !loadedOnce) {
      setLoading(true);
      setError(null);
      getMaterialStudyGuide(courseId, material.id)
        .then((g) => {
          setGuide(g);
          setLoadedOnce(true);
        })
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load study guide'))
        .finally(() => setLoading(false));
    }
  };

  const handleGenerate = () => {
    if (currentQuiz) {
      // Already generated for this tier (just hidden after a previous
      // "Done") - show it again without wasting another Gemini call.
      setShowQuiz(true);
      return;
    }
    setGenerating(true);
    setError(null);
    generateMaterialStudyGuide(courseId, material.id, difficulty)
      .then((g) => {
        setGuide(g);
        setShowQuiz(true);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Study guide generation failed - please try again.'),
      )
      .finally(() => setGenerating(false));
  };

  return (
    <>
      <button type="button" className="try-quiz-btn" onClick={handleToggle}>
        {open ? 'Hide' : 'Study Guide'}
      </button>

      {open && (
        <div className="study-guide-body">
          {loading && <div className="empty">Loading…</div>}
          {error && <div className="msg-error">{error}</div>}

          {guide && !loading && (
            <>
              {guide.documentation ? (
                <div
                  className="msg-ai-body lesson-doc"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(guide.documentation) }}
                />
              ) : (
                <div className="empty">No study guide generated yet for this material.</div>
              )}

              {showQuiz && currentQuiz && currentQuiz.questions?.length > 0 && (
                <LessonQuizModal
                  lessonTitle={`${material.title} (${difficulty === 'hard' ? 'Hard' : 'Medium'})`}
                  questions={currentQuiz.questions}
                  onClose={() => setShowQuiz(false)}
                  onFinish={() => setShowQuiz(false)}
                />
              )}

              {!showQuiz && (
                <div className="lesson-quiz-actions">
                  <div className="quiz-difficulty-pill" role="tablist" aria-label="Quiz difficulty">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={difficulty === 'medium'}
                      className={`quiz-difficulty-seg${difficulty === 'medium' ? ' active' : ''}`}
                      disabled={generating}
                      onClick={() => setDifficulty('medium')}
                    >
                      Medium{guide.quiz ? ' ✓' : ''}
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={difficulty === 'hard'}
                      className={`quiz-difficulty-seg${difficulty === 'hard' ? ' active' : ''}`}
                      disabled={generating}
                      onClick={() => setDifficulty('hard')}
                    >
                      Hard{guide.quiz_hard ? ' ✓' : ''}
                    </button>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={generating}
                    onClick={handleGenerate}
                  >
                    {generating ? 'Generating…' : currentQuiz ? 'Show Quiz' : 'Generate Quiz'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
