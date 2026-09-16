import type { ApiProgramme, ApiProgrammePhase } from '../api/client';
import { getNow } from './devDate';

// Ce module ne contient plus que la position dans le programme (semaine/phase), utilisée par
// les écrans Programme et Progression.
//
// Le choix du jour — type de séance prévu aujourd'hui, jour de repos, jour de match, jour
// indisponible, prochaine séance — appartient désormais au moteur déterministe côté backend
// (backend/contexte_jour.py, exposé par GET /api/jour/contexte). Les helpers qui le
// redérivaient ici à partir du seul gabarit hebdomadaire ont été retirés : ils ignoraient le
// calendrier de matchs et les disponibilités, et faisaient exister deux vérités concurrentes
// sur « qu'est-ce que je fais aujourd'hui ».

/** Semaine en cours du programme (1-indexée, plafonnée à duree_semaines) — même formule
 * que _semaine_courante_programme() côté backend (backend/main.py), à garder synchronisée. */
export function semaineActuelle(programme: ApiProgramme): number {
  const debut = new Date(programme.date_debut);
  const jours = Math.floor((getNow().getTime() - debut.getTime()) / (1000 * 60 * 60 * 24));
  const semaine = Math.floor(jours / 7) + 1;
  return Math.min(Math.max(semaine, 1), programme.duree_semaines);
}

export function phaseCourante(programme: ApiProgramme, semaine: number): ApiProgrammePhase | undefined {
  return programme.phases.find((p) => semaine >= p.semaine_debut && semaine <= p.semaine_fin);
}
