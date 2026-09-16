import { getDevSimulatedDate } from '../utils/devDate';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

/**
 * Erreur d'API exploitable par l'interface.
 *
 * `message` est toujours une phrase lisible par l'utilisateur (jamais « API /path → 500 » ni
 * « failed to fetch ») : le backend renvoie déjà ses refus métier en français dans `detail`
 * (jour de match, jour de repos, profil manquant...), on les reprend tels quels ; tout le
 * reste est traduit ici en une phrase qui dit ce qui s'est passé. `technique` garde le
 * détail brut pour les logs, jamais affiché.
 */
export class ApiError extends Error {
  readonly status: number;
  /** true : la requête n'a jamais atteint le serveur (hors ligne, serveur éteint). */
  readonly reseau: boolean;
  readonly technique: string;

  constructor(params: { message: string; status: number; reseau: boolean; technique: string }) {
    super(params.message);
    this.name = 'ApiError';
    this.status = params.status;
    this.reseau = params.reseau;
    this.technique = params.technique;
  }

  /** Le serveur a refusé l'action pour une raison métier explicable (409) : ce n'est pas une
   * panne, l'écran doit afficher l'explication et proposer une alternative, pas un « réessayer ». */
  get estRefusMetier(): boolean {
    return this.status === 409 || this.status === 400;
  }
}

/** Phrase par défaut selon le code HTTP, quand le backend n'a pas fourni de `detail` lisible. */
function messageParDefaut(status: number, reseau: boolean): string {
  if (reseau) return "Connexion impossible. Vérifie ta connexion et réessaie.";
  if (status === 404) return "Cette donnée n'existe plus.";
  if (status === 422) return "Certaines informations envoyées n'ont pas été acceptées.";
  if (status === 502 || status === 503 || status === 504)
    return "Le service est momentanément indisponible. Réessaie dans un instant.";
  if (status >= 500) return "Une erreur est survenue de notre côté. Réessaie dans un instant.";
  return "L'action n'a pas pu aboutir.";
}

/** Extrait le `detail` FastAPI d'un corps d'erreur, s'il est lisible par un humain. */
function detailLisible(corps: string): string | null {
  if (!corps) return null;
  try {
    const parsed = JSON.parse(corps) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    // 422 Pydantic : liste d'erreurs de validation, illisible telle quelle pour l'utilisateur.
    return null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const devDate = getDevSimulatedDate();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(devDate ? { 'X-Dev-Date': devDate } : {}),
      },
      ...options,
    });
  } catch (e) {
    throw new ApiError({
      message: messageParDefaut(0, true),
      status: 0,
      reseau: true,
      technique: `${path} : ${e instanceof Error ? e.message : String(e)}`,
    });
  }

  if (!res.ok) {
    const corps = await res.text().catch(() => '');
    throw new ApiError({
      message: detailLisible(corps) ?? messageParDefaut(res.status, false),
      status: res.status,
      reseau: false,
      technique: `API ${path} → ${res.status}${corps ? ` : ${corps}` : ''}`,
    });
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

/** Message affichable pour n'importe quelle exception remontée d'un appel API. */
export function messageErreur(e: unknown, secours = "L'action n'a pas pu aboutir."): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error && e.message) return e.message;
  return secours;
}

// ---------- Types miroir du backend ----------

export interface ApiExerciseSet {
  reps: number;
  loadKg: number;
}

export interface ApiExercise {
  id: string;
  name: string;
  sets: ApiExerciseSet[];
}

export interface ApiSeanceExercice {
  exercice_id: number;
  series: number;
  repetitions: string;
  charge_indicative?: string;
  notes?: string;
  rpe_cible?: number | null;
  temps_repos_recommande_s?: number | null;
  // Anciens exercice_id de ce slot (Étape 7C, remplacement) : présent uniquement si l'exercice
  // de ce slot a déjà été remplacé au moins une fois.
  historique_exercice_ids?: number[];
}

