import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { getHistoriqueSeances, messageErreur } from '../api/client';
import { EtatChargement, EtatErreur, EtatVide } from '../components/EtatEcran';
import type { ApiEtatDeclareAvant, ApiExerciceRealise, ApiHistoriqueSeance } from '../api/client';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
}

function realiseParExerciceId(entry: ApiHistoriqueSeance): Map<number, ApiExerciceRealise> {
  return new Map(entry.exercices_realises.map((ex) => [ex.exercice_id, ex]));
}

function formatPct(pct: unknown): string | null {
  if (typeof pct !== 'number' || pct === 0) return pct === 0 ? 'stable' : null;
  return `${pct > 0 ? '+' : ''}${Math.round(pct)}%`;
}

function DecisionAdaptation({ decision }: { decision: Record<string, unknown> }) {
  const chargePct = formatPct(decision.ajustement_charge_pct);
  const volumePct = formatPct(decision.ajustement_volume_pct);
  const intensiteMax = typeof decision.intensite_max === 'string' ? decision.intensite_max : null;
  const raisons = (Array.isArray(decision.raisons) ? (decision.raisons as unknown[]) : []).filter(
    (r): r is string => typeof r === 'string'
  );
  const correctionAppliquee = decision.correction_charge_appliquee === true;

  return (
    <div className="subtle historique-entry__adaptation">
      <strong>Pourquoi cette séance ?</strong>
      <ul>
        {chargePct && <li>Charge : {chargePct}</li>}
        {volumePct && <li>Volume : {volumePct}</li>}
        {intensiteMax && <li>Intensité max : {intensiteMax}</li>}
        {raisons.map((raison, i) => (
          <li key={i}>{raison}</li>
        ))}
        {correctionAppliquee && <li>Une correction automatique de charge a été appliquée.</li>}
      </ul>
    </div>
  );
}

const LIBELLES_ETAT_DECLARE: Record<keyof ApiEtatDeclareAvant, string> = {
  sommeil: 'Sommeil',
  motivation: 'Motivation',
  temps_dispo: 'Temps dispo',
  envie_texte: 'Envie',
  entrainement_club_semaine: 'Club cette semaine',
};

function EtatDeclare({ etat }: { etat: ApiEtatDeclareAvant }) {
  const champs = (Object.keys(LIBELLES_ETAT_DECLARE) as (keyof ApiEtatDeclareAvant)[])
    .map((cle) => ({ cle, valeur: etat[cle] }))
    .filter((c) => c.valeur != null && c.valeur !== '');

  if (champs.length === 0) return null;

  return (
    <div className="subtle historique-entry__etat">
      <strong>État déclaré avant séance</strong>
      <ul>
        {champs.map(({ cle, valeur }) => (
          <li key={cle}>
            {LIBELLES_ETAT_DECLARE[cle]} : {valeur}
          </li>
        ))}
      </ul>
    </div>
  );
}

function resumeSeries(series: ApiExerciceRealise['series']): string {
  return series
    .map((s) => {
      const poids = s.poids_kg != null ? `${s.poids_kg}kg` : '—';
      const reps = s.repetitions != null ? `${s.repetitions}` : '—';
      return `${poids}×${reps}`;
    })
    .join(', ');
}

function SeanceCard({ entry }: { entry: ApiHistoriqueSeance }) {
  const realiseParId = realiseParExerciceId(entry);
  const aDesPrevus = entry.exercices_prevus.length > 0;

  return (
    <section className="card historique-entry">
      <div className="historique-entry__head">
        <div>
          <div className="historique-entry__date">{formatDate(entry.date)}</div>
          <div className="subtle">{entry.type_seance}</div>
        </div>
        <div className="historique-entry__badges">
          {entry.pourcentage_complete != null && (
            <span className="tag">{Math.round(entry.pourcentage_complete)}% complété</span>
          )}
          {entry.rpe != null && <span className="tag">RPE {entry.rpe}</span>}
        </div>
      </div>

      {entry.etat_declare_avant && <EtatDeclare etat={entry.etat_declare_avant} />}

      {entry.decision_adaptation && <DecisionAdaptation decision={entry.decision_adaptation} />}

      {aDesPrevus ? (
        <ul className="historique-entry__exercices">
          {entry.exercices_prevus.map((prevu, i) => {
            const realise = realiseParId.get(prevu.exercice_id);
            return (
              <li key={`${prevu.exercice_id}-${i}`} className="historique-exercice">
                <div className="historique-exercice__nom">{prevu.nom ?? `Exercice #${prevu.exercice_id}`}</div>
                <div className="subtle">
                  Prévu : {prevu.series ?? '?'} séries × {prevu.repetitions ?? '?'}
                  {prevu.charge_indicative ? ` (${prevu.charge_indicative})` : ''}
                </div>
                {realise ? (
                  <div className="subtle historique-exercice__realise">
                    Réalisé : {resumeSeries(realise.series)}
                  </div>
                ) : (
                  <div className="subtle historique-exercice__realise">Non réalisé</div>
                )}
              </li>
            );
          })}
        </ul>
      ) : entry.exercices_realises.length > 0 ? (
        // Anciennes entrées sans exercices_prevus détaillés : on n'a que le réalisé.
        <ul className="historique-entry__exercices">
          {entry.exercices_realises.map((ex, i) => (
            <li key={`${ex.exercice_id}-${i}`} className="historique-exercice">
              <div className="historique-exercice__nom">{ex.nom ?? `Exercice #${ex.exercice_id}`}</div>
              <div className="subtle historique-exercice__realise">Réalisé : {resumeSeries(ex.series)}</div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="subtle">Détail des exercices indisponible pour cette séance.</p>
      )}

      {entry.notes && <p className="subtle historique-entry__notes">« {entry.notes} »</p>}
    </section>
  );
}

export default function Historique() {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<ApiHistoriqueSeance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const charger = useCallback(() => {
    setLoading(true);
    setError(null);
    getHistoriqueSeances()
      .then(setEntries)
      .catch((e) => setError(messageErreur(e, "Ton historique n'a pas pu être chargé.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(charger, [charger]);

  return (
    <div className="screen">
      <Header title="Historique" />
      <button className="back-btn" onClick={() => navigate('/progression')}>
        ← Progression
      </button>
      <h1 className="page-title">Historique des séances</h1>

      {loading && <EtatChargement message="Chargement de tes séances…" />}

      {!loading && error && (
        <EtatErreur
          titre="Historique indisponible"
          message={`${error} Tes séances terminées ne sont pas perdues.`}
          action={{ label: 'Réessayer', onClick: charger }}
          actionSecondaire={{ label: 'Voir ma journée', onClick: () => navigate('/') }}
        />
      )}

      {!loading && !error && entries.length === 0 && (
        // « Pourquoi est-ce vide ? » : parce qu'aucune séance n'a encore été terminée — et on
        // dit comment y remédier plutôt que d'afficher « Aucun historique ».
        <EtatVide
          titre="Rien à afficher pour l’instant"
          message="Tes séances terminées apparaîtront ici : ce que tu avais prévu, ce que tu as réellement fait, et pourquoi LEVEL avait adapté la séance."
          action={{ label: 'Voir ma séance du jour', onClick: () => navigate('/') }}
        />
      )}

      {!loading && !error && entries.map((entry) => <SeanceCard key={entry.id} entry={entry} />)}
    </div>
  );
}
