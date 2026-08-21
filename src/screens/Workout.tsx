import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { todaysWorkout } from '../data/mockData';

type SetKey = string; // `${exerciseId}-${setIndex}`

const REST_SECONDS = 90;

export default function Workout() {
  const navigate = useNavigate();
  const [checked, setChecked] = useState<Set<SetKey>>(new Set());
  const [restRemaining, setRestRemaining] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [rpe, setRpe] = useState<number | null>(null);

  const totalSets = useMemo(
    () => todaysWorkout.exercises.reduce((sum, ex) => sum + ex.sets.length, 0),
    []
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
          disabled={rpe === null}
          style={{ opacity: rpe === null ? 0.5 : 1 }}
          onClick={() => navigate('/')}
        >
          Terminer la séance
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
      <h1 className="page-title">{todaysWorkout.name}</h1>
      <p className="subtle" style={{ marginBottom: 16 }}>
        {checked.size}/{totalSets} séries validées
      </p>

      {restRemaining !== null && (
        <div className="rest-timer">
          <span>Repos</span>
          <span>{restRemaining}s</span>
        </div>
      )}

      {todaysWorkout.exercises.map((ex) => (
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
