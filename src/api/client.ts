const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
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

export interface ApiSeance {
  id: number;
  date: string;
  nom: string;
  exercices: ApiExercise[];
  statut: 'planifiee' | 'terminee';
  rpe: number | null;
  duree_reelle: number | null;
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
export const updateSeance = (
  id: number,
  payload: Partial<Pick<ApiSeance, 'statut' | 'rpe' | 'duree_reelle' | 'exercices'>>
) => request<ApiSeance>(`/api/seances/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });

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

export interface ApiHistoriqueSeance {
  id: number;
  date: string;
  phase_calendaire: string;
  type_seance: string;
  exercices_prevus: unknown[];
  exercices_realises: unknown[];
  rpe: number | null;
  pourcentage_complete?: number | null;
  zone_sensible_signalee?: string | null;
  xp_gagne?: number | null;
  notes: string | null;
  etat_declare_avant: ApiEtatDeclareAvant;
}

export const getHistoriqueSeances = () => request<ApiHistoriqueSeance[]>('/api/historique_seances');
export const addHistoriqueSeance = (
  payload: Omit<ApiHistoriqueSeance, 'id' | 'phase_calendaire' | 'xp_gagne'>
) => request<ApiHistoriqueSeance>('/api/historique_seances', { method: 'POST', body: JSON.stringify(payload) });

// ---------- Génération de séance assistée (moteur de règles + Mistral) ----------

export interface ApiEtatDuJour {
  sommeil?: string | null;
  motivation?: string | null;
  temps_dispo?: string | null;
  envie_texte?: string | null;
  entrainement_club_semaine?: string | null;
}

export interface ApiSeanceGeneree {
  id: number;
  nom_seance: string;
  duree_min: number;
  exercices: unknown[];
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

export const terminerSeanceIA = (payload: { seance_id: number; compte_rendu: string }) =>
  request<ApiTerminerSeanceResult>('/api/seance/terminer', { method: 'POST', body: JSON.stringify(payload) });

// ---------- Stats & progression ----------

export const getStats = () => request<ApiStats>('/api/stats');
export const getChargeProgress = (nomExercice = 'Développé couché') =>
  request<ApiChargePoint[]>(`/api/progress/charge?nom_exercice=${encodeURIComponent(nomExercice)}`);
export const getThemeScores = () => request<ApiThemeScore[]>('/api/progress/themes');
