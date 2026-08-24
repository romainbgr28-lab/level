import type { ApiProgramme, ApiProgrammePhase } from '../api/client';

// gabarit_hebdomadaire est keyé par jour ABRÉGÉ ("Lun", "Mer", ...), pas le nom complet —
// mêmes abréviations que src/screens/Onboarding.tsx (JOURS) et backend/regles_seance.py
// (JOURS_SEMAINE_ABBREV). Ne pas confondre avec le nom complet utilisé pour
// calendrier_matchs.jour_habituel (JOURS_SEMAINE dans Onboarding.tsx).
export const JOURS_SEMAINE_ABBREV = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

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

export function jourAbbrevAujourdhui(): string {
  // getDay() : 0 = dimanche ... 6 = samedi -> décalage vers JOURS_SEMAINE_ABBREV (0 = lundi).
  const index = (new Date().getDay() + 6) % 7;
  return JOURS_SEMAINE_ABBREV[index];
}

/** Type de séance prévu par le gabarit hebdomadaire pour aujourd'hui, ou undefined si le
 * jour courant n'est pas couvert par le gabarit (jour non disponible déclaré à l'onboarding). */
export function typeSeanceGabaritAujourdhui(programme: ApiProgramme): string | undefined {
  return programme.gabarit_hebdomadaire[jourAbbrevAujourdhui()];
}
