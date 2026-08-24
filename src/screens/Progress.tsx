import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import { genererProgramme, getChargeProgress, getProgrammeActif, getStats, getStreaks } from '../api/client';
import type { ApiChargePoint, ApiProgramme, ApiStats, ApiStreakDay } from '../api/client';

function semaineActuelle(programme: ApiProgramme): number {
  const debut = new Date(programme.date_debut);
  const jours = Math.floor((Date.now() - debut.getTime()) / (1000 * 60 * 60 * 24));
  const semaine = Math.floor(jours / 7) + 1;
  return Math.min(Math.max(semaine, 1), programme.duree_semaines);
}

function phaseCourante(programme: ApiProgramme, semaine: number) {
  return programme.phases.find((p) => semaine >= p.semaine_debut && semaine <= p.semaine_fin);
}

function ProgrammeSection({ programme }: { programme: ApiProgramme }) {
  const semaine = semaineActuelle(programme);
  const phase = phaseCourante(programme, semaine);
  const jours = Object.entries(programme.gabarit_hebdomadaire);

  return (
    <section className="card">
      <div className="card__eyebrow">Mon programme</div>
      {phase && (
        <p className="subtle" style={{ marginBottom: 12 }}>
          Phase actuelle : <strong>{phase.nom}</strong> (semaine {semaine}/{programme.duree_semaines}) — {phase.description}
        </p>
      )}

      <div className="streak-grid" style={{ marginBottom: 16 }}>
        {Array.from({ length: programme.duree_semaines }).map((_, i) => {
          const num = i + 1;
          return (
            <div
              key={num}
              className={`streak-cell${num === semaine ? ' active' : ''}`}
              title={`Semaine ${num}`}
            />
          );
        })}
      </div>

      <div className="choice-list">
        {jours.map(([jour, type]) => (
          <div key={jour} className="choice-item" style={{ justifyContent: 'space-between' }}>
            <span>{jour}</span>
            <span className="subtle">{type}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Progress() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [charge, setCharge] = useState<ApiChargePoint[]>([]);
  const [streaks, setStreaks] = useState<ApiStreakDay[]>([]);
  const [programme, setProgramme] = useState<ApiProgramme | null>(null);
  const [programmeLoading, setProgrammeLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getStats(), getChargeProgress(), getStreaks(), getProgrammeActif()])
      .then(([s, c, streakDays, prog]) => {
        setStats(s);
        setCharge(c);
        setStreaks(streakDays);
        if (prog) {
          setProgramme(prog);
          return;
        }
        // Aucun programme actif (ex : profil créé avant l'ajout de cette fonctionnalité,
        // ou génération à l'onboarding qui a échoué) : on en génère un à la volée.
        setProgrammeLoading(true);
        genererProgramme()
          .then(setProgramme)
          .catch(() => {})
          .finally(() => setProgrammeLoading(false));
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

      {programme ? (
        <ProgrammeSection programme={programme} />
      ) : (
        programmeLoading && (
          <section className="card">
            <div className="card__eyebrow">Mon programme</div>
            <p className="subtle">Construction de ton programme personnalisé…</p>
          </section>
        )
      )}

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
