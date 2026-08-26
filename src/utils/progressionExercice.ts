/**
 * Comparaison purement informative entre la dernière performance validée et la
 * performance en cours sur un même exercice. N'influence ni la charge prévue, ni
 * aucune recommandation : c'est un simple miroir du passé.
 *
 * Règles (voir audit Étape 7B) :
 * A. charge ↑ et reps non en baisse -> progression de charge
 * B. charge identique et reps ↑ -> progression de répétitions
 * C. charge ↑ mais reps ↓ -> ne jamais afficher "+X kg", se rabattre sur le volume
 * D/E. sinon, afficher l'évolution du volume total si elle est significative
 * F. sinon (données insuffisantes ou delta négligeable) -> aucun affichage
 */

export interface SerieProgression {
  poids_kg: number | null;
  repetitions: number | null;
}

export type ProgressionExercice =
  | { type: 'charge'; label: string }
  | { type: 'reps'; label: string }
  | { type: 'volume'; label: string }
  | null;

const SEUIL_VOLUME_PCT = 1;

function volumeTotal(series: SerieProgression[]): number {
  return series.reduce(
    (total, s) => (s.poids_kg != null && s.repetitions != null ? total + s.poids_kg * s.repetitions : total),
    0
  );
}

function moyenneReps(series: SerieProgression[]): number | null {
  const valides = series.filter((s): s is SerieProgression & { repetitions: number } => s.repetitions != null);
  if (!valides.length) return null;
  return valides.reduce((sum, s) => sum + s.repetitions, 0) / valides.length;
}

function formatNombre(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/**
 * Ne compare que des séries déjà validées (coche === true) des deux côtés ; c'est à
 * l'appelant de filtrer en amont, cohérent avec la définition backend de "validée".
 */
export function calculerProgressionExercice(
  precedentesValidees: SerieProgression[],
  actuellesValidees: SerieProgression[]
): ProgressionExercice {
  if (!precedentesValidees.length || !actuellesValidees.length) return null;

  const volumePrecedent = volumeTotal(precedentesValidees);
  const volumeActuel = volumeTotal(actuellesValidees);
  if (volumePrecedent <= 0 || volumeActuel <= 0) return null;

  const chargePrecedente = precedentesValidees[0].poids_kg;
  const chargeActuelle = actuellesValidees[0].poids_kg;
  const repsPrecedentes = moyenneReps(precedentesValidees);
  const repsActuelles = moyenneReps(actuellesValidees);

  if (chargePrecedente != null && chargeActuelle != null && repsPrecedentes != null && repsActuelles != null) {
    if (chargeActuelle > chargePrecedente && repsActuelles >= repsPrecedentes) {
      return { type: 'charge', label: `Charge : +${formatNombre(chargeActuelle - chargePrecedente)} kg` };
    }
    if (chargeActuelle === chargePrecedente && repsActuelles > repsPrecedentes) {
      return { type: 'reps', label: `Répétitions : +${formatNombre(repsActuelles - repsPrecedentes)}` };
    }
  }

  const deltaVolumePct = ((volumeActuel - volumePrecedent) / volumePrecedent) * 100;
  if (deltaVolumePct >= SEUIL_VOLUME_PCT) {
    return { type: 'volume', label: `Volume : +${Math.round(deltaVolumePct)} %` };
  }
  if (deltaVolumePct <= -SEUIL_VOLUME_PCT) {
    return { type: 'volume', label: `Volume : −${Math.round(Math.abs(deltaVolumePct))} %` };
  }

  return null;
}
