import { useState } from 'react';
import type { QuizResponse } from '../../types/chat';
import { ModalShell } from './ModalShell';

interface Props {
  data: QuizResponse;
  onClose: () => void;
}

export function QuizModal({ data, onClose }: Props) {
  const [answers, setAnswers] = useState<Record<number, string>>({});

  const answerQuestion = (qi: number, letter: string) => {
    if (answers[qi] !== undefined) return;
    setAnswers((prev) => ({ ...prev, [qi]: letter }));
  };

  const correctCount = data.questions.filter((q, i) => answers[i] === q.answer).length;
  const answeredCount = Object.keys(answers).length;
  const total = data.questions.length;

  return (
    <ModalShell onClose={onClose}>
      <h2>Quiz: {data.topic}</h2>
      <div className="modal-subtitle">{total} questions · based on your conversation</div>

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
