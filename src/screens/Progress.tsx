import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import LineChart from '../components/LineChart';
import {
  genererProgramme,
  messageErreur,
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
import { EtatChargement, EtatErreur, EtatVide } from '../components/EtatEcran';

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
  const [programmeErreur, setProgrammeErreur] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [chargementErreur, setChargementErreur] = useState<string | null>(null);

  const charger = useCallback(() => {
    setLoading(true);
    setChargementErreur(null);
    setProgrammeErreur(null);
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
        // ou génération à l'onboarding qui a échoué) : on en construit un à la volée. L'appel
        // est idempotent côté backend, un second montage de l'écran ne crée pas un doublon.
        setProgrammeLoading(true);
        genererProgramme()
          .then(setProgramme)
          .catch((e) =>
            // Échec silencieux auparavant : l'écran affichait alors un blanc permanent, sans
            // dire pourquoi ni quoi faire.
            setProgrammeErreur(messageErreur(e, "Ton programme n'a pas pu être construit."))
          )
          .finally(() => setProgrammeLoading(false));
      })
      .catch((e) => setChargementErreur(messageErreur(e, 'Ta progression n’a pas pu être chargée.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(charger, [charger]);

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
        <h1 className="page-title">Progression</h1>
        <EtatChargement message="Chargement de ta progression…" />
      </div>
    );
  }

  if (chargementErreur) {
    return (
      <div className="screen">
        <Header title="Progression" />
        <h1 className="page-title">Progression</h1>
        <EtatErreur
          message={chargementErreur}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Retour à aujourd’hui', onClick: () => navigate('/aujourdhui') }}
        />
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
      ) : programmeLoading ? (
        <EtatChargement message="Construction de ton programme personnalisé…" />
      ) : (
        <EtatVide
          titre="Mon programme"
          message={
            programmeErreur
              ? `${programmeErreur} Tu peux relancer la construction depuis l’écran Programme.`
              : 'Aucun programme actif pour le moment : sans lui, LEVEL ne peut pas répartir tes séances dans la semaine.'
          }
          action={{ label: 'Construire mon programme', onClick: () => navigate('/programme') }}
        />
      )}

      <div className="section-divider" />

      <section className="card">
        <div className="card__eyebrow">Charge par séance</div>
        {exercicesSuivis.length === 0 ? (
          <p className="subtle">
            Tes courbes de charge apparaîtront ici dès que tu auras logué un même exercice sur
            deux séances. LEVEL suit alors ce que tu entraînes vraiment, exercice par exercice.
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
        {streaks.some((d) => d.sport_fait || d.apprentissage_fait) ? (
          <div className="streak-grid">
            {streaks.map((day) => (
              <div
                key={day.date}
                className={`streak-cell${day.sport_fait || day.apprentissage_fait ? ' active' : ''}`}
              />
            ))}
          </div>
        ) : (
          <p className="subtle">
            Chaque jour où tu termines une séance s’allume ici. Ta première séance validée
            démarre la série.
          </p>
        )}
      </section>
    </div>
  );
}