export interface ApiSeance {
  id: number;
  date: string;
  nom: string;
  exercices: ApiSeanceExercice[];
  statut: 'planifiee' | 'prévue' | 'terminee';
  explication: string | null;
  rpe: number | null;
  duree_prevue: number | null;
  duree_reelle: number | null;
  note?: string | null;
}

// ---------- Bibliothèque d'exercices ----------

export interface ApiExerciceBibliotheque {
  id: number;
  nom: string;
  groupe_musculaire: string;
  instructions: string[];
  image_url: string | null;
  type: string;
  materiel_requis: string | null;
  sport_specifique: string | null;
  points_securite: string | null;
  charge_recommandee: 'poids_du_corps' | 'charge_legere' | 'charge_moderee' | 'charge_lourde_progressive';
  pattern_mouvement?: string | null;
  groupe_musculaire_principal?: string | null;
  materiel_requis_liste?: string[] | null;
}

// ---------- Remplacement d'exercice (Étape 7C) ----------

export interface ApiAlternativeExercice {
  exercice: ApiExerciceBibliotheque;
  score: number;
  memes_criteres: string[];
}

export interface ApiAlternativesExercice {
  exercice_actuel_id: number;
  alternatives: ApiAlternativeExercice[];
}

export interface ApiRemplacerExerciceResult {
  seance: ApiSeance;
  series_deja_realisees: number;
  message_confirmation: string | null;
}

// ---------- Séries loguées (logging temps réel façon Hevy) ----------

export type ApiDifficulte = 'facile' | 'comme_prevu' | 'dur';

export interface ApiSerieLoggee {
  id: number;
  seance_id: number;
  exercice_id: number;
  numero_serie: number;
  poids_kg: number | null;
  repetitions: number | null;
  coche: boolean;
  difficulte?: ApiDifficulte | null;
  rpe_approx?: number | null;
  // Prévu, calculé côté serveur à la création (null sur les séries loguées avant
  // l'introduction de ces champs). Jamais à envoyer depuis le client.
  reps_prevues?: number | null;
  charge_prevue_kg?: number | null;
  horodatage: string | null;
}

export interface ApiDernierePerformance {
  date: string | null;
  series: ApiSerieLoggee[];
}

export interface ApiModuleQuestion {
  type: 'qcm' | 'open';
  id: string;
  prompt: string;
  options?: string[];
  correctIndex?: number;
  explanation?: string;
}

export interface ApiModule {
  id: number;
  categorie: string;
  niveau: string;
  titre: string;
  contenu: string;
  questions: ApiModuleQuestion[];
}

export interface ApiQualitesPhysiques {
  force: number;
  explosivite: number;
  vitesse: number;
  endurance: number;
}

export interface ApiCalendrierException {
  date: string;
  label?: string | null;
}

export interface ApiEntrainementsClub {
  actif: boolean;
  seances_par_semaine?: number | null;
}

export interface ApiCalendrierMatchs {
  jour_habituel: string | null;
  exceptions: ApiCalendrierException[];
  entrainements_club?: ApiEntrainementsClub | null;
}

export interface ApiObjectifEsthetique {
  tags: string[];
  texte_libre?: string | null;
}

// ---------- User Model V2 ----------

// Thèmes valides (voir backend/user_model_v2.py::THEMES_OBJECTIFS_V2). Le frontend affiche des
// libellés lisibles pour chacun (voir LABELS_THEMES_OBJECTIFS dans Onboarding.tsx) mais envoie
// toujours ces identifiants techniques au backend.
export type ThemeObjectifV2 =
  | 'esthetique_hypertrophie'
  | 'force'
  | 'perte_de_gras'
  | 'performance_sport_pratique'
  | 'endurance'
  | 'discipline_mentale';

export interface ApiObjectifV2 {
  theme: ThemeObjectifV2;
  rang: number;
  // Calculé côté backend à partir du rang — jamais choisi par l'utilisateur, jamais envoyé
  // avec une valeur signifiante depuis le frontend (voir Onboarding : toujours 0, ignoré/
  // recalculé par le backend à l'enregistrement).
  poids: number;
}

