import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { calculerProgressionExercice } from '../utils/progressionExercice';
import {
  ApiError,
  createSerieLoggee,
  deleteSerieLoggee,
  deleteTodaySeance,
  genererSeance,
  getAlternativesExercice,
  getContexteJour,
  getDernierePerformance,
  getExercicesBibliotheque,
  getSeriesLoggees,
  getTodaySeance,
  messageErreur,
  remplacerExercice,
  terminerSeanceIA,
  updateSerieLoggee,
} from '../api/client';
import type {
  ApiAlternativeExercice,
  ApiContexteJour,
  ApiDernierePerformance,
  ApiDifficulte,
  ApiEtatDuJour,
  ApiExerciceBibliotheque,
  ApiSeance,
  ApiSeanceExercice,
  ApiSeanceGeneree,
  ApiSerieLoggee,
  ApiTerminerSeanceResult,
} from '../api/client';
import SemaineStrip from '../components/SemaineStrip';
import { EtatChargement, EtatErreur, LigneErreur } from '../components/EtatEcran';
import { feedback } from '../components/Toast';
import { donneesModifiees } from '../utils/donneesFraiches';
import { typeSeanceMeta } from '../data/programmeTypes';
import { getNow } from '../utils/devDate';

const dateLabel = getNow().toLocaleDateString('fr-FR', {
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
// Valeurs contrôlées identiques à backend/main.py::ZONES_SENSIBLES_VALIDES (groupes musculaires
// de regles_seance.GROUPES_PAR_TYPE_SEANCE) : ne pas ajouter de libellé qui n'y figure pas, le
// matching des garde-fous se fait par égalité de chaîne.
const ZONE_SENSIBLE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Aucune' },
  { value: 'jambes', label: 'Jambes' },
  { value: 'dos', label: 'Dos' },
  { value: 'épaules', label: 'Épaules' },
  { value: 'bras', label: 'Bras' },
  { value: 'mollets', label: 'Mollets' },
  { value: 'abdos', label: 'Abdos' },
];
const TYPE_SEANCE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Automatique (recommandé)' },
  { value: 'force', label: 'Force' },
  { value: 'explosivité_vitesse', label: 'Explosivité / vitesse' },
  { value: 'esthétique', label: 'Esthétique' },
  { value: 'endurance', label: 'Endurance' },
  { value: 'décharge', label: 'Décharge / récupération' },
];


const REST_SECONDS = 90;

const DIFFICULTE_OPTIONS: { value: ApiDifficulte; label: string }[] = [
  { value: 'facile', label: 'Facile' },
  { value: 'comme_prevu', label: 'Comme prévu' },
  { value: 'dur', label: 'Dur' },
];

// Vues de l'écran Aujourd'hui. `reprise` : une séance déjà commencée a été retrouvée au
// chargement (l'app a été fermée en cours de séance) — on demande à l'utilisateur ce qu'il veut
// en faire plutôt que de le replonger dedans sans prévenir, ou pire, de repartir de zéro.
type View = 'loading' | 'no-seance' | 'form' | 'reprise' | 'apercu' | 'seance' | 'fin-seance' | 'terminee';

// Début de séance persisté : sans ça, fermer puis rouvrir l'app remettait le chronomètre à
// zéro et la durée réelle envoyée en fin de séance était fausse. Une seule séance à la fois,
// donc une seule entrée ; elle est effacée dès que la séance est terminée ou supprimée.
const CLE_DEBUT_SEANCE = 'level.seance.debut';

function lireDebutSeance(seanceId: number): number | null {
  try {
    const brut = localStorage.getItem(CLE_DEBUT_SEANCE);
    if (!brut) return null;
    const parsed = JSON.parse(brut) as { id?: unknown; debut?: unknown };
    return parsed.id === seanceId && typeof parsed.debut === 'number' ? parsed.debut : null;
  } catch {
    return null;
  }
}

function ecrireDebutSeance(seanceId: number, debut: number): void {
  try {
    localStorage.setItem(CLE_DEBUT_SEANCE, JSON.stringify({ id: seanceId, debut }));
  } catch {
    /* stockage indisponible (navigation privée) : le chronomètre repart du chargement, sans
       jamais empêcher la séance. */
  }
}

function effacerDebutSeance(): void {
  try {
    localStorage.removeItem(CLE_DEBUT_SEANCE);
  } catch {
    /* idem */
  }
}

// RPE proposé à partir des difficultés réellement loguées pendant la séance : l'écran de fin
// annonce un RPE « calculé automatiquement », il doit donc l'être réellement plutôt que de
// laisser le champ vide. facile -> 5, comme prévu -> 7, dur -> 9 ; moyenne arrondie, bornée
// 1..10. Renvoie null si aucune série n'a été validée avec une difficulté (rien à déduire).
const RPE_PAR_DIFFICULTE: Record<ApiDifficulte, number> = { facile: 5, comme_prevu: 7, dur: 9 };

// Fin de séance : quatre ressentis suffisent à recueillir un RPE exploitable — la grille 1-10
// n'apportait rien à l'utilisateur, seulement au backend qui n'en a de toute façon besoin que
// comme signal approximatif (cf. RPE_PAR_DIFFICULTE, déjà une approximation à 3 valeurs).
const RESSENTI_OPTIONS: { label: string; rpe: number }[] = [
  { label: 'Facile', rpe: 3 },
  { label: 'Bien', rpe: 6 },
  { label: 'Difficile', rpe: 8 },
  { label: 'Très difficile', rpe: 10 },
];

function ressentiProche(rpeValue: number): string {
  return RESSENTI_OPTIONS.reduce((best, o) =>
    Math.abs(o.rpe - rpeValue) < Math.abs(best.rpe - rpeValue) ? o : best
  ).label;
}

export function rpeSuggere(series: ApiSerieLoggee[]): number | null {
  const notes = series
    .filter((s) => s.coche && s.difficulte)
    .map((s) => RPE_PAR_DIFFICULTE[s.difficulte as ApiDifficulte])
    .filter((n): n is number => typeof n === 'number');
  if (notes.length === 0) return null;
  const moyenne = notes.reduce((a, b) => a + b, 0) / notes.length;
  return Math.min(10, Math.max(1, Math.round(moyenne)));
}

function nomSeance(s: ApiSeance | ApiSeanceGeneree): string {
  return 'nom' in s ? s.nom : s.nom_seance;
}

function dureeSeanceMin(s: ApiSeance | ApiSeanceGeneree): number | null {
  return 'duree_min' in s ? s.duree_min : s.duree_prevue;
}

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

// Ce que LEVEL a décidé pour aujourd'hui quand aucune séance n'est en cours. Chaque statut
// renvoyé par le moteur (backend/contexte_jour.py) est traité explicitement : l'utilisateur
// doit toujours savoir ce qu'il fait aujourd'hui et pourquoi, y compris quand la réponse est
// « rien ». Aucune donnée n'est inventée ici : tout vient du contexte, et l'absence de contexte
// est affichée comme telle.
function ContexteProgrammeLigne({ contexte }: { contexte: ApiContexteJour }) {
  if (contexte.semaine_programme == null) return null;
  return (
    <p className="subtle" style={{ margin: '0 0 6px' }}>
      Semaine {contexte.semaine_programme}/{contexte.duree_semaines}
      {contexte.phase_nom ? ` — phase ${contexte.phase_nom}` : ''}.
    </p>
  );
}

