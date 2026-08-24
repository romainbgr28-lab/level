import type { ApiProgramme, ApiProgrammePhase } from '../api/client';

// Doit rester synchronisé avec regles_seance.JOURS_SEMAINE côté backend.
export const JOURS_SEMAINE = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

/** Semaine en cours du programme (1-indexée, plafonnée à duree_semaines) — même formule
 * que _semaine_courante_programme() côté backend (backend/main.py), à garder synchronisée. */
export function semaineActuelle(programme: ApiProgramme): number {
  const debut = new Date(programme.date_debut);
  const jours = Math.floor((Date.now() - debut.getTime()) / (1000 * 60 * 60 * 24));
  const semaine = Math.floor(jours / 7) + 1;
  return Math.min(Math.max(semaine, 1), programme.duree_semaines);
}

export function phaseCourante(programme: ApiProgramme, semaine: number): ApiProgrammePhase | undefined {
  return programme.phases.find((p) => semaine >= p.semaine_debut && semaine <= p.semaine_fin);
}

export function jourFrancaisAujourdhui(): string {
  // getDay() : 0 = dimanche ... 6 = samedi -> décalage vers JOURS_SEMAINE (0 = lundi).
  const index = (new Date().getDay() + 6) % 7;
  return JOURS_SEMAINE[index];
}

/** Type de séance prévu par le gabarit hebdomadaire pour aujourd'hui, ou undefined si le
 * jour courant n'est pas couvert par le gabarit (jour non disponible déclaré à l'onboarding). */
export function typeSeanceGabaritAujourdhui(programme: ApiProgramme): string | undefined {
  return programme.gabarit_hebdomadaire[jourFrancaisAujourdhui()];
}