export interface ApiContexteSportif {
  sport: string | null; // null | "football" | libellé libre d'un autre sport pratiqué
  frequence_hebdo: number | null;
  poste: string | null; // pertinent seulement si sport === "football"
}

// {lundi: minutes|null, ..., dimanche: minutes|null} — 7 clés toujours présentes.
export type ApiDisponibilites = Record<string, number | null>;

export interface ApiProfil {
  id: number;
  // --- Champs legacy (voir backend/schemas.py::ProfilBase) : conservés en lecture pour la
  // compatibilité descendante (toujours renvoyés par le backend), mais optionnels à l'écriture
  // — l'onboarding V2 ci-dessous ne les envoie plus, ils sont dérivés côté backend depuis les
  // champs V2. ---
  objectifs?: string[];
  poste?: string;
  contraintes_temps?: string;
  // --- Champs V2 ---
  objectifs_v2: ApiObjectifV2[];
  contexte_sportif: ApiContexteSportif;
  disponibilites: ApiDisponibilites;
  age: number;
  taille_cm: number;
  poids_kg: number;
  niveau_physique: string;
  niveaux_qualites_physiques: ApiQualitesPhysiques;
  calendrier_matchs: ApiCalendrierMatchs;
  objectif_esthetique: ApiObjectifEsthetique | null;
  materiel: string;
  date_creation: string | null;
  niveau_observe?: Record<string, { valeur: number | null; confiance: number; n_seances: number }> | null;
}

export interface ApiStats {
  streak: number;
  record_streak: number;
  xp_total: number;
  total_seances: number;
  total_modules: number;
  rpe_average: number;
}

export interface ApiChargePoint {
  date: string;
  loadKg: number;
}

export interface ApiThemeScore {
  theme: string;
  percent: number;
}

/** Exercice ayant assez de séries loguées pour tracer une courbe (voir backend
 * /api/progress/exercices) — la liste suit ce que le joueur entraîne vraiment. */
export interface ApiExerciceSuivi {
  exercice_id: number;
  nom: string;
  seances: number;
}

/** Volume soulevé sur une semaine glissante ; `date` est le premier jour de la fenêtre. */
export interface ApiVolumeSemaine {
  date: string;
  volume_kg: number;
}

export interface ApiBilanProgression {
  exercice: string;
  charge_precedente_kg: number;
  charge_kg: number;
  variation_pct: number;
}

export interface ApiBilanStagnation {
  exercice: string;
  charge_kg: number;
}

/** Miroir de backend/schemas.py::BilanOut — chaque champ provient de séances réellement
 * terminées et de séries réellement loguées (null/[] quand la donnée n'existe pas). */
export interface ApiBilan {
  periode_debut: string;
  periode_fin: string;
  seances_realisees: number;
  seances_realisees_precedent: number;
  jours_actifs: number;
  jours_fenetre: number;
  volume_kg: number;
  volume_kg_precedent: number;
  volume_variation_pct: number | null;
  rpe_moyen: number | null;
  completion_moyenne: number | null;
  progressions: ApiBilanProgression[];
  stagnations: ApiBilanStagnation[];
  points: string[];
  prochaine_adaptation: string | null;
}

export interface ApiStreakDay {
  date: string;
  sport_fait: boolean;
  apprentissage_fait: boolean;
}

// ---------- Profil ----------

export const getProfil = () => request<ApiProfil | null>('/api/profil');
export const saveProfil = (payload: Omit<ApiProfil, 'id' | 'date_creation'>) =>
  request<ApiProfil>('/api/profil', { method: 'POST', body: JSON.stringify(payload) });
// Mise à jour partielle (backend/main.py::patch_profil) : seuls les champs envoyés sont
// modifiés, et le backend régénère le programme actif dans la foulée — les disponibilités et le
// calendrier de matchs sont les entrées directes de la structure hebdomadaire.
/** Miroir de backend/schemas.py::ProfilPatchOut : dit ce que la modification a réellement
 * entraîné, pour que l'écran annonce un recalcul de programme seulement s'il a eu lieu. */
