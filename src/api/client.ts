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

export interface ApiProfil {
  id: number;
  objectifs: string[];
  poste: string;
  age: number;
  taille_cm: number;
  poids_kg: number;
  niveau_physique: string;
  niveaux_qualites_physiques: ApiQualitesPhysiques;
  calendrier_matchs: ApiCalendrierMatchs;
  objectif_esthetique: ApiObjectifEsthetique | null;
  contraintes_temps: string;
  materiel: string;
  date_creation: string | null;
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
