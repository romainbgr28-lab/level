import { getDevSimulatedDate } from '../utils/devDate';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const devDate = getDevSimulatedDate();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(devDate ? { 'X-Dev-Date': devDate } : {}),
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${path} → ${res.status}${body ? ` : ${body}` : ''}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
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

export interface ApiStreakDay {
  date: string;
  sport_fait: boolean;
  apprentissage_fait: boolean;
}

// ---------- Profil ----------

export const getProfil = () => request<ApiProfil | null>('/api/profil');
export const saveProfil = (payload: Omit<ApiProfil, 'id' | 'date_creation'>) =>
  request<ApiProfil>('/api/profil', { method: 'POST', body: JSON.stringify(payload) });
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

export const genererProgramme = () =>
  request<ApiProgramme>('/api/programme/generer', { method: 'POST', body: JSON.stringify({}) });

export const getProgrammeActif = () => request<ApiProgramme | null>('/api/programme/actif');

// ---------- Stats & progression ----------

export const getStats = () => request<ApiStats>('/api/stats');
export const getChargeProgress = (nomExercice = 'Développé couché') =>
  request<ApiChargePoint[]>(`/api/progress/charge?nom_exercice=${encodeURIComponent(nomExercice)}`);
export const getThemeScores = () => request<ApiThemeScore[]>('/api/progress/themes');
