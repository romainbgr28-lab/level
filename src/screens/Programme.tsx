import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { genererProgramme, getContexteJour, getProgrammeActif } from '../api/client';
import type { ApiContexteJour, ApiProgramme } from '../api/client';
import { typeSeanceMeta } from '../data/programmeTypes';
// Semaine courante partagée avec l'écran Aujourd'hui : s'appuie sur getNow() et respecte donc
// la date simulée (src/utils/devDate.ts), là où un Date.now() local l'ignorait silencieusement.
import { semaineActuelle } from '../utils/programme';

// Libellés des statuts de jour décidés par le moteur (backend/contexte_jour.py) : le frontend
// se contente de les nommer, il n'en redérive aucun.
const LIBELLE_STATUT_JOUR: Record<string, string> = {
  match: 'Match',
  repos: 'Repos',
  indisponible: 'Indisponible',
};

function statutSemaine(num: number, semaineActuelleNum: number): 'passee' | 'actuelle' | 'a-venir' {
  if (num < semaineActuelleNum) return 'passee';
  if (num === semaineActuelleNum) return 'actuelle';
  return 'a-venir';
}

export default function Programme() {
  const [programme, setProgramme] = useState<ApiProgramme | null>(null);
  const [contexte, setContexte] = useState<ApiContexteJour | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProgrammeActif()
      .then(setProgramme)
      .finally(() => setLoading(false));
    // Le contexte porte la semaine réelle (match, indisponibilité, jour courant) : sans lui on
    // ne saurait afficher que le gabarit brut, qui ne dit rien des contraintes du calendrier.
    getContexteJour()
      .then(setContexte)
      .catch(() => setContexte(null));
  }, []);

  async function handleGenerer() {
    setGenerating(true);
    setError(null);
    try {
      const prog = await genererProgramme();
      setProgramme(prog);
      setContexte(await getContexteJour().catch(() => null));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur lors de la génération du programme.');
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Mon programme" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  if (!programme) {
    return (
      <div className="screen">
        <Header title="Mon programme" />
        <h1 className="page-title">Mon programme</h1>
        <section className="card">
          <p className="subtle" style={{ marginBottom: 14 }}>Aucun programme actif pour le moment.</p>
          {error && (
            <p className="subtle" style={{ color: 'var(--danger)', marginBottom: 12 }}>
              {error}
            </p>
          )}
          <button className="btn btn--primary" disabled={generating} onClick={handleGenerer}>
            {generating ? 'Génération en cours…' : 'Générer mon programme'}
          </button>
        </section>
      </div>
    );
  }

  const semaine = semaineActuelle(programme);
  const jours = Object.entries(programme.gabarit_hebdomadaire);
  const phaseActive = programme.phases.find(
    (phase) => semaine >= phase.semaine_debut && semaine <= phase.semaine_fin
  );
  const debut = new Date(programme.date_debut);
  const fin = new Date(debut.getTime() + programme.duree_semaines * 7 * 24 * 60 * 60 * 1000);
  const formatDate = (d: Date) => d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' });

  return (
    <div className="screen">
      <Header title="Mon programme" />

      <section className="programme-hero">
        <div className="programme-hero__eyebrow">Programme en cours</div>
        <div className="programme-hero__figure">
          <span className="programme-hero__num">{semaine}</span>
          <span className="programme-hero__total">/ {programme.duree_semaines}</span>
        </div>
        <div className="programme-hero__dates">
          {formatDate(debut)} — {formatDate(fin)}
        </div>

        <div className="programme-weeks">
          {Array.from({ length: programme.duree_semaines }).map((_, i) => {
            const num = i + 1;
            const statut = statutSemaine(num, semaine);
            return (
              <div key={num} className={`programme-week programme-week--${statut}`} title={`Semaine ${num}`}>
                <span className="programme-week__bar" />
                <span className="programme-week__num">{num}</span>
              </div>
            );
          })}
        </div>
      </section>

      {phaseActive && (
        <section className="card">
          <div className="card__eyebrow">Phase actuelle</div>
          <div className="programme-phase__nom" style={{ color: 'var(--text)', fontSize: 20 }}>
            {phaseActive.nom}
          </div>
          <p className="subtle" style={{ marginTop: 6 }}>{phaseActive.description}</p>
        </section>
      )}

      <section className="card">
        <div className="card__eyebrow">Toutes les phases</div>
        {programme.phases.map((phase) => {
          const active = phase === phaseActive;
          return (
            <div key={phase.nom} className={`programme-phase ${active ? 'programme-phase--active' : ''}`}>
              <div className="programme-phase__head">
                <span className="programme-phase__nom">{phase.nom}</span>
                <span className="subtle">
                  S{phase.semaine_debut}–{phase.semaine_fin}
                </span>
              </div>
            </div>
          );
        })}
      </section>

      <section className="card">
        <div className="card__eyebrow">Ma semaine</div>
        {contexte && contexte.semaine.length > 0
          ? contexte.semaine.map((jour) => {
              const meta = jour.type_seance_prevu ? typeSeanceMeta(jour.type_seance_prevu) : null;
              return (
                <div
                  key={jour.date}
                  className={`programme-jour${jour.est_aujourdhui ? ' programme-jour--aujourdhui' : ''}${
                    jour.est_passe ? ' programme-jour--passe' : ''
                  }`}
                >
                  <span className="programme-jour__label">{jour.jour_label}</span>
                  <span
                    className="programme-jour__type"
                    style={meta ? { color: meta.color } : undefined}
                  >
                    {meta ? meta.label : (LIBELLE_STATUT_JOUR[jour.statut] ?? '—')}
                  </span>
                </div>
              );
            })
          : // Contexte indisponible (réseau) : on affiche le gabarit brut plutôt que rien, en
            // précisant que les contraintes du calendrier n'y sont pas reflétées.
            jours.map(([jour, type]) => {
              const meta = typeSeanceMeta(type);
              return (
                <div key={jour} className="programme-jour">
                  <span className="programme-jour__label">{jour}</span>
                  <span className="programme-jour__type" style={{ color: meta.color }}>
                    {meta.label}
                  </span>
                </div>
              );
            })}
      </section>
    </div>
  );
}
