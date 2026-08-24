import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import {
  createSerieLoggee,
  deleteTodaySeance,
  genererSeance,
  getDernierePerformance,
  getExercicesBibliotheque,
  getSeriesLoggees,
  getTodayModule,
  getTodaySeance,
  terminerSeanceIA,
  updateSerieLoggee,
} from '../api/client';
import type {
  ApiDernierePerformance,
  ApiDifficulte,
  ApiEtatDuJour,
  ApiExerciceBibliotheque,
  ApiModule,
  ApiSeance,
  ApiSeanceExercice,
  ApiSeanceGeneree,
  ApiSerieLoggee,
  ApiTerminerSeanceResult,
} from '../api/client';

const dateLabel = new Date().toLocaleDateString('fr-FR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

const SOMMEIL_OPTIONS = ['Mauvais', 'Moyen', 'Bon', 'Excellent'];
const MOTIVATION_OPTIONS = ['Faible', 'Correcte', 'Élevée'];
const CLUB_SEMAINE_OPTIONS: { value: string; label: string }[] = [
  { value: 'non', label: 'Non' },
  { value: '1_fois', label: 'Oui, 1 fois' },
  { value: '2_fois_ou_plus', label: 'Oui, 2 fois ou plus' },
];
const TYPE_SEANCE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Automatique (recommandé)' },
  { value: 'force', label: 'Force' },
  { value: 'explosivité_vitesse', label: 'Explosivité / vitesse' },
  { value: 'esthétique', label: 'Esthétique' },
  { value: 'décharge', label: 'Décharge / récupération' },
];

const REST_SECONDS = 90;

const DIFFICULTE_OPTIONS: { value: ApiDifficulte; label: string }[] = [
  { value: 'facile', label: 'Facile' },
  { value: 'comme_prevu', label: 'Comme prévu' },
  { value: 'dur', label: 'Dur' },
];

type View = 'loading' | 'no-seance' | 'form' | 'seance' | 'fin-seance' | 'terminee';

