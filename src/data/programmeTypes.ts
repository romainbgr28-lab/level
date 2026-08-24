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

export function typeSeanceMeta(type: string): TypeSeanceMeta {
  return TYPE_SEANCE_META[type] ?? FALLBACK_META;
}
