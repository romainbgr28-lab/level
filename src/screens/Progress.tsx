import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import { getChargeProgress, getStats, getStreaks, getThemeScores } from '../api/client';
import type { ApiChargePoint, ApiStats, ApiStreakDay, ApiThemeScore } from '../api/client';

export default function Progress() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [charge, setCharge] = useState<ApiChargePoint[]>([]);
  const [themes, setThemes] = useState<ApiThemeScore[]>([]);
  const [streaks, setStreaks] = useState<ApiStreakDay[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getStats(), getChargeProgress(), getThemeScores(), getStreaks()])
      .then(([s, c, t, streakDays]) => {
        setStats(s);
        setCharge(c);
        setThemes(t);
        setStreaks(streakDays);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="screen">
        <Header title="Progression" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Progression" />
      <h1 className="page-title">Progression</h1>

      {stats && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.total_seances}</div>
            <div className="stat-tile__label">Séances totales</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">🔥 {stats.streak}</div>
            <div className="stat-tile__label">Streak actuel</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.xp_total.toLocaleString('fr-FR')}</div>
            <div className="stat-tile__label">XP total</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.rpe_average}</div>
            <div className="stat-tile__label">RPE moyen</div>
          </div>
        </div>
      )}

      <button className="btn btn--ghost" style={{ marginBottom: 20 }} onClick={() => navigate('/bilan')}>
        Voir le bilan hebdomadaire
      </button>

      <section className="card">
        <div className="card__eyebrow">Développé couché — charge (dernières séances)</div>
        <div className="chart-wrap">
          {charge.length >= 2 ? (
            <LineChart data={charge} />
          ) : (
            <p className="subtle">Pas encore assez de données pour ce graphique.</p>
          )}
        </div>
      </section>

      <section className="card">
        <div className="card__eyebrow">Score par thème</div>
        {themes.length === 0 && <p className="subtle">Aucun quiz complété pour l’instant.</p>}
        {themes.map((t) => (
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
          {streaks.map((day) => (
            <div
              key={day.date}
              className={`streak-cell${day.sport_fait || day.apprentissage_fait ? ' active' : ''}`}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
