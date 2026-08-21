import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { weeklyReview } from '../data/mockData';

export default function WeeklyReview() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <Header title="Bilan hebdomadaire" />
      <button className="back-btn" onClick={() => navigate('/progression')}>
        ← Progression
      </button>
      <h1 className="page-title">{weeklyReview.weekLabel}</h1>

      <section className="card card--coach">
        <div className="card__eyebrow">Force identifiée</div>
        <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{weeklyReview.strength.statement}</p>
        <p className="subtle">{weeklyReview.strength.evidence}</p>
      </section>

      <section className="card">
        <div className="card__eyebrow">Point faible identifié</div>
        <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{weeklyReview.weakness.statement}</p>
        <p className="subtle">{weeklyReview.weakness.evidence}</p>
      </section>

      <section className="card">
        <div className="card__eyebrow">Ajustement prévu</div>
        <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{weeklyReview.adjustment.statement}</p>
        <p className="subtle">{weeklyReview.adjustment.evidence}</p>
      </section>
    </div>
  );
}
