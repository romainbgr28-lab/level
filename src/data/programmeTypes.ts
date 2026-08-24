// Métadonnées d'affichage partagées entre l'écran Progression (résumé) et l'écran
// dédié Programme (détail) pour représenter chaque type de séance du gabarit
// hebdomadaire de façon cohérente (icône + couleur) plutôt qu'en texte brut.

export interface TypeSeanceMeta {
  label: string;
  icon: string;
  color: string;
}

export const TYPE_SEANCE_META: Record<string, TypeSeanceMeta> = {
  force: { label: 'Force', icon: '🏋️', color: 'var(--danger)' },
  explosivité_vitesse: { label: 'Explosivité / vitesse', icon: '⚡', color: 'var(--warning)' },
  esthétique: { label: 'Esthétique', icon: '💪', color: 'var(--accent-2)' },
  endurance: { label: 'Endurance', icon: '🏃', color: 'var(--success)' },
  repos: { label: 'Repos', icon: '😴', color: 'var(--text-faint)' },
};

const FALLBACK_META: TypeSeanceMeta = { label: 'Séance', icon: '•', color: 'var(--text-dim)' };

function sansAccents(s: string): string {
  return s
    .replace(/é|è|ê/g, 'e')
    .replace(/à/g, 'a');
}

// Tolère une valeur légèrement différente de la casse/des accents canoniques (déjà observé
// dans des programmes générés avant la normalisation appliquée côté backend à la génération —
// voir backend/main.py::_normaliser_type_seance_programme) plutôt que de retomber sur le
// FALLBACK_META générique pour un type par ailleurs parfaitement valide.
export function typeSeanceMeta(type: string): TypeSeanceMeta {
  if (TYPE_SEANCE_META[type]) return TYPE_SEANCE_META[type];
  const cible = sansAccents(type.trim().toLowerCase());
  const cle = Object.keys(TYPE_SEANCE_META).find((k) => sansAccents(k.toLowerCase()) === cible);
  return cle ? TYPE_SEANCE_META[cle] : FALLBACK_META;
}
