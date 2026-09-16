/**
 * Petit bus de fraîcheur des données.
 *
 * Problème qu'il résout : l'utilisateur modifie son profil, termine une séance ou régénère son
 * programme depuis un écran, puis en consulte un autre qui affichait encore l'état d'avant
 * (streak et XP de l'en-tête, résumé de programme, stats). Les écrans rechargent bien à leur
 * montage, mais les composants toujours montés (l'en-tête, la barre de navigation) non.
 *
 * Après une mutation importante, l'appelant publie le sujet touché ; les composants concernés
 * se rechargent. Aucune donnée n'est stockée ici : c'est une invalidation, pas un cache — il
 * n'y a jamais deux sources de vérité, le backend reste la seule.
 */

export type SujetDonnees = 'profil' | 'programme' | 'seance' | 'stats';

type Abonne = (sujet: SujetDonnees) => void;

const abonnes = new Set<Abonne>();

/** Signale qu'un ou plusieurs sujets viennent de changer côté serveur. */
export function donneesModifiees(...sujets: SujetDonnees[]): void {
  for (const sujet of sujets) {
    for (const abonne of Array.from(abonnes)) abonne(sujet);
  }
}

/** S'abonne aux changements ; renvoie la fonction de désabonnement (à rendre depuis un effet). */
export function surDonneesModifiees(abonne: Abonne): () => void {
  abonnes.add(abonne);
  return () => {
    abonnes.delete(abonne);
  };
}
