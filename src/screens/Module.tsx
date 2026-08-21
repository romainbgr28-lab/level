import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { todaysModule } from '../data/mockData';
import type { QcmQuestion } from '../types';

export default function Module() {
  const navigate = useNavigate();
  const [openAnswer, setOpenAnswer] = useState('');
  const [openSubmitted, setOpenSubmitted] = useState(false);
  const [qcmAnswers, setQcmAnswers] = useState<Record<string, number>>({});

  function selectQcm(question: QcmQuestion, index: number) {
    if (qcmAnswers[question.id] !== undefined) return;
    setQcmAnswers((prev) => ({ ...prev, [question.id]: index }));
  }

  const allAnswered =
    openSubmitted &&
    todaysModule.questions.filter((q) => q.type === 'qcm').every((q) => qcmAnswers[q.id] !== undefined);

  return (
    <div className="screen">
      <Header title="Module" />
      <button className="back-btn" onClick={() => navigate('/')}>
        ← Retour
      </button>
      <span className="tag">{todaysModule.category}</span>
      <h1 className="page-title" style={{ marginTop: 10 }}>
        {todaysModule.title}
      </h1>

      <div className="module-text">
        {todaysModule.content.split('\n\n').map((para, i) => (
          <p key={i} style={{ marginBottom: 14 }}>
            {para}
          </p>
        ))}
      </div>

      {todaysModule.questions.map((q) => {
        if (q.type === 'open') {
          return (
            <div className="question-block" key={q.id}>
              <p className="question-block__prompt">{q.prompt}</p>
              <textarea
                className="textarea"
                value={openAnswer}
                onChange={(e) => setOpenAnswer(e.target.value)}
                disabled={openSubmitted}
                placeholder="Ta réponse…"
              />
              {!openSubmitted && (
                <button
                  className="btn btn--ghost btn--sm"
                  style={{ marginTop: 8, width: 'auto' }}
                  disabled={openAnswer.trim().length === 0}
                  onClick={() => setOpenSubmitted(true)}
                >
                  Valider
                </button>
              )}
              {openSubmitted && (
                <div className="feedback feedback--ok">
                  Merci pour ta réponse. Prendre conscience d’un exemple concret est la première
                  étape pour neutraliser ce biais.
                </div>
              )}
            </div>
          );
        }

        const answered = qcmAnswers[q.id];
        return (
          <div className="question-block" key={q.id}>
            <p className="question-block__prompt">{q.prompt}</p>
            {q.options.map((opt, i) => {
              let cls = 'qcm-option';
              if (answered !== undefined) {
                if (i === q.correctIndex) cls += ' correct';
                else if (i === answered) cls += ' incorrect';
              }
              return (
                <button key={i} className={cls} onClick={() => selectQcm(q, i)} disabled={answered !== undefined}>
                  {opt}
                </button>
              );
            })}
            {answered !== undefined && (
              <div className={`feedback ${answered === q.correctIndex ? 'feedback--ok' : 'feedback--ko'}`}>
                {answered === q.correctIndex ? 'Correct — ' : 'Incorrect — '}
                {q.explanation}
              </div>
            )}
          </div>
        );
      })}

      <button className="btn btn--primary" disabled={!allAnswered} style={{ opacity: allAnswered ? 1 : 0.5 }} onClick={() => navigate('/')}>
        Terminer le module
      </button>
    </div>
  );
}