function EtatDuJourSansSeance({
  contexte,
  autoGenerationErreur,
  onGenerer,
  onAdapter,
  onVoirProgramme,
  onVoirProfil,
  onReessayer,
}: {
  contexte: ApiContexteJour | null;
  autoGenerationErreur: string | null;
  onGenerer: () => void;
  onAdapter: () => void;
  onVoirProgramme: () => void;
  onVoirProfil: () => void;
  onReessayer: () => void;
}) {
  if (!contexte || contexte.statut === 'aucun_profil') {
    return (
      <section className="card">
        <div className="card__eyebrow">Séance du jour</div>
        <p style={{ margin: '4px 0 10px', fontWeight: 600 }}>Ton profil n’est pas encore complet</p>
        <p className="subtle" style={{ margin: '0 0 14px' }}>
          LEVEL a besoin de tes objectifs, de ton sport et de tes disponibilités pour construire
          ton programme et décider ce que tu fais aujourd’hui.
        </p>
        <button className="btn btn--primary" onClick={onVoirProfil}>
          Compléter mon profil
        </button>
      </section>
    );
  }

  if (contexte.statut === 'aucun_programme') {
    return (
      <section className="card">
        <div className="card__eyebrow">Séance du jour</div>
        <p style={{ margin: '4px 0 10px', fontWeight: 600 }}>Aucun programme actif</p>
        <p className="subtle" style={{ margin: '0 0 14px' }}>
          Sans programme, LEVEL ne sait pas encore comment répartir tes séances dans la semaine.
          Construis-le depuis l’écran Programme — ou génère une séance isolée pour t’entraîner
          dès aujourd’hui.
        </p>
        <button className="btn btn--primary" style={{ marginBottom: 8 }} onClick={onVoirProgramme}>
          Construire mon programme
        </button>
        <button className="btn btn--ghost" onClick={onGenerer}>
          Générer seulement la séance du jour
        </button>
      </section>
    );
  }

  if (contexte.statut === 'match') {
    return (
      <section className="apercu apercu--repos">
        <div className="apercu__eyebrow">Aujourd’hui</div>
        <h2 className="apercu__title">Jour de match</h2>
        <p className="apercu__lead">
          Rien ne doit compromettre ta performance du jour.
        </p>
        <button className="btn btn--primary apercu__cta" onClick={onVoirProgramme}>
          Voir ma semaine →
        </button>
        <button type="button" className="link-discreet apercu__adapter" onClick={onAdapter}>
          Adapter
        </button>
      </section>
    );
  }

  if (contexte.statut === 'indisponible') {
    return (
      <section className="apercu apercu--repos">
        <div className="apercu__eyebrow">Aujourd’hui</div>
        <h2 className="apercu__title">Jour non disponible</h2>
        <p className="apercu__lead">
          Aucune disponibilité déclarée le {contexte.jour_label.toLowerCase()}.
        </p>
        <button className="btn btn--primary apercu__cta" onClick={onVoirProfil}>
          Modifier mes disponibilités
        </button>
        <button type="button" className="link-discreet apercu__adapter" onClick={onAdapter}>
          Adapter
        </button>
      </section>
    );
  }

  if (contexte.statut === 'repos') {
    return (
      <section className="apercu apercu--repos">
        <div className="apercu__eyebrow">Aujourd’hui</div>
        <h2 className="apercu__title">Jour de repos</h2>
        <p className="apercu__lead">
          {contexte.phase_calendaire === 'lendemain_match'
            ? 'Lendemain de match : récupère aujourd’hui.'
            : 'Tu as suffisamment chargé cette semaine. Récupère aujourd’hui.'}
        </p>
        <button className="btn btn--primary apercu__cta" onClick={onVoirProgramme}>
          Voir ma semaine →
        </button>
        <button type="button" className="link-discreet apercu__adapter" onClick={onAdapter}>
          Adapter
        </button>
      </section>
    );
  }

  // statut === 'seance' : une séance est prévue mais n'a pas (encore) été générée.
  return (
    <section className="card">
      <div className="card__eyebrow">Séance du jour</div>
      <p style={{ margin: '4px 0 10px', fontWeight: 600 }}>
        {contexte.type_seance_prevu ? typeSeanceMeta(contexte.type_seance_prevu).label : 'Séance'}
      </p>
      <ContexteProgrammeLigne contexte={contexte} />
      {autoGenerationErreur ? (
        <>
          {/* La génération automatique a échoué : on dit pourquoi, et on propose d'abord de
              refaire exactement ce qui a échoué (réessayer), puis les autres sorties. */}
          <p className="subtle" style={{ margin: '0 0 14px' }}>
            Ta séance n’a pas pu être préparée automatiquement. {autoGenerationErreur}
          </p>
          <button className="btn btn--primary" style={{ marginBottom: 8 }} onClick={onReessayer}>
            Réessayer
          </button>
          <button className="btn btn--ghost" style={{ marginBottom: 8 }} onClick={onGenerer}>
            Préciser mon état du jour et générer
          </button>
          <button className="btn btn--ghost" onClick={onVoirProgramme}>
            Voir mon programme
          </button>
        </>
      ) : (
        <button className="btn btn--primary" onClick={onGenerer}>
          Générer ma séance du jour
        </button>
      )}
    </section>
  );
}

