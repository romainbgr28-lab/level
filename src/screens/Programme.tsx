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
        <div className="card__eyebrow">Gabarit hebdomadaire</div>
        {jours.map(([jour, type]) => {
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
