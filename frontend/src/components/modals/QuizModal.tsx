import { useEffect, useRef, useState } from 'react';
import type { QuizResponse } from '../../types/chat';
import { createQuizAttempt, updateQuizAttempt } from '../../api/quizProgress';
import { ModalShell } from './ModalShell';

interface Props {
  data: QuizResponse;
  subject: string | null;
  onClose: () => void;
}

export function QuizModal({ data, subject, onClose }: Props) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const attemptId = useRef<number | null>(null);
  const attemptStarted = useRef(false);

  useEffect(() => {
    if (attemptStarted.current) return;
    attemptStarted.current = true;

    createQuizAttempt(data.topic, subject, data.questions.length)
      .then((attempt) => {
        attemptId.current = attempt.id;
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const answerQuestion = (qi: number, letter: string) => {
    if (answers[qi] !== undefined) return;
    const nextAnswers = { ...answers, [qi]: letter };
    setAnswers(nextAnswers);

    const answeredCount = Object.keys(nextAnswers).length;
    const correctCount = data.questions.filter((q, i) => nextAnswers[i] === q.answer).length;
    if (attemptId.current !== null) {
      updateQuizAttempt(attemptId.current, answeredCount, correctCount).catch(() => {});
    }
  };

  const correctCount = data.questions.filter((q, i) => answers[i] === q.answer).length;
  const answeredCount = Object.keys(answers).length;
  const total = data.questions.length;

  return (
    <ModalShell onClose={onClose}>
      <h2>Quiz: {data.topic}</h2>
      <div className="modal-subtitle">{total} questions · based on your conversation</div>

      <div className="progress-track" style={{ marginTop: 12 }}>
        <div className="progress-fill" style={{ width: `${total ? (answeredCount / total) * 100 : 0}%` }} />
      </div>
      <div className="progress-percent" style={{ marginTop: 4 }}>
        {total ? Math.round((answeredCount / total) * 100) : 0}% answered
      </div>

      {data.questions.map((q, qi) => {
        const chosen = answers[qi];
        const answered = chosen !== undefined;
        return (
          <div className="quiz-question" key={qi}>
            <p>
              {qi + 1}. {q.question}
            </p>
            {q.options.map((opt) => {
              const letter = opt[0];
              let cls = 'quiz-option';
              if (answered) {
                if (letter === q.answer) cls += ' correct';
                else if (letter === chosen) cls += ' wrong';
              }
              return (
                <button
                  key={opt}
                  className={cls}
                  disabled={answered}
                  onClick={() => answerQuestion(qi, letter)}
                >
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
          Score: {correctCount} / {total}
          {answeredCount === total && correctCount === total ? ' 🎉' : ''}
        </div>
        <button className="modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
