import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { getBilanHebdomadaire, messageErreur } from '../api/client';
import { EtatChargement, EtatErreur, EtatVide } from '../components/EtatEcran';
import type { ApiBilan } from '../api/client';

function formatJour(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

function formatVolume(kg: number): string {
  if (kg >= 1000) return `${(kg / 1000).toFixed(1).replace('.', ',')} t`;
  return `${Math.round(kg)} kg`;
}

function Variation({ pct }: { pct: number | null }) {
  if (pct === null) return null;
  const signe = pct > 0 ? '+' : '';
  return (
    <span className="subtle">
      {' '}
      ({signe}
      {Math.round(pct)} % vs semaine précédente)
    </span>
  );
}

export default function WeeklyReview() {
  const navigate = useNavigate();
  const [bilan, setBilan] = useState<ApiBilan | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const charger = useCallback(() => {
    setLoading(true);
    setErreur(null);
    getBilanHebdomadaire()
      .then(setBilan)
      .catch((e) => setErreur(messageErreur(e, "Ton bilan n'a pas pu être calculé.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(charger, [charger]);

  return (
    <div className="screen">
      <Header title="Bilan hebdomadaire" />
      <button className="back-btn" onClick={() => navigate('/progression')}>
        ← Progression
      </button>

      {loading && <EtatChargement message="Calcul de ton bilan…" />}

      {!loading && erreur && (
        <EtatErreur
          titre="Bilan indisponible"
          message={erreur}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Retour à la progression', onClick: () => navigate('/progression') }}
        />
      )}

      {!loading && !erreur && bilan && (
        <>
          <h1 className="page-title">
            {formatJour(bilan.periode_debut)} — {formatJour(bilan.periode_fin)}
          </h1>

          {bilan.seances_realisees === 0 ? (
            // Aucune séance terminée : on le dit franchement, et on donne la sortie.
            <EtatVide
              titre="Pas encore de bilan"
              message={`Aucune séance terminée sur les ${bilan.jours_fenetre} derniers jours. Ton bilan compare volume, charges et RPE d'une semaine à l'autre : il s'alimente dès ta première séance validée.`}
              action={{ label: 'Voir ma séance du jour', onClick: () => navigate('/') }}
            />
          ) : (
            <>
              <div className="stat-grid">
                <div className="stat-tile">
                  <div className="stat-tile__value">{bilan.seances_realisees}</div>
                  <div className="stat-tile__label">Séances réalisées</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-tile__value">{formatVolume(bilan.volume_kg)}</div>
                  <div className="stat-tile__label">Volume soulevé</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-tile__value">
                    {bilan.jours_actifs}/{bilan.jours_fenetre}
                  </div>
                  <div className="stat-tile__label">Jours actifs</div>
                </div>
                {bilan.rpe_moyen !== null && (
                  <div className="stat-tile">
                    <div className="stat-tile__value">{bilan.rpe_moyen}</div>
                    <div className="stat-tile__label">RPE moyen</div>
                  </div>
                )}
              </div>

              <section className="card card--coach">
                <div className="card__eyebrow">Ce que montre la semaine</div>
                <ul className="bilan-points">
                  {bilan.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>

              {bilan.progressions.length > 0 && (
                <section className="card">
                  <div className="card__eyebrow">Charges en progression</div>
                  {bilan.progressions.map((p) => (
                    <p key={p.exercice} className="bilan-ligne">
                      <strong>{p.exercice}</strong>
                      <span className="subtle">
                        {Math.round(p.charge_precedente_kg)} → {Math.round(p.charge_kg)} kg (+
                        {Math.round(p.variation_pct)} %)
                      </span>
                    </p>
                  ))}
                </section>
              )}

              {bilan.stagnations.length > 0 && (
                <section className="card">
                  <div className="card__eyebrow">À débloquer</div>
                  {bilan.stagnations.map((s) => (
                    <p key={s.exercice} className="bilan-ligne">
                      <strong>{s.exercice}</strong>
                      <span className="subtle">
                        charge inchangée à {Math.round(s.charge_kg)} kg
                      </span>
                    </p>
                  ))}
                </section>
              )}

              {bilan.volume_kg_precedent > 0 && (
                <p className="subtle" style={{ marginBottom: 12 }}>
                  Volume : {formatVolume(bilan.volume_kg)}
                  <Variation pct={bilan.volume_variation_pct} />
                </p>
              )}

              {bilan.prochaine_adaptation && (
                <section className="card">
                  <div className="card__eyebrow">Ce que LEVEL adapte ensuite</div>
                  <p style={{ fontSize: 15 }}>{bilan.prochaine_adaptation}</p>
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