export interface ApiProfilPatchResult {
  profil: ApiProfil;
  programme_recalcule: boolean;
  programme_erreur: string | null;
  seance_du_jour_supprimee: boolean;
}

export const patchProfil = (payload: {
  disponibilites?: ApiDisponibilites;
  calendrier_matchs?: ApiCalendrierMatchs;
  objectifs_v2?: ApiObjectifV2[];
  materiel?: string;
}) => request<ApiProfilPatchResult>('/api/profil', { method: 'PATCH', body: JSON.stringify(payload) });

export const deleteProfil = () => request<void>('/api/profil', { method: 'DELETE' });

// ---------- Séances ----------

export const getTodaySeance = () => request<ApiSeance | null>('/api/seances/today');
export const deleteTodaySeance = () => request<void>('/api/seances/today', { method: 'DELETE' });
export const updateSeance = (
  id: number,
  payload: Partial<Pick<ApiSeance, 'statut' | 'rpe' | 'duree_reelle' | 'exercices' | 'note'>>
) => request<ApiSeance>(`/api/seances/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });

// ---------- Bibliothèque d'exercices ----------

export const getExercicesBibliotheque = () => request<ApiExerciceBibliotheque[]>('/api/exercices_bibliotheque');
export const getExerciceBibliotheque = (id: number) =>
  request<ApiExerciceBibliotheque>(`/api/exercices_bibliotheque/${id}`);
export const getDernierePerformance = (exerciceId: number, seanceId?: number) =>
  request<ApiDernierePerformance>(
    `/api/exercices_bibliotheque/${exerciceId}/derniere_performance${seanceId ? `?seance_id=${seanceId}` : ''}`
  );

// ---------- Remplacement d'exercice (Étape 7C) ----------

export const getAlternativesExercice = (seanceId: number, exerciceId: number) =>
  request<ApiAlternativesExercice>(`/api/seance/${seanceId}/exercices/${exerciceId}/alternatives`);

export const remplacerExercice = (
  seanceId: number,
  payload: { exercice_id_actuel: number; exercice_id_nouveau: number }
) =>
  request<ApiRemplacerExerciceResult>(`/api/seance/${seanceId}/remplacer_exercice`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

// ---------- Séries loguées ----------

export const getSeriesLoggees = (seanceId: number) =>
  request<ApiSerieLoggee[]>(`/api/series_loggees?seance_id=${seanceId}`);
export const createSerieLoggee = (payload: {
  seance_id: number;
  exercice_id: number;
  numero_serie: number;
  poids_kg: number | null;
  repetitions: number | null;
  coche: boolean;
  difficulte?: ApiDifficulte | null;
}) => request<ApiSerieLoggee>('/api/series_loggees', { method: 'POST', body: JSON.stringify(payload) });
export const updateSerieLoggee = (
  id: number,
  payload: Partial<Pick<ApiSerieLoggee, 'poids_kg' | 'repetitions' | 'coche' | 'difficulte'>>
) => request<ApiSerieLoggee>(`/api/series_loggees/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
export const deleteSerieLoggee = (id: number) =>
  request<void>(`/api/series_loggees/${id}`, { method: 'DELETE' });

// ---------- Historique d'exercices ----------

export const addExerciceHistorique = (payload: {
  seance_id: number;
  nom_exercice: string;
  series: number;
  repetitions: number;
  charge_kg: number;
  date: string;
}) => request('/api/exercices_historique', { method: 'POST', body: JSON.stringify(payload) });

// ---------- Modules ----------

export const getTodayModule = () => request<ApiModule | null>('/api/modules/today');

// ---------- Sessions d'apprentissage ----------

export const addSessionApprentissage = (payload: {
  module_id: number;
  date: string;
  reponses: Record<string, unknown>;
  score: number | null;
}) => request('/api/sessions_apprentissage', { method: 'POST', body: JSON.stringify(payload) });

// ---------- Streaks ----------

export const getStreaks = (days = 35) => request<ApiStreakDay[]>(`/api/streaks?days=${days}`);

// ---------- Historique de séances (prévu vs réalisé, contexte, phase calendaire) ----------

export interface ApiEtatDeclareAvant {
  sommeil?: string | null;
  motivation?: string | null;
  temps_dispo?: string | null;
  envie_texte?: string | null;
  entrainement_club_semaine?: string | null;
}

export interface ApiExercicePrevu {
  exercice_id: number;
  nom?: string | null;
  series?: number;
  repetitions?: string;
  charge_indicative?: string | null;
}

export interface ApiSerieRealisee {
  numero_serie: number;
  poids_kg: number | null;
  repetitions: number | null;
}

export interface ApiExerciceRealise {
  exercice_id: number;
  nom: string | null;
  series: ApiSerieRealisee[];
}

export interface ApiHistoriqueSeance {
  id: number;
  date: string;
  phase_calendaire: string;
  type_seance: string;
  exercices_prevus: ApiExercicePrevu[];
  exercices_realises: ApiExerciceRealise[];
  rpe: number | null;
  pourcentage_complete?: number | null;
  zone_sensible_signalee?: string | null;
  xp_gagne?: number | null;
  notes: string | null;
  etat_declare_avant: ApiEtatDeclareAvant;
  decision_adaptation?: Record<string, unknown> | null;
}

export const getHistoriqueSeances = () => request<ApiHistoriqueSeance[]>('/api/historique_seances');

// ---------- Génération de séance assistée (moteur de règles + Mistral) ----------

export interface ApiEtatDuJour {
  sommeil?: string | null;
  motivation?: string | null;
  temps_dispo?: string | null;
  envie_texte?: string | null;
  entrainement_club_semaine?: string | null;
  type_seance_force?: string | null;
  forcer_seance_legere?: boolean;
}

export interface ApiSeanceGeneree {
  id: number;
  nom_seance: string;
  duree_min: number;
  exercices: ApiSeanceExercice[];
  explication: string;
  recommandation: Record<string, unknown>;
}

export interface ApiTerminerSeanceResult {
  resume: Record<string, unknown>;
  xp_gagne: number;
  historique_id: number;
}

export const genererSeance = (payload: ApiEtatDuJour) =>
  request<ApiSeanceGeneree>('/api/seance/generer', { method: 'POST', body: JSON.stringify(payload) });

export const terminerSeanceIA = (payload: {
  seance_id: number;
  rpe: number | null;
  note: string | null;
  duree_reelle_min?: number | null;
  zone_sensible?: string | null;
}) => request<ApiTerminerSeanceResult>('/api/seance/terminer', { method: 'POST', body: JSON.stringify(payload) });

// ---------- Programme structuré (8 semaines) ----------

export interface ApiProgrammePhase {
  nom: string;
  semaine_debut: number;
  semaine_fin: number;
  description: string;
}

export interface ApiProgramme {
  id: number;
  utilisateur_id: number;
  date_debut: string;
  duree_semaines: number;
  phases: ApiProgrammePhase[];
  gabarit_hebdomadaire: Record<string, string>;
  trajectoire_progression: Record<string, number[]>;
  statut: 'actif' | 'terminé';
  date_creation: string | null;
}

/**
 * Construit le programme. Sans `regenerer`, l'appel est idempotent : si un programme actif
 * existe déjà, le backend le renvoie tel quel (double clic, double montage d'écran, retry
 * réseau ne repartent jamais de zéro). `regenerer: true` est réservé à une régénération
 * explicitement demandée par l'utilisateur.
 */
export const genererProgramme = (regenerer = false) =>
  request<ApiProgramme>('/api/programme/generer', {
    method: 'POST',
    body: JSON.stringify({ regenerer }),
  });

export const getProgrammeActif = () => request<ApiProgramme | null>('/api/programme/actif');

// ---------- Contexte du jour (décision déterministe : backend/contexte_jour.py) ----------

// Miroir de contexte_jour.STATUTS_JOUR : chaque valeur est traitée explicitement par
// src/screens/Today.tsx, ne jamais en ajouter ici sans y ajouter la branche correspondante.
export type ApiStatutJour =
  | 'aucun_profil'
  | 'aucun_programme'
  | 'match'
  | 'repos'
  | 'indisponible'
  | 'seance';

export interface ApiJourSemaine {
  date: string;
  jour_abbrev: string;
  jour_label: string;
  statut: ApiStatutJour;
  type_seance_prevu: string | null;
  est_aujourdhui: boolean;
  est_passe: boolean;
}

export interface ApiProchaineSeance {
  date: string;
  jour_abbrev: string;
  jour_label: string;
  type_seance_prevu: string;
}

export interface ApiContexteJour {
  date: string;
  jour_abbrev: string;
  jour_label: string;
  statut: ApiStatutJour;
  type_seance_prevu: string | null;
  phase_calendaire: string;
  semaine_programme: number | null;
  duree_semaines: number | null;
  phase_nom: string | null;
  phase_description: string | null;
  seance_id: number | null;
  seance_statut: string | null;
  seance_nom: string | null;
  prochaine_seance: ApiProchaineSeance | null;
  semaine: ApiJourSemaine[];
}

export const getContexteJour = () => request<ApiContexteJour>('/api/jour/contexte');

// ---------- Stats & progression ----------

export const getStats = () => request<ApiStats>('/api/stats');
export const getChargeProgress = (nomExercice = 'Développé couché') =>
  request<ApiChargePoint[]>(`/api/progress/charge?nom_exercice=${encodeURIComponent(nomExercice)}`);
export const getThemeScores = () => request<ApiThemeScore[]>('/api/progress/themes');
export const getExercicesSuivis = () => request<ApiExerciceSuivi[]>('/api/progress/exercices');
export const getVolumeProgress = () => request<ApiVolumeSemaine[]>('/api/progress/volume');
export const getBilanHebdomadaire = () => request<ApiBilan>('/api/bilan/hebdomadaire');

// ---------- Coach conversationnel (V0) ----------
//
// Le chat est l'interface de la V0 ; le moteur reste le cerveau. `actions` expose les actions
// métier réellement exécutées côté backend pour produire la réponse : l'écran peut donc
// distinguer « LEVEL a fait quelque chose » de « LEVEL a seulement parlé », et rafraîchir
// ce qu'il faut (voir Coach.tsx).

export interface ApiCoachAction {
  nom: string;
  arguments: Record<string, unknown>;
  resultat: Record<string, unknown>;
}

export interface ApiCoachMessage {
  reponse: string;
  actions: ApiCoachAction[];
  contexte: ApiCoachContexte;
}

export interface ApiCoachMessageHistorique {
  id: number;
  role: 'utilisateur' | 'coach';
  contenu: string;
  actions: { nom: string }[] | null;
  date: string;
  horodatage: string | null;
}

/** Miroir souple de backend/coach_contexte.construire_contexte : seuls les champs réellement
 *  affichés sont typés ici, le reste est ignoré (le backend peut en ajouter sans casser l'app). */
export interface ApiCoachContexte {
  date: string;
  jour_label: string | null;
  profil: Record<string, unknown> | null;
  jour: {
    statut: ApiStatutJour;
    statut_label: string;
    type_seance_prevu: string | null;
  };
  seance_du_jour: {
    id: number;
    nom: string;
    statut: string;
    duree_prevue_min: number | null;
    exercices: string[];
  } | null;
}

export const envoyerMessageCoach = (message: string) =>
  request<ApiCoachMessage>('/api/coach/message', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });

export const getConversationCoach = () =>
  request<ApiCoachMessageHistorique[]>('/api/coach/conversation');

export const getCoachContexte = () => request<ApiCoachContexte>('/api/coach/contexte');

/** Invoque directement une action métier, sans passer par le LLM (raccourcis de l'interface).
 *  Même registre et mêmes garde-fous que ceux exposés au modèle : un raccourci ne peut pas
 *  contourner une règle que le chat respecte. */
export const executerActionCoach = (nom: string, args: Record<string, unknown> = {}) =>
  request<{ nom: string; resultat: Record<string, unknown> }>('/api/coach/action', {
    method: 'POST',
    body: JSON.stringify({ nom, arguments: args }),
  });