function formatDuree(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// Cible de répétitions ("10-12" -> 10) et de charge ("20 kg" -> 20, "poids du corps" -> null)
// pré-remplies pour valider une série en 1 tap sans que l'utilisateur ait à taper quoi que ce soit.
function repsCible(repetitions: string): number | null {
  const m = repetitions.match(/\d+/);
  return m ? Number(m[0]) : null;
}

function chargeCible(chargeIndicative?: string | null): number | null {
  if (!chargeIndicative || /corps/i.test(chargeIndicative)) return null;
  const m = chargeIndicative.match(/\d+([.,]\d+)?/);
  return m ? Number(m[0].replace(',', '.')) : null;
}

export default function Today() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>('loading');
  const [learningModule, setLearningModule] = useState<ApiModule | null>(null);

  const [seance, setSeance] = useState<ApiSeance | ApiSeanceGeneree | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [sommeil, setSommeil] = useState('');
  const [motivation, setMotivation] = useState('');
  const [tempsDispo, setTempsDispo] = useState('');
  const [envieTexte, setEnvieTexte] = useState('');
  const [clubSemaine, setClubSemaine] = useState('');
  const [typeSeanceForce, setTypeSeanceForce] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // ---- Logging temps réel façon Hevy ----
  const [bibliotheque, setBibliotheque] = useState<Record<number, ApiExerciceBibliotheque>>({});
  const [seriesParExercice, setSeriesParExercice] = useState<Record<number, ApiSerieLoggee[]>>({});
  const [draftParExercice, setDraftParExercice] = useState<
    Record<number, { poids: string; reps: string }>
  >({});
  const [precedentParExercice, setPrecedentParExercice] = useState<Record<number, ApiDernierePerformance>>({});
  const [detailExerciceId, setDetailExerciceId] = useState<number | null>(null);
  const [sessionStart, setSessionStart] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [restSecondsLeft, setRestSecondsLeft] = useState<number | null>(null);
  const [editingSerieId, setEditingSerieId] = useState<number | null>(null);
  const [editDraftParSerie, setEditDraftParSerie] = useState<Record<number, { poids: string; reps: string }>>({});
  const [manualOpenId, setManualOpenId] = useState<number | 'auto'>('auto');

  const [rpe, setRpe] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [resultat, setResultat] = useState<ApiTerminerSeanceResult | null>(null);

  useEffect(() => {
    Promise.all([getTodaySeance(), getTodayModule()]).then(([s, m]) => {
      setLearningModule(m);
      if (s) {
        setSeance(s);
        setView(s.statut === 'terminee' ? 'terminee' : 'seance');
      } else {
        setView('no-seance');
      }
    });
  }, []);

  // Charge la bibliothèque + les séries déjà loguées quand on entre dans la séance.
  useEffect(() => {
    if (view !== 'seance' || !seance) return;
    getExercicesBibliotheque().then((list) => {
      const map: Record<number, ApiExerciceBibliotheque> = {};
      for (const ex of list) map[ex.id] = ex;
      setBibliotheque(map);
    });
    getSeriesLoggees(seance.id).then((rows) => {
      const grouped: Record<number, ApiSerieLoggee[]> = {};
      for (const row of rows) {
        (grouped[row.exercice_id] ??= []).push(row);
      }
      setSeriesParExercice(grouped);
    });
    for (const item of seance.exercices) {
      getDernierePerformance(item.exercice_id, seance.id).then((perf) => {
        setPrecedentParExercice((prev) => ({ ...prev, [item.exercice_id]: perf }));
      });
    }
    setSessionStart((prev) => prev ?? Date.now());
  }, [view, seance]);

  useEffect(() => {
    if (view !== 'seance' || sessionStart === null) return;
    const interval = setInterval(() => setElapsedSec(Math.floor((Date.now() - sessionStart) / 1000)), 1000);
    return () => clearInterval(interval);
  }, [view, sessionStart]);

  useEffect(() => {
    if (restSecondsLeft === null) return;
    if (restSecondsLeft <= 0) {
      setRestSecondsLeft(null);
      return;
    }
    const t = setTimeout(() => setRestSecondsLeft((s) => (s !== null ? s - 1 : null)), 1000);
    return () => clearTimeout(t);
  }, [restSecondsLeft]);

  const totaux = useMemo(() => {
    let volume = 0;
    let nbValidees = 0;
    for (const rows of Object.values(seriesParExercice)) {
      for (const r of rows) {
        if (r.coche) {
          volume += (r.poids_kg ?? 0) * (r.repetitions ?? 0);
          nbValidees += 1;
        }
      }
    }
    return { volume, nbValidees };
  }, [seriesParExercice]);

  function estExerciceComplet(item: ApiSeanceExercice): boolean {
    const series = seriesParExercice[item.exercice_id] ?? [];
    const cible = item.series ?? series.length;
    return cible > 0 && series.length >= cible;
  }

  const currentExerciceId = useMemo(() => {
    if (!seance) return null;
    const premierIncomplet = seance.exercices.find((it) => !estExerciceComplet(it));
    return premierIncomplet
      ? premierIncomplet.exercice_id
      : (seance.exercices[seance.exercices.length - 1]?.exercice_id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seance, seriesParExercice]);

  const openExerciceId = manualOpenId === 'auto' ? currentExerciceId : manualOpenId;

  function draftFor(exerciceId: number) {
    return draftParExercice[exerciceId] ?? { poids: '', reps: '' };
  }

  function setDraft(exerciceId: number, patch: Partial<{ poids: string; reps: string }>) {
    setDraftParExercice((prev) => ({ ...prev, [exerciceId]: { ...draftFor(exerciceId), ...patch } }));
  }

  function reposPourExercice(item: ApiSeanceExercice): number {
    return item.temps_repos_recommande_s ?? REST_SECONDS;
  }

  async function handleValiderSerie(item: ApiSeanceExercice) {
    if (!seance) return;
    const exerciceId = item.exercice_id;
    const draft = draftFor(exerciceId);
    const poids = draft.poids.trim() ? Number(draft.poids) : null;
    const reps = draft.reps.trim() ? Number(draft.reps) : null;
    const numero = (seriesParExercice[exerciceId]?.length ?? 0) + 1;

    const created = await createSerieLoggee({
      seance_id: seance.id,
      exercice_id: exerciceId,
      numero_serie: numero,
      poids_kg: poids,
      repetitions: reps,
      coche: true,
    });

    setSeriesParExercice((prev) => ({ ...prev, [exerciceId]: [...(prev[exerciceId] ?? []), created] }));
    setDraft(exerciceId, { poids: '', reps: '' });
    setRestSecondsLeft(reposPourExercice(item));
  }

  // Validation rapide en 1 tap : facile / comme prévu / dur — poids et répétitions sont
  // pré-remplis depuis la cible calculée par la génération, aucune saisie nécessaire.
  async function handleValiderRapide(item: ApiSeanceExercice, difficulte: ApiDifficulte) {
    if (!seance) return;
    const exerciceId = item.exercice_id;
    const numero = (seriesParExercice[exerciceId]?.length ?? 0) + 1;

    const created = await createSerieLoggee({
      seance_id: seance.id,
      exercice_id: exerciceId,
      numero_serie: numero,
      poids_kg: chargeCible(item.charge_indicative),
      repetitions: repsCible(item.repetitions),
      coche: true,
      difficulte,
    });

    setSeriesParExercice((prev) => ({ ...prev, [exerciceId]: [...(prev[exerciceId] ?? []), created] }));
    setRestSecondsLeft(reposPourExercice(item));
  }

  function editDraftFor(serie: ApiSerieLoggee) {
    return editDraftParSerie[serie.id] ?? { poids: serie.poids_kg?.toString() ?? '', reps: serie.repetitions?.toString() ?? '' };
  }

  function ouvrirEditionSerie(serie: ApiSerieLoggee) {
    setEditingSerieId(serie.id);
    setEditDraftParSerie((prev) => ({ ...prev, [serie.id]: editDraftFor(serie) }));
  }

  async function handleEnregistrerEditionSerie(exerciceId: number, serie: ApiSerieLoggee) {
    const draft = editDraftFor(serie);
    const updated = await updateSerieLoggee(serie.id, {
      poids_kg: draft.poids.trim() ? Number(draft.poids) : null,
      repetitions: draft.reps.trim() ? Number(draft.reps) : null,
    });
    setSeriesParExercice((prev) => ({
      ...prev,
      [exerciceId]: (prev[exerciceId] ?? []).map((s) => (s.id === updated.id ? updated : s)),
    }));
    setEditingSerieId(null);
  }

  async function handleToggleSerie(exerciceId: number, serie: ApiSerieLoggee) {
    const updated = await updateSerieLoggee(serie.id, { coche: !serie.coche });
    setSeriesParExercice((prev) => ({
      ...prev,
      [exerciceId]: (prev[exerciceId] ?? []).map((s) => (s.id === updated.id ? updated : s)),
    }));
  }

  function handleAjouterSerie(exerciceId: number) {
    // Une série "brouillon" locale : elle n'est persistée qu'au moment où elle est validée.
    setDraftParExercice((prev) => ({ ...prev, [exerciceId]: { poids: '', reps: '' } }));
  }

  async function handleGenerer() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: ApiEtatDuJour = {
        sommeil: sommeil || null,
        motivation: motivation || null,
        temps_dispo: tempsDispo.trim() || null,
        envie_texte: envieTexte.trim() || null,
        entrainement_club_semaine: clubSemaine || null,
        type_seance_force: typeSeanceForce || null,
      };
      const generee = await genererSeance(payload);
      setSeance(generee);
      setView('seance');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur lors de la génération de la séance.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTerminer() {
    if (!seance) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await terminerSeanceIA({
        seance_id: seance.id,
        rpe,
        note: note.trim() || null,
        duree_reelle_min: Math.round(elapsedSec / 60),
      });
      setResultat(res);
      setView('terminee');
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement de la séance.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReset() {
    if (!window.confirm('Supprimer la séance du jour et en générer une nouvelle ?')) return;
    setSubmitting(true);
    setError(null);
    try {
      await deleteTodaySeance();
      setSeance(null);
      setView('no-seance');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur lors de la réinitialisation.');
    } finally {
      setSubmitting(false);
    }
  }

  if (view === 'loading') {
    return (
      <div className="screen">
        <Header title="Aujourd’hui" />
        <p className="subtle">Chargement…</p>
      </div>
    );
  }

  const detailExercice = detailExerciceId !== null ? bibliotheque[detailExerciceId] : null;

  return (
    <div className="screen">
      <Header title="Aujourd’hui" />
      <h1 className="page-title" style={{ textTransform: 'capitalize' }}>
        {dateLabel}
      </h1>

      {view === 'no-seance' && (
        <section className="card">
          <div className="card__eyebrow">Séance du jour</div>
          <p className="subtle" style={{ margin: '4px 0 14px' }}>
            Aucune séance générée pour aujourd’hui.
          </p>
          <button className="btn btn--primary" onClick={() => setView('form')}>
            Générer ma séance du jour
          </button>
        </section>
      )}

      {view === 'form' && (
        <section className="card">
          <div className="card__eyebrow">État du jour</div>

          <div className="onboarding-theme">
            <div className="section-title">Sommeil de la nuit dernière</div>
            <div className="tag-row tag-row--select">
              {SOMMEIL_OPTIONS.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`tag tag--selectable ${sommeil === o ? 'tag--active' : ''}`}
                  onClick={() => setSommeil(o)}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Motivation du jour</div>
            <div className="tag-row tag-row--select">
              {MOTIVATION_OPTIONS.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`tag tag--selectable ${motivation === o ? 'tag--active' : ''}`}
                  onClick={() => setMotivation(o)}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">As-tu eu un entraînement club cette semaine ?</div>
            <div className="tag-row tag-row--select">
              {CLUB_SEMAINE_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`tag tag--selectable ${clubSemaine === o.value ? 'tag--active' : ''}`}
                  onClick={() => setClubSemaine(o.value)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Temps disponible aujourd’hui</div>
            <input
              type="text"
              className="textarea"
              style={{ minHeight: 'unset', padding: 12 }}
              placeholder="Ex : 45 min"
              value={tempsDispo}
              onChange={(e) => setTempsDispo(e.target.value)}
            />
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Type de séance souhaité (optionnel)</div>
            <p className="subtle" style={{ margin: '0 0 8px' }}>
              Par défaut, le type est déterminé automatiquement selon ton calendrier de matchs et ton
              profil. Tu peux forcer un type précis si tu sais ce que tu veux travailler aujourd’hui.
            </p>
            <div className="tag-row tag-row--select">
              {TYPE_SEANCE_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`tag tag--selectable ${typeSeanceForce === o.value ? 'tag--active' : ''}`}
                  onClick={() => setTypeSeanceForce(o.value)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div className="onboarding-theme">
            <div className="section-title">Envie du moment (optionnel)</div>
            <textarea
              className="textarea"
              placeholder="Ex : j’ai envie de pousser fort aujourd’hui…"
              value={envieTexte}
              onChange={(e) => setEnvieTexte(e.target.value)}
            />
          </div>

          {error && (
            <p className="subtle" style={{ color: '#e5484d', margin: '4px 0 12px' }}>
              {error}
            </p>
          )}

          <button className="btn btn--primary" disabled={submitting} onClick={handleGenerer}>
            {submitting ? 'Génération en cours…' : 'Générer ma séance du jour'}
          </button>
        </section>
      )}

      {view === 'seance' && seance && (
        <>
          <div className="workout-totals">
            <div className="stat-tile">
              <div className="stat-tile__value">{formatDuree(elapsedSec)}</div>
              <div className="stat-tile__label">Durée</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile__value">{Math.round(totaux.volume)}</div>
              <div className="stat-tile__label">Volume (kg)</div>
            </div>
            <div className="stat-tile">
              <div className="stat-tile__value">{totaux.nbValidees}</div>
              <div className="stat-tile__label">Séries validées</div>
            </div>
          </div>

          {restSecondsLeft !== null && (
            <div className="rest-timer">
              <span>Temps de repos</span>
              <span>{formatDuree(restSecondsLeft)}</span>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setRestSecondsLeft((s) => (s ?? 0) + 30)}>
                +30s
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setRestSecondsLeft(null)}>
                Passer
              </button>
            </div>
          )}

          {(('duree_prevue' in seance ? seance.duree_prevue : seance.duree_min) ?? null) !== null && (
            <p className="subtle" style={{ margin: '0 0 12px' }}>
              Durée prévue : environ {'duree_prevue' in seance ? seance.duree_prevue : seance.duree_min} min
            </p>
          )}

          <h2 className="card__title" style={{ marginBottom: 12 }}>
            {'nom' in seance ? seance.nom : seance.nom_seance}
          </h2>

          {seance.exercices.map((item) => {
            const ex = bibliotheque[item.exercice_id];
            const series = seriesParExercice[item.exercice_id] ?? [];
            const precedent = precedentParExercice[item.exercice_id];
            const draft = draftFor(item.exercice_id);
            const draftVisible = item.exercice_id in draftParExercice;
            const cible = item.series ?? series.length;
            const prochaineNumero = series.length + 1;
            const seanceTerminee = 'statut' in seance && seance.statut === 'terminee';
            const complet = estExerciceComplet(item);
            const isOpen = openExerciceId === item.exercice_id;
            const objectifLabel = `${item.series}x${item.repetitions}${
              item.charge_indicative ? ` · ${item.charge_indicative}` : ''
            }${item.rpe_cible ? ` · RPE ${item.rpe_cible}` : ''}`;

            return (
              <div
                className={`exercise-block ${isOpen ? 'exercise-block--active' : 'exercise-block--collapsed'} ${
                  complet ? 'exercise-block--done' : ''
                }`}
                key={item.exercice_id}
              >
                <button
                  type="button"
                  className="exercise-block__head"
                  onClick={() => setManualOpenId(isOpen ? -1 : item.exercice_id)}
                >
                  <span className="exercise-block__title-wrap">
                    <span
                      className="exercise-block__name"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailExerciceId(item.exercice_id);
                      }}
                    >
                      {ex?.nom ?? `Exercice #${item.exercice_id}`}
                    </span>
                    <span className="exercise-block__group">{ex?.groupe_musculaire}</span>
                  </span>
                  <span className={`exercise-block__status ${complet ? 'exercise-block__status--done' : ''}`}>
                    {complet ? '✓' : `${series.length}/${cible}`}
                  </span>
                </button>

                {isOpen && (
                  <>
                    <div className="exercise-block__previous">
                      {precedent && precedent.series.length > 0
                        ? `Précédent : ${precedent.series
                            .map((s) => `${s.poids_kg ?? '–'} kg x ${s.repetitions ?? '–'}`)
                            .join(', ')}`
                        : `Objectif : ${objectifLabel}`}
                    </div>

                    {series.map((s) => {
                      if (editingSerieId === s.id) {
                        return (
                          <div className="set-row" key={s.id}>
                            <span className="set-row__num">{s.numero_serie}</span>
                            <input
                              type="number"
                              inputMode="decimal"
                              className="set-row__input"
                              placeholder="kg"
                              value={editDraftFor(s).poids}
                              onChange={(e) =>
                                setEditDraftParSerie((prev) => ({
                                  ...prev,
                                  [s.id]: { ...editDraftFor(s), poids: e.target.value },
                                }))
                              }
                            />
                            <input
                              type="number"
                              inputMode="numeric"
                              className="set-row__input"
                              placeholder="reps"
                              value={editDraftFor(s).reps}
                              onChange={(e) =>
                                setEditDraftParSerie((prev) => ({
                                  ...prev,
                                  [s.id]: { ...editDraftFor(s), reps: e.target.value },
                                }))
                              }
                            />
                            <button
                              type="button"
                              className="checkbox"
                              onClick={() => handleEnregistrerEditionSerie(item.exercice_id, s)}
                              aria-label="Enregistrer"
                            >
                              ✓
                            </button>
                          </div>
                        );
                      }
                      return (
                        <div className="set-line set-line--done" key={s.id}>
                          <button
                            type="button"
                            className={`checkbox checkbox--sm ${s.coche ? 'checked' : ''}`}
                            onClick={() => handleToggleSerie(item.exercice_id, s)}
                            aria-label="Valider la série"
                          >
                            {s.coche ? '✓' : ''}
                          </button>
                          <span className="set-line__text">
                            {s.repetitions ?? '–'} reps · {s.poids_kg ?? '–'} kg
                            {s.difficulte && (
                              <> · {DIFFICULTE_OPTIONS.find((d) => d.value === s.difficulte)?.label}</>
                            )}
                          </span>
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label="Modifier la série"
                            onClick={() => ouvrirEditionSerie(s)}
                          >
                            ✎
                          </button>
                        </div>
                      );
                    })}

                    {!seanceTerminee && prochaineNumero <= cible && !draftVisible && (
                      <div className="set-card set-card--active">
                        <div className="set-card__head">
                          <span className="set-card__num">Série {prochaineNumero}</span>
                          <span className="set-card__target">
                            {repsCible(item.repetitions) ?? item.repetitions} reps
                            {item.charge_indicative ? ` · ${item.charge_indicative}` : ''}
                          </span>
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label="Saisir manuellement"
                            onClick={() => handleAjouterSerie(item.exercice_id)}
                          >
                            ✎
                          </button>
                        </div>
                        <div className="quick-row">
                          {DIFFICULTE_OPTIONS.map((o) => (
                            <button
                              key={o.value}
                              type="button"
                              className={`quick-btn quick-btn--${o.value}`}
                              onClick={() => handleValiderRapide(item, o.value)}
                            >
                              {o.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {draftVisible && (
                      <div className="set-row">
                        <span className="set-row__num">{series.length + 1}</span>
                        <input
                          type="number"
                          inputMode="decimal"
                          className="set-row__input"
                          placeholder="kg"
                          value={draft.poids}
                          onChange={(e) => setDraft(item.exercice_id, { poids: e.target.value })}
                        />
                        <input
                          type="number"
                          inputMode="numeric"
                          className="set-row__input"
                          placeholder="reps"
                          value={draft.reps}
                          onChange={(e) => setDraft(item.exercice_id, { reps: e.target.value })}
                        />
                        <button
                          type="button"
                          className="checkbox"
                          onClick={() => handleValiderSerie(item)}
                          aria-label="Valider la série"
                        >
                          ✓
                        </button>
                      </div>
                    )}

                    {Array.from({ length: Math.max(0, cible - prochaineNumero) }, (_, i) => (
                      <div className="set-line set-line--upcoming" key={`upcoming-${item.exercice_id}-${i}`}>
                        <span className="set-line__num">Série {prochaineNumero + i + 1}</span>
                        <span className="set-line__text">
                          {repsCible(item.repetitions) ?? item.repetitions} reps
                          {item.charge_indicative ? ` · ${item.charge_indicative}` : ''}
                        </span>
                      </div>
                    ))}

                    {!draftVisible && prochaineNumero > cible && !seanceTerminee && (
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        style={{ marginTop: 10 }}
                        onClick={() => handleAjouterSerie(item.exercice_id)}
                      >
                        + Ajouter une série
                      </button>
                    )}
                  </>
                )}
              </div>
            );
          })}

          {'explication' in seance && seance.explication && (
            <p className="subtle" style={{ marginTop: 4, marginBottom: 14, lineHeight: 1.55 }}>
              {seance.explication}
            </p>
          )}

          <button className="btn btn--primary" onClick={() => setView('fin-seance')}>
            Terminer la séance
          </button>
          <button className="btn btn--ghost" style={{ marginTop: 10 }} disabled={submitting} onClick={handleReset}>
            Réinitialiser (générer une nouvelle séance)
          </button>
          {error && (
            <p className="subtle" style={{ color: '#e5484d', marginTop: 10 }}>
              {error}
            </p>
          )}
        </>
      )}

      {view === 'fin-seance' && seance && (
        <section className="card">
          <div className="card__eyebrow">Fin de séance</div>
          <p className="subtle" style={{ margin: '4px 0 12px' }}>
            {totaux.nbValidees} séries validées · {Math.round(totaux.volume)} kg de volume total ·{' '}
            {formatDuree(elapsedSec)} écoulées
          </p>
          <div className="section-title">RPE (calculé automatiquement depuis tes validations rapides — ajuster si besoin)</div>
          <div className="rpe-grid">
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                className={`rpe-btn ${rpe === n ? 'selected' : ''}`}
                onClick={() => setRpe(n)}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="section-title">Ressenti général (optionnel)</div>
          <textarea
            className="textarea"
            placeholder="Un mot sur la séance…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          {error && (
            <p className="subtle" style={{ color: '#e5484d', margin: '4px 0 12px' }}>
              {error}
            </p>
          )}
          <button
            className="btn btn--primary"
            style={{ marginTop: 14 }}
            disabled={submitting}
            onClick={handleTerminer}
          >
            {submitting ? 'Enregistrement…' : 'Valider la fin de séance'}
          </button>
        </section>
      )}

      {view === 'terminee' && seance && (
        <section className="card">
          <div className="card__eyebrow">Séance du jour</div>
          <h2 className="card__title">{'nom' in seance ? seance.nom : seance.nom_seance}</h2>
          <p className="subtle" style={{ marginTop: 14 }}>
            Séance terminée{resultat ? ` · +${resultat.xp_gagne} XP` : ' pour aujourd’hui.'}
          </p>
          {resultat && (() => {
            const prevue = resultat.resume.duree_prevue_min as number | null | undefined;
            const reelle = resultat.resume.duree_reelle_min as number | null | undefined;
            if (prevue == null || reelle == null) return null;
            return (
              <p className="subtle" style={{ marginTop: 6 }}>
                Durée réelle : {reelle} min (prévue : {prevue} min)
              </p>
            );
          })()}
        </section>
      )}

      {learningModule && (
        <section className="card">
          <div className="card__eyebrow">Module du jour</div>
          <span className="tag">{learningModule.categorie}</span>
          <h2 className="card__title" style={{ marginTop: 10 }}>
            {learningModule.titre}
          </h2>
          <p className="subtle" style={{ margin: '6px 0 14px' }}>
            {learningModule.contenu.slice(0, 120)}…
          </p>
          <button className="btn btn--ghost" onClick={() => navigate('/module')}>
            Ouvrir
          </button>
        </section>
      )}

      {detailExercice && (
        <div className="modal-overlay" onClick={() => setDetailExerciceId(null)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <button className="modal-sheet__close" onClick={() => setDetailExerciceId(null)}>
              Fermer
            </button>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              {detailExercice.nom}
            </h2>
            <span className="tag">{detailExercice.groupe_musculaire}</span>{' '}
            <span className="tag">{detailExercice.type}</span>
            {detailExercice.image_url && (
              <img className="modal-sheet__image" src={detailExercice.image_url} alt={detailExercice.nom} />
            )}
            {detailExercice.instructions.length > 0 && (
              <ul className="instruction-list">
                {detailExercice.instructions.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
