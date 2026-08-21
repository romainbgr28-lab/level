import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { getTodayModule, getTodaySeance } from '../api/client';
import type { ApiModule, ApiSeance } from '../api/client';

const dateLabel = new Date().toLocaleDateString('fr-FR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

export default function Today() {
  const navigate = useNavigate();
  const [seance, setSeance] = useState<ApiSeance | null>(null);
  const [learningModule, setLearningModule] = useState<ApiModule | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getTodaySeance(), getTodayModule()])
      .then(([s, m]) => {
        setSeance(s);
        setLearningModule(m);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen">
        <Header title="Aujourd’hui" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  const preview = seance?.exercices.slice(0, 3) ?? [];

  return (
    <div className="screen">
      <Header title="Aujourd’hui" />
      <h1 className="page-title" style={{ textTransform: 'capitalize' }}>
        {dateLabel}
      </h1>

      {seance && (
        <section className="card">
          <div className="card__eyebrow">Séance du jour</div>
          <h2 className="card__title">{seance.nom}</h2>
          <p className="subtle" style={{ margin: '4px 0 12px' }}>
            {seance.duree_reelle ?? '—'} min · {seance.exercices.length} exercices
          </p>
          <div>
            {preview.map((ex) => (
              <div className="exercise-row" key={ex.id}>
                <span className="exercise-row__name">{ex.name}</span>
                <span className="exercise-row__meta">
                  {ex.sets.length}x{ex.sets[0]?.reps}
                </span>
              </div>
            ))}
          </div>
          <button className="btn btn--primary" style={{ marginTop: 14 }} onClick={() => navigate('/seance')}>
            Commencer
          </button>
        </section>
      )}

      {learningModule && (
        <section className="card">
          <div className="card__eyebrow">Module du jour</div>
          <span className="tag">{learningModule.categorie}</span>
          <h2 className="card__title" style={{ marginTop: 10 }}>
            {learningModule.titre}
          </h2>
          <p className="subtle" style={{ margin: '6px 0 14px' }}>
            {learningModule.contenu.slice(0, 120)}…
          </p>
          <button className="btn btn--ghost" onClick={() => navigate('/module')}>
            Ouvrir
          </button>
        </section>
      )}

      <section className="card card--coach">
        <div className="card__eyebrow">Ton coach</div>
        <p style={{ fontSize: 15, lineHeight: 1.55 }}>
          Bonne récupération hier, on garde le cap aujourd’hui.
        </p>
      </section>
    </div>
  );
}
