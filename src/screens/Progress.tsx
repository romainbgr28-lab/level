import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import { userStats, benchPressProgress, themeScores, streakHistory } from '../data/mockData';

export default function Progress() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <Header title="Progression" />
      <h1 className="page-title">Progression</h1>

      <div className="stat-grid">
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.totalSeances}</div>
          <div className="stat-tile__label">Séances totales</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile__value">🔥 {userStats.streak}</div>
          <div className="stat-tile__label">Streak actuel</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.xpTotal.toLocaleString('fr-FR')}</div>
          <div className="stat-tile__label">XP total</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.rpeAverage}</div>
          <div className="stat-tile__label">RPE moyen</div>
        </div>
      </div>

      <button className="btn btn--ghost" style={{ marginBottom: 20 }} onClick={() => navigate('/bilan')}>
        Voir le bilan hebdomadaire
      </button>

      <section className="card">
        <div className="card__eyebrow">Développé couché — charge (8 dernières séances)</div>
        <div className="chart-wrap">
          <LineChart data={benchPressProgress} />
        </div>
      </section>

      <section className="card">
        <div className="card__eyebrow">Score par thème</div>
        {themeScores.map((t) => (
          <div className="theme-row" key={t.theme}>
            <div className="theme-row__head">
              <span className="theme-row__label">{t.theme}</span>
              <span className="theme-row__pct">{t.percent}%</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${t.percent}%` }} />
            </div>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="card__eyebrow">Streak — 35 derniers jours</div>
        <div className="streak-grid">
          {streakHistory.map((active, i) => (
            <div key={i} className={`streak-cell${active ? ' active' : ''}`} />
          ))}
        </div>
      </section>
    </div>
  );
}
