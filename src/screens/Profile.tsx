import { useEffect, useState } from 'react';
import Header from '../components/Header';
import { deleteProfil, getProfil, getStats } from '../api/client';
import type { ApiProfil, ApiStats } from '../api/client';

export default function Profile() {
  const [profil, setProfil] = useState<ApiProfil | null>(null);
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    Promise.all([getProfil(), getStats()])
      .then(([p, s]) => {
        setProfil(p);
        setStats(s);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleReset() {
    if (!window.confirm('Supprimer le profil et relancer l’onboarding ?')) return;
    setResetting(true);
    try {
      await deleteProfil();
      window.location.reload();
    } catch {
      setResetting(false);
    }
  }

  if (loading) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  if (!profil) {
    return (
      <div className="screen">
        <Header title="Profil" />
        <p className="subtle">Aucun profil enregistré.</p>
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Profil" />
      <h1 className="page-title">Profil</h1>

      <div className="section-title">Objectifs</div>
      <div className="tag-row">
        {profil.objectifs.map((g) => (
          <span className="tag" key={g}>
            {g}
          </span>
        ))}
      </div>

      <div className="section-title">Niveaux actuels</div>
      <div className="info-row">
        <span className="info-row__label">Physique</span>
        <span className="info-row__value">{profil.niveau_physique}</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Intellectuel</span>
        <span className="info-row__value">{profil.niveau_intellectuel}</span>
      </div>

      <div className="section-title">Contraintes & matériel</div>
      <div className="info-row">
        <span className="info-row__label">Temps disponible</span>
        <span className="info-row__value">{profil.contraintes_temps}</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Matériel</span>
        <span className="info-row__value">{profil.materiel}</span>
      </div>

      <button className="btn btn--ghost" style={{ margin: '20px 0' }}>
        Modifier mes objectifs
      </button>

      {stats && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.total_seances}</div>
            <div className="stat-tile__label">Séances</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.total_modules}</div>
            <div className="stat-tile__label">Modules</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile__value">{stats.record_streak}</div>
            <div className="stat-tile__label">Record streak</div>
          </div>
        </div>
      )}

      <div className="section-title">Développement</div>
      <p className="subtle" style={{ marginBottom: 10 }}>
        Bouton temporaire, le temps qu'un vrai flux d'édition de profil existe.
      </p>
      <button
        className="btn btn--ghost"
        style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
        disabled={resetting}
        onClick={handleReset}
      >
        {resetting ? 'Suppression…' : 'Réinitialiser le profil (relance l’onboarding)'}
      </button>
    </div>
  );
}
