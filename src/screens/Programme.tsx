import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { genererProgramme, getProgrammeActif } from '../api/client';
import type { ApiProgramme } from '../api/client';
import { typeSeanceMeta } from '../data/programmeTypes';

function semaineActuelle(programme: ApiProgramme): number {
  const debut = new Date(programme.date_debut);
  const jours = Math.floor((Date.now() - debut.getTime()) / (1000 * 60 * 60 * 24));
  const semaine = Math.floor(jours / 7) + 1;
  return Math.min(Math.max(semaine, 1), programme.duree_semaines);
}

function statutSemaine(num: number, semaineActuelleNum: number): 'passee' | 'actuelle' | 'a-venir' {
  if (num < semaineActuelleNum) return 'passee';
  if (num === semaineActuelleNum) return 'actuelle';
  return 'a-venir';
}

export default function Programme() {
  const [programme, setProgramme] = useState<ApiProgramme | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProgrammeActif()
      .then(setProgramme)
      .finally(() => setLoading(false));
  }, []);

  async function handleGenerer() {
    setGenerating(true);
    setError(null);
    try {
      const prog = await genererProgramme();
      setProgramme(prog);
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

  return (
    <div className="screen">
      <Header title="Mon programme" />
      <h1 className="page-title">Mon programme</h1>

      <section className="card">
        <div className="card__eyebrow">Frise des 8 semaines</div>
        <div className="programme-weeks">
          {Array.from({ length: programme.duree_semaines }).map((_, i) => {
            const num = i + 1;
            const statut = statutSemaine(num, semaine);
            return (
              <div key={num} className={`programme-week programme-week--${statut}`} title={`Semaine ${num}`}>
                {num}
              </div>
            );
          })}
        </div>
        <div className="programme-weeks-legend">
          <span><i className="programme-weeks-legend__dot programme-weeks-legend__dot--passee" />Passée</span>
          <span><i className="programme-weeks-legend__dot programme-weeks-legend__dot--actuelle" />Actuelle</span>
          <span><i className="programme-weeks-legend__dot programme-weeks-legend__dot--a-venir" />À venir</span>
        </div>
      </section>

      <section className="card">
        <div className="card__eyebrow">Phases du programme</div>
        {programme.phases.map((phase) => {
          const active = semaine >= phase.semaine_debut && semaine <= phase.semaine_fin;
          return (
            <div key={phase.nom} className={`programme-phase ${active ? 'programme-phase--active' : ''}`}>
              <div className="programme-phase__head">
                <span className="programme-phase__nom">{phase.nom}</span>
                <span className="subtle">
                  Semaines {phase.semaine_debut}–{phase.semaine_fin}
                </span>
              </div>
              <p className="subtle" style={{ margin: '4px 0 0' }}>{phase.description}</p>
            </div>
          );
        })}
      </section>

      <section className="card">
        <div className="card__eyebrow">Gabarit hebdomadaire</div>
        <div className="choice-list">
          {jours.map(([jour, type]) => {
            const meta = typeSeanceMeta(type);
            return (
              <div key={jour} className="choice-item programme-jour" style={{ justifyContent: 'space-between' }}>
                <span>{jour}</span>
                <span className="programme-jour__type" style={{ color: meta.color }}>
                  <span aria-hidden="true">{meta.icon}</span> {meta.label}
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
