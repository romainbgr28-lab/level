import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { addExerciceHistorique, getTodaySeance, updateSeance } from '../api/client';
import type { ApiSeance } from '../api/client';

type SetKey = string; // `${exerciseId}-${setIndex}`

const REST_SECONDS = 90;

export default function Workout() {
  const navigate = useNavigate();
  const [seance, setSeance] = useState<ApiSeance | null>(null);
  const [loading, setLoading] = useState(true);
  const [checked, setChecked] = useState<Set<SetKey>>(new Set());
  const [restRemaining, setRestRemaining] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [rpe, setRpe] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getTodaySeance()
      .then(setSeance)
      .finally(() => setLoading(false));
  }, []);

  const totalSets = useMemo(
    () => seance?.exercices.reduce((sum, ex) => sum + ex.sets.length, 0) ?? 0,
    [seance]
  );

  function toggleSet(key: SetKey) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
        setRestRemaining(REST_SECONDS);
        startTimer();
      }
      return next;
    });
  }

  function startTimer() {
    let remaining = REST_SECONDS;
    const interval = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(interval);
        setRestRemaining(null);
      } else {
        setRestRemaining(remaining);
      }
    }, 1000);
  }

  async function finishWorkout() {
    if (!seance || rpe === null) return;
    setSubmitting(true);
    try {
      await updateSeance(seance.id, { statut: 'terminee', rpe, duree_reelle: seance.duree_reelle ?? 45 });
      await Promise.all(
        seance.exercices.map((ex) =>
          addExerciceHistorique({
            seance_id: seance.id,
            nom_exercice: ex.name,
            series: ex.sets.length,
            repetitions: ex.sets[0]?.reps ?? 0,
            charge_kg: ex.sets[0]?.loadKg ?? 0,
            date: seance.date,
          })
        )
      );
      navigate('/');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Séance en cours" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  if (!seance) {
    return (
      <div className="screen">
        <Header title="Séance en cours" />
        <p className="subtle">Aucune séance prévue aujourd’hui.</p>
      </div>
    );
  }

  if (finished) {
    return (
      <div className="screen">
        <Header title="Séance en cours" />
        <h1 className="page-title">Ton ressenti</h1>
        <p className="subtle" style={{ marginBottom: 8 }}>
          Comment as-tu perçu l’effort de cette séance ? (RPE, 1 = très facile, 10 = maximal)
        </p>
        <div className="rpe-grid">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((val) => (
            <button
              key={val}
              className={`rpe-btn${rpe === val ? ' selected' : ''}`}
              onClick={() => setRpe(val)}
              aria-pressed={rpe === val}
            >
              {val}
            </button>
          ))}
        </div>
        <button
          className="btn btn--primary"
          disabled={rpe === null || submitting}
          style={{ opacity: rpe === null || submitting ? 0.5 : 1 }}
          onClick={finishWorkout}
        >
          {submitting ? 'Enregistrement…' : 'Terminer la séance'}
        </button>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Séance en cours" />
      <button className="back-btn" onClick={() => navigate('/')}>
        ← Annuler
      </button>
      <h1 className="page-title">{seance.nom}</h1>
      <p className="subtle" style={{ marginBottom: 16 }}>
        {checked.size}/{totalSets} séries validées
      </p>

      {restRemaining !== null && (
        <div className="rest-timer">
          <span>Repos</span>
          <span>{restRemaining}s</span>
        </div>
      )}

      {seance.exercices.map((ex) => (
        <div className="exercise-block" key={ex.id}>
          <h3 style={{ fontSize: 16, marginBottom: 10 }}>{ex.name}</h3>
          {ex.sets.map((set, i) => {
            const key = `${ex.id}-${i}`;
            const isChecked = checked.has(key);
            return (
              <div className="set-row" key={key}>
                <span className="set-row__label">Série {i + 1}</span>
                <span className="set-row__load">
                  {set.reps} reps{set.loadKg > 0 ? ` × ${set.loadKg} kg` : ''}
                </span>
                <button
                  className={`checkbox${isChecked ? ' checked' : ''}`}
                  onClick={() => toggleSet(key)}
                  aria-label={`Série ${i + 1} ${isChecked ? 'validée' : 'à valider'}`}
                >
                  {isChecked && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
                      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      ))}

      <button className="btn btn--primary" onClick={() => setFinished(true)}>
        Terminer la séance
      </button>
    </div>
  );
}
