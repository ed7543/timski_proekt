import { useEffect, useMemo, useRef, useState } from 'react';
import { getLesson, generateLessonQuiz } from '../../api/courses';
import type { LessonOut, LessonDetailOut, QuizQuestionOut, QuizDifficulty } from '../../types/course';
import { ApiError } from '../../api/client';
import { BackArrowIcon } from '../icons';
import { ModalShell } from '../modals/ModalShell';
import { renderMarkdown } from '../../utils/markdown';

interface Props {
  courseId: number;
  lesson: LessonOut;
  onBack: () => void;
  /** Jump straight into the quiz (generating it first if needed) - used by the
   * "Try Quiz" button on the lesson list, instead of landing on the documentation. */
  autoOpenQuiz?: boolean;
  /** Called once when the student finishes the quiz with a perfect score. */
  onQuizPassed?: (lessonId: number) => void;
}

// Gemini's generated documentation sometimes opens with its own heading that just
// restates context already shown above the text - either "Предмет: <course name>",
// or the lesson's own topic title repeated verbatim as a "## <topic title>" heading
// right under the h2 that already shows it. Both are a display-layer cleanup (the
// stored text itself is untouched), not a content edit.
const COURSE_HEADING_RE = /^#{1,6}\s*Предмет\s*:?.*$/im;
const HEADING_LINE_RE = /^#{1,6}\s*(.+?)\s*#*$/;

