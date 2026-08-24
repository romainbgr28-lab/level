import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import { getChargeProgress, getStats, getStreaks } from '../api/client';
import type { ApiChargePoint, ApiStats, ApiStreakDay } from '../api/client';

export default function Progress() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [charge, setCharge] = useState<ApiChargePoint[]>([]);
  const [streaks, setStreaks] = useState<ApiStreakDay[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getStats(), getChargeProgress(), getStreaks()])
      .then(([s, c, streakDays]) => {
        setStats(s);
        setCharge(c);
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
