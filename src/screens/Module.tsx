import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { addSessionApprentissage, getTodayModule } from '../api/client';
import type { ApiModule } from '../api/client';

export default function Module() {
  const navigate = useNavigate();
  const [learningModule, setLearningModule] = useState<ApiModule | null>(null);
  const [loading, setLoading] = useState(true);
  const [openAnswer, setOpenAnswer] = useState('');
  const [openSubmitted, setOpenSubmitted] = useState(false);
  const [qcmAnswers, setQcmAnswers] = useState<Record<string, number>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getTodayModule()
      .then(setLearningModule)
      .finally(() => setLoading(false));
  }, []);

  function selectQcm(questionId: string, index: number) {
    if (qcmAnswers[questionId] !== undefined) return;
    setQcmAnswers((prev: Record<string, number>) => ({ ...prev, [questionId]: index }));
  }

  const qcmQuestions = learningModule?.questions.filter((q) => q.type === 'qcm') ?? [];
  const allAnswered = openSubmitted && qcmQuestions.every((q) => qcmAnswers[q.id] !== undefined);

  async function finishModule() {
    if (!learningModule) return;
    const correctCount = qcmQuestions.filter((q) => qcmAnswers[q.id] === q.correctIndex).length;
    const score = qcmQuestions.length > 0 ? (correctCount / qcmQuestions.length) * 100 : 100;
    await addSessionApprentissage({
      module_id: learningModule.id,
      date: new Date().toISOString().slice(0, 10),
      reponses: { open: openAnswer, qcm: qcmAnswers },
      score,
    });
    setSaved(true);
    navigate('/');
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Module" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  if (!learningModule) {
    return (
      <div className="screen">
        <Header title="Module" />
        <p className="subtle">Aucun module disponible.</p>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Module" />
      <button className="back-btn" onClick={() => navigate('/')}>
        ← Retour
      </button>
      <span className="tag">{learningModule.categorie}</span>
      <h1 className="page-title" style={{ marginTop: 10 }}>
        {learningModule.titre}
      </h1>

      <div className="module-text">
        {learningModule.contenu.split('\n\n').map((para, i) => (
          <p key={i} style={{ marginBottom: 14 }}>
            {para}
          </p>
        ))}
      </div>

      {learningModule.questions.map((q) => {
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
            {q.options?.map((opt, i) => {
              let cls = 'qcm-option';
              if (answered !== undefined) {
                if (i === q.correctIndex) cls += ' correct';
                else if (i === answered) cls += ' incorrect';
              }
              return (
                <button
                  key={i}
                  className={cls}
                  onClick={() => selectQcm(q.id, i)}
                  disabled={answered !== undefined}
                >
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

      <button
        className="btn btn--primary"
        disabled={!allAnswered || saved}
        style={{ opacity: allAnswered && !saved ? 1 : 0.5 }}
        onClick={finishModule}
      >
        Terminer le module
      </button>
    </div>
  );
}