function normalizeForCompare(text: string): string {
  return text
    .toLowerCase()
    .replace(/[.,:;!?"'()«»„“]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function stripCourseHeading(documentation: string, lessonTitle: string): string {
  const lines = documentation.split('\n');
  const firstNonEmptyIdx = lines.findIndex((line) => line.trim() !== '');
  if (firstNonEmptyIdx === -1) return documentation;

  const normalizedTitle = normalizeForCompare(lessonTitle);
  const idx = lines.findIndex((line, i) => {
    if (i > firstNonEmptyIdx + 1) return false; // only look at the first couple of lines
    const trimmed = line.trim();
    if (COURSE_HEADING_RE.test(trimmed)) return true;
    const headingMatch = HEADING_LINE_RE.exec(trimmed);
    return !!headingMatch && normalizeForCompare(headingMatch[1]) === normalizedTitle;
  });
  if (idx === -1) return documentation;

  lines.splice(idx, 1);
  return lines.join('\n').replace(/^\s+/, '');
}

function LessonQuizModal({
  lessonTitle,
  questions,
  onClose,
  onFinish,
}: {
  lessonTitle: string;
  questions: QuizQuestionOut[];
  onClose: () => void;
  onFinish: (passed: boolean) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, number>>({});

  const answerQuestion = (qi: number, optionIndex: number) => {
    if (answers[qi] !== undefined) return;
    setAnswers((prev) => ({ ...prev, [qi]: optionIndex }));
  };

  const answeredCount = Object.keys(answers).length;
  const correctCount = questions.filter((q, i) => answers[i] === q.correct_option_index).length;
  const allCorrect = answeredCount === questions.length && correctCount === questions.length;

  return (
    <ModalShell onClose={onClose} className="quiz-modal" maxWidth={640}>
      <h2>Quiz</h2>
      <div className="modal-subtitle">
        {lessonTitle} · {questions.length} questions
      </div>

      {questions.map((q, qi) => {
        const chosen = answers[qi];
        const answered = chosen !== undefined;
        return (
          <div className="quiz-question" key={qi}>
            <p>
              {qi + 1}. {q.question}
            </p>
            {q.options.map((opt, oi) => {
              let cls = 'quiz-option';
              if (answered) {
                if (oi === q.correct_option_index) cls += ' correct';
                else if (oi === chosen) cls += ' wrong';
              }
              return (
                <button key={oi} className={cls} disabled={answered} onClick={() => answerQuestion(qi, oi)}>
                  {opt}
                </button>
              );
            })}
            <div className={`quiz-explanation${answered ? ' show' : ''}`}>{q.explanation}</div>
          </div>
        );
      })}

      <div className="modal-footer">
        <div className="quiz-score">
          Score: {correctCount} / {questions.length}
          {allCorrect ? ' 🎉' : ''}
        </div>
        <button type="button" className="modal-close" onClick={() => onFinish(allCorrect)}>
          Done
        </button>
      </div>
    </ModalShell>
  );
}

export function LessonDetail({ courseId, lesson, onBack, autoOpenQuiz, onQuizPassed }: Props) {
  const [detail, setDetail] = useState<LessonDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);
  const [showQuiz, setShowQuiz] = useState(false);
  const [difficulty, setDifficulty] = useState<QuizDifficulty>('medium');
  const autoOpenHandled = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetail(null);
    setQuizError(null);
    setShowQuiz(false);
    setDifficulty('medium');
    autoOpenHandled.current = false;
    getLesson(courseId, lesson.id)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        if (autoOpenQuiz && !autoOpenHandled.current) {
          autoOpenHandled.current = true;
          if (d.quiz) {
            setShowQuiz(true);
          } else if (d.documentation) {
            setGenerating(true);
            generateLessonQuiz(courseId, lesson.id)
              .then((withQuiz) => {
                if (cancelled) return;
                setDetail(withQuiz);
                setShowQuiz(true);
              })
              .catch((err) => {
                if (!cancelled) {
                  setQuizError(err instanceof ApiError ? err.message : 'Quiz generation failed - please try again.');
                }
              })
              .finally(() => {
                if (!cancelled) setGenerating(false);
              });
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load lesson');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, lesson.id]);

  const html = useMemo(
    () =>
      detail?.documentation
        ? renderMarkdown(stripCourseHeading(detail.documentation, lesson.topic_title))
        : '',
    [detail?.documentation, lesson.topic_title],
  );

  // The quiz currently selected via the Medium/Hard toggle below - each
  // tier lives in its own column (quiz / quiz_hard) and is generated
  // independently, so switching tabs never wipes the other one out.
  const currentQuiz = difficulty === 'hard' ? detail?.quiz_hard : detail?.quiz;

  const handleGenerateQuiz = () => {
    if (currentQuiz) {
      // Quiz already exists for this tier (just hidden after a previous
      // "Done") - show it again without wasting another Gemini call.
      setShowQuiz(true);
      return;
    }
    setGenerating(true);
    setQuizError(null);
    generateLessonQuiz(courseId, lesson.id, difficulty)
      .then((d) => {
        setDetail(d);
        setShowQuiz(true);
      })
      .catch((err) => {
        setQuizError(err instanceof ApiError ? err.message : 'Quiz generation failed - please try again.');
      })
      .finally(() => setGenerating(false));
  };

  const handleRegenerateQuiz = () => {
    setGenerating(true);
    setQuizError(null);
    generateLessonQuiz(courseId, lesson.id, difficulty)
      .then((d) => {
        setDetail(d);
        setShowQuiz(true);
      })
      .catch((err) => {
        setQuizError(err instanceof ApiError ? err.message : 'Quiz generation failed - please try again.');
      })
      .finally(() => setGenerating(false));
  };

  const handleQuizFinish = (passed: boolean) => {
    setShowQuiz(false);
    if (passed) onQuizPassed?.(lesson.id);
  };

  return (
    <div className="lesson-detail">
      <button type="button" className="course-back lesson-back" onClick={onBack}>
        <BackArrowIcon /> Back to lessons
      </button>

      <h2 className="lesson-detail-title">{lesson.topic_title}</h2>

      {loading && <div className="empty">Loading…</div>}
      {error && <div className="msg-error">{error}</div>}

      {detail && !loading && !error && (
        <>
          {detail.documentation ? (
            <div className="msg-ai-body lesson-doc" dangerouslySetInnerHTML={{ __html: html }} />
          ) : (
            <div className="empty">No documentation has been generated for this lesson yet.</div>
          )}

          {showQuiz && currentQuiz && currentQuiz.questions?.length > 0 && (
            <LessonQuizModal
              lessonTitle={`${lesson.topic_title} (${difficulty === 'hard' ? 'Hard' : 'Medium'})`}
              questions={currentQuiz.questions}
              onClose={() => setShowQuiz(false)}
              onFinish={handleQuizFinish}
            />
          )}

          {quizError && <div className="msg-error">{quizError}</div>}

          {!showQuiz && (
            <div className="lesson-quiz-actions">
              {detail.documentation && (
                <div className="quiz-difficulty-pill" role="tablist" aria-label="Quiz difficulty">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={difficulty === 'medium'}
                    className={`quiz-difficulty-seg${difficulty === 'medium' ? ' active' : ''}`}
                    disabled={generating}
                    onClick={() => setDifficulty('medium')}
                  >
                    Medium{detail.quiz ? ' ✓' : ''}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={difficulty === 'hard'}
                    className={`quiz-difficulty-seg${difficulty === 'hard' ? ' active' : ''}`}
                    disabled={generating}
                    onClick={() => setDifficulty('hard')}
                  >
                    Hard{detail.quiz_hard ? ' ✓' : ''}
                  </button>
                </div>
              )}
              <button
                type="button"
                className="modal-close"
                disabled={!detail.documentation || generating}
                onClick={handleGenerateQuiz}
              >
                {generating ? 'Generating…' : currentQuiz ? 'Show Quiz' : 'Generate Quiz'}
              </button>
              {currentQuiz && (
                <button
                  type="button"
                  className="modal-close ghost"
                  disabled={generating}
                  onClick={handleRegenerateQuiz}
                >
                  Regenerate Quiz
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
