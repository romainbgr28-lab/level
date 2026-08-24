import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { addExerciceHistorique, addHistoriqueSeance, getTodaySeance, updateSeance } from '../api/client';
import type { ApiSeance } from '../api/client';

type SetKey = string; // `${exerciseId}-${setIndex}`
type Phase = 'checkin' | 'exercices' | 'ressenti';

const REST_SECONDS = 90;
const SOMMEIL_OPTIONS = ['Mauvais', 'Moyen', 'Bon', 'Excellent'];
const MOTIVATION_OPTIONS = ['Faible', 'Correcte', 'Élevée'];
const CLUB_SEMAINE_OPTIONS: { value: string; label: string }[] = [
  { value: 'non', label: 'Non' },
  { value: '1_fois', label: 'Oui, 1 fois' },
  { value: '2_fois_ou_plus', label: 'Oui, 2 fois ou plus' },
];

export default function Workout() {
  const navigate = useNavigate();
  const [seance, setSeance] = useState<ApiSeance | null>(null);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState<Phase>('checkin');
  const [checked, setChecked] = useState<Set<SetKey>>(new Set());
  const [restRemaining, setRestRemaining] = useState<number | null>(null);
  const [rpe, setRpe] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [sommeil, setSommeil] = useState('');
  const [motivation, setMotivation] = useState('');
  const [tempsDispo, setTempsDispo] = useState('');
  const [envieTexte, setEnvieTexte] = useState('');
  const [clubSemaine, setClubSemaine] = useState('');

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

      // Historique par exercice (alimente le graphique de charge en Progression)
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

      // Journal détaillé de la séance : prévu vs réalisé + contexte déclaré avant
      const exercicesRealises = seance.exercices
        .map((ex) => ({
          id: ex.id,
          name: ex.name,
          sets: ex.sets.filter((_, i) => checked.has(`${ex.id}-${i}`)),
        }))
        .filter((ex) => ex.sets.length > 0);

      await addHistoriqueSeance({
        date: seance.date,
        type_seance: seance.nom,
        exercices_prevus: seance.exercices,
        exercices_realises: exercicesRealises,
        rpe,
        notes: notes.trim() || null,
        etat_declare_avant: {
          sommeil: sommeil || null,
          motivation: motivation || null,
          temps_dispo: tempsDispo || null,
          envie_texte: envieTexte.trim() || null,
          entrainement_club_semaine: clubSemaine || null,
        },
      });

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

  if (phase === 'checkin') {
    return (
      <div className="screen">
        <Header title="Séance en cours" />
        <button className="back-btn" onClick={() => navigate('/')}>
          ← Annuler
        </button>
        <h1 className="page-title">Avant de commencer</h1>
        <p className="subtle" style={{ marginBottom: 18 }}>
          Quelques infos rapides pour adapter le suivi de cette séance.
        </p>

        <div className="onboarding-theme">
          <div className="section-title">Sommeil de la nuit dernière</div>
          <div className="tag-row tag-row--select">
            {SOMMEIL_OPTIONS.map((o) => (
              <button
                key={o}
                type="button"
                className={`tag tag--selectable ${sommeil === o ? 'tag--active' : ''}`}
                onClick={() => setSommeil(o)}
              >
                {o}
              </button>
            ))}
          </div>
        </div>

        <div className="onboarding-theme">
          <div className="section-title">Motivation du jour</div>
          <div className="tag-row tag-row--select">
            {MOTIVATION_OPTIONS.map((o) => (
              <button
                key={o}
                type="button"
                className={`tag tag--selectable ${motivation === o ? 'tag--active' : ''}`}
                onClick={() => setMotivation(o)}
              >
                {o}
              </button>
            ))}
          </div>
        </div>

        <div className="onboarding-theme">
          <div className="section-title">As-tu eu un entraînement club cette semaine ?</div>
          <div className="tag-row tag-row--select">
            {CLUB_SEMAINE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                className={`tag tag--selectable ${clubSemaine === o.value ? 'tag--active' : ''}`}
                onClick={() => setClubSemaine(o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="onboarding-theme">
          <div className="section-title">Temps disponible aujourd’hui</div>
          <input
            type="text"
            className="textarea"
            style={{ minHeight: 'unset', padding: 12 }}
            placeholder="Ex : 45 min"
            value={tempsDispo}
            onChange={(e) => setTempsDispo(e.target.value)}
          />
        </div>

        <div className="onboarding-theme">
          <div className="section-title">Envie du moment (optionnel)</div>
          <textarea
            className="textarea"
            placeholder="Ex : j’ai envie de pousser fort aujourd’hui…"
            value={envieTexte}
            onChange={(e) => setEnvieTexte(e.target.value)}
          />
        </div>

        <button className="btn btn--primary" onClick={() => setPhase('exercices')}>
          Commencer la séance
        </button>
      </div>
    );
  }

  if (phase === 'ressenti') {
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
        <textarea
          className="textarea"
          style={{ marginBottom: 18 }}
          placeholder="Notes sur la séance (optionnel)…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
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

      <button className="btn btn--primary" onClick={() => setPhase('ressenti')}>
        Terminer la séance
      </button>
    </div>
  );
}
