import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { todaysWorkout, todaysModule, coachMessage } from '../data/mockData';

const dateLabel = new Date().toLocaleDateString('fr-FR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

export default function Today() {
  const navigate = useNavigate();
  const preview = todaysWorkout.exercises.slice(0, 3);

  return (
    <div className="screen">
      <Header title="Aujourd’hui" />
      <h1 className="page-title" style={{ textTransform: 'capitalize' }}>
        {dateLabel}
      </h1>

      <section className="card">
        <div className="card__eyebrow">Séance du jour</div>
        <h2 className="card__title">{todaysWorkout.name}</h2>
        <p className="subtle" style={{ margin: '4px 0 12px' }}>
          {todaysWorkout.durationMin} min · {todaysWorkout.exercises.length} exercices
        </p>
        <div>
          {preview.map((ex) => (
            <div className="exercise-row" key={ex.id}>
              <span className="exercise-row__name">{ex.name}</span>
              <span className="exercise-row__meta">
                {ex.sets.length}x{ex.sets[0].reps}
              </span>
            </div>
          ))}
        </div>
        <button className="btn btn--primary" style={{ marginTop: 14 }} onClick={() => navigate('/seance')}>
          Commencer
        </button>
      </section>

      <section className="card">
        <div className="card__eyebrow">Module du jour</div>
        <span className="tag">{todaysModule.category}</span>
        <h2 className="card__title" style={{ marginTop: 10 }}>
          {todaysModule.title}
        </h2>
        <p className="subtle" style={{ margin: '6px 0 14px' }}>
          {todaysModule.hook}
        </p>
        <button className="btn btn--ghost" onClick={() => navigate('/module')}>
          Ouvrir
        </button>
      </section>

      <section className="card card--coach">
        <div className="card__eyebrow">Ton coach</div>
        <p style={{ fontSize: 15, lineHeight: 1.55 }}>{coachMessage.message}</p>
      </section>
    </div>
  );
}
