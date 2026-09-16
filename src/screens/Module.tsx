import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { addSessionApprentissage, getTodayModule, messageErreur } from '../api/client';
import { EtatChargement, EtatErreur, EtatVide, LigneErreur } from '../components/EtatEcran';
import { donneesModifiees } from '../utils/donneesFraiches';
import type { ApiModule } from '../api/client';

export default function Module() {
  const navigate = useNavigate();
  const [learningModule, setLearningModule] = useState<ApiModule | null>(null);
  const [loading, setLoading] = useState(true);
  const [openAnswer, setOpenAnswer] = useState('');
  const [openSubmitted, setOpenSubmitted] = useState(false);
  const [qcmAnswers, setQcmAnswers] = useState<Record<string, number>>({});
  const [saved, setSaved] = useState(false);
  const [chargementErreur, setChargementErreur] = useState<string | null>(null);
  const [actionErreur, setActionErreur] = useState<string | null>(null);

  const charger = useCallback(() => {
    setLoading(true);
    setChargementErreur(null);
    getTodayModule()
      .then(setLearningModule)
      .catch((e) => setChargementErreur(messageErreur(e, "Le module du jour n'a pas pu être chargé.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(charger, [charger]);

  function selectQcm(questionId: string, index: number) {
    if (qcmAnswers[questionId] !== undefined) return;
    setQcmAnswers((prev: Record<string, number>) => ({ ...prev, [questionId]: index }));
  }

  const qcmQuestions = learningModule?.questions.filter((q) => q.type === 'qcm') ?? [];
  const allAnswered = openSubmitted && qcmQuestions.every((q) => qcmAnswers[q.id] !== undefined);

  async function finishModule() {
    if (!learningModule || saved) return; // `saved` sert aussi de garde anti double-clic
    const correctCount = qcmQuestions.filter((q) => qcmAnswers[q.id] === q.correctIndex).length;
    const score = qcmQuestions.length > 0 ? (correctCount / qcmQuestions.length) * 100 : 100;
    setActionErreur(null);
    setSaved(true);
    try {
      await addSessionApprentissage({
        module_id: learningModule.id,
        date: new Date().toISOString().slice(0, 10),
        reponses: { open: openAnswer, qcm: qcmAnswers },
        score,
      });
    } catch (e) {
      // Enregistrement raté : on ne quitte pas l'écran (les réponses seraient perdues sans
      // avoir été sauvegardées) et on rouvre le bouton pour réessayer.
      setSaved(false);
      setActionErreur(messageErreur(e, "Tes réponses n'ont pas pu être enregistrées."));
      return;
    }
    donneesModifiees('stats');
    navigate('/aujourdhui');
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Module" />
        <EtatChargement message="Chargement du module du jour…" />
      </div>
    );
  }

  if (chargementErreur) {
    return (
      <div className="screen">
        <Header title="Module" />
        <EtatErreur
          titre="Module indisponible"
          message={chargementErreur}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Retour à aujourd’hui', onClick: () => navigate('/aujourdhui') }}
        />
      </div>
    );
  }

  if (!learningModule) {
    return (
      <div className="screen">
        <Header title="Module" />
        <EtatVide
          titre="Pas de module aujourd’hui"
          message="Aucun module d’apprentissage n’est prévu pour le moment. Ta progression physique, elle, continue."
          action={{ label: 'Voir ma journée', onClick: () => navigate('/aujourdhui') }}
        />
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Module" />
      <button className="back-btn" onClick={() => navigate('/aujourdhui')}>
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

      <LigneErreur message={actionErreur} />

      <button
        className="btn btn--primary"
        disabled={!allAnswered || saved}
        style={{ opacity: allAnswered && !saved ? 1 : 0.5 }}
        onClick={finishModule}
      >
        {saved ? 'Enregistrement…' : 'Terminer le module'}
      </button>
      {/* Bouton inactif : on dit ce qu'il reste à faire plutôt que de laisser deviner. */}
      {!allAnswered && !saved && (
        <p className="subtle" style={{ marginTop: 8 }}>
          Réponds à la question ouverte et à toutes les questions à choix pour terminer.
        </p>
      )}
    </div>
  );
}
