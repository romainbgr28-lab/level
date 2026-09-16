import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import {
  genererProgramme,
  getChargeProgress,
  getExercicesSuivis,
  getProgrammeActif,
  getStats,
  getStreaks,
  getVolumeProgress,
} from '../api/client';
import type {
  ApiChargePoint,
  ApiExerciceSuivi,
  ApiProgramme,
  ApiStats,
  ApiStreakDay,
  ApiVolumeSemaine,
} from '../api/client';
import { phaseCourante, semaineActuelle } from '../utils/programme';

function tronquer(texte: string, max: number): string {
  return texte.length > max ? `${texte.slice(0, max).trimEnd()}…` : texte;
}

function ProgrammeSummary({ programme }: { programme: ApiProgramme }) {
  const navigate = useNavigate();
  const semaine = semaineActuelle(programme);
  const phase = phaseCourante(programme, semaine);

  return (
    <section className="card card--coach programme-summary">
      <div className="programme-summary__head">
        <div className="card__eyebrow" style={{ marginBottom: 0 }}>Mon programme</div>
        <span className="subtle">Semaine {semaine}/{programme.duree_semaines}</span>
      </div>
      {phase && (
        <p className="programme-summary__phase">
          Phase actuelle : <strong>{phase.nom}</strong> — {tronquer(phase.description, 70)}
        </p>
      )}
      <button className="btn btn--ghost btn--sm" onClick={() => navigate('/programme')}>
        Voir le programme complet →
      </button>
    </section>
  );
}

export default function Progress() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [charge, setCharge] = useState<ApiChargePoint[]>([]);
  // Exercices réellement entraînés (>= 2 séances loguées) : la courbe suit ce que le joueur
  // fait, au lieu d'un exercice choisi en dur qui reste vide pour la plupart des profils.
  const [exercicesSuivis, setExercicesSuivis] = useState<ApiExerciceSuivi[]>([]);
  const [exerciceCourant, setExerciceCourant] = useState<string | null>(null);
  const [volume, setVolume] = useState<ApiVolumeSemaine[]>([]);
  const [streaks, setStreaks] = useState<ApiStreakDay[]>([]);
  const [programme, setProgramme] = useState<ApiProgramme | null>(null);
  const [programmeLoading, setProgrammeLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getStats(), getExercicesSuivis(), getStreaks(), getProgrammeActif(), getVolumeProgress()])
      .then(([s, suivis, streakDays, prog, volumeSemaines]) => {
        setStats(s);
        setExercicesSuivis(suivis);
        setStreaks(streakDays);
        setVolume(volumeSemaines);
        if (suivis.length > 0) {
          setExerciceCourant(suivis[0].nom);
        }
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

  useEffect(() => {
    if (!exerciceCourant) {
      setCharge([]);
      return;
    }
    let annule = false;
    getChargeProgress(exerciceCourant)
      .then((points) => {
        if (!annule) setCharge(points);
      })
      .catch(() => {
        if (!annule) setCharge([]);
      });
    return () => {
      annule = true;
    };
  }, [exerciceCourant]);

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

      <button className="btn btn--ghost" style={{ marginBottom: 12 }} onClick={() => navigate('/bilan')}>
        Voir le bilan hebdomadaire
      </button>
      <button className="btn btn--ghost" style={{ marginBottom: 20 }} onClick={() => navigate('/historique')}>
        Voir l'historique des séances
      </button>

      {programme ? (
        <ProgrammeSummary programme={programme} />
      ) : (
        programmeLoading && (
          <section className="card card--coach">
            <div className="card__eyebrow">Mon programme</div>
            <p className="subtle">Construction de ton programme personnalisé…</p>
          </section>
        )
      )}

      <div className="section-divider" />

      <section className="card">
        <div className="card__eyebrow">Charge par séance</div>
        {exercicesSuivis.length === 0 ? (
          <p className="subtle">
            Aucune courbe disponible : logue tes charges sur au moins deux séances d'un même
            exercice pour voir ta progression.
          </p>
        ) : (
          <>
            <div className="chip-row">
              {exercicesSuivis.map((ex) => (
                <button
                  key={ex.exercice_id}
                  type="button"
                  className={`chip${ex.nom === exerciceCourant ? ' chip--active' : ''}`}
                  onClick={() => setExerciceCourant(ex.nom)}
                >
                  {ex.nom}
                </button>
              ))}
            </div>
            <div className="chart-wrap">
              {charge.length >= 2 ? (
                <LineChart data={charge} />
              ) : (
                <p className="subtle">Pas encore assez de données pour ce graphique.</p>
              )}
            </div>
          </>
        )}
      </section>

      <section className="card">
        <div className="card__eyebrow">Volume soulevé — par semaine</div>
        <div className="chart-wrap">
          {volume.length >= 2 ? (
            <LineChart
              data={volume.map((v) => ({ date: v.date, loadKg: Math.round(v.volume_kg) }))}
            />
          ) : (
            <p className="subtle">
              Il faut au moins deux semaines de séries loguées pour tracer cette évolution.
            </p>
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