export default function Today() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>('loading');

  const [seance, setSeance] = useState<ApiSeance | ApiSeanceGeneree | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contexte, setContexte] = useState<ApiContexteJour | null>(null);
  // Erreur de chargement initial (réseau, backend indisponible...) distincte d'une absence
  // légitime de programme/séance : évite d'afficher "Aucune séance" alors qu'on n'a en réalité
  // pas réussi à savoir s'il y en avait une (cf. audit P0.6 — la génération auto ne doit pas se
  // désactiver silencieusement sur un simple accroc réseau).
  const [chargementErreur, setChargementErreur] = useState(false);
  // Raison d'un échec de la génération automatique de la séance du jour (Mistral indisponible,
  // bibliothèque vide...). Distincte de `error` (flux manuel) : elle explique pourquoi l'écran
  // propose un bouton plutôt qu'une séance déjà prête.
  const [autoGenerationErreur, setAutoGenerationErreur] = useState<string | null>(null);

  const [sommeil, setSommeil] = useState('');
  const [motivation, setMotivation] = useState('');
  const [tempsDispo, setTempsDispo] = useState('');
  const [envieTexte, setEnvieTexte] = useState('');
  const [clubSemaine, setClubSemaine] = useState('');
  const [typeSeanceForce, setTypeSeanceForce] = useState('');
  const [forcerSeanceLegere, setForcerSeanceLegere] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // ---- Logging temps réel façon Hevy ----
  const [bibliotheque, setBibliotheque] = useState<Record<number, ApiExerciceBibliotheque>>({});
  const [seriesParExercice, setSeriesParExercice] = useState<Record<number, ApiSerieLoggee[]>>({});
  const [draftParExercice, setDraftParExercice] = useState<
    Record<number, { poids: string; reps: string; difficulte?: ApiDifficulte }>
  >({});
  const [precedentParExercice, setPrecedentParExercice] = useState<Record<number, ApiDernierePerformance>>({});
  const [detailExerciceId, setDetailExerciceId] = useState<number | null>(null);
  const [sessionStart, setSessionStart] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [restSecondsLeft, setRestSecondsLeft] = useState<number | null>(null);
  const [editingSerieId, setEditingSerieId] = useState<number | null>(null);
  const [editDraftParSerie, setEditDraftParSerie] = useState<
    Record<number, { poids: string; reps: string; difficulte?: ApiDifficulte }>
  >({});
  const [manualOpenId, setManualOpenId] = useState<number | 'auto'>('auto');

  // ---- Remplacement d'exercice (Étape 7C) ----
  const [replaceTargetId, setReplaceTargetId] = useState<number | null>(null);
  const [alternatives, setAlternatives] = useState<ApiAlternativeExercice[]>([]);
  const [loadingAlternatives, setLoadingAlternatives] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [replaceError, setReplaceError] = useState<string | null>(null);

  const [rpe, setRpe] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [zoneSensible, setZoneSensible] = useState('');
  const [resultat, setResultat] = useState<ApiTerminerSeanceResult | null>(null);

  // ---- Actions en cours & erreurs d'action ----
  // Garde anti double-clic : la référence est mise à jour de façon synchrone, contrairement à
  // l'état React, donc deux taps rapprochés sur « Valider » ou « Terminer » ne peuvent pas
  // lancer deux requêtes (et donc créer deux séries, deux historiques, deux fois l'XP).
  const enCoursRef = useRef<Set<string>>(new Set());
  const [enCours, setEnCours] = useState<string[]>([]);
  const [actionErreur, setActionErreur] = useState<string | null>(null);
  const [quitterOuvert, setQuitterOuvert] = useState(false);
  // ---- Adapter (mécanisme universel : quelque chose a changé -> Adapter) ----
  const [adapterOuvert, setAdapterOuvert] = useState(false);
  const [adapterEtape, setAdapterEtape] = useState<'menu' | 'temps' | 'autre'>('menu');
  const [adapterTexte, setAdapterTexte] = useState('');
  const [adapterEnCours, setAdapterEnCours] = useState(false);
  const [adapterErreur, setAdapterErreur] = useState<string | null>(null);
  const [confirmationReset, setConfirmationReset] = useState(false);
  const [serieASupprimer, setSerieASupprimer] = useState<{
    exerciceId: number;
    serie: ApiSerieLoggee;
  } | null>(null);
  const [confirmationRemplacement, setConfirmationRemplacement] = useState<{
    nouvelExerciceId: number;
    nbValidees: number;
    nomActuel: string;
    nomNouveau: string;
  } | null>(null);

  const estEnCours = (cle: string) => enCours.includes(cle);

  /**
   * Exécute une action réseau en garantissant : pas de double exécution, un état visible
   * pendant l'attente, et une erreur lisible en cas d'échec (jamais un bouton qui ne fait rien).
   */
  async function executer<T>(cle: string, fn: () => Promise<T>, secours: string): Promise<T | undefined> {
    if (enCoursRef.current.has(cle)) return undefined;
    enCoursRef.current.add(cle);
    setEnCours((prev) => [...prev, cle]);
    setActionErreur(null);
    try {
      return await fn();
    } catch (e) {
      setActionErreur(messageErreur(e, secours));
      return undefined;
    } finally {
      enCoursRef.current.delete(cle);
      setEnCours((prev) => prev.filter((c) => c !== cle));
    }
  }

  useEffect(() => {
    void chargerToday();
  }, []);

  // Charge le programme actif + la séance du jour, avec une reprise unique sur accroc réseau
  // (un échec ponctuel du premier fetch ne doit pas être interprété comme "pas de programme" et
  // faire disparaître silencieusement la génération automatique — cf. audit P0.6).
  async function fetchAvecReprise<T>(fn: () => Promise<T>): Promise<T> {
    try {
      return await fn();
    } catch {
      return await fn();
    }
  }

  async function chargerToday() {
    setChargementErreur(false);
    setAutoGenerationErreur(null);
    let ctx: ApiContexteJour | null;
    let existante: ApiSeance | ApiSeanceGeneree | null;
    try {
      [ctx, existante] = await Promise.all([fetchAvecReprise(getContexteJour), fetchAvecReprise(getTodaySeance)]);
    } catch {
      setChargementErreur(true);
      setView('no-seance');
      return;
    }
    setContexte(ctx);

    if (existante) {
      setSeance(existante);
      if (existante.statut === 'terminee') {
        effacerDebutSeance();
        setView('terminee');
        return;
      }
      // Séance déjà commencée retrouvée au chargement (app fermée en cours de séance, onglet
      // rouvert) : on demande explicitement ce qu'il veut en faire, avec sa progression sous
      // les yeux, au lieu de le replonger dedans sans contexte.
      let dejaCommencee = false;
      try {
        const rows = await getSeriesLoggees(existante.id);
        dejaCommencee = rows.some((r) => r.coche);
        const grouped: Record<number, ApiSerieLoggee[]> = {};
        for (const row of rows) (grouped[row.exercice_id] ??= []).push(row);
        setSeriesParExercice(grouped);
      } catch {
        // Accroc réseau sur les séries seules : on n'empêche pas d'entrer dans la séance, elles
        // seront rechargées par l'effet de la vue séance.
      }
      setView(dejaCommencee ? 'reprise' : 'apercu');
      return;
    }

    // Le statut du jour est décidé par le moteur (backend/contexte_jour.py) : jour de match,
    // jour indisponible et jour de repos ne déclenchent jamais de génération automatique — le
    // backend refuserait d'ailleurs en 409 (voir main.py::generer_seance).
    if (ctx && ctx.statut === 'seance') {
      // Programme actif avec une séance prévue aujourd'hui : on la génère
      // automatiquement, sans attendre un clic sur "Générer ma séance".
      // generer_seance() est idempotent côté backend (renvoie la séance existante si une
      // génération concurrente l'a déjà créée), donc pas de risque de doublon ici.
      try {
        const generee = await genererSeance({
          sommeil: null,
          motivation: null,
          temps_dispo: null,
          envie_texte: null,
          entrainement_club_semaine: null,
          type_seance_force: null,
          forcer_seance_legere: false,
        });
        setSeance(generee);
        setView('apercu');
        return;
      } catch (e) {
        // Si la génération automatique échoue, on retombe sur le flux manuel (bouton fallback),
        // mais on garde la raison, formulée pour un humain : sans elle, l'écran affichait un
        // simple bouton "Générer" qui rejouait le même échec sans que l'utilisateur sache
        // pourquoi. Un refus métier (409 : match, repos) n'est pas une panne — le contexte du
        // jour l'explique déjà correctement, inutile d'y ajouter un message d'erreur.
        if (!(e instanceof ApiError && e.estRefusMetier)) {
          setAutoGenerationErreur(messageErreur(e, 'La préparation automatique n’a pas abouti.'));
        }
      }
    }

    setView('no-seance');
  }

  // Type de séance prévu aujourd'hui, tel que décidé par le moteur : sert uniquement à
  // l'affichage (bandeau éditorial, explication du repos), jamais à décider quoi que ce soit.
  const typeSeancePrevu = contexte?.type_seance_prevu ?? null;

  // Charge la bibliothèque + les séries déjà loguées quand on entre dans la séance.
  useEffect(() => {
    // Également chargé en vue "terminee" : le récapitulatif de fin affiche les séries réellement
    // enregistrées, y compris après un rechargement de la page (où `resultat` est perdu).
    if ((view !== 'seance' && view !== 'terminee' && view !== 'reprise' && view !== 'apercu') || !seance) return;
    // Échecs tolérés : ces chargements enrichissent l'affichage (noms d'exercices, séries déjà
    // enregistrées, performance précédente). Une panne réseau ne doit pas vider la séance en
    // cours ni provoquer une exception non gérée — l'écran reste utilisable en l'état.
    getExercicesBibliotheque()
      .then((list) => {
        const map: Record<number, ApiExerciceBibliotheque> = {};
        for (const ex of list) map[ex.id] = ex;
        setBibliotheque(map);
      })
      .catch(() => setActionErreur((prev) => prev ?? 'Les noms des exercices n’ont pas pu être chargés.'));
    getSeriesLoggees(seance.id)
      .then((rows) => {
        const grouped: Record<number, ApiSerieLoggee[]> = {};
        for (const row of rows) {
          (grouped[row.exercice_id] ??= []).push(row);
        }
        setSeriesParExercice(grouped);
      })
      .catch(() => {
        /* Les séries déjà chargées restent affichées ; la validation d'une nouvelle série
           remontera une erreur explicite si le serveur est toujours injoignable. */
      });
    if (view !== 'seance') return;
    for (const item of seance.exercices) {
      getDernierePerformance(item.exercice_id, seance.id)
        .then((perf) => {
          setPrecedentParExercice((prev) => ({ ...prev, [item.exercice_id]: perf }));
        })
        .catch(() => {
          /* Pas d'historique affichable pour cet exercice : le bloc affiche l'objectif prévu. */
        });
    }
    // Chronomètre repris là où il en était si la séance avait déjà été commencée (l'app a pu
    // être fermée entre-temps), démarré sinon.
    const debutEnregistre = lireDebutSeance(seance.id);
    if (debutEnregistre !== null) {
      setSessionStart(debutEnregistre);
    } else {
      const maintenant = Date.now();
      ecrireDebutSeance(seance.id, maintenant);
      setSessionStart(maintenant);
    }
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

  // Progression globale de la séance (bandeau visuel) : même calcul de cible par exercice que
  // le badge par bloc (series prévues moins l'historique d'un éventuel remplacement), sans
  // jamais dépasser la cible même si l'utilisateur a loggé des séries bonus.
  const seanceProgress = useMemo(() => {
    if (!seance) return { total: 0, faites: 0 };
    let total = 0;
    let faites = 0;
    for (const item of seance.exercices) {
      const series = seriesParExercice[item.exercice_id] ?? [];
      const cible = Math.max(0, (item.series ?? series.length) - validesHistoriquePourExercice(item));
      const validees = series.filter((s) => s.coche).length;
      total += cible;
      faites += Math.min(validees, cible);
    }
    return { total, faites };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seance, seriesParExercice]);

  function seriesValideesPourExercice(item: ApiSeanceExercice): ApiSerieLoggee[] {
    const series = seriesParExercice[item.exercice_id] ?? [];
    return series.filter((s) => s.coche);
  }

  // Après un remplacement (Étape 7C), les séries déjà validées sur les anciens exercice_id de ce
  // slot (historique_exercice_ids) comptent pour la complétion du slot, sans jamais être
  // transférées vers le nouvel exercice_id (vérité historique intacte, cf. remplacerExercice).
  function validesHistoriquePourExercice(item: ApiSeanceExercice): number {
    return (item.historique_exercice_ids ?? []).reduce(
      (acc, id) => acc + (seriesParExercice[id] ?? []).filter((s) => s.coche).length,
      0
    );
  }

  function estExerciceComplet(item: ApiSeanceExercice): boolean {
    const series = seriesParExercice[item.exercice_id] ?? [];
    const cible = Math.max(0, (item.series ?? series.length) - validesHistoriquePourExercice(item));
    const validees = seriesValideesPourExercice(item);
    return cible > 0 && validees.length >= cible;
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
    return draftParExercice[exerciceId] ?? { poids: '', reps: '', difficulte: undefined };
  }

  function setDraft(
    exerciceId: number,
    patch: Partial<{ poids: string; reps: string; difficulte: ApiDifficulte | undefined }>
  ) {
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

    const created = await executer(
      `serie-${exerciceId}`,
      () =>
        createSerieLoggee({
          seance_id: seance.id,
          exercice_id: exerciceId,
          numero_serie: numero,
          poids_kg: poids,
          repetitions: reps,
          coche: true,
          difficulte: draft.difficulte ?? null,
        }),
      "Cette série n’a pas pu être enregistrée."
    );
    if (!created) return;

    setSeriesParExercice((prev) => ({ ...prev, [exerciceId]: [...(prev[exerciceId] ?? []), created] }));
    setDraft(exerciceId, { poids: '', reps: '', difficulte: undefined });
    setRestSecondsLeft(reposPourExercice(item));
  }

  // Validation rapide en 1 tap : facile / comme prévu / dur — poids et répétitions sont
  // pré-remplis depuis la cible calculée par la génération, aucune saisie nécessaire.
  async function handleValiderRapide(item: ApiSeanceExercice, difficulte: ApiDifficulte) {
    if (!seance) return;
    const exerciceId = item.exercice_id;
    const numero = (seriesParExercice[exerciceId]?.length ?? 0) + 1;

    const created = await executer(
      `serie-${exerciceId}`,
      () =>
        createSerieLoggee({
          seance_id: seance.id,
          exercice_id: exerciceId,
          numero_serie: numero,
          poids_kg: chargeCible(item.charge_indicative),
          repetitions: repsCible(item.repetitions),
          coche: true,
          difficulte,
        }),
      "Cette série n’a pas pu être enregistrée."
    );
    if (!created) return;

    setSeriesParExercice((prev) => ({ ...prev, [exerciceId]: [...(prev[exerciceId] ?? []), created] }));
    setRestSecondsLeft(reposPourExercice(item));
  }

  function editDraftFor(serie: ApiSerieLoggee) {
    return (
      editDraftParSerie[serie.id] ?? {
        poids: serie.poids_kg?.toString() ?? '',
        reps: serie.repetitions?.toString() ?? '',
        difficulte: serie.difficulte ?? undefined,
      }
    );
  }

  function ouvrirEditionSerie(serie: ApiSerieLoggee) {
    setEditingSerieId(serie.id);
    setEditDraftParSerie((prev) => ({ ...prev, [serie.id]: editDraftFor(serie) }));
  }

  async function handleEnregistrerEditionSerie(exerciceId: number, serie: ApiSerieLoggee) {
    const draft = editDraftFor(serie);
    const updated = await executer(
      `edit-${serie.id}`,
      () =>
        updateSerieLoggee(serie.id, {
          poids_kg: draft.poids.trim() ? Number(draft.poids) : null,
          repetitions: draft.reps.trim() ? Number(draft.reps) : null,
          difficulte: draft.difficulte ?? null,
        }),
      "La correction n’a pas pu être enregistrée. Ta série précédente est intacte."
    );
    if (!updated) return;
    setSeriesParExercice((prev) => ({
      ...prev,
      [exerciceId]: (prev[exerciceId] ?? []).map((s) => (s.id === updated.id ? updated : s)),
    }));
    setEditingSerieId(null);
    feedback('Série corrigée');
  }

  async function handleToggleSerie(exerciceId: number, serie: ApiSerieLoggee) {
    const updated = await executer(
      `toggle-${serie.id}`,
      () => updateSerieLoggee(serie.id, { coche: !serie.coche }),
      "Ce changement n’a pas pu être enregistré."
    );
    if (!updated) return;
    setSeriesParExercice((prev) => ({
      ...prev,
      [exerciceId]: (prev[exerciceId] ?? []).map((s) => (s.id === updated.id ? updated : s)),
    }));
  }

  function handleAjouterSerie(exerciceId: number) {
    // Une série "brouillon" locale : elle n'est persistée qu'au moment où elle est validée.
    setDraftParExercice((prev) => ({ ...prev, [exerciceId]: { poids: '', reps: '' } }));
  }

  // Retire le brouillon local d'une série pas encore validée : aucun appel API, rien n'a
  // jamais été créé en base pour cette série.
  function handleAnnulerDraft(exerciceId: number) {
    setDraftParExercice((prev) => {
      const next = { ...prev };
      delete next[exerciceId];
      return next;
    });
  }

  async function confirmerSuppressionSerie() {
    if (!serieASupprimer) return;
    const { exerciceId, serie } = serieASupprimer;
    const ok = await executer(
      `suppr-${serie.id}`,
      async () => {
        await deleteSerieLoggee(serie.id);
        return true;
      },
      "Cette série n’a pas pu être supprimée."
    );
    if (!ok) return;
    setSeriesParExercice((prev) => ({
      ...prev,
      [exerciceId]: (prev[exerciceId] ?? []).filter((s) => s.id !== serie.id),
    }));
    if (editingSerieId === serie.id) setEditingSerieId(null);
    setSerieASupprimer(null);
    feedback('Série supprimée');
  }

  async function ouvrirRemplacement(exerciceId: number) {
    if (!seance) return;
    setReplaceTargetId(exerciceId);
    setAlternatives([]);
    setReplaceError(null);
    setLoadingAlternatives(true);
    try {
      const res = await getAlternativesExercice(seance.id, exerciceId);
      setAlternatives(res.alternatives);
    } catch (e) {
      setReplaceError(messageErreur(e, "Les alternatives n'ont pas pu être chargées."));
    } finally {
      setLoadingAlternatives(false);
    }
  }

  function fermerRemplacement() {
    setReplaceTargetId(null);
    setAlternatives([]);
    setReplaceError(null);
  }

  /** Étape de confirmation : si des séries ont déjà été réalisées sur l'exercice remplacé,
   * l'utilisateur doit savoir ce qu'elles deviennent avant de valider (elles restent dans son
   * historique, elles ne sont jamais transférées ni perdues). Sans série réalisée, il n'y a
   * rien à expliquer : le remplacement est direct. */
  function demanderRemplacement(nouvelExerciceId: number) {
    if (!seance || replaceTargetId === null) return;
    const nbValideesActuel = (seriesParExercice[replaceTargetId] ?? []).filter((s) => s.coche).length;
    if (nbValideesActuel === 0) {
      void choisirAlternative(nouvelExerciceId);
      return;
    }
    setConfirmationRemplacement({
      nouvelExerciceId,
      nbValidees: nbValideesActuel,
      nomActuel: bibliotheque[replaceTargetId]?.nom ?? `Exercice #${replaceTargetId}`,
      nomNouveau:
        bibliotheque[nouvelExerciceId]?.nom ??
        alternatives.find((a) => a.exercice.id === nouvelExerciceId)?.exercice.nom ??
        `Exercice #${nouvelExerciceId}`,
    });
  }

  async function choisirAlternative(nouvelExerciceId: number) {
    if (!seance || replaceTargetId === null) return;

    setReplacing(true);
    setReplaceError(null);
    try {
      const res = await remplacerExercice(seance.id, {
        exercice_id_actuel: replaceTargetId,
        exercice_id_nouveau: nouvelExerciceId,
      });
      setSeance(res.seance);
      const nouvelExercice = alternatives.find((a) => a.exercice.id === nouvelExerciceId)?.exercice;
      if (nouvelExercice) {
        setBibliotheque((prev) => ({ ...prev, [nouvelExerciceId]: nouvelExercice }));
      }
      // Ouvre automatiquement le nouvel exercice pour que l'utilisateur voie tout de suite le
      // remplacement pris en compte, sans perdre les séries déjà réalisées (cf. cible ajustée
      // via historique_exercice_ids dans le rendu du bloc-exercice).
      setManualOpenId(nouvelExerciceId);
      setConfirmationRemplacement(null);
      fermerRemplacement();
      feedback(res.message_confirmation ?? 'Exercice remplacé');
    } catch (e) {
      setReplaceError(messageErreur(e, "Le remplacement n'a pas abouti. L'exercice actuel reste en place."));
    } finally {
      setReplacing(false);
    }
  }

  function ouvrirAdapter() {
    setAdapterEtape('menu');
    setAdapterTexte('');
    setAdapterErreur(null);
    setAdapterOuvert(true);
  }

  function fermerAdapter() {
    if (adapterEnCours) return;
    setAdapterOuvert(false);
    setAdapterEtape('menu');
    setAdapterTexte('');
    setAdapterErreur(null);
  }

  /** Applique une adaptation via le moteur de décision existant (genererSeance) : jamais de
   * logique de recommandation côté frontend. Si une séance du jour existe déjà et n'a pas été
   * commencée, elle est supprimée avant régénération — sinon le backend, idempotent, renverrait
   * l'ancienne séance inchangée. */
  async function appliquerAdaptation(patch: Partial<ApiEtatDuJour>) {
    setAdapterEnCours(true);
    setAdapterErreur(null);
    try {
      if (seance) {
        await deleteTodaySeance();
        effacerDebutSeance();
      }
      const payload: ApiEtatDuJour = {
        sommeil: null,
        motivation: null,
        temps_dispo: null,
        envie_texte: null,
        entrainement_club_semaine: null,
        type_seance_force: null,
        forcer_seance_legere: false,
        ...patch,
      };
      const generee = await genererSeance(payload);
      setSeance(generee);
      setSeriesParExercice({});
      setAutoGenerationErreur(null);
      donneesModifiees('seance');
      setAdapterOuvert(false);
      setAdapterEtape('menu');
      setAdapterTexte('');
      setView('apercu');
    } catch (e) {
      setAdapterErreur(messageErreur(e, "Cette adaptation n'a pas pu être appliquée."));
    } finally {
      setAdapterEnCours(false);
    }
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
        forcer_seance_legere: forcerSeanceLegere,
      };
      // Idempotent côté backend (voir main.py::generer_seance) : si une séance existe déjà pour
      // aujourd'hui, elle est renvoyée telle quelle plutôt que dupliquée.
      const generee = await genererSeance(payload);
      setSeance(generee);
      setAutoGenerationErreur(null);
      setView('apercu');
    } catch (e) {
      setError(messageErreur(e, "Ta séance n'a pas pu être générée."));
    } finally {
      setSubmitting(false);
    }
  }

  /** Rejoue exactement la génération automatique qui a échoué, sans repasser par le
   * questionnaire : le cas le plus fréquent est un service momentanément indisponible. */
  async function handleReessayerGeneration() {
    setAutoGenerationErreur(null);
    setView('loading');
    await chargerToday();
  }

  // Pré-remplit le RPE à partir des difficultés réellement loguées avant d'ouvrir l'écran de
  // fin : l'utilisateur n'a plus qu'à confirmer ou ajuster. Sans difficulté loguée, le champ
  // reste vide plutôt que d'afficher une valeur inventée.
  function ouvrirFinDeSeance() {
    const toutesSeries = Object.values(seriesParExercice).flat();
    setRpe((actuel) => actuel ?? rpeSuggere(toutesSeries));
    setActionErreur(null);
    setView('fin-seance');
  }

  async function handleTerminer() {
    if (!seance) return;
    setSubmitting(true);
    setError(null);
    // Clé d'action : un double tap ne peut pas envoyer deux fois la fin de séance (le backend
    // est également idempotent, voir main.py::terminer_seance — les deux garde-fous se
    // complètent, celui-ci évite en plus l'aller-retour inutile).
    const res = await executer(
      'terminer',
      () =>
        terminerSeanceIA({
          seance_id: seance.id,
          rpe,
          note: note.trim() || null,
          duree_reelle_min: Math.round(elapsedSec / 60),
          zone_sensible: zoneSensible || null,
        }),
      "Ta séance n'a pas pu être enregistrée. Tes séries sont conservées : réessaie."
    );
    setSubmitting(false);
    if (!res) return;
    setResultat(res);
    effacerDebutSeance();
    // XP, streak et historique viennent de changer : l'en-tête et les écrans encore montés
    // doivent refléter le nouvel état plutôt que celui d'avant la séance.
    donneesModifiees('seance', 'stats');
    setView('terminee');
  }

  /** Quitte la séance en conservant tout ce qui a été enregistré : les séries loguées restent
   * en base, la séance reste ouverte, et l'écran Aujourd'hui proposera de la reprendre. */
  function quitterEnConservant() {
    setQuitterOuvert(false);
    navigate('/programme');
  }

  async function handleReset() {
    if (!seance) return;
    setSubmitting(true);
    setError(null);
    const ok = await executer(
      'reset',
      async () => {
        await deleteTodaySeance();
        return true;
      },
      "La séance n'a pas pu être supprimée."
    );
    setSubmitting(false);
    if (!ok) return;
    effacerDebutSeance();
    setSeance(null);
    setSeriesParExercice({});
    setSessionStart(null);
    setElapsedSec(0);
    setForcerSeanceLegere(false);
    setConfirmationReset(false);
    setQuitterOuvert(false);
    donneesModifiees('seance');
    setView('no-seance');
  }

  if (view === 'loading') {
    return (
      <div className="screen">
        <Header title="Aujourd’hui" />
        <h1 className="page-title" style={{ textTransform: 'capitalize' }}>
          {dateLabel}
        </h1>
        <EtatChargement message="LEVEL prépare ta journée…" />
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

      {/* Repère de semaine : utile pour se situer avant/après la séance, retiré pendant
          l'effort où seule l'action en cours compte. */}
      {contexte && contexte.semaine.length > 0 && view !== 'seance' && view !== 'fin-seance' && view !== 'apercu' && (
        <SemaineStrip jours={contexte.semaine} />
      )}

      {view === 'no-seance' && (
        <>
          {/* Réseau indisponible : on ne sait pas ce que prévoit le programme, donc on ne
              prétend pas qu'il n'y a rien de prévu — on propose de réessayer. */}
          {chargementErreur ? (
            <EtatErreur
              titre="Ta journée n’a pas pu être chargée"
              message="LEVEL n’a pas réussi à joindre le serveur, donc il ne sait pas ce que prévoit ton programme aujourd’hui. Rien n’est perdu."
              action={{
                label: 'Réessayer',
                onClick: () => void chargerToday(),
              }}
              actionSecondaire={{
                label: 'Générer ma séance quand même',
                onClick: () => setView('form'),
              }}
            />
          ) : (
            <EtatDuJourSansSeance
              contexte={contexte}
              autoGenerationErreur={autoGenerationErreur}
              onGenerer={() => setView('form')}
              onAdapter={ouvrirAdapter}
              onVoirProgramme={() => navigate('/programme')}
              onVoirProfil={() => navigate('/profil')}
              onReessayer={() => void handleReessayerGeneration()}
            />
          )}
        </>
      )}

      {/* Séance retrouvée en cours : l'utilisateur choisit, il ne subit pas. */}
      {view === 'reprise' && seance && (
        <section className="card">
          <div className="card__eyebrow">Séance en cours</div>
          <h2 className="card__title">{'nom' in seance ? seance.nom : seance.nom_seance}</h2>
          <p className="subtle" style={{ margin: '8px 0 14px' }}>
            Tu as déjà enregistré {totaux.nbValidees} série{totaux.nbValidees > 1 ? 's' : ''}
            {totaux.volume > 0 ? ` · ${Math.round(totaux.volume)} kg` : ''}. Tout est conservé —
            tu peux reprendre là où tu t’étais arrêté.
          </p>
          <button className="btn btn--primary" style={{ marginBottom: 8 }} onClick={() => setView('seance')}>
            Reprendre ma séance
          </button>
          <button className="btn btn--ghost" style={{ marginBottom: 8 }} onClick={ouvrirFinDeSeance}>
            Terminer la séance maintenant
          </button>
          <button className="btn btn--ghost" onClick={() => navigate('/programme')}>
            Plus tard — voir mon programme
          </button>
        </section>
      )}

      {view === 'form' && (
        <section className="card">
          <div className="card__eyebrow">État du jour</div>
          {forcerSeanceLegere && (
            <p className="subtle" style={{ margin: '4px 0 14px' }}>
              {contexte?.statut === 'match'
                ? 'Jour de match — activation très légère uniquement.'
                : 'Aucune séance prévue aujourd’hui — séance légère malgré tout.'}
            </p>
          )}

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

          <LigneErreur message={error} />

          <button className="btn btn--primary" disabled={submitting} onClick={handleGenerer}>
            {submitting ? 'Génération en cours…' : 'Générer ma séance du jour'}
          </button>
          {/* Sortie explicite : entrer dans ce questionnaire ne doit pas être un aller simple. */}
          <button
            className="btn btn--ghost"
            style={{ marginTop: 8 }}
            disabled={submitting}
            onClick={() => {
              setForcerSeanceLegere(false);
              setError(null);
              setView('no-seance');
            }}
          >
            Annuler
          </button>
        </section>
      )}

      {/* Aperçu minimal avant d'entrer dans la séance : LEVEL a déjà décidé, l'utilisateur n'a
          qu'à comprendre quoi et combien de temps, pas à parcourir toute la séance. */}
      {view === 'apercu' && seance && (
        <section className="apercu">
          <div className="apercu__eyebrow">
            {contexte?.phase_calendaire === 'veille_match'
              ? 'Match demain'
              : typeSeancePrevu
                ? typeSeanceMeta(typeSeancePrevu).label
                : 'Séance du jour'}
          </div>
          <h2 className="apercu__title">{nomSeance(seance)}</h2>
          {dureeSeanceMin(seance) != null && <div className="apercu__duree">{dureeSeanceMin(seance)} min</div>}

          {seance.exercices[0] && (
            <div className="apercu__preview">
              <div className="apercu__preview-name">
                {bibliotheque[seance.exercices[0].exercice_id]?.nom ?? '…'}
              </div>
              <div className="apercu__preview-meta">
                {seance.exercices[0].charge_indicative ? `${seance.exercices[0].charge_indicative} · ` : ''}
                {seance.exercices[0].series} × {seance.exercices[0].repetitions}
              </div>
            </div>
          )}

          <button className="btn btn--primary apercu__cta" onClick={() => setView('seance')}>
            Commencer →
          </button>

          {'explication' in seance && seance.explication && (
            <details className="editorial-why apercu__why">
              <summary>Pourquoi ?</summary>
              <p>{seance.explication}</p>
            </details>
          )}

          <button type="button" className="link-discreet apercu__adapter" onClick={ouvrirAdapter}>
            Adapter
          </button>
        </section>
      )}

      {view === 'seance' && seance && (
        <>
          {(() => {
            const indexActif = Math.max(0, seance.exercices.findIndex((it) => it.exercice_id === currentExerciceId));
            return (
              <div className="editorial-head">
                <div className="editorial-head__eyebrow">
                  {dateLabel.toUpperCase()}
                  {typeSeancePrevu && <> · {typeSeanceMeta(typeSeancePrevu).label.toUpperCase()}</>}
                </div>
                {contexte?.semaine_programme != null && (
                  <div className="editorial-head__semaine">
                    Semaine {contexte.semaine_programme}/{contexte.duree_semaines}
                  </div>
                )}
                <div className="editorial-position">
                  {String(indexActif + 1).padStart(2, '0')} / {String(seance.exercices.length).padStart(2, '0')}
                </div>
              </div>
            );
          })()}

          {(() => {
            const items = seance.exercices;
            const actif = items.find((it) => it.exercice_id === openExerciceId) ?? null;
            const aVenir = items.filter((it) => it !== actif && !estExerciceComplet(it));
            const termines = items.filter((it) => it !== actif && estExerciceComplet(it));
            const ordonnes = actif ? [actif, ...aVenir, ...termines] : [...aVenir, ...termines];
            const debutAVenir = actif ? 1 : 0;
            const debutTermines = debutAVenir + aVenir.length;
            return ordonnes.map((item, ordreIndex) => (
              <div key={item.exercice_id}>
                {ordreIndex === debutAVenir && aVenir.length > 0 && (
                  <div className="editorial-section-label">À suivre</div>
                )}
                {ordreIndex === debutTermines && termines.length > 0 && (
                  <div className="editorial-section-label editorial-section-label--done">Terminé</div>
                )}
                {(() => {
            const isOpen = item === actif;
            const ex = bibliotheque[item.exercice_id];
            const series = seriesParExercice[item.exercice_id] ?? [];
            const precedent = precedentParExercice[item.exercice_id];
            const draft = draftFor(item.exercice_id);
            const draftVisible = item.exercice_id in draftParExercice;
            // Après un remplacement (Étape 7C), les séries déjà validées sur les anciens
            // exercice_id de ce slot (historique_exercice_ids) ne sont jamais transférées vers
            // le nouvel exercice_id : on les déduit du total prévu du slot pour que le badge et
            // la liste de séries à faire reflètent ce qu'il reste réellement à faire, sans jamais
            // recalculer/réduire item.series lui-même (qui reste la vérité du total prévu, cf.
            // pourcentage_complete côté backend).
            const cible = Math.max(0, (item.series ?? series.length) - validesHistoriquePourExercice(item));
            const prochaineNumero = series.length + 1;
            const seanceTerminee = 'statut' in seance && seance.statut === 'terminee';
            const complet = estExerciceComplet(item);
            const nbValideesExercice = seriesValideesPourExercice(item).length;
            const objectifLabel = `${item.series}x${item.repetitions}${
              item.charge_indicative ? ` · ${item.charge_indicative}` : ''
            }${item.rpe_cible ? ` · RPE ${item.rpe_cible}` : ''}`;

            if (!isOpen) {
              return (
                <button
                  type="button"
                  className={`editorial-line ${complet ? 'editorial-line--done' : ''}`}
                  onClick={() => setDetailExerciceId(item.exercice_id)}
                >
                  {ex?.nom ?? `Exercice #${item.exercice_id}`}
                </button>
              );
            }

            return (
              <div className="editorial-active" key={item.exercice_id}>
                <div className="editorial-active__head">
                  <span
                    className="editorial-active__name"
                    onClick={() => setDetailExerciceId(item.exercice_id)}
                  >
                    {ex?.nom ?? `Exercice #${item.exercice_id}`}
                  </span>
                  {!seanceTerminee && !complet && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Je ne peux pas faire cet exercice — le remplacer"
                      title="Je ne peux pas faire cet exercice"
                      onClick={() => ouvrirRemplacement(item.exercice_id)}
                    >
                      ⇄
                    </button>
                  )}
                </div>
                <div className="editorial-active__target">
                  {objectifLabel}
                  {!complet && ` · ${nbValideesExercice}/${cible}`}
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

                {isOpen && (
                  <>
                    <div className="exercise-block__previous">
                      {precedent && precedent.series.length > 0 ? (
                        <>
                          <div className="exercise-block__previous-title">
                            Dernière séance
                            {precedent.date
                              ? ` · ${new Date(precedent.date).toLocaleDateString('fr-FR', {
                                  day: 'numeric',
                                  month: 'long',
                                })}`
                              : ''}
                          </div>
                          {precedent.series.map((s) => (
                            <div className="exercise-block__previous-row" key={s.id}>
                              {s.poids_kg ?? '–'} kg × {s.repetitions ?? '–'}
                            </div>
                          ))}
                          {(() => {
                            const progression = calculerProgressionExercice(
                              precedent.series,
                              seriesValideesPourExercice(item)
                            );
                            return progression ? (
                              <div className={`exercise-block__progression exercise-block__progression--${progression.type}`}>
                                {progression.label}
                              </div>
                            ) : null;
                          })()}
                        </>
                      ) : (
                        `Objectif : ${objectifLabel}`
                      )}
                    </div>

                    {series.map((s) => {
                      if (editingSerieId === s.id) {
                        return (
                          <div key={s.id}>
                          <div className="set-row">
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
                          <div className="quick-row">
                            {DIFFICULTE_OPTIONS.map((o) => (
                              <button
                                key={o.value}
                                type="button"
                                className={`quick-btn quick-btn--${o.value}`}
                                style={editDraftFor(s).difficulte === o.value ? { outline: '2px solid currentColor' } : undefined}
                                onClick={() =>
                                  setEditDraftParSerie((prev) => ({
                                    ...prev,
                                    [s.id]: { ...editDraftFor(s), difficulte: o.value },
                                  }))
                                }
                              >
                                {o.label}
                              </button>
                            ))}
                          </div>
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
                          {!seanceTerminee && (
                            <button
                              type="button"
                              className="icon-btn"
                              aria-label="Supprimer la série"
                              onClick={() => setSerieASupprimer({ exerciceId: item.exercice_id, serie: s })}
                            >
                              🗑
                            </button>
                          )}
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
                      <div>
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
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label="Annuler cette série"
                            onClick={() => handleAnnulerDraft(item.exercice_id)}
                          >
                            🗑
                          </button>
                        </div>
                        <div className="quick-row">
                          {DIFFICULTE_OPTIONS.map((o) => (
                            <button
                              key={o.value}
                              type="button"
                              className={`quick-btn quick-btn--${o.value}`}
                              style={draft.difficulte === o.value ? { outline: '2px solid currentColor' } : undefined}
                              onClick={() => setDraft(item.exercice_id, { difficulte: o.value })}
                            >
                              {o.label}
                            </button>
                          ))}
                        </div>
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

                    {!seanceTerminee && !complet && (
                      // Sortie explicite quand l'exercice est infaisable : sans ce lien, le seul
                      // accès au remplacement était une icône ⇄, que personne ne cherche quand
                      // il a mal quelque part.
                      <button
                        type="button"
                        className="link-discreet"
                        style={{ marginTop: 10 }}
                        onClick={() => ouvrirRemplacement(item.exercice_id)}
                      >
                        Je ne peux pas faire cet exercice
                      </button>
                    )}
                  </>
                )}
              </div>
            );
                })()}
              </div>
            ));
          })()}

          {'explication' in seance && seance.explication && (
            <details className="editorial-why">
              <summary>Pourquoi cette séance ?</summary>
              <p>{seance.explication}</p>
            </details>
          )}

          {(() => {
            const toutTermine = seanceProgress.total > 0 && seanceProgress.faites >= seanceProgress.total;
            const activeItem = seance.exercices.find((it) => it.exercice_id === currentExerciceId) ?? null;
            const validationEnCours = activeItem ? estEnCours(`serie-${activeItem.exercice_id}`) : false;
            return (
              <div className="editorial-cta">
                {toutTermine ? (
                  <button className="btn btn--primary" onClick={ouvrirFinDeSeance}>
                    Terminer la séance →
                  </button>
                ) : (
                  <button
                    className="btn btn--primary"
                    disabled={!activeItem || validationEnCours}
                    onClick={() => activeItem && handleValiderRapide(activeItem, 'comme_prevu')}
                  >
                    {validationEnCours ? 'Enregistrement…' : 'Valider la série →'}
                  </button>
                )}
                {/* Toujours une sortie sans perte : quitter n'efface rien, et terminer reste
                    possible même si la séance n'est pas allée au bout. */}
                <button className="session-actions__reset link-discreet" onClick={() => setQuitterOuvert(true)}>
                  Quitter la séance
                </button>
              </div>
            );
          })()}
          <LigneErreur message={actionErreur ?? error} />
        </>
      )}

      {view === 'fin-seance' && seance && (
        <section className="apercu">
          <div className="apercu__eyebrow">Séance terminée</div>
          <h2 className="apercu__title">{formatDuree(elapsedSec)}</h2>
          <p className="apercu__lead">
            {totaux.nbValidees} série{totaux.nbValidees > 1 ? 's' : ''}
          </p>

          <div className="section-title">Comment c’était ?</div>
          <div className="ressenti-grid">
            {RESSENTI_OPTIONS.map((o) => (
              <button
                key={o.label}
                type="button"
                className={`btn btn--ghost ressenti-btn ${rpe !== null && ressentiProche(rpe) === o.label ? 'ressenti-btn--active' : ''}`}
                onClick={() => setRpe(o.rpe)}
              >
                {o.label}
              </button>
            ))}
          </div>

          <details className="editorial-why" style={{ margin: '20px 0 0' }}>
            <summary>Plus de détails</summary>
            <div style={{ marginTop: 14 }}>
              <div className="section-title">Ressenti général (optionnel)</div>
              <textarea
                className="textarea"
                placeholder="Un mot sur la séance…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="section-title">Zone sensible ressentie pendant la séance (optionnel)</div>
              <div className="tag-row">
                {ZONE_SENSIBLE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    className={`tag tag--selectable ${zoneSensible === o.value ? 'tag--active' : ''}`}
                    onClick={() => setZoneSensible(o.value)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          </details>

          <LigneErreur message={actionErreur ?? error} />
          <button
            className="btn btn--primary apercu__cta"
            disabled={submitting || estEnCours('terminer') || rpe === null}
            onClick={handleTerminer}
          >
            {submitting || estEnCours('terminer') ? 'Enregistrement…' : 'Valider'}
          </button>
          {/* Changement d'avis : revenir à la séance ne perd rien, tout est déjà enregistré. */}
          <button
            type="button"
            className="link-discreet apercu__adapter"
            disabled={submitting || estEnCours('terminer')}
            onClick={() => {
              setActionErreur(null);
              setError(null);
              setView('seance');
            }}
          >
            Revenir à ma séance
          </button>
        </section>
      )}

      {view === 'terminee' && seance && (
        <>
          <div className="editorial-head">
            <div className="editorial-head__eyebrow">
              {dateLabel.toUpperCase()}
              {typeSeancePrevu && <> · {typeSeanceMeta(typeSeancePrevu).label.toUpperCase()}</>}
            </div>
            <div className="editorial-head__semaine">Séance terminée</div>
          </div>

          <section className="card">
            <h2 className="card__title">{'nom' in seance ? seance.nom : seance.nom_seance}</h2>
            {/* Récapitulatif calculé sur les séries réellement enregistrées : rien n'est affiché
                si rien n'a été logué, plutôt qu'un total fabriqué. */}
            {totaux.nbValidees > 0 ? (
              <p className="subtle" style={{ marginTop: 10 }}>
                {totaux.nbValidees} série{totaux.nbValidees > 1 ? 's' : ''} validée
                {totaux.nbValidees > 1 ? 's' : ''} · {Math.round(totaux.volume)} kg de volume total
              </p>
            ) : (
              <p className="subtle" style={{ marginTop: 10 }}>
                Aucune série enregistrée sur cette séance.
              </p>
            )}
            {resultat && (
              <p className="subtle" style={{ marginTop: 6 }}>
                +{resultat.xp_gagne} XP
              </p>
            )}
            {resultat &&
              (() => {
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

          {/* « Et ensuite ? » : la séance terminée n'est jamais un cul-de-sac, même quand le
              programme ne prévoit rien de précis derrière. */}
          <section className="card">
            <div className="card__eyebrow">Ensuite</div>
            {contexte?.prochaine_seance ? (
              <>
                <p style={{ margin: '4px 0 0', fontWeight: 600 }}>
                  {contexte.prochaine_seance.jour_label} —{' '}
                  {typeSeanceMeta(contexte.prochaine_seance.type_seance_prevu).label}
                </p>
                <p className="subtle" style={{ marginTop: 6 }}>
                  Cette séance sera adaptée à partir de ce que tu viens de réaliser.
                </p>
              </>
            ) : (
              <p className="subtle" style={{ margin: '4px 0 0' }}>
                Récupération jusqu’à ta prochaine séance. Ton programme te dit ce qui vient
                ensuite dans la semaine.
              </p>
            )}
            <button
              className="btn btn--primary"
              style={{ marginTop: 14 }}
              onClick={() => navigate('/programme')}
            >
              Voir mon programme
            </button>
          </section>

          <div className="editorial-cta">
            <button className="btn btn--ghost" onClick={() => navigate('/historique')}>
              Voir l’historique →
            </button>
          </div>
        </>
      )}

      {/* Quitter la séance : trois sorties explicites, aucune perte silencieuse. */}
      {quitterOuvert && (
        <div className="modal-overlay" onClick={() => setQuitterOuvert(false)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Quitter la séance ?
            </h2>
            <p className="subtle" style={{ marginBottom: 16 }}>
              {totaux.nbValidees > 0
                ? `Tes ${totaux.nbValidees} série${totaux.nbValidees > 1 ? 's' : ''} sont déjà enregistrées. Elles sont conservées quoi qu'il arrive.`
                : 'Rien n’a encore été enregistré sur cette séance.'}
            </p>
            <button
              className="btn btn--primary"
              style={{ marginBottom: 8 }}
              onClick={() => setQuitterOuvert(false)}
            >
              Continuer ma séance
            </button>
            <button className="btn btn--ghost" style={{ marginBottom: 8 }} onClick={quitterEnConservant}>
              Quitter et conserver ma progression
            </button>
            {totaux.nbValidees > 0 && (
              <button className="btn btn--ghost" style={{ marginBottom: 8 }} onClick={ouvrirFinDeSeance}>
                Terminer la séance maintenant
              </button>
            )}
            <button
              className="link-discreet"
              style={{ color: 'var(--danger)' }}
              onClick={() => {
                setQuitterOuvert(false);
                setConfirmationReset(true);
              }}
            >
              Remplacer par une nouvelle séance
            </button>
          </div>
        </div>
      )}

      {/* Adapter : le mécanisme universel de LEVEL. Options contextuelles et courtes, jamais une
          liste exhaustive — « Autre » ouvre la porte au langage naturel pour le reste. */}
      {adapterOuvert && (
        <div className="modal-overlay" onClick={fermerAdapter}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 12 }}>
              Adapter la séance
            </h2>

            {adapterEtape === 'menu' && (
              <>
                {adapterEnCours && (
                  <p className="subtle" style={{ margin: '0 0 12px' }}>
                    Adaptation en cours…
                  </p>
                )}
                <button
                  type="button"
                  className="btn btn--ghost adapter-option"
                  disabled={adapterEnCours}
                  onClick={() => void appliquerAdaptation({ motivation: 'Faible' })}
                >
                  Je suis fatigué
                </button>
                <button
                  type="button"
                  className="btn btn--ghost adapter-option"
                  disabled={adapterEnCours}
                  onClick={() => setAdapterEtape('temps')}
                >
                  Je manque de temps
                </button>
                <button
                  type="button"
                  className="btn btn--ghost adapter-option"
                  disabled={adapterEnCours}
                  onClick={() => void appliquerAdaptation({ forcer_seance_legere: true })}
                >
                  Je ne peux pas faire cette séance
                </button>
                <button
                  type="button"
                  className="btn btn--ghost adapter-option"
                  disabled={adapterEnCours}
                  onClick={() => setAdapterEtape('autre')}
                >
                  Autre
                </button>
              </>
            )}

            {adapterEtape === 'temps' && (
              <>
                <p className="subtle" style={{ margin: '0 0 12px' }}>
                  Combien de temps as-tu aujourd’hui ?
                </p>
                {['15 min', '30 min', '45 min'].map((t) => (
                  <button
                    key={t}
                    type="button"
                    className="btn btn--ghost adapter-option"
                    disabled={adapterEnCours}
                    onClick={() => void appliquerAdaptation({ temps_dispo: t })}
                  >
                    {t}
                  </button>
                ))}
              </>
            )}

            {adapterEtape === 'autre' && (
              <>
                <textarea
                  className="textarea"
                  placeholder="Ex : je pars en vacances vendredi, j’ai mal à l’épaule, je n’ai que des haltères…"
                  value={adapterTexte}
                  onChange={(e) => setAdapterTexte(e.target.value)}
                  autoFocus
                />
                <button
                  type="button"
                  className="btn btn--primary"
                  style={{ marginTop: 10 }}
                  disabled={adapterEnCours || !adapterTexte.trim()}
                  onClick={() => void appliquerAdaptation({ envie_texte: adapterTexte.trim() })}
                >
                  {adapterEnCours ? 'Adaptation…' : 'Envoyer'}
                </button>
              </>
            )}

            <LigneErreur message={adapterErreur} />

            {adapterEtape !== 'menu' ? (
              <button
                type="button"
                className="link-discreet"
                style={{ marginTop: 12 }}
                disabled={adapterEnCours}
                onClick={() => setAdapterEtape('menu')}
              >
                ← Retour
              </button>
            ) : (
              <button
                type="button"
                className="link-discreet"
                style={{ marginTop: 12 }}
                disabled={adapterEnCours}
                onClick={fermerAdapter}
              >
                Annuler
              </button>
            )}
          </div>
        </div>
      )}

      {/* Suppression de la séance du jour : conséquence annoncée avant, jamais après. */}
      {confirmationReset && (
        <div className="modal-overlay" onClick={() => setConfirmationReset(false)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Générer une nouvelle séance ?
            </h2>
            <p className="subtle" style={{ marginBottom: 16 }}>
              La séance du jour sera supprimée et remplacée par une nouvelle.
              {totaux.nbValidees > 0
                ? ` Les ${totaux.nbValidees} série${totaux.nbValidees > 1 ? 's' : ''} que tu as enregistrées aujourd’hui ne compteront plus dans cette séance.`
                : ''}
            </p>
            <LigneErreur message={actionErreur} />
            <button
              className="btn btn--ghost"
              style={{ marginBottom: 8 }}
              disabled={estEnCours('reset')}
              onClick={() => {
                setConfirmationReset(false);
                setActionErreur(null);
              }}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              style={{ background: 'var(--danger)' }}
              disabled={estEnCours('reset')}
              onClick={() => void handleReset()}
            >
              {estEnCours('reset') ? 'Suppression…' : 'Supprimer et régénérer'}
            </button>
          </div>
        </div>
      )}

      {serieASupprimer && (
        <div className="modal-overlay" onClick={() => setSerieASupprimer(null)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Supprimer cette série ?
            </h2>
            <p className="subtle" style={{ marginBottom: 16 }}>
              Série {serieASupprimer.serie.numero_serie} ·{' '}
              {serieASupprimer.serie.repetitions ?? '–'} reps · {serieASupprimer.serie.poids_kg ?? '–'} kg.
              Elle ne comptera plus dans ta séance ni dans ta progression.
            </p>
            <LigneErreur message={actionErreur} />
            <button
              className="btn btn--ghost"
              style={{ marginBottom: 8 }}
              disabled={estEnCours(`suppr-${serieASupprimer.serie.id}`)}
              onClick={() => {
                setSerieASupprimer(null);
                setActionErreur(null);
              }}
            >
              Garder cette série
            </button>
            <button
              className="btn btn--primary"
              style={{ background: 'var(--danger)' }}
              disabled={estEnCours(`suppr-${serieASupprimer.serie.id}`)}
              onClick={() => void confirmerSuppressionSerie()}
            >
              {estEnCours(`suppr-${serieASupprimer.serie.id}`) ? 'Suppression…' : 'Supprimer'}
            </button>
          </div>
        </div>
      )}

      {confirmationRemplacement && (
        <div className="modal-overlay" onClick={() => setConfirmationRemplacement(null)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Remplacer par {confirmationRemplacement.nomNouveau} ?
            </h2>
            <p className="subtle" style={{ marginBottom: 16 }}>
              Tes {confirmationRemplacement.nbValidees} série
              {confirmationRemplacement.nbValidees > 1 ? 's' : ''} déjà réalisée
              {confirmationRemplacement.nbValidees > 1 ? 's' : ''} sur{' '}
              {confirmationRemplacement.nomActuel} restent dans ton historique. Les suivantes se
              feront sur {confirmationRemplacement.nomNouveau}.
            </p>
            <LigneErreur message={replaceError} />
            <button
              className="btn btn--ghost"
              style={{ marginBottom: 8 }}
              disabled={replacing}
              onClick={() => setConfirmationRemplacement(null)}
            >
              Annuler
            </button>
            <button
              className="btn btn--primary"
              disabled={replacing}
              onClick={() => void choisirAlternative(confirmationRemplacement.nouvelExerciceId)}
            >
              {replacing ? 'Remplacement…' : 'Remplacer'}
            </button>
          </div>
        </div>
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

      {replaceTargetId !== null && (
        <div className="modal-overlay" onClick={fermerRemplacement}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <button className="modal-sheet__close" onClick={fermerRemplacement}>
              Fermer
            </button>
            <h2 className="card__title" style={{ clear: 'both', marginBottom: 8 }}>
              Je ne peux pas faire {bibliotheque[replaceTargetId]?.nom ?? `Exercice #${replaceTargetId}`}
            </h2>
            <p className="subtle" style={{ marginBottom: 12 }}>
              Douleur, matériel pris, mouvement impossible aujourd’hui : choisis un exercice
              équivalent. LEVEL ne propose que des alternatives compatibles avec ton matériel,
              ton niveau et le groupe musculaire prévu.
            </p>
            {loadingAlternatives && <p className="subtle">Recherche d’alternatives…</p>}
            {!loadingAlternatives && !replaceError && alternatives.length === 0 && (
              <p className="subtle">
                Aucune alternative compatible avec ton matériel actuel. Tu peux passer cet
                exercice et continuer la séance : il ne sera pas compté comme réalisé, et ta
                prochaine séance en tiendra compte.
              </p>
            )}
            <LigneErreur message={replaceError} />
            {!loadingAlternatives &&
              alternatives.map((alt) => (
                <button
                  key={alt.exercice.id}
                  type="button"
                  className="btn btn--ghost"
                  style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 8 }}
                  disabled={replacing}
                  onClick={() => demanderRemplacement(alt.exercice.id)}
                >
                  <strong>{alt.exercice.nom}</strong>
                  <div className="subtle">
                    {alt.exercice.groupe_musculaire} · {alt.exercice.type}
                    {alt.exercice.materiel_requis ? ` · ${alt.exercice.materiel_requis}` : ''}
                  </div>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
